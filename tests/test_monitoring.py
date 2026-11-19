"""Monitoring, replayed against the simulator.

The tests drive the simulator's Plant directly, the way the other tests do. The twin code itself
never imports the simulator: it only ever sees Reading objects.
"""

import pytest

from shared.messages import Reading
from simulator.plant import Plant
from simulator.scenarios import SCENARIOS
from twin.impact import Mode
from twin.model import load_graph
from twin.monitoring import Monitor


@pytest.fixture(scope="module")
def G():
    return load_graph()


def replay(G, scenario, duration, seed=1):
    """Feed a scenario through the monitor with wall time = simulated time.

    While the link is down nothing is fed. When it comes back, the backlog arrives at once,
    as the store and forward would send it.
    """
    plant, monitor = Plant(SCENARIOS[scenario], seed=seed), Monitor(G)
    events, backlog = [], []
    for t in range(duration):
        tick = plant.step(float(t))
        backlog += [Reading(tag, float(t), v) for tag, v in tick.visible.items()]
        if not tick.link_down:
            for reading in backlog:
                events += monitor.feed(reading, received_at=float(t))
            backlog = []
        events += monitor.wall_step(t + 0.5)
    return events


def first(events, kind, node, check=None, mode=None):
    for e in events:
        if (e.kind, e.node) == (kind, node) and check in (None, e.check) and mode in (None, e.mode):
            return e.ts
    return None


def test_normal_operation_raises_nothing(G):
    assert replay(G, "normal", 900) == []


@pytest.mark.parametrize("seed", [2, 3])
def test_normal_operation_is_quiet_with_other_noise(G, seed):
    assert replay(G, "normal", 600, seed=seed) == []


def test_spoof_pt201_is_suspected_from_physics(G):
    events = replay(G, "spoof_pt201", 260)
    assert first(events, "flag_open", "PT201", "out_of_range") is None  # it looks normal
    assert 120 < first(events, "flag_open", "PT201", "valve_vs_pressure") < 200
    assert 205 < first(events, "flag_open", "PT201", "flare_vs_pressure") < 220
    assert first(events, "hyp_open", "PT201", mode=Mode.WRONG_READINGS) is not None


def test_vendor_remote_access_shows_the_loop_pushing_the_wrong_way(G):
    events = replay(G, "vendor_remote_access", 420)
    assert first(events, "flag_open", "FT202", "out_of_range") < 100  # oil outflow drops first
    assert 300 < first(events, "hyp_open", "LV201", mode=Mode.LOST_CONTROL) < 420


def test_instrument_air_loss(G):
    events = replay(G, "instrument_air_loss", 450)
    assert first(events, "hyp_open", "Instrument_Air", mode=Mode.LOST) is not None
    assert first(events, "flag_open", "BDV201", "blowdown") is not None


def test_controller_offline_is_told_apart_from_link_loss(G):
    events = replay(G, "dcs_separation_offline", 90)
    assert first(events, "hyp_open", "DCS_Separation", mode=Mode.DOWN) is not None
    assert first(events, "hyp_open", "Satellite_Link") is None


def test_satellite_link_loss_and_recovery(G):
    events = replay(G, "satellite_link_loss", 700)
    assert first(events, "hyp_open", "Satellite_Link", mode=Mode.DOWN) < 70
    assert first(events, "hyp_close", "Satellite_Link") is not None
    # No per-controller false alarm while everything is quiet
    assert first(events, "hyp_open", "DCS_Separation") is None


def test_flags_do_not_flap_while_the_psv_cycles(G):
    events = replay(G, "spoof_pt201", 600)
    opens = [e for e in events if e.kind == "flag_open" and e.check == "flare_vs_pressure"]
    assert len(opens) == 1


def test_frozen_sensor_is_flagged(G):
    monitor = Monitor(G)
    events = []
    for t in range(40):
        events += monitor.feed(Reading("PT201", float(t), 20.0), received_at=float(t))
    assert first(events, "flag_open", "PT201", "frozen") is not None


def test_normal_pump_loop_swing_is_not_a_jump(G):
    # Seen live: FT501 stepped 5.05 m3/h (half its normal range) in normal operation
    monitor = Monitor(G)
    events = []
    for t, v in enumerate([61.852, 56.802] * 3):
        events += monitor.feed(Reading("FT501", float(t), v), received_at=float(t))
    assert first(events, "flag_open", "FT501", "jump") is None
