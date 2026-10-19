import csv
from collections import Counter
from pathlib import Path

import networkx as nx

class GraphError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(f"{len(errors)} problem(s) found:\n  " + "\n  ".join(errors))


def to_number(text):
    # '' -> None, '3.5' -> 3.5
    return float(text) if text else None


class GraphBuilder:
    def __init__(self, nodes_path, edges_path, node_columns, edge_columns, node_types):
        self.nodes_path = Path(nodes_path)
        self.node_columns = node_columns
        self.node_types = node_types

        self.edges_path = Path(edges_path)
        self.edge_columns = edge_columns
        
        self.graph = None

    def read_csv(self, path, required_columns):
        # utf-8-sig removes the BOM that Excel adds when saving a CSV
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = required_columns - set(reader.fieldnames or [])
            if missing:
                raise GraphError([f"{path.name}: missing columns {sorted(missing)}"])
            return [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    def build(self):
        nodes = self.read_csv(self.nodes_path, self.node_columns)
        edges = self.read_csv(self.edges_path, self.edge_columns)

        G = nx.DiGraph()
        for node in nodes:
            attrs = {key: (value or None) for key, value in node.items() if key != "id"}
            attrs["layer"] = int(node["layer"])
            attrs["normal_min"] = to_number(node["normal_min"])
            attrs["normal_max"] = to_number(node["normal_max"])
            G.add_node(node["id"], **attrs)

        for edge in edges:
            G.add_edge(edge["source"], edge["target"], rel=edge["rel"], reason=edge["reason"])

        self.graph = G
        return G

    def print_summary(self):
        node_types = Counter(t for _, t in self.graph.nodes(data="type"))
        edge_rels = Counter(r for _, _, r in self.graph.edges(data="rel"))
        print(f"OK: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        print("  nodes by type:", dict(node_types.most_common()))
        print("  edges by rel: ", dict(edge_rels.most_common()))