"""Impact analysis: if this node fails in this way, what else is affected?

Implements the rules in the "Impact Analysis Rules" doc. Rule numbers match the doc.
Rule V is the extra visibility rule: a down network node cuts the data path to shore.
"""

from collections import deque
from dataclasses import asdict, dataclass, field
from enum import StrEnum

import networkx as nx

from twin import config
from twin.model import CYBER, reporter_of


class Mode(StrEnum):
    """How the start node fails."""

    WRONG_READINGS = "wrong_readings"  # sensor
    LOST_CONTROL = "lost_control"  # actuator: stuck valve, tampered loop
    DOWN = "down"  # any cyber node
    LOST = "lost"  # utility
    STOPPED = "stopped"  # equipment
    COMPROMISED = "compromised"  # any cyber node: gives reach only


class Effect(StrEnum):
    WRONG_READINGS = "wrong_readings"
    DOWN = "down"
    COMPROMISED = "compromised"
    LOST = "lost"
    STOPPED = "stopped"
    LOSS_OF_CONTROL = "loss_of_control"
    LOSS_OF_PROTECTION = "loss_of_protection"
    PROCESS_IMPACT = "process_impact"
    LOSS_OF_VIEW = "loss_of_view"
    REACHABLE = "reachable"


DAMAGE = {Effect.LOSS_OF_CONTROL, Effect.LOSS_OF_PROTECTION, Effect.PROCESS_IMPACT,
          Effect.STOPPED, Effect.LOST}

START_EFFECT = {
    Mode.WRONG_READINGS: Effect.WRONG_READINGS,
    Mode.LOST_CONTROL: Effect.LOSS_OF_CONTROL,
    Mode.DOWN: Effect.DOWN,
    Mode.LOST: Effect.LOST,
    Mode.STOPPED: Effect.STOPPED,
    Mode.COMPROMISED: Effect.COMPROMISED,
}


def modes_for(node_type: str) -> list[Mode]:
    """The failure modes that make sense for a node type."""
    if node_type == "sensor":
        return [Mode.WRONG_READINGS]
    if node_type == "actuator":
        return [Mode.LOST_CONTROL]
    if node_type == "utility":
        return [Mode.LOST]
    if node_type == "equipment":
        return [Mode.STOPPED]
    if node_type in CYBER:
        return [Mode.DOWN, Mode.COMPROMISED]
    return []


@dataclass(frozen=True)
class Impact:
    node: str
    effect: Effect
    rule: str  # rule number from the doc, "V" for the visibility rule
    source: str  # the node this impact came from
    detail: str = ""


@dataclass
class ImpactResult:
    start: str
    mode: Mode
    firewall_holds: bool
    impacts: list[Impact] = field(default_factory=list)

    @property
    def damage(self) -> list[Impact]:
        return [i for i in self.impacts if i.effect in DAMAGE]

    @property
    def reach(self) -> list[Impact]:
        return [i for i in self.impacts if i.effect == Effect.REACHABLE]

    @property
    def visibility(self) -> list[Impact]:
        return [i for i in self.impacts if i.effect == Effect.LOSS_OF_VIEW]

    def nodes(self, effects: set[Effect] | None = None) -> set[str]:
        return {i.node for i in self.impacts if effects is None or i.effect in effects}

    def path_to(self, node: str) -> list[str]:
        """The chain of nodes from the start node to this node, following the first impact found."""
        first = {}
        for impact in self.impacts:
            first.setdefault(impact.node, impact)
        path = [node]
        while path[-1] != self.start and path[-1] in first:
            path.append(first[path[-1]].source)
        return path[::-1]

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "mode": str(self.mode),
            "firewall_holds": self.firewall_holds,
            "impacts": [asdict(i) | {"effect": str(i.effect)} for i in self.impacts],
        }


def analyze(G: nx.DiGraph, node: str, mode: Mode, firewall_holds: bool = True) -> ImpactResult:
    if node not in G:
        raise ValueError(f"unknown node {node}")
    if mode not in modes_for(G.nodes[node]["type"]):
        raise ValueError(f"{mode} does not apply to {node} ({G.nodes[node]['type']})")
    return _Walk(G, node, mode, firewall_holds).run()


