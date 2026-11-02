"""The simulated platform: wires process, sensors, DCS, SIS and faults into one tick."""

from dataclasses import dataclass
from typing import NamedTuple

from simulator import config, process
from simulator.config import SisAction
from simulator.control import DCS, SIS
from simulator.faults import Fault, FaultEffects
from simulator.process import ProcessState
from simulator.sensors import Sensors


class Event(NamedTuple):
    kind: str
    detail: str


@dataclass(frozen=True)
class Tick:
    """The outcome of one tick. Only `visible` may ever leave the platform."""

    visible: dict[str, float]
    true: dict[str, float]
    events: list[Event]
    link_down: bool


class Plant:
    def __init__(
        self, faults: list[Fault] | None = None, noise: bool = True, seed: int | None = None
    ) -> None:
        self.faults = faults or []
        self.state = ProcessState()
        self.dcs = DCS()
        self.sis = SIS()
        self.sensors = Sensors(noise, seed)
        self.active_faults: list[Fault] = []

    def step(self, t: float, dt: float = config.TICK_S) -> Tick:
        """Read the sensors at time t, run the controls on those readings, advance the process."""
        events = self._update_active_faults(t)
        effects = FaultEffects.of(self.active_faults)
        self.state.air_supply_ok = not effects.air_lost

        true = process.true_values(self.state)
        reported = self.sensors.read(true, effects.spoofs)

        targets = self.dcs.commands(reported, effects.offline, effects.tampered_setpoints, dt)
        if config.SIS not in effects.offline:
            events += self._run_sis(reported, targets)
        self._apply_fail_positions(targets)

        psv_was_open = self.state.psv_open
        process.move_actuators(self.state, targets, effects.stuck, dt)
        process.advance(self.state, dt)
        if self.state.psv_open != psv_was_open:
            kind = "psv_lift" if self.state.psv_open else "psv_reseat"
            events.append(Event(kind, "PSV201"))

        return Tick(self._visible(reported, effects.offline), true, events, effects.link_down)

    def _update_active_faults(self, t: float) -> list[Event]:
        active = [fault for fault in self.faults if fault.is_active(t)]
        started = [fault for fault in active if fault not in self.active_faults]
        ended = [fault for fault in self.active_faults if fault not in active]
        self.active_faults = active
        return [Event("fault_on", f"{fault.kind} {fault.target}") for fault in started] + [
            Event("fault_off", f"{fault.kind} {fault.target}") for fault in ended
        ]

    def _run_sis(self, reported: dict[str, float], targets: dict[str, float]) -> list[Event]:
        events = [Event("trip", name) for name in self.sis.check(reported)]
        targets.update(self.sis.commands())

        actions = self.sis.actions()
        if SisAction.STOP_COMPRESSOR in actions and self.state.compressor_running:
            self.state.compressor_running = False
            events.append(Event("compressor_stop", config.SIS))
        if SisAction.STOP_PUMPS in actions:
            self.state.pumps_running = False
        return events

    def _apply_fail_positions(self, targets: dict[str, float]) -> None:
        """A dead output or lost air drives the actuator to its fail position, whatever is asked."""
        air_lost = self.state.air_barg < config.AIR_MIN_BARG
        for actuator, fail_position in config.FAIL_POSITION_PCT.items():
            no_command = actuator not in targets
            if no_command or (air_lost and actuator in config.PNEUMATIC_VALVES):
                targets[actuator] = fail_position

    @staticmethod
    def _visible(reported: dict[str, float], offline: set[str]) -> dict[str, float]:
        """Readings that reach the historian. An offline controller's tags stop reporting."""
        silenced = {tag for name in offline for tag in config.REPORTED_BY.get(name, [])}
        return {tag: value for tag, value in reported.items() if tag not in silenced}
