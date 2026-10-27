from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import networkx as nx
import plotly.graph_objects as go

COLORS = {"equipment": "#2a78d6", "utility": "#2a78d6", "sensor": "#eb6834", "actuator": "#eb6834"}
NODE_SIZE = 1400

class GraphVisualizer:

    def __init__(self, G):
        self.G = G

    def layout(self):
        level_zero_rows = {"equipment": 0, "utility": 0, "actuator": 1, "sensor": 2}
        rows = {}

        for node, data in self.G.nodes(data=True):
            if data['layer'] == 0:
                row = level_zero_rows[data['type']]
            else: 
                row = data['layer'] + 2
            rows.setdefault(row, []).append(node)

        rows[1].sort(key=lambda node: rows[0].index(self.G.nodes[node]['equipment']))
        rows[2].sort(key=lambda node: rows[0].index(self.G.nodes[node]['equipment']))

        pos = {}
        for row, nodes in rows.items():
            for i, node in enumerate(nodes):
                x = (i + 0.5) * 30 / len(nodes)
                pos[node] = (x, row)
        return pos
        

    def draw(self):
        # Define area to draw
        fig, ax = plt.subplots(figsize=(20, 10))
        pos = self.layout()

        # Give each node type a color and draw
        colors = []
        for _, t in self.G.nodes(data='type'):
            colors.append(COLORS.get(t, '#1baf7a'))
        nx.draw_networkx_nodes(self.G, pos, ax=ax, node_size=NODE_SIZE, node_color=colors)

        # Define edge lists and draw
        network, network_colors, others, others_colors = [], [], [], []
        for source, target, rel in self.G.edges(data='rel'):
            if rel == 'network':
                network.append((source, target))
                network_colors.append(COLORS.get(self.G.nodes[source]['type'], '#1baf7a'))
            else:
                others.append((source, target))
                others_colors.append(COLORS.get(self.G.nodes[source]['type'], '#1baf7a'))

        nx.draw_networkx_edges(self.G, pos, edgelist=network, ax=ax, node_size=NODE_SIZE, arrowsize=15, edge_color=network_colors)
        nx.draw_networkx_edges(self.G, pos, edgelist=others, ax=ax, node_size=NODE_SIZE, arrowsize=15, edge_color=others_colors, style='dashed')

        labels = {n: n.replace('_', '\n') for n in self.G.nodes}
        nx.draw_networkx_labels(self.G, pos, ax=ax, font_size=7, font_color='black', labels=labels)

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

    def interactive_draw(self):
        pos = self.layout()

        edge_x = []
        edge_y = []
        for source, target in self.G.edges():
            x0, y0 = pos[source]
            x1, y1 = pos[target]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        node_x = []
        node_y = []
        for node in self.G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=edge_x,
                y=edge_y,
                mode="lines",
                line=dict(width=1, color="gray"),
                hoverinfo="none",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=node_x,
                y=node_y,
                mode="markers+text",
                text=list(self.G.nodes()),
                textposition="top center",
                marker=dict(size=18, color="royalblue"),
            )
        )

        fig.update_layout(title="Basic NetworkX Graph", showlegend=False)
        return fig

    def save(self):
        pass