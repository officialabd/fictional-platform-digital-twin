from twin.graph_builder import GraphBuilder
from twin.graph_visualizer import GraphVisualizer
from twin.load_neo4j import Neo4jLoader
import matplotlib.pyplot as plt
from dotenv import load_dotenv

load_dotenv()

NODE_COLUMNS = {"id", "name", "type", "layer", "purdue", "equipment", "unit",
                "normal_min", "normal_max", "fail_position", "description"}
EDGE_COLUMNS = {"source", "target", "rel", "reason"}

PHYSICAL = {"equipment", "utility"}
CONTROL = {"controller", "safety_system"}
CYBER = CONTROL | {"supervisory", "site_operations", "dmz", "wan", "onshore", "enterprise"}
NODE_TYPES = PHYSICAL | CYBER | {"sensor", "actuator"}

builder = GraphBuilder("data/nodes.csv", "data/edges.csv", NODE_COLUMNS, EDGE_COLUMNS, NODE_TYPES)

G = builder.build()

# builder.print_summary()

visualizer = GraphVisualizer(G)
visualizer.show_interactive()  # writes runs/asset_graph.html and opens it in the browser


# with Neo4jLoader() as loader:
#     loader.load(G)
#     loader.compare_counts(G)