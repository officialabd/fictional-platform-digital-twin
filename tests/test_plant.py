import pytest

from simulator import config
from simulator.faults import Fault, FaultKind
from simulator.plant import Event, Plant, Tick
from simulator.scenarios import SCENARIOS


def run(plant: Plant, seconds: int, start: int = 0) -> tuple[Tick, list[Event]]:
    """Step the plant and return the last tick and every event along the way."""
    events = []
    for t in range(start, start + seconds):
        tick = plant.step(float(t))
        events += tick.events
    return tick, events


def test_every_tag_exists_in_the_graph(node_rows):
    assert set(config.TAGS) <= set(node_rows)


def test_steady_state_holds_for_10_minutes_inside_normal_ranges(node_rows):
    plant = Plant(noise=False)
    first, _ = run(plant, 1)
    last, events = run(plant, 600, start=1)
    assert events == []
    for tag, value in last.true.items():
        assert value == pytest.approx(first.true[tag], abs=1e-6), tag
        row = node_rows[tag]
        if row["normal_min"] and row["unit"] != "on/off":
            assert float(row["normal_min"]) <= value <= float(row["normal_max"]), tag


def test_noisy_steady_state_trips_nothing():
    _, events = run(Plant(seed=1), 600)
    assert events == []


def test_gas_detection_gives_a_full_shutdown():
    plant = Plant(noise=False)
    plant.state.gas_lel["GD802"] = 65.0
    _, events = run(plant, 10)
    state = plant.state
    assert Event("trip", "GD802_gas") in events
    assert state.positions["SDV101"] == 0 and state.positions["BDV201"] == 100
    assert not state.compressor_running and state.positions["P501"] == 0


def test_spoofed_pt201_blinds_the_trip_and_only_the_psv_is_left():
    plant = Plant(SCENARIOS["spoof_pt201"], noise=False)
    tick, events = run(plant, 600)
    assert Event("trip", "PT201_high") not in events
    assert Event("psv_lift", "PSV201") in events
    assert tick.visible["PT201"] == 19.0
    assert tick.true["PT201"] > config.TRIPS["PT201_high"].limit


def test_truth_keeps_the_real_value_while_the_tag_is_spoofed():
    plant = Plant([Fault(FaultKind.SPOOF, "LT201", 0, value=10.0)], noise=False)
    tick = plant.step(0.0)
    assert tick.visible["LT201"] == 10.0
    assert tick.true["LT201"] == pytest.approx(50.0)


def test_instrument_air_loss_sends_every_pneumatic_valve_to_its_fail_position():
    plant = Plant(SCENARIOS["instrument_air_loss"], noise=False)
    run(plant, 460)  # 60 s of normal operation, then 7.5 to 4.5 barg takes 6 minutes
    for valve in config.PNEUMATIC_VALVES:
        assert plant.state.positions[valve] == config.FAIL_POSITION_PCT[valve], valve


def test_stuck_valve_ignores_commands():
    plant = Plant(
        [
            Fault(FaultKind.STUCK, "LV201", 0),
            Fault(FaultKind.TAMPER, "LV201", 0, value=80.0),
        ],
        noise=False,
    )
    run(plant, 120)
    assert plant.state.positions["LV201"] == 50.0


def test_offline_controller_fails_its_valves_and_goes_silent():
    plant = Plant([Fault(FaultKind.OFFLINE, "DCS_Separation", 0)], noise=False)
    tick, _ = run(plant, 30)
    assert plant.state.positions["PV201"] == 100 and plant.state.positions["LV201"] == 0
    assert plant.state.positions["HV101"] == config.HV101_NORMAL_PCT  # stays in place
    assert "LT201" not in tick.visible and "LSHH201" in tick.visible
    assert "LT201" in tick.true


def test_offline_sis_fails_its_valves_to_a_safe_position():
    plant = Plant([Fault(FaultKind.OFFLINE, config.SIS, 0)], noise=False)
    run(plant, 5)
    assert plant.state.positions["SDV101"] == 0 and plant.state.positions["BDV201"] == 100


def test_tampered_level_setpoint_causes_the_scrubber_cascade():
    plant = Plant(SCENARIOS["vendor_remote_access"], noise=False)
    _, events = run(plant, 3000)
    trips = [event.detail for event in events if event.kind == "trip"]
    assert trips[0] == "LT301_high"
    assert Event("compressor_stop", config.SIS) in events


def test_fault_start_and_end_are_logged():
    plant = Plant([Fault(FaultKind.LINK, "Satellite_Link", 1, end_s=2)], noise=False)
    assert plant.step(0.0).events == []
    tick = plant.step(1.0)
    assert tick.link_down and tick.events == [Event("fault_on", "link Satellite_Link")]
    tick = plant.step(2.0)
    assert not tick.link_down and tick.events == [Event("fault_off", "link Satellite_Link")]


def test_link_loss_does_not_touch_the_process():
    normal, _ = run(Plant(noise=False), 200)
    cut_off, _ = run(Plant(SCENARIOS["satellite_link_loss"], noise=False), 200)
    assert cut_off.true == normal.true
