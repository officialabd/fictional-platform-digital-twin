import json
import webbrowser
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import plotly.graph_objects as go
from matplotlib.lines import Line2D

COLORS = {"equipment": "#2a78d6", "utility": "#2a78d6", "sensor": "#eb6834", "actuator": "#eb6834"}
CYBER_COLOR = "#1baf7a"
NODE_SIZE = 1400
LAYOUT_WIDTH = 30        # x span of every row, in data units
MIN_CONTROLLER_GAP = 4   # minimum x distance between controllers in layer 1
MIN_COLUMN = 2           # minimum column width per equipment, in device slots
CONTROLLER_ROW_GAP = 1   # empty rows between sensors and controllers, keeps reads edges steep

# Interactive view
EDGE_COLOR = "#8a9099"
EDGE_FADED = "rgba(154, 160, 166, 0.12)"
IN_COLOR = "#7b3fe4"    # edges coming into the selected node
OUT_COLOR = "#e0218a"   # edges leaving the selected node
CURVE_POINTS = 21       # odd, so the arrow sits on the exact middle point
ARROW_SIZE = 12
# Rough pixels per data unit. Only used to make curves bend evenly on screen.
PX_X, PX_Y = 50, 85


class GraphVisualizer:

    def __init__(self, G):
        self.G = G

    def layout(self):
        """Rows: 0 equipment, 1 actuators, 2 sensors, then one row per cyber layer.

        Each piece of equipment gets a column wide enough for its own sensors and
        actuators, which sit directly above it. Controllers (layer 1) sit above the
        field devices they read and command. Higher layers are spread evenly.
        """
        nodes = self.G.nodes
        equipment = [n for n, d in nodes(data=True) if d['type'] in ('equipment', 'utility')]
        field = {eq: {'actuator': [], 'sensor': []} for eq in equipment}
        upper = {}
        for n, d in nodes(data=True):
            if d['type'] in ('actuator', 'sensor'):
                field[d['equipment']][d['type']].append(n)
            elif d['layer'] > 0:
                upper.setdefault(d['layer'], []).append(n)

        # Field level: columns sized by the number of devices on each equipment
        width = {eq: max(len(f['actuator']), len(f['sensor']), MIN_COLUMN)
                 for eq, f in field.items()}
        scale = LAYOUT_WIDTH / sum(width.values())
        pos, left = {}, 0.0
        for eq in equipment:
            w = width[eq] * scale
            pos[eq] = (left + w / 2, 0)
            for row, kind in ((1, 'actuator'), (2, 'sensor')):
                devices = field[eq][kind]
                for i, n in enumerate(devices):
                    pos[n] = (left + (i + 0.5) * w / len(devices), row)
            left += w

        for layer in sorted(upper):
            row = layer + 2 + CONTROLLER_ROW_GAP
            if layer == 1:
                # Controllers: average x of their placed neighbours, then push apart
                def centre(n):
                    xs = [pos[m][0] for m in nx.all_neighbors(self.G, n) if m in pos]
                    return sum(xs) / len(xs) if xs else LAYOUT_WIDTH / 2
                ordered = sorted(upper[layer], key=centre)
                xs = [centre(n) for n in ordered]
                for i in range(1, len(xs)):
                    xs[i] = max(xs[i], xs[i - 1] + MIN_CONTROLLER_GAP)
                overflow = xs[-1] - (LAYOUT_WIDTH - 1)
                if overflow > 0:
                    xs = [x - overflow for x in xs]
                for n, x in zip(ordered, xs, strict=True):
                    pos[n] = (x, row)
            else:
                for i, n in enumerate(upper[layer]):
                    pos[n] = ((i + 0.5) * LAYOUT_WIDTH / len(upper[layer]), row)
        return pos


    def draw(self):
        # Define area to draw
        fig, ax = plt.subplots(figsize=(20, 10))
        pos = self.layout()

        # Give each node type a color and draw
        colors = []
        for _, t in self.G.nodes(data='type'):
            colors.append(COLORS.get(t, CYBER_COLOR))
        nx.draw_networkx_nodes(self.G, pos, ax=ax, node_size=NODE_SIZE, node_color=colors)

        # Define edge lists and draw
        network, network_colors, others, others_colors = [], [], [], []
        for source, target, rel in self.G.edges(data='rel'):
            if rel == 'network':
                network.append((source, target))
                network_colors.append(COLORS.get(self.G.nodes[source]['type'], CYBER_COLOR))
            else:
                others.append((source, target))
                others_colors.append(COLORS.get(self.G.nodes[source]['type'], CYBER_COLOR))

        nx.draw_networkx_edges(self.G, pos, edgelist=network, ax=ax, node_size=NODE_SIZE, arrowsize=15, edge_color=network_colors)
        nx.draw_networkx_edges(self.G, pos, edgelist=others, ax=ax, node_size=NODE_SIZE, arrowsize=15, edge_color=others_colors, style='dashed')

        labels = {n: n.replace('_', '\n') for n in self.G.nodes}
        nx.draw_networkx_labels(self.G, pos, ax=ax, font_size=7, font_color='black', labels=labels)

        legend = [
            Line2D([], [], marker='o', color='none', markerfacecolor='#2a78d6', markersize=10, label='Equipment'),
            Line2D([], [], marker='o', color='none', markerfacecolor='#eb6834', markersize=10, label='Sensors and actuators'),
            Line2D([], [], marker='o', color='none', markerfacecolor=CYBER_COLOR, markersize=10, label='Cyber systems')
        ]

        ax.legend(handles=legend, loc='upper right')
        ax.set_title('Platform asset graph')
        ax.axis('off')
        fig.tight_layout()
        return fig

    @staticmethod
    def curve(p0, p1):
        """Quadratic curve from p0 to p1 that bends to the right of the travel direction.

        Bending right means A->B and B->A curve to opposite sides, so a two way
        link shows as two separate arrows instead of one line drawn twice.
        Edges inside one row bend more so they pass around the nodes between them.
        """
        # Work in rough screen pixels so the bend looks the same in every direction
        x0, y0 = p0[0] * PX_X, p0[1] * PX_Y
        x1, y1 = p1[0] * PX_X, p1[1] * PX_Y
        dx, dy = x1 - x0, y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        right = (dy / length, -dx / length)

        peak = 30 + 0.08 * length if p0[1] == p1[1] else max(0.06 * length, 8)
        cx = (x0 + x1) / 2 + right[0] * 2 * peak  # control point sits at twice the peak
        cy = (y0 + y1) / 2 + right[1] * 2 * peak

        xs, ys = [], []
        for i in range(CURVE_POINTS):
            t = i / (CURVE_POINTS - 1)
            a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t ** 2
            xs.append((a * x0 + b * cx + c * x1) / PX_X)
            ys.append((a * y0 + b * cy + c * y1) / PX_Y)
        return xs, ys

    def interactive_draw(self):
        pos = self.layout()
        fig = go.Figure()

        # One trace per edge so the click script can recolor each edge on its own.
        # The arrow marker sits in the middle and points along the curve.
        arrow_sizes = [0] * CURVE_POINTS
        arrow_sizes[CURVE_POINTS // 2] = ARROW_SIZE
        for source, target, data in self.G.edges(data=True):
            xs, ys = self.curve(pos[source], pos[target])
            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="lines+markers",
                line=dict(width=1, color=EDGE_COLOR),
                marker=dict(symbol="arrow", size=arrow_sizes, angleref="previous",
                            color=EDGE_COLOR),
                hovertemplate=(f"{source} → {target}<br>{data['rel']}: {data['reason']}"
                               "<extra></extra>"),
            ))

        # Nodes go last so they draw on top of the edges
        nodes = list(self.G.nodes(data=True))
        fig.add_trace(go.Scatter(
            x=[pos[n][0] for n, _ in nodes],
            y=[pos[n][1] for n, _ in nodes],
            mode="markers+text",
            text=[n for n, _ in nodes],
            textposition="top center",
            textfont=dict(size=10),
            customdata=[n for n, _ in nodes],
            hovertext=[f"{d['name']} ({d['type']})" for _, d in nodes],
            hovertemplate="%{hovertext}<extra></extra>",
            marker=dict(size=18, color=[COLORS.get(d['type'], CYBER_COLOR) for _, d in nodes],
                        line=dict(width=1, color="white")),
        ))

        fig.update_layout(
            title="Platform asset graph (click a node for details)",
            showlegend=False,
            hovermode="closest",
            plot_bgcolor="white",
            margin=dict(l=20, r=380, t=60, b=20),  # right margin leaves room for the info panel
            xaxis=dict(visible=False),
            yaxis=dict(visible=False, range=[-1.2, 11.6]),
            height=900,
        )
        return fig

    def _click_script(self):
        """JavaScript added to the HTML page: node selection, edge colors, info panel."""
        nodes = {n: d for n, d in self.G.nodes(data=True)}
        edges = [[s, t, d['rel'], d['reason']] for s, t, d in self.G.edges(data=True)]
        meta = {
            "nodes": nodes, "edges": edges,
            "colors": {"edge": EDGE_COLOR, "faded": EDGE_FADED, "in": IN_COLOR, "out": OUT_COLOR},
        }
        script = (Path(__file__).parent / "graph_click.js").read_text(encoding="utf-8")
        # plotly replaces {plot_id} with the div id of the figure
        return "const META = " + json.dumps(meta) + ";\n" + script

    def save_html(self, path="runs/asset_graph.html"):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig = self.interactive_draw()
        fig.write_html(path, include_plotlyjs=True, post_script=self._click_script(),
                       config={"displaylogo": False, "responsive": True})
        return path

    def show_interactive(self, path="runs/asset_graph.html"):
        path = self.save_html(path)
        webbrowser.open(path.resolve().as_uri())
        return path
