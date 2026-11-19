import json
import webbrowser
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import plotly.graph_objects as go
from matplotlib.lines import Line2D

from twin.edge_router import route_edges

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
ARROW_SIZE = 12
NODE_HOVER_RADIUS = 22  # pixels around a node where edges give up hover and clicks
# Assumed pixels per x unit (about 1500 px of plot width on a 1920 px screen).
# The router uses it to space ports, lanes and hover points. y is in real pixels.
PX_X = 50
X_RANGE = (-0.5, LAYOUT_WIDTH + 0.5)


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
            slots = width[eq]
            sensors, actuators = field[eq]['sensor'], field[eq]['actuator']
            pos[eq] = (left + slots * scale / 2, 0)
            # Sensors sit in slot centres. Actuators sit on the gaps between sensors,
            # so vertical edges through either row pass between nodes, not through them.
            first = (slots - len(sensors)) / 2
            for i, n in enumerate(sensors):
                pos[n] = (left + (first + i + 0.5) * scale, 2)
            gaps = len(sensors) - 1
            if 0 < len(actuators) <= gaps:
                picks = [first + 1 + round((j + 0.5) * gaps / len(actuators) - 0.5)
                         for j in range(len(actuators))]
            else:
                picks = [(j + 0.5) * slots / len(actuators) for j in range(len(actuators))]
            for n, p in zip(actuators, picks, strict=True):
                pos[n] = (left + p * scale, 1)
            left += slots * scale

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

    def interactive_draw(self):
        node_xy, paths, plot_height = route_edges(self.G, self.layout(), PX_X)
        fig = go.Figure()

        # One trace per edge so the click script can recolor each edge on its own.
        # The arrow marker sits in the middle of the longest segment.
        # These traces never take hover or clicks; the hover traces below do that.
        hover_points = {}  # rel -> (xs, ys, texts, colors)
        for (source, target, data), (pts, arrow_at) in zip(
                self.G.edges(data=True), paths, strict=True):
            sizes = [0] * len(pts)
            sizes[arrow_at] = ARROW_SIZE
            fig.add_trace(go.Scatter(
                x=[p[0] for p in pts], y=[p[1] for p in pts],
                mode="lines+markers",
                line=dict(width=1, color=EDGE_COLOR),
                marker=dict(symbol="arrow", size=sizes, angleref="previous", color=EDGE_COLOR),
                hoverinfo="skip",
            ))
            # Hover points every few pixels along the path, except near nodes, so
            # that near a node the node is the only thing that can be hovered or clicked
            text = f"{source} → {target}<br>{data['rel']}: {data['reason']}"
            color = COLORS.get(self.G.nodes[source]['type'], CYBER_COLOR)  # tooltip = source color
            hx, hy, ht, hc = hover_points.setdefault(data['rel'], ([], [], [], []))
            for x, y in self._sample(pts):
                if all(((x - nx_) * PX_X) ** 2 + (y - ny_) ** 2 > NODE_HOVER_RADIUS ** 2
                       for nx_, ny_ in node_xy.values()):
                    hx.append(x)
                    hy.append(y)
                    ht.append(text)
                    hc.append(color)

        # Invisible hover points, one trace per edge type so the filter can hide them
        for rel, (hx, hy, ht, hc) in sorted(hover_points.items()):
            fig.add_trace(go.Scatter(
                x=hx, y=hy, mode="markers", name=rel, meta="edge-hover",
                marker=dict(size=6, opacity=0),
                hovertext=ht, hovertemplate="%{hovertext}<extra></extra>",
                hoverlabel=dict(bgcolor=hc, bordercolor="white", font=dict(color="white")),
            ))

        # Nodes go last so they draw on top of the edges
        nodes = list(self.G.nodes(data=True))
        fig.add_trace(go.Scatter(
            x=[node_xy[n][0] for n, _ in nodes],
            y=[node_xy[n][1] for n, _ in nodes],
            mode="markers",
            customdata=[n for n, _ in nodes],
            hovertext=[f"{d['name']} ({d['type']})" for _, d in nodes],
            hovertemplate="%{hovertext}<extra></extra>",
            marker=dict(size=18, color=[COLORS.get(d['type'], CYBER_COLOR) for _, d in nodes],
                        line=dict(width=1, color="white")),
        ))

        # Labels are annotations with a white background, so lines that pass
        # behind a label stop at it instead of running through the text
        for n, _ in nodes:
            fig.add_annotation(
                x=node_xy[n][0], y=node_xy[n][1], yshift=15, text=n, showarrow=False,
                font=dict(size=9, color="#333"), bgcolor="rgba(255,255,255,0.9)", borderpad=1,
            )

        margin = dict(l=20, r=380, t=60, b=20)  # right margin leaves room for the info panel
        fig.update_layout(
            title="Platform asset graph (click a node for details)",
            showlegend=False,
            hovermode="closest",
            plot_bgcolor="white",
            margin=margin,
            xaxis=dict(visible=False, range=list(X_RANGE)),
            # y is in pixels: the router sized every gap to fit its tracks
            yaxis=dict(visible=False, range=[0, plot_height]),
            height=round(plot_height) + margin["t"] + margin["b"],
        )
        return fig

    @staticmethod
    def _sample(pts, step_px=6):
        """Points every step_px pixels along a polyline (x in layout units, y in px)."""
        out = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
            length = ((x1 - x0) * PX_X) ** 2 + (y1 - y0) ** 2
            k = max(int(length ** 0.5 // step_px), 1)
            out.extend((x0 + (x1 - x0) * i / k, y0 + (y1 - y0) * i / k) for i in range(k))
        out.append(pts[-1])
        return out

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
