"""Data sync: receive readings from the broker and hand them to the service loop.

paho runs its own network thread. It only decodes and queues; all database work happens on
the service thread, so nothing is shared but the queue.
"""

import logging
import queue
import time

import paho.mqtt.client as mqtt

from shared.messages import QOS, SUBSCRIPTION, Reading, decode

log = logging.getLogger(__name__)


def parse(payload: bytes) -> Reading | None:
    """A bad payload is logged and skipped, it never stops the twin."""
    try:
        return decode(payload)
    except ValueError as error:
        log.warning("%s", error)
        return None


class Subscriber:
    def __init__(self, host: str, port: int, client_id: str) -> None:
        self.inbox: queue.Queue[tuple[Reading, float]] = queue.Queue()
        self.connected = False
        # Clean session: the twin only gets readings published after it connects,
        # so start it before the simulator
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.connect_async(host, port)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = not reason_code.is_failure
        log.info("broker connect: %s", reason_code)
        if self.connected:
            # Subscribe on every connect, so a broker restart does not leave us deaf
            client.subscribe(SUBSCRIPTION, qos=QOS)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = False
        log.warning("broker disconnected: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        reading = parse(message.payload)
        if reading is not None:
            self.inbox.put((reading, time.time()))

    def drain(self) -> list[tuple[Reading, float]]:
        items = []
        while True:
            try:
                items.append(self.inbox.get_nowait())
            except queue.Empty:
                return items

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()