class _Walk:
    """Breadth-first walk. Each (node, effect) is recorded once, so loops end."""

    def __init__(self, G, start, mode, firewall_holds):
        self.G = G
        self.result = ImpactResult(start, mode, firewall_holds)
        self.seen = {(start, START_EFFECT[mode])}
        # Queue items: (node, effect, scope). Scope limits a controller's loss of control to some
        # actuators, or the SIS's loss of protection to some targets. None means everything.
        self.queue = deque([(start, START_EFFECT[mode], None)])

    def run(self) -> ImpactResult:
        while self.queue:
            node, effect, scope = self.queue.popleft()
            for rule in RULES:
                rule(self, node, effect, scope)
        return self.result

    # Helpers

    def type(self, node):
        return self.G.nodes[node]["type"]

    def out(self, node, rel):
        return [t for _, t, r in self.G.out_edges(node, data="rel") if r == rel]

    def into(self, node, rel):
        return [s for s, _, r in self.G.in_edges(node, data="rel") if r == rel]

    def add(self, node, effect, rule, source, detail="", scope=None):
        if (node, effect) in self.seen:
            return
        # A stopped node is already worse than disturbed
        if effect == Effect.PROCESS_IMPACT and (node, Effect.STOPPED) in self.seen:
            return
        self.seen.add((node, effect))
        self.result.impacts.append(Impact(node, effect, rule, source, detail))
        self.queue.append((node, effect, scope))


# Rules. Each takes (walk, node, effect, scope) and adds what follows from it.


def rule_1(w, node, effect, scope):
    """reads: a sensor with wrong readings costs its controller the loops that use it."""
    if effect != Effect.WRONG_READINGS:
        return
    for ctrl in w.out(node, "reads"):
        if w.type(ctrl) != "controller":
            continue
        loops = {a for a in w.out(ctrl, "commands") if node in config.LOOP_INPUTS.get(a, ())}
        if loops:
            w.add(ctrl, Effect.LOSS_OF_CONTROL, "1", node,
                  f"loops: {', '.join(sorted(loops))}", scope=frozenset(loops))


def rule_2(w, node, effect, scope):
    """reads: a sensor with wrong readings costs the SIS the trips that use it."""
    if effect != Effect.WRONG_READINGS:
        return
    for sis in w.out(node, "reads"):
        targets = config.TRIP_TARGETS.get(node, set())
        if w.type(sis) == "safety_system" and targets:
            w.add(sis, Effect.LOSS_OF_PROTECTION, "2", node,
                  f"trips on: {', '.join(sorted(targets))}", scope=frozenset(targets))


def rule_3(w, node, effect, scope):
    """reads: a down controller still has working sensors, but nobody sees them."""
    if effect != Effect.DOWN or w.type(node) not in ("controller", "safety_system"):
        return
    reporter = reporter_of(w.G)
    # Its sensors, plus the position feedback of the actuators it commands. PT201 is read by
    # both DCS_Separation and the SIS but shown through the DCS, so a down SIS does not hide it.
    for tag in w.into(node, "reads") + w.out(node, "commands"):
        if reporter.get(tag) == node:
            w.add(tag, Effect.LOSS_OF_VIEW, "3", node, "values no longer reach the operator")


def rule_4(w, node, effect, scope):
    """commands: a down or confused DCS gives its actuators wrong commands or none."""
    if w.type(node) != "controller" or effect not in (Effect.DOWN, Effect.LOSS_OF_CONTROL):
        return
    for actuator in w.out(node, "commands"):
        if scope is None or actuator in scope:
            w.add(actuator, Effect.LOSS_OF_CONTROL, "4", node)


def rule_5(w, node, effect, scope):
    """commands: a down SIS, or one that lost protection, may not move its safety valves."""
    if w.type(node) != "safety_system" or effect not in (Effect.DOWN, Effect.LOSS_OF_PROTECTION):
        return
    for valve in w.out(node, "commands"):
        if scope is None or valve in scope:
            w.add(valve, Effect.LOSS_OF_PROTECTION, "5", node, "may not move on a trip")


