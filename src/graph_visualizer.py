from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import networkx as nx


COLORS = {"equipment": "#2a78d6", "utility": "#2a78d6", "sensor": "#eb6834", "actuator": "#eb6834"}

class GraphVisualizer:

    def __init__(self, G):
        self.G = G

    def layout(self):
        pass

    def draw(self):
        # Define area to draw
        fig, ax = plt.subplots(figsize=(20, 10))
        pos = nx.spring_layout(self.G, seed=1)

        # Give each node type a color and draw
        colors = []
        for _, t in self.G.nodes(data='type'):
            colors.append(COLORS.get(t, '#1baf7a'))
        nx.draw_networkx_nodes(self.G, pos, ax=ax, node_size=200, node_color=colors)

        # Define edge lists and draw
        network, others = [], []
        for source, target, rel in self.G.edges(data='rel'):
            if rel == 'network':
                network.append((source, target))
            else:
                others.append((source, target))

        nx.draw_networkx_edges(self.G, pos, edgelist=network, ax=ax, node_size=200, edge_color='gray')
        nx.draw_networkx_edges(self.G, pos, edgelist=others, ax=ax, node_size=200, edge_color='gray', style='dashed')

        nx.draw_networkx_labels(self.G, pos, ax=ax, font_size=8)

        legend = [
            Line2D([], [], marker='o', color='none', markerfacecolor='#2a78d6', markersize=10, label='Equipment'),
            Line2D([], [], marker='o', color='none', markerfacecolor='#eb6834', markersize=10, label='Sensors and actuators'),
            Line2D([], [], marker='o', color='none', markerfacecolor='#1baf7a', markersize=10, label='Cyber systems')
        ]

        ax.legend(handles=legend, loc='upper right')
        ax.set_title('Platform asset graph')
        ax.axis('off')
        fig.tight_layout()
        return fig

    def save(self):
        pass