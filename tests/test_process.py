import pytest

from simulator import config, process
from simulator.process import ProcessState


def run_until(state: ProcessState, condition, limit_s: int = 3600) -> int:
    """Advance one second at a time and return how long the condition took to become true."""
    for second in range(limit_s):
        if condition(state):
            return second
        process.advance(state, dt=1.0)
    raise AssertionError(f"condition not reached in {limit_s} s")


def test_normal_state_is_balanced():
    flows = process.compute_flows(ProcessState())
    assert flows.oil_in == pytest.approx(flows.oil_out)
    assert flows.water_in == pytest.approx(flows.water_out)
    assert flows.gas_in == pytest.approx(flows.gas_out)


def test_every_tag_has_a_true_value():
    assert set(config.TAGS) == set(process.true_values(ProcessState()))


def test_blocked_gas_outlet_lifts_the_psv_within_a_minute():
    state = ProcessState()
    state.positions["PV201"] = 0.0
    assert run_until(state, lambda s: s.psv_open) == pytest.approx(36, abs=5)


def test_psv_reseats_once_pressure_falls():
    state = ProcessState(psv_open=True, gas_sm3=20 * 27.5)
    process.advance(state, dt=1.0)
    assert not state.psv_open


def test_closed_oil_outlet_reaches_the_high_high_level_in_about_16_minutes():
    state = ProcessState()
    state.positions["LV201"] = 0.0
    seconds = run_until(state, lambda s: s.level_pct >= config.LSHH201_PCT)
    assert seconds / 60 == pytest.approx(16, abs=1)


def test_stopped_pumps_block_the_oil_outlet():
    state = ProcessState()
    state.positions["P501"] = 0.0
    assert process.compute_flows(state).oil_out == 0.0


def test_stopped_compressor_sends_gas_to_the_flare():
    state = ProcessState(compressor_running=False)
    flows = process.compute_flows(state)
    assert flows.compressor == 0.0
    assert flows.flare > config.FLARE_PURGE_SM3H + 10000
    assert flows.gas_in == pytest.approx(flows.gas_out)


def test_closed_inlet_stops_inflow_and_the_separator_cools():
    state = ProcessState()
    state.positions["SDV101"] = 0.0
    assert process.compute_flows(state).inflow == 0.0
    process.advance(state, dt=60.0)
    assert state.separator_temp_c < config.SEPARATOR_TEMP_C


def test_lost_air_supply_decays_to_the_limit_in_about_6_minutes():
    state = ProcessState(air_supply_ok=False)
    seconds = run_until(state, lambda s: s.air_barg < config.AIR_MIN_BARG)
    assert seconds / 60 == pytest.approx(6, abs=0.1)


def test_actuators_respect_their_stroke_rate():
    state = ProcessState()
    process.move_actuators(state, {"PV201": 100.0, "BDV201": 100.0}, stuck=set(), dt=1.0)
    assert state.positions["PV201"] == 50.0 + config.CONTROL_VALVE_PCT_PER_S
    assert state.positions["BDV201"] == config.SHUTDOWN_VALVE_PCT_PER_S


def test_stuck_actuator_ignores_its_target():
    state = ProcessState()
    process.move_actuators(state, {"LV201": 100.0}, stuck={"LV201"}, dt=1.0)
    assert state.positions["LV201"] == 50.0


def test_stopped_pumps_ignore_a_speed_command():
    state = ProcessState(pumps_running=False)
    process.move_actuators(state, {"P501": 75.0}, stuck=set(), dt=1.0)
    assert state.positions["P501"] == 75.0 - config.CONTROL_VALVE_PCT_PER_S


def test_shut_in_suction_pressure_never_goes_negative():
    state = ProcessState(gas_sm3=config.ATM_BAR * 19.8)
    assert process.true_values(state)["PT401"] == 0.0
