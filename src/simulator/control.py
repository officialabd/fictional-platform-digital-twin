"""DCS control loops and SIS safety trips: Purdue level 1.

Both act on reported values, not true ones, so a spoofed sensor fools them. PT201 feeds both on
purpose: spoofing it blinds the control loop and the pressure trip at once, leaving only the PSV.
"""

from simulator import config
from simulator.config import SisAction


class PIController:
    """Velocity form PI: each tick nudges the output, so saturation cannot wind up the integral."""

    def __init__(self, loop: config.Loop) -> None:
        self.kp = loop.kp
        self.ti_s = loop.ti_s
        self.direction = loop.direction
        self.output = loop.normal_output_pct
        self.last_error: float | None = None

    def update(self, reading: float, setpoint: float, dt: float) -> float:
        error = self.direction * (reading - setpoint)
        if self.last_error is None:
            self.last_error = error
        self.output += self.kp * (error - self.last_error + error * dt / self.ti_s)
        self.output = min(max(self.output, 0.0), 100.0)
        self.last_error = error
        return self.output


class DCS:
    def __init__(self) -> None:
        self.controllers = {actuator: PIController(loop) for actuator, loop in config.LOOPS.items()}

    def commands(
        self,
        readings: dict[str, float],
        offline: set[str],
        tampered_setpoints: dict[str, float],
        dt: float,
    ) -> dict[str, float]:
        """Target position per actuator. An offline controller sends nothing for its actuators."""
        targets = {}
        if config.HV101_CONTROLLER not in offline:
            targets["HV101"] = config.HV101_NORMAL_PCT
        for actuator, loop in config.LOOPS.items():
            if loop.controller in offline:
                continue
            setpoint = tampered_setpoints.get(actuator, loop.setpoint)
            targets[actuator] = self.controllers[actuator].update(
                readings[loop.input_tag], setpoint, dt
            )
        return targets


class SIS:
    def __init__(self) -> None:
        self.tripped: set[str] = set()

    def check(self, readings: dict[str, float]) -> list[str]:
        """Latch and return new trips. Nothing in the simulator resets a trip once it fires."""
        new_trips = [
            name
            for name, trip in config.TRIPS.items()
            if name not in self.tripped and readings[trip.tag] >= trip.limit
        ]
        self.tripped.update(new_trips)
        return new_trips

    def actions(self) -> set[SisAction]:
        return {action for name in self.tripped for action in config.TRIPS[name].actions}

    def commands(self) -> dict[str, float]:
        """Target positions of the two valves only the SIS commands."""
        actions = self.actions()
        return {
            "SDV101": 0.0 if SisAction.CLOSE_INLET in actions else 100.0,
            "BDV201": 100.0 if SisAction.BLOWDOWN in actions else 0.0,
        }
