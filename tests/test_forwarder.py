import pytest

from shared.messages import Reading
from simulator import config
from simulator.forwarder import Forwarder
from simulator.plant import Plant
from simulator.scenarios import SCENARIOS
from simulator.storage import Historian


class FakeLink:
    """Stands in for the broker, so these tests need no network."""

    def __init__(self, auto_ack: bool = True) -> None:
        self.connected = True
        self.auto_ack = auto_ack
        self.delivered: list[Reading] = []
        self.unacked: list[int] = []
        self.refuse_publish = False

    def publish(self, reading: Reading) -> int | None:
        if self.refuse_publish:
            return None
        self.delivered.append(reading)
        message_id = len(self.delivered)
        self.unacked.append(message_id)
        return message_id

    def take_acks(self) -> list[int]:
        if not self.auto_ack:
            return []
        acks, self.unacked = self.unacked, []
        return acks


@pytest.fixture
def historian(tmp_path):
    historian = Historian(tmp_path)
    yield historian
    historian.close()


def test_readings_are_sent_once_when_the_link_stays_up(historian):
    link = FakeLink()
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    forwarder.tick(link_down=False)
    forwarder.tick(link_down=False)
    assert link.delivered == [Reading("PT201", 0.0, 20.0)]
    assert forwarder.marker == 1


def test_nothing_is_sent_while_the_link_is_down(historian):
    link = FakeLink()
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    forwarder.tick(link_down=True)
    assert link.delivered == []


def test_marker_waits_for_the_acknowledgement(historian):
    link = FakeLink(auto_ack=False)
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    forwarder.tick(link_down=False)
    assert len(link.delivered) == 1
    assert forwarder.marker == 0


def test_marker_stops_at_the_first_gap_in_acknowledgements(historian):
    link = FakeLink(auto_ack=False)
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0, "LT201": 50.0, "LT202": 32.0})
    forwarder.tick(link_down=False)

    link.auto_ack, link.unacked = True, [2, 3]
    forwarder.tick(link_down=False)
    assert forwarder.marker == 0

    link.unacked = [1]
    forwarder.tick(link_down=False)
    assert forwarder.marker == 3


def test_unacknowledged_readings_are_resent_after_a_link_loss(historian):
    link = FakeLink(auto_ack=False)
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    forwarder.tick(link_down=False)
    forwarder.tick(link_down=True)
    forwarder.tick(link_down=False)
    assert link.delivered == [Reading("PT201", 0.0, 20.0)] * 2


def test_acknowledged_readings_are_not_resent_after_a_link_loss(historian):
    link = FakeLink()
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    forwarder.tick(link_down=False)
    forwarder.tick(link_down=False)
    forwarder.tick(link_down=True)
    forwarder.tick(link_down=False)
    assert len(link.delivered) == 1


def test_refused_publish_is_retried_on_the_next_tick(historian):
    link = FakeLink()
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    link.refuse_publish = True
    forwarder.tick(link_down=False)
    link.refuse_publish = False
    forwarder.tick(link_down=False)
    assert link.delivered == [Reading("PT201", 0.0, 20.0)]


def test_flush_sends_the_backlog_and_returns_once_acknowledged(historian):
    link = FakeLink()
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    forwarder.flush(timeout_s=5)
    assert forwarder.marker == 1


def test_flush_gives_up_when_the_broker_is_gone(historian):
    link = FakeLink()
    link.connected = False
    forwarder = Forwarder(historian, link)
    historian.store(0.0, {"PT201": 20.0})
    forwarder.flush(timeout_s=5)
    assert link.delivered == []


def test_link_loss_scenario_backfills_with_original_timestamps(historian):
    link = FakeLink()
    forwarder = Forwarder(historian, link)
    plant = Plant(SCENARIOS["satellite_link_loss"], noise=False)
    delivered_during_outage = 0
    for t in range(700):
        tick = plant.step(float(t))
        historian.store(float(t), tick.visible)
        forwarder.tick(tick.link_down)
        if t == 300:
            delivered_during_outage = sum(r.ts >= 60.0 for r in link.delivered)

    assert delivered_during_outage == 0
    received = {(reading.tag, reading.ts) for reading in link.delivered}
    assert len(received) == 700 * len(config.TAGS)
    assert ("PT201", 300.0) in received
