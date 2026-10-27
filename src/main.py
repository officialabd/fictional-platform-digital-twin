from graph_builder import GraphBuilder
from graph_visualizer import GraphVisualizer
from load_neo4j import Neo4jLoader
import matplotlib.pyplot as plt
from dotenv import load_dotenv

load_dotenv()

NODE_COLUMNS = {"id", "name", "type", "layer", "purdue", "equipment", "unit",
                "normal_min", "normal_max", "fail_position"}
EDGE_COLUMNS = {"source", "target", "rel", "reason"}

PHYSICAL = {"equipment", "utility"}
CONTROL = {"controller", "safety_system"}
CYBER = CONTROL | {"supervisory", "site_operations", "dmz", "wan", "onshore", "enterprise"}
NODE_TYPES = PHYSICAL | CYBER | {"sensor", "actuator"}

builder = GraphBuilder("data/nodes.csv", "data/edges.csv", NODE_COLUMNS, EDGE_COLUMNS, NODE_TYPES)

G = builder.build()

# builder.print_summary()

visualizer = GraphVisualizer(G)
fig = visualizer.interactive_draw()
# fig.canvas.manager.window.state('zoomed')
# fig.show()


with Neo4jLoader() as loader:
    loader.load(G)
    loader.compare_counts(G)