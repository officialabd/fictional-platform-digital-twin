"""Store and forward: how readings get to shore across an unreliable link.

Readings are stored in the historian first, and only then sent. The forwarded marker moves when
the broker acknowledges a message, not when it is sent. After a link loss everything past the
marker is sent again with its original timestamp, so the twin can backfill the gap. A resend can
duplicate a reading, and the twin has to ignore duplicates.

Known limit: MQTT message ids wrap at 65,535, so more unacknowledged readings than that would
confuse the marker. The rates used here do not get close.
"""

import time
from typing import Protocol

from shared.messages import Reading
from simulator.storage import Historian

BATCH_SIZE = 2000  # rows sent per tick, so a long backlog cannot stall the simulation
FLUSH_POLL_S = 0.05


class Link(Protocol):
    """The way out of the platform. The forwarder does not care what is behind it."""

    connected: bool

    def publish(self, reading: Reading) -> int | None:
        """Send a reading. Returns its message id, or None if it could not be sent."""

    def take_acks(self) -> list[int]:
        """Return the message ids acknowledged since the last call."""


class Forwarder:
    def __init__(self, historian: Historian, link: Link) -> None:
        self.historian = historian
        self.link = link
        self.marker = 0  # every row up to here is acknowledged
        self.last_sent = 0  # every row up to here is sent
        self.in_flight: dict[int, int] = {}  # message id -> row id
        self.acked_ahead: set[int] = set()  # rows acknowledged before an earlier row was
        self.was_up = False

    def tick(self, link_down: bool) -> None:
        """Process acknowledgements, then send what is waiting if the link is up."""
        for message_id in self.link.take_acks():
            self._on_ack(message_id)

        up = self.link.connected and not link_down
        if up and not self.was_up:
            self._rewind()
        if up:
            self._send_batch()
        self.was_up = up

    def flush(self, timeout_s: float) -> None:
        """Wait for the backlog to be acknowledged, so a finished run does not lose its tail."""
        deadline = time.monotonic() + timeout_s
        while (
            self.link.connected
            and self.marker < self.historian.last_row_id()
            and time.monotonic() < deadline
        ):
            self.tick(link_down=False)
            time.sleep(FLUSH_POLL_S)

    def _send_batch(self) -> None:
        for row_id, reading in self.historian.rows_after(self.last_sent, BATCH_SIZE):
            message_id = self.link.publish(reading)
            if message_id is None:
                return
            self.in_flight[message_id] = row_id
            self.last_sent = row_id

    def _on_ack(self, message_id: int) -> None:
        row_id = self.in_flight.pop(message_id, None)
        if row_id is None:
            return  # sent before the last rewind, and it will be sent again anyway
        self.acked_ahead.add(row_id)
        while self.marker + 1 in self.acked_ahead:
            self.marker += 1
            self.acked_ahead.remove(self.marker)

    def _rewind(self) -> None:
        self.last_sent = self.marker
        self.in_flight.clear()
        self.acked_ahead.clear()
