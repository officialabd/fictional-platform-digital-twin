"""Orthogonal edge routing for the interactive asset graph.

Every edge is drawn with horizontal and vertical segments only.
- Horizontal runs live in the channels (gaps) between rows. Each run gets its own
  track inside its channel, so two edges never lie on top of each other.
- Channel heights grow to fit the tracks they need, so rows move apart where it is busy.
- Where many edges meet one side of a node, they attach at spread out ports and
  fan into the node, instead of all arriving at one point.

Input positions are (x, row) from GraphVisualizer.layout(). Output y values are
in pixels from the bottom of the plot, x stays in layout units.
"""
from dataclasses import dataclass

DEVICE_TYPES = {"sensor", "actuator"}

NODE_R = 9          # node marker radius, px
PORT_PX = 12        # distance between neighbouring ports on one side of a node
TRACK_PX = 8        # distance between neighbouring tracks in a channel
FAN_PX = 14         # ports sit this far above or below the node centre
PAD_NODE = 22       # space between a row's nodes and the first track below them
PAD_LABEL = 34      # space between a row's nodes and the first track above them (labels)
MIN_GAP = 70        # minimum distance between two rows
OUTER_PAD = 12      # space beyond the first and last track in the outer channels
OVERLAP_PX = 5      # runs closer than this horizontally count as overlapping
CLEAR_PX = 18       # a vertical line passing a row keeps this far from its nodes
LANE_PX = 6         # two vertical lines crossing the same rows keep this far apart


@dataclass
class Run:
    """One horizontal segment of an edge, inside one channel."""
    edge: int
    channel: int
    x0: float
    x1: float
    pref: int = 1     # +1: long runs go to the top of the channel, -1: to the bottom
    track: int = 0


@dataclass
class End:
    """Where an edge attaches to a node: which node, top or bottom, heading which way."""
    edge: int
    node: str
    side: int         # +1 top, -1 bottom
    heading: float    # x the edge heads to after leaving the node, used to order ports
    port: float = 0.0


