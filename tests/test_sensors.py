import pytest

from simulator import config, process
from simulator.process import ProcessState
from simulator.sensors import Sensors


def true_values() -> dict[str, float]:
    return process.true_values(ProcessState())


def test_without_noise_sensors_report_the_true_value():
    reported = Sensors(noise=False).read(true_values(), spoofs={})
    for tag, value in true_values().items():
        assert reported[tag] == pytest.approx(value, abs=1e-3), tag


def test_noise_changes_analog_sensors_only():
    reported = Sensors(seed=1).read(true_values(), spoofs={})
    assert reported["PT201"] != true_values()["PT201"]
    assert reported["LSHH201"] == true_values()["LSHH201"]
    assert reported["SDV101"] == true_values()["SDV101"]


def test_same_seed_gives_the_same_readings():
    assert Sensors(seed=7).read(true_values(), {}) == Sensors(seed=7).read(true_values(), {})


def test_spoof_replaces_the_reported_value():
    reported = Sensors(noise=False).read(true_values(), spoofs={"PT201": 19.0})
    assert reported["PT201"] == 19.0


def test_spoofed_reading_still_looks_alive():
    sensors = Sensors(seed=1)
    values = {sensors.read(true_values(), spoofs={"PT201": 19.0})["PT201"] for _ in range(5)}
    assert len(values) > 1
    assert all(abs(value - 19.0) < 5 * config.NOISE_SD["PT201"] for value in values)


def test_noise_never_reports_below_zero():
    true = {**true_values(), "GD801": 0.0}
    sensors = Sensors(seed=1)
    assert all(sensors.read(true, spoofs={})["GD801"] >= 0.0 for _ in range(50))
