import pytest

from simulator import config, process
from simulator.config import SisAction
from simulator.control import DCS, SIS, PIController
from simulator.process import ProcessState


def normal_readings() -> dict[str, float]:
    return process.true_values(ProcessState())


def test_controller_holds_its_output_at_setpoint():
    controller = PIController(config.LOOPS["PV201"])
    assert controller.update(20.0, setpoint=20.0, dt=1.0) == 50.0


def test_pressure_loop_opens_when_the_reading_is_high():
    controller = PIController(config.LOOPS["PV201"])
    assert controller.update(21.0, setpoint=20.0, dt=1.0) > 50.0


def test_anti_surge_loop_opens_when_the_flow_is_low():
    controller = PIController(config.LOOPS["FV401"])
    assert controller.update(20000.0, setpoint=21000.0, dt=1.0) > 12.5


def test_controller_output_stays_between_0_and_100():
    controller = PIController(config.LOOPS["PV201"])
    for _ in range(100):
        output = controller.update(30.0, setpoint=20.0, dt=1.0)
    assert output == 100.0


def test_dcs_commands_every_actuator_it_runs():
    targets = DCS().commands(normal_readings(), offline=set(), tampered_setpoints={}, dt=1.0)
    assert set(targets) == set(config.LOOPS) | {"HV101"}


def test_offline_controller_sends_no_commands():
    targets = DCS().commands(
        normal_readings(), offline={"DCS_Separation"}, tampered_setpoints={}, dt=1.0
    )
    assert set(targets) == {"FV401", "P501"}


def test_tampered_setpoint_moves_the_loop():
    readings = normal_readings()
    targets = DCS().commands(readings, set(), tampered_setpoints={"LV201": 80.0}, dt=1.0)
    # Level reads far below the new setpoint, so the loop closes the oil valve
    assert targets["LV201"] < config.LOOPS["LV201"].normal_output_pct


@pytest.mark.parametrize(
    "tag, below, at, trip",
    [
        ("PT201", 26.9, 27.0, "PT201_high"),
        ("LSHH201", 0.0, 1.0, "LSHH201"),
        ("LT301", 69.9, 70.0, "LT301_high"),
        ("GD801", 59.9, 60.0, "GD801_gas"),
        ("GD802", 59.9, 60.0, "GD802_gas"),
        ("FD801", 0.0, 1.0, "FD801_fire"),
    ],
)
def test_trip_fires_at_its_limit(tag, below, at, trip):
    sis = SIS()
    assert sis.check({**normal_readings(), tag: below}) == []
    assert sis.check({**normal_readings(), tag: at}) == [trip]


def test_trip_stays_latched_and_is_reported_once():
    sis = SIS()
    assert sis.check({**normal_readings(), "PT201": 28.0}) == ["PT201_high"]
    assert sis.check(normal_readings()) == []
    assert sis.commands() == {"SDV101": 0.0, "BDV201": 100.0}


def test_no_trip_keeps_inlet_open_and_blowdown_closed():
    assert SIS().commands() == {"SDV101": 100.0, "BDV201": 0.0}


def test_gas_detection_asks_for_a_full_shutdown():
    sis = SIS()
    sis.check({**normal_readings(), "GD802": 65.0})
    assert sis.actions() == set(SisAction)