def route_edges(G, pos, px_per_x):
    """Return (node_xy, paths, plot_height_px).

    paths[i] = (points, arrow_index) for the i-th edge of G.edges().
    """
    rows = sorted({r for _, r in pos.values()})
    row_index = {r: i for i, r in enumerate(rows)}
    n = len(rows)
    # Channel k lies below rows[k] and above rows[k-1]. Channel 0 is under the
    # bottom row, channel n is above the top row.
    is_device = {v: d.get("type") in DEVICE_TYPES for v, d in G.nodes(data=True)}
    x = {v: p[0] for v, p in pos.items()}
    r_of = {v: row_index[p[1]] for v, p in pos.items()}
    nodes_in_row = {i: [v for v in pos if r_of[v] == i] for i in range(n)}

    edges = list(G.edges())
    plans = []      # per edge: (src_end, tgt_end, runs, crossing_x or None)
    lanes = []      # vertical lines crossing rows: (x, lowest row crossed, highest row crossed)

    def crossed(a, b):
        lo, hi = sorted((a, b))
        return lo + 1, hi - 1

    # Lanes used by device ends that pass straight through rows
    def free_x(want, row_lo, row_hi):
        step = 2 / px_per_x
        for k in range(600):
            for cand in ((want + k * step), (want - k * step)) if k else (want,):
                if all(abs(cand - x[v]) * px_per_x >= CLEAR_PX
                       for i in range(row_lo, row_hi + 1) for v in nodes_in_row[i]) and \
                   all(abs(cand - lx) * px_per_x >= LANE_PX or hi < row_lo or lo > row_hi
                       for lx, lo, hi in lanes):
                    return cand
        return want

    # ---- 1. decide channels for every edge ----
    for i, (s, t) in enumerate(edges):
        rs, rt = r_of[s], r_of[t]
        if rs == rt:
            ch, side = (0, -1) if rs == 0 else (rs + 1, 1)
            src, tgt = End(i, s, side, x[t]), End(i, t, side, x[s])
            runs = [Run(i, ch, 0, 0, pref=side)]
            plans.append((src, tgt, runs, None))
            continue
        up = rt > rs
        cs = rs + 1 if up else rs          # channel next to the source, facing the target
        ct = rt if up else rt + 1          # channel next to the target, facing the source
        src = End(i, s, 1 if up else -1, x[t])
        tgt = End(i, t, -1 if up else 1, x[s])
        if cs == ct:
            runs = [Run(i, cs, 0, 0)]
            cross = None
        elif is_device[t]:
            # Run next to the source, then straight through the rows into the device
            runs = [Run(i, cs, 0, 0)]
            tgt.heading = x[t]
            cross = None
            lanes.append((x[t], *crossed(rs, rt)))
        elif is_device[s]:
            runs = [Run(i, ct, 0, 0)]
            src.heading = x[s]
            cross = None
            lanes.append((x[s], *crossed(rs, rt)))
        else:
            runs = [Run(i, cs, 0, 0), Run(i, ct, 0, 0)]
            cross = "free"
        plans.append((src, tgt, runs, cross))

    # Free crossing x for hub to hub edges that pass other rows (after device lanes are known)
    for k, (src, tgt, runs, cross) in enumerate(plans):
        if cross == "free":
            lo, hi = crossed(r_of[src.node], r_of[tgt.node])
            cx = free_x(x[tgt.node], lo, hi)
            lanes.append((cx, lo, hi))
            src.heading = tgt.heading = cx
            plans[k] = (src, tgt, runs, cx)

    # ---- 2. ports: spread the ends on each side of a node, ordered by heading ----
    sides = {}
    for src, tgt, _, _ in plans:
        for end in (src, tgt):
            sides.setdefault((end.node, end.side), []).append(end)
    degree = {}
    for (node, side), ends in sides.items():
        # Ties (two way links) are ordered so the same edge is the inner one at both nodes
        ends.sort(key=lambda e: (e.heading, e.edge if e.heading >= x[node] else -e.edge))
        for k, end in enumerate(ends):
            end.port = x[node] + (k - (len(ends) - 1) / 2) * PORT_PX / px_per_x
        degree[(node, side)] = len(ends)

    # ---- 3. run endpoints and track preferences ----
    for src, tgt, runs, cross in plans:
        if len(runs) == 1:
            runs[0].x0, runs[0].x1 = src.port, tgt.port
        else:
            runs[0].x0, runs[0].x1 = src.port, cross
            runs[1].x0, runs[1].x1 = cross, tgt.port
        if src.side == tgt.side:
            continue  # same row: pref already set to "away from the row"
        # Long runs go towards the busier end so short runs nest inside them
        for run in runs:
            ends = [e for e in (src, tgt) if (e is src and run is runs[0]) or
                    (e is tgt and run is runs[-1])]
            upper = lower = 1
            for e in ends:
                # An end attached to the row above this channel uses its bottom side
                if e.side == -1:
                    upper = degree[(e.node, e.side)]
                else:
                    lower = degree[(e.node, e.side)]
            run.pref = 1 if upper >= lower else -1

    # ---- 4. tracks: overlapping runs in one channel never share a track ----
    by_channel = {}
    for _, _, runs, _ in plans:
        for run in runs:
            by_channel.setdefault(run.channel, []).append(run)
    margin = OVERLAP_PX / px_per_x
    n_tracks = {}
    for ch, runs in by_channel.items():
        runs.sort(key=lambda r: r.pref * abs(r.x1 - r.x0))
        placed = []
        for run in runs:
            a, b = sorted((run.x0, run.x1))
            below = [p.track for p in placed
                     if not (b + margin < min(p.x0, p.x1) or a - margin > max(p.x0, p.x1))]
            run.track = max(below) + 1 if below else 0
            placed.append(run)
        n_tracks[ch] = max(r.track for r in runs) + 1

    # ---- 5. channel heights and row y positions ----
    def pads(ch):
        bottom = OUTER_PAD if ch == 0 else PAD_LABEL
        top = OUTER_PAD if ch == n else PAD_NODE
        return bottom, top

    height, first_track = {}, {}
    for ch in range(n + 1):
        bottom, top = pads(ch)
        k = n_tracks.get(ch, 0)
        need = bottom + top + max(k - 1, 0) * TRACK_PX
        if 0 < ch < n:
            need = max(need, MIN_GAP)
        elif k == 0:
            need = bottom + top
        height[ch] = need
        band = max(k - 1, 0) * TRACK_PX
        first_track[ch] = bottom + (need - bottom - top - band) / 2

    row_y, y = {}, 0.0
    channel_y0 = {}
    for ch in range(n + 1):
        channel_y0[ch] = y
        y += height[ch]
        if ch < n:
            row_y[ch] = y
    total_height = y

    def track_y(run):
        return channel_y0[run.channel] + first_track[run.channel] + run.track * TRACK_PX

    node_xy = {v: (x[v], row_y[r_of[v]]) for v in pos}

    # ---- 6. polylines ----
    paths = []
    for src, tgt, runs, _ in plans:
        sx, sy = node_xy[src.node]
        tx, ty = node_xy[tgt.node]
        pts = [(sx, sy), (src.port, sy + src.side * FAN_PX)]
        for run in runs:
            yy = track_y(run)
            pts.append((run.x0, yy))
            pts.append((run.x1, yy))
        pts.append((tgt.port, ty + tgt.side * FAN_PX))
        pts.append((tx, ty))
        pts = _clean(pts)
        paths.append(_with_arrow(pts, px_per_x))
    return node_xy, paths, total_height


def _clean(pts):
    """Drop repeated points."""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    return out


def _with_arrow(pts, px_per_x):
    """Insert a point in the middle of the longest segment for the direction arrow."""
    def seg_len(a, b):
        return ((b[0] - a[0]) * px_per_x) ** 2 + (b[1] - a[1]) ** 2
    k = max(range(len(pts) - 1), key=lambda i: seg_len(pts[i], pts[i + 1]))
    a, b = pts[k], pts[k + 1]
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return pts[:k + 1] + [mid] + pts[k + 1:], k + 1
