"""Draw the asset graph as an interactive HTML page.

Example: python -m twin.main
"""

from dotenv import load_dotenv

from twin.graph_visualizer import GraphVisualizer
from twin.model import load_graph

load_dotenv()

G = load_graph()

visualizer = GraphVisualizer(G)
visualizer.show_interactive()  # writes runs/asset_graph.html and opens it in the browser

# from twin.load_neo4j import Neo4jLoader
# with Neo4jLoader() as loader:
#     loader.load(G)
#     loader.compare_counts(G)
