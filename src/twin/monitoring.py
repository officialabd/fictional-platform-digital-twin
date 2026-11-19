"""Monitoring: flag what looks wrong in the readings, and say which failure could explain it.

Checks run once per simulated second, when every reading of that second has arrived (or the
next second starts). Stale checks run on the wall clock, since no data means no simulated time.

A flag is a symptom on a node. A hypothesis is a suspected failure, (node, mode), that the
impact analysis can take as its start. The twin never says "confirmed", only "suspected".
"""

from collections import deque
from dataclasses import dataclass, field

import networkx as nx

from shared.messages import Reading
from twin import config
from twin.impact import Mode
from twin.model import reporter_of, tags

HISTORY_S = 300


@dataclass(frozen=True)
class Finding:
    """One check that is true right now."""

    node: str
    check: str
    severity: str  # info, warning, alarm
    detail: str
    persist_s: float = 0.0
    hypothesis: tuple[str, Mode, str] | None = None  # (node, mode, confidence)

    @property
    def key(self) -> tuple[str, str]:
        return (self.node, self.check)


@dataclass
class Event:
    kind: str  # flag_open, flag_close, hyp_open, hyp_update, hyp_close
    node: str
    ts: float | None
    check: str = ""
    severity: str = ""
    detail: str = ""
    mode: Mode | None = None
    evidence: str = ""
    confidence: str = ""


CONFIDENCE = {"low": 0, "medium": 1, "high": 2}


@dataclass
class _Hyp:
    node: str
    mode: Mode
    evidence: set[str] = field(default_factory=set)
    confidence: str = "low"