def rule_6(w, node, effect, scope):
    """trips: a down SIS, or one that lost protection, may not stop the equipment it trips."""
    if w.type(node) != "safety_system" or effect not in (Effect.DOWN, Effect.LOSS_OF_PROTECTION):
        return
    for equipment in w.out(node, "trips"):
        if scope is None or equipment in scope:
            w.add(equipment, Effect.LOSS_OF_PROTECTION, "6", node, "may not stop on a trip")


def rule_7(w, node, effect, scope):
    """acts_on: an actuator out of control disturbs its equipment."""
    if effect != Effect.LOSS_OF_CONTROL or w.type(node) != "actuator":
        return
    for equipment in w.out(node, "acts_on"):
        w.add(equipment, Effect.PROCESS_IMPACT, "7", node)


def rule_8(w, node, effect, scope):
    """flows_to: a disturbed or stopped unit disturbs everything downstream."""
    if effect not in (Effect.PROCESS_IMPACT, Effect.STOPPED):
        return
    for downstream in w.out(node, "flows_to"):
        w.add(downstream, Effect.PROCESS_IMPACT, "8", node)


def rule_9(w, node, effect, scope):
    """flows_to backwards: a stopped unit backs flow up into its feeders, one level only."""
    if effect != Effect.STOPPED:
        return
    for upstream in w.into(node, "flows_to"):
        w.add(upstream, Effect.PROCESS_IMPACT, "9", node, "flow backs up")


def rule_10_11(w, node, effect, scope):
    """supplies: a lost utility (or a stopped unit that supplies one) takes its consumers down.
    Valves go to their fail position (Rule 10), equipment and utilities stop (Rule 11)."""
    if effect not in (Effect.LOST, Effect.STOPPED):
        return
    for consumer in w.out(node, "supplies"):
        kind = w.type(consumer)
        if kind == "actuator":
            fail = w.G.nodes[consumer].get("fail_position") or "its fail position"
            w.add(consumer, Effect.LOSS_OF_CONTROL, "10", node, f"goes to fail position: {fail}")
        elif kind == "utility":
            w.add(consumer, Effect.LOST, "11", node)
        else:
            w.add(consumer, Effect.STOPPED, "11", node)


def rule_12(w, node, effect, scope):
    """measured_by: damage does not spread to the sensor. Nothing to do, kept for the record."""


def rule_13(w, node, effect, scope):
    """network: a compromised node gives the attacker reach, hop by hop. Reach is not damage.
    A holding firewall can be reached but not crossed."""
    if effect not in (Effect.COMPROMISED, Effect.REACHABLE):
        return
    holds = w.result.firewall_holds
    if effect == Effect.REACHABLE and node == config.FIREWALL and holds:
        return
    for neighbour in w.out(node, "network"):
        if neighbour == w.result.start:
            continue
        detail = "blocked here" if neighbour == config.FIREWALL and holds else ""
        w.add(neighbour, Effect.REACHABLE, "13", node, detail)


def rule_v(w, node, effect, scope):
    """A down node on the data path to shore blinds the twin. Every controller, and every tag
    it reports, is out of view onshore. Offshore operators can still see them."""
    if effect != Effect.DOWN or node not in config.DATA_PATH:
        return
    lost = [n for n, t in w.G.nodes(data="type") if t in ("controller", "safety_system")]
    reporter = reporter_of(w.G)
    for ctrl in sorted(lost):
        w.add(ctrl, Effect.LOSS_OF_VIEW, "V", node, "onshore: no data path to the twin")
        for tag in sorted(t for t, c in reporter.items() if c == ctrl):
            w.add(tag, Effect.LOSS_OF_VIEW, "V", ctrl, "onshore: no data path to the twin")


RULES = [rule_1, rule_2, rule_3, rule_4, rule_5, rule_6, rule_7, rule_8, rule_9,
         rule_10_11, rule_12, rule_13, rule_v]
