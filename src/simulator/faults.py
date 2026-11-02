"""The fault injector: what can go wrong, and when it is active."""

from dataclasses import dataclass
from enum import StrEnum


class FaultKind(StrEnum):
    SPOOF = "spoof"  # a sensor reports a false value
    STUCK = "stuck"  # a valve ignores its commands
    OFFLINE = "offline"  # a controller stops commanding and reporting
    LINK = "link"  # the link to shore is down
    TAMPER = "tamper"  # someone changes a control loop's setpoint
    AIR_LOSS = "air_loss"  # the instrument air supply is lost


@dataclass(frozen=True)
class Fault:
    kind: FaultKind
    target: str
    start_s: float
    end_s: float | None = None  # None means it lasts until the end of the run
    value: float | None = None  # the spoofed reading or the tampered setpoint

    def is_active(self, t: float) -> bool:
        return t >= self.start_s and (self.end_s is None or t < self.end_s)


@dataclass(frozen=True)
class FaultEffects:
    """What the active faults mean for one tick, in the terms the rest of the simulator uses."""

    spoofs: dict[str, float]
    tampered_setpoints: dict[str, float]
    stuck: set[str]
    offline: set[str]
    air_lost: bool
    link_down: bool

    @classmethod
    def of(cls, active: list[Fault]) -> "FaultEffects":
        def targets(kind: FaultKind) -> set[str]:
            return {fault.target for fault in active if fault.kind == kind}

        def values(kind: FaultKind) -> dict[str, float]:
            return {fault.target: fault.value for fault in active if fault.kind == kind}

        return cls(
            spoofs=values(FaultKind.SPOOF),
            tampered_setpoints=values(FaultKind.TAMPER),
            stuck=targets(FaultKind.STUCK),
            offline=targets(FaultKind.OFFLINE),
            air_lost=bool(targets(FaultKind.AIR_LOSS)),
            link_down=bool(targets(FaultKind.LINK)),
        )