class Monitor:
    def __init__(self, G: nx.DiGraph) -> None:
        self.G = G
        self.tags = tags(G)
        self.reporter = reporter_of(G)
        self.buf: dict[str, deque[tuple[float, float]]] = {}
        self.received_at: dict[str, float] = {}
        self.ts: float | None = None  # simulated second being collected
        self.pending: dict[tuple[str, str], float] = {}  # key -> ts the check first held
        self.jump_until: dict[str, float] = {}
        self.flags: dict[tuple[str, str], Finding] = {}
        self.sim_findings: dict[tuple[str, str], Finding] = {}
        self.wall_findings: dict[tuple[str, str], Finding] = {}
        self.hyps: dict[tuple[str, Mode], _Hyp] = {}
        self.missing: dict[tuple[str, str], float] = {}  # key -> ts its check stopped holding
        self.wall_keys: set[tuple[str, str]] = set()

    # Input

    def feed(self, reading: Reading, received_at: float) -> list[Event]:
        """Take one new (not duplicate) reading. Returns events when a simulated second closes."""
        self.received_at[reading.tag] = received_at
        events = []
        if self.ts is not None and reading.ts > self.ts:
            events = self._close_second(self.ts)
        if self.ts is None or reading.ts >= self.ts:
            self.ts = reading.ts
            buf = self.buf.setdefault(reading.tag, deque())
            buf.append((reading.ts, reading.value))
            while buf and buf[0][0] < reading.ts - HISTORY_S:
                buf.popleft()
        # Older readings (late resends) are stored by the service but not checked again
        return events

    def wall_step(self, now: float) -> list[Event]:
        """Stale checks. Call about once a second."""
        self.wall_findings = {f.key: f for f in self._stale_checks(now)}
        self.wall_keys |= set(self.wall_findings)
        return self._update(self.ts)

    # Helpers for the checks

    def value(self, tag: str) -> float | None:
        buf = self.buf.get(tag)
        return buf[-1][1] if buf else None

    def window(self, tag: str, seconds: float = config.WINDOW_S) -> list[tuple[float, float]]:
        buf = self.buf.get(tag, ())
        if not buf:
            return []
        end = buf[-1][0]
        return [(t, v) for t, v in buf if t > end - seconds]

    def slope_per_min(self, tag: str, seconds: float = config.WINDOW_S) -> float | None:
        """Least squares slope over the window, in units per minute."""
        pts = self.window(tag, seconds)
        if len(pts) < seconds / 2:
            return None
        n = len(pts)
        mt = sum(t for t, _ in pts) / n
        mv = sum(v for _, v in pts) / n
        den = sum((t - mt) ** 2 for t, _ in pts)
        return 60 * sum((t - mt) * (v - mv) for t, v in pts) / den if den else None

    def mean(self, tag: str, seconds: float = config.WINDOW_S) -> float | None:
        pts = self.window(tag, seconds)
        return sum(v for _, v in pts) / len(pts) if pts else None

    def node(self, n: str) -> dict:
        return self.G.nodes[n]

    # Checks on the simulated clock

    def _close_second(self, ts: float) -> list[Event]:
        findings = []
        for check in (self._tag_checks, self._physics_checks):
            findings.extend(check(ts))
        self.sim_findings = {f.key: f for f in findings}
        return self._update(ts)

    def _tag_checks(self, ts: float) -> list[Finding]:
        out = []
        for tag in self.tags:
            v = self.value(tag)
            d = self.node(tag)
            if v is None or d["type"] != "sensor":
                continue
            unit, lo, hi = d.get("unit"), d.get("normal_min"), d.get("normal_max")
            if unit == "on/off":
                if v >= 0.5:
                    out.append(Finding(tag, "switch_on", "alarm", f"{tag} is on"))
                continue
            if lo is not None and hi is not None:
                if v < lo or v > hi:
                    side = "below" if v < lo else "above"
                    out.append(Finding(tag, "out_of_range", "warning",
                                       f"{v:g} {unit}, {side} normal {lo:g} to {hi:g}",
                                       config.RANGE_PERSIST_S))
                out += self._jump(tag, ts, hi - lo, unit)
            limit = config.TRIP_LIMITS.get(tag)
            if limit is not None and v >= config.NEAR_TRIP_FRACTION * limit:
                out.append(Finding(tag, "near_trip", "alarm",
                                   f"{v:g} {unit}, trip at {limit:g}"))
            out += self._frozen(tag)
        return out

    def _jump(self, tag, ts, width, unit) -> list[Finding]:
        buf = self.buf[tag]
        if len(buf) >= 2 and buf[-1][0] - buf[-2][0] <= config.TICK_S:
            step = abs(buf[-1][1] - buf[-2][1])
            if step > config.JUMP_FRACTION * width:
                self.jump_until[tag] = ts + config.JUMP_HOLD_S
        if self.jump_until.get(tag, -1) >= ts:
            return [Finding(tag, "jump", "warning", "jumped more than its whole normal range "
                            "in one second")]
        return []

    def _frozen(self, tag) -> list[Finding]:
        last = [v for _, v in list(self.buf[tag])[-config.FROZEN_READINGS:]]
        if len(last) == config.FROZEN_READINGS and len(set(last)) == 1 and last[0] != 0:
            return [Finding(tag, "frozen", "warning",
                            f"same value {last[0]:g} for {len(last)} readings",
                            hypothesis=(tag, Mode.WRONG_READINGS, "low"))]
        return []

    def _physics_checks(self, ts: float) -> list[Finding]:
        v = self.value
        out = []
        air = v("PT901")
        air_ok = air is None or air >= config.AIR_MIN_BARG
        inlet_open = (v("SDV101") or 0) > config.VALVE_OPEN_PCT
        inflow = (v("FT101") or 0) > config.INFLOW_PRESENT_M3H

        # Instrument air lost: every pneumatic valve goes to its fail position
        if not air_ok:
            out.append(Finding("Instrument_Air", "air_lost", "alarm",
                               f"PT901 {air:g} barg, below {config.AIR_MIN_BARG:g}",
                               hypothesis=("Instrument_Air", Mode.LOST, "high")))

        # Gas outlet closing but the pressure does not rise
        pv, pt = v("PV201"), v("PT201")
        rise = self.slope_per_min("PT201")
        if (pv is not None and pt is not None and rise is not None and inlet_open and inflow
                and pv < config.GAS_VALVE_LOW_PCT and rise < config.PRESSURE_RISE_BAR_PER_MIN
                and self._in_range("PT201", pt)):
            out.append(Finding("PT201", "valve_vs_pressure", "alarm",
                               f"PV201 at {pv:.0f}% but PT201 steady at {pt:g} barg",
                               config.PHYSICS_PERSIST_S,
                               ("PT201", Mode.WRONG_READINGS, "medium")))

        # Gas going to the flare while nothing reported explains it
        flare, bdv, power = v("FT701"), v("BDV201"), v("JT401")
        if (flare is not None and pt is not None and flare > config.FLARE_HIGH_SM3H
                and (bdv or 0) < config.VALVE_OPEN_PCT
                and (power or 0) > config.COMPRESSOR_RUNNING_MW
                and pt < config.TRIP_LIMITS["PT201"]):
            out.append(Finding("PT201", "flare_vs_pressure", "alarm",
                               f"flare at {flare:.0f} Sm3/h, blowdown closed, compressor "
                               f"running, but PT201 at {pt:g} barg (PSV lifts at 30)",
                               config.TICK_S * 3, ("PT201", Mode.WRONG_READINGS, "high")))

        # Separator liquid balance: levels must follow inflow minus outflows
        means = [self.mean(t) for t in ("FT101", "FT202", "FT203")]
        s1, s2 = self.slope_per_min("LT201"), self.slope_per_min("LT202")
        if None not in means and s1 is not None and s2 is not None:
            imbalance = means[0] - means[1] - means[2]
            if abs(imbalance) > config.LIQUID_IMBALANCE_M3H:
                expected = imbalance * config.LEVEL_PCT_PER_MIN_PER_M3H
                actual = s1 + s2
                if actual * expected <= 0 or abs(actual) < 0.25 * abs(expected):
                    out.append(Finding("Separator", "liquid_balance", "warning",
                                       f"in minus out is {imbalance:+.0f} m3/h, levels should "
                                       f"move {expected:+.1f} %/min but move {actual:+.1f}",
                                       config.PHYSICS_PERSIST_S))

        # Control loops pushing the wrong way
        for actuator, (tag, direction, normal) in config.LOOPS.items():
            a, x = v(actuator), v(tag)
            d = self.node(tag)
            lo, hi = d.get("normal_min"), d.get("normal_max")
            if a is None or x is None or (actuator in config.PNEUMATIC and not air_ok):
                continue
            high, low = x > hi, x < lo
            opens = a > normal + config.LOOP_MARGIN_PCT
            closes = a < normal - config.LOOP_MARGIN_PCT
            wrong = (high and (closes if direction > 0 else opens)) or (
                low and (opens if direction > 0 else closes))
            if wrong:
                out.append(Finding(actuator, "loop_not_correcting", "alarm",
                                   f"{tag} at {x:g} is out of range, but {actuator} at {a:.0f}% "
                                   "pushes the wrong way", config.PHYSICS_PERSIST_S,
                                   (actuator, Mode.LOST_CONTROL, "medium")))

        # Machines stopped
        if power is not None and power < config.COMPRESSOR_RUNNING_MW:
            out.append(Finding("Compressor", "stopped", "alarm", f"JT401 at {power:g} MW",
                               config.TICK_S * 3, ("Compressor", Mode.STOPPED, "high")))
        speed = v("P501")
        if speed is not None and speed < 1:
            out.append(Finding("Export_Pumps", "stopped", "alarm", "P501 speed at 0",
                               config.TICK_S * 3, ("Export_Pumps", Mode.STOPPED, "high")))

        # The SIS acted. Not a fault, but the operator must know
        if v("SDV101") is not None and not inlet_open:
            out.append(Finding("SDV101", "inlet_shut", "info", "inlet shutdown valve closed"))
        if (bdv or 0) > config.VALVE_OPEN_PCT:
            out.append(Finding("BDV201", "blowdown", "info", "blowdown valve open to flare"))
        return out

    def _in_range(self, tag, value) -> bool:
        d = self.node(tag)
        return d["normal_min"] <= value <= d["normal_max"]

    # Checks on the wall clock

    def _stale_checks(self, now: float) -> list[Finding]:
        if not self.received_at:
            return []
        stale = {t for t in self.tags if now - self.received_at.get(t, now) > config.STALE_S}
        seen = set(self.received_at)
        if seen and stale >= seen:
            return [Finding(config.SATELLITE_LINK, "no_data", "alarm",
                            f"no reading for over {config.STALE_S:g} s. The data path to shore "
                            "is down somewhere: SCADA, Historian, Firewall or Satellite_Link",
                            hypothesis=(config.SATELLITE_LINK, Mode.DOWN, "medium"))]
        out = []
        by_ctrl: dict[str, set[str]] = {}
        for tag, ctrl in self.reporter.items():
            if tag in seen:
                by_ctrl.setdefault(ctrl, set()).add(tag)
        silent = set()
        for ctrl, its_tags in by_ctrl.items():
            if its_tags <= stale:
                silent |= its_tags
                out.append(Finding(ctrl, "silent", "alarm",
                                   f"all {len(its_tags)} tags it reports went quiet, others fine",
                                   hypothesis=(ctrl, Mode.DOWN, "high")))
        for tag in sorted(stale - silent):
            out.append(Finding(tag, "stale", "warning", f"no reading for {config.STALE_S:g} s"))
        return out

    # Flag and hypothesis lifecycle

    def _update(self, ts: float | None) -> list[Event]:
        events = []
        current = self.sim_findings | self.wall_findings
        for key, f in current.items():
            since = self.pending.setdefault(key, ts if ts is not None else 0.0)
            held = (ts or 0.0) - since >= f.persist_s
            if key not in self.flags and held:
                self.flags[key] = f
                events.append(Event("flag_open", f.node, ts, f.check, f.severity, f.detail))
            elif key in self.flags:
                self.flags[key] = f  # keep the detail current
        for key in list(self.pending):
            if key not in current:
                del self.pending[key]
        # A flag on the simulated clock clears only after its check has been false for a while,
        # so a cycling PSV does not open and close the same flag every 30 seconds.
        # Wall clock flags (stale data) clear as soon as data is back.
        for key in [k for k in self.flags if k not in current]:
            gone = self.missing.setdefault(key, ts or 0.0)
            hold = 0.0 if key in self.wall_keys else config.CLEAR_HOLD_S
            if (ts or 0.0) - gone >= hold:
                f = self.flags.pop(key)
                del self.missing[key]
                events.append(Event("flag_close", f.node, ts, f.check))
        for key in [k for k in self.missing if k in current]:
            del self.missing[key]
        return events + self._update_hypotheses(ts)

    def _update_hypotheses(self, ts) -> list[Event]:
        wanted: dict[tuple[str, Mode], _Hyp] = {}
        for f in self.flags.values():
            if f.hypothesis is None:
                continue
            node, mode, conf = f.hypothesis
            h = wanted.setdefault((node, mode), _Hyp(node, mode))
            h.evidence.add(f"{f.node} {f.check}")
            if CONFIDENCE[conf] > CONFIDENCE[h.confidence]:
                h.confidence = conf
        events = []
        for key, h in wanted.items():
            old = self.hyps.get(key)
            if old is None:
                events.append(Event("hyp_open", h.node, ts, mode=h.mode,
                                    evidence=", ".join(sorted(h.evidence)),
                                    confidence=h.confidence))
            elif (old.evidence, old.confidence) != (h.evidence, h.confidence):
                events.append(Event("hyp_update", h.node, ts, mode=h.mode,
                                    evidence=", ".join(sorted(h.evidence)),
                                    confidence=h.confidence))
        for key, h in self.hyps.items():
            if key not in wanted:
                events.append(Event("hyp_close", h.node, ts, mode=h.mode))
        self.hyps = wanted
        return events
