"""Loads the asset graph. Every part of the twin uses this, so they all see the same graph."""

from pathlib import Path

import networkx as nx

from twin.graph_builder import GraphBuilder

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

NODE_COLUMNS = {"id", "name", "type", "layer", "purdue", "equipment", "unit",
                "normal_min", "normal_max", "fail_position", "description"}
EDGE_COLUMNS = {"source", "target", "rel", "reason"}

PHYSICAL = {"equipment", "utility"}
CONTROL = {"controller", "safety_system"}
CYBER = CONTROL | {"supervisory", "site_operations", "dmz", "wan", "onshore", "enterprise"}
FIELD = {"sensor", "actuator"}
NODE_TYPES = PHYSICAL | CYBER | FIELD


def load_graph(data_dir: Path = DATA_DIR) -> nx.DiGraph:
    builder = GraphBuilder(data_dir / "nodes.csv", data_dir / "edges.csv",
                           NODE_COLUMNS, EDGE_COLUMNS, NODE_TYPES)
    return builder.build()


def tags(G: nx.DiGraph) -> list[str]:
    """Nodes that report a value: the sensors plus actuator position feedback."""
    return [n for n, t in G.nodes(data="type") if t in FIELD]


def reporter_of(G: nx.DiGraph) -> dict[str, str]:
    """Which controller each tag reaches the twin through: reads edges for sensors,
    commands edges for actuator feedback. A sensor read by both a DCS and the SIS (PT201)
    reports through the DCS."""
    out = {}
    for source, target, rel in G.edges(data="rel"):
        if rel == "reads" and (source not in out or G.nodes[target]["type"] == "controller"):
            out[source] = target
        elif rel == "commands" and G.nodes[target]["type"] == "actuator":
            out[target] = source
    return out
