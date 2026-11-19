"""Twin dashboard. Reads twin.db only: no broker, no simulator, no scenario controls.

Run: streamlit run src/twin/dashboard/app.py
"""

import copy

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from twin import config
from twin.dashboard.map_view import map_figure
from twin.dashboard.status import COLORS, LABELS, Snapshot, runs, snapshot
from twin.graph_visualizer import GraphVisualizer
from twin.impact import DAMAGE, Effect, Impact, ImpactResult, Mode, analyze, modes_for
from twin.model import load_graph, tags
from twin.store import TwinStore, run_db

RING = {"damage": COLORS["alarm"], "reach": "#7b3fe4", "visibility": "#555b66"}

st.set_page_config(page_title="Platform Twin", layout="wide")


@st.cache_resource
def graph():
    return load_graph()


@st.cache_resource
def base_figure():
    """Routing the edges is slow, so the figure is built once and only recolored."""
    return GraphVisualizer(graph()).interactive_draw(title=" ", panel=False)


def label(mode: str) -> str:
    return str(mode).replace("_", " ")


# Sidebar


G = graph()
st.sidebar.title("Platform twin")
run_ids = runs()
if not run_ids:
    st.info("No twin runs yet. Start the twin service first: "
            "`python -m twin.service --run-id <id>`")
    st.stop()
run_id = st.sidebar.selectbox("Run", run_ids)
auto = st.sidebar.toggle("Live refresh (1 s)", value=True)
firewall_holds = st.sidebar.toggle("What-if: firewall holds", value=True,
                                   help="The twin cannot know this. Set it to the case you "
                                        "want to explore.")
st.sidebar.caption("Node colors")
for key in COLORS:
    st.sidebar.markdown(f"<span style='color:{COLORS[key]}'>&#9679;</span> {LABELS[key]}",
                        unsafe_allow_html=True)
st.sidebar.caption("Rings (what-if)")
for key, color in RING.items():
    st.sidebar.markdown(f"<span style='color:{color}'>&#9675;</span> {key}",
                        unsafe_allow_html=True)


# Views


def header(snap: Snapshot) -> None:
    age = snap.last_data_age
    cols = st.columns(5)
    cols[0].metric("Simulated time", "-" if snap.sim_ts is None else f"{snap.sim_ts:.0f} s")
    cols[1].metric("Newest reading", "-" if age is None else f"{age:.0f} s ago")
    cols[2].metric("Alarms", sum(f["severity"] == "alarm" for f in snap.flags))
    cols[3].metric("Warnings", sum(f["severity"] == "warning" for f in snap.flags))
    cols[4].metric("Suspected failures", len(snap.hypotheses))
    missing = sum(snap.gaps.values())
    if snap.link == "lost":
        st.error(f"No data for {age:.0f} s. Values below are the last received. "
                 "No data does not mean the platform stopped.")
    elif missing:
        st.warning(f"{missing} readings still missing. The twin is filling the gap.")
    elif snap.link == "none":
        st.info("Waiting for the first reading. Is the simulator running with this run id?")


def impact_rows(result: ImpactResult, group: list) -> pd.DataFrame:
    return pd.DataFrame([{
        "node": i.node, "effect": label(i.effect), "rule": i.rule, "via": i.source,
        "detail": i.detail, "path": " > ".join(result.path_to(i.node)),
    } for i in group])


def show_impact(result: ImpactResult) -> None:
    for name, group in (("Damage", result.damage), ("Visibility", result.visibility),
                        ("Reach", result.reach)):
        if group:
            st.markdown(f"**{name}** ({len(group)})")
            st.dataframe(impact_rows(result, group), hide_index=True, width="stretch")
    if not result.impacts:
        st.write("Nothing else is affected by the rules.")


def from_dict(d: dict) -> ImpactResult:
    return ImpactResult(d["start"], Mode(d["mode"]), d["firewall_holds"],
                        [Impact(i["node"], Effect(i["effect"]), i["rule"], i["source"],
                                i["detail"]) for i in d["impacts"]])


def overview(snap: Snapshot) -> None:
    st.subheader("Suspected failures")
    if not snap.hypotheses:
        st.write("None.")
    for h in snap.hypotheses:
        result = from_dict(h["impact"])
        st.markdown(f"- **{h['node']}: {label(h['mode'])}** ({h['confidence']} confidence, "
                    f"since t={h['since_ts']:.0f} s). Evidence: {h['evidence']}. "
                    f"Affects {len(result.nodes(DAMAGE))} nodes, "
                    f"hides {len(result.visibility)} from view.")
    st.subheader("Active flags")
    if snap.flags:
        st.dataframe(pd.DataFrame([{
            "severity": f["severity"], "node": f["node"], "check": f["check_name"],
            "detail": f["detail"], "since (s)": f["since_ts"],
        } for f in snap.flags]), hide_index=True, width="stretch")
    else:
        st.write("None.")


def what_if_result(node: str) -> ImpactResult | None:
    modes = modes_for(G.nodes[node]["type"])
    if not modes:
        return None
    mode = st.radio("Failure mode", modes, format_func=label, horizontal=True,
                    key=f"mode_{node}")
    return analyze(G, node, Mode(mode), firewall_holds)


def graph_view(snap: Snapshot) -> None:
    nodes = list(G.nodes)
    left, right = st.columns([3, 1])
    with right:
        st.markdown("**What if...**  \nClick a node on the graph, or pick one here.")
        # A graph click is applied here, before the selectbox exists in this run
        if "clicked_node" in st.session_state:
            st.session_state.whatif_node = st.session_state.pop("clicked_node")
        st.session_state.setdefault("whatif_node", "PT201")
        node = st.selectbox("Node", nodes, key="whatif_node")
        result = what_if_result(node)
    rings = {node: "#000000"}
    if result is not None:
        for i in result.visibility:
            rings[i.node] = RING["visibility"]
        for i in result.reach:
            rings[i.node] = RING["reach"]
        for i in result.damage:
            rings[i.node] = RING["damage"]

    fig = copy.deepcopy(base_figure())
    trace = fig.data[-1]  # the node trace is drawn last
    trace.marker.color = [COLORS[snap.node_status.get(n, "no_data")] for n in nodes]
    trace.marker.line.width = [4 if n in rings else 1 for n in nodes]
    trace.marker.line.color = [rings.get(n, "white") for n in nodes]
    with left:
        event = st.plotly_chart(fig, key="graph", on_select="rerun", selection_mode="points",
                                theme=None, config={"displaylogo": False})
    points = [p for p in event.selection.points if p.get("curve_number") == len(fig.data) - 1]
    if points:
        clicked = nodes[points[0]["point_index"]]
        if clicked != st.session_state.get("last_click"):
            st.session_state.last_click = clicked
            st.session_state.clicked_node = clicked
            st.rerun(scope="fragment")
    if result is not None:
        with right:
            st.caption(f"{label(result.mode)} on {node}, firewall "
                       f"{'holds' if firewall_holds else 'does not hold'}")
        st.subheader(f"What if {node} is {label(result.mode)}")
        show_impact(result)


def sensors_view(snap: Snapshot) -> None:
    rows = []
    for tag in tags(G):
        d, item = G.nodes[tag], snap.latest.get(tag)
        lo, hi = d.get("normal_min"), d.get("normal_max")
        rows.append({
            "tag": tag, "name": d["name"],
            "value": None if item is None else item.value, "unit": d.get("unit"),
            "normal": "" if lo is None else f"{lo:g} to {hi:g}",
            "status": LABELS[snap.tag_status(tag)],
            "age (s)": None if item is None else round(item.age(snap.now), 1),
            "missing": snap.gaps.get(tag, 0),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=420)

    picked = st.multiselect("Trends", tags(G), default=["PT201", "PV201", "FT701"],
                            key="trend_tags")
    window = st.slider("Window (simulated seconds)", 60, 3600, 600, step=60, key="window")
    if not picked or snap.sim_ts is None:
        return
    store = TwinStore(run_db(run_id), read_only=True)
    try:
        data = store.history(picked, since_ts=snap.sim_ts - window)
    finally:
        store.close()
    frame = pd.DataFrame([dict(r) for r in data])
    cols = st.columns(2)
    for k, tag in enumerate(picked):
        d = G.nodes[tag]
        fig = go.Figure()
        if d.get("normal_min") is not None:
            fig.add_hrect(y0=d["normal_min"], y1=d["normal_max"], fillcolor=COLORS["ok"],
                          opacity=0.12, line_width=0)
        part = frame[frame["tag"] == tag] if not frame.empty else frame
        if not part.empty:
            fig.add_trace(go.Scatter(x=part["ts"], y=part["value"], mode="lines",
                                     line=dict(color="#2a78d6", width=1.5)))
        fig.update_layout(title=f"{tag} ({d.get('unit') or ''})", height=260,
                          margin=dict(l=10, r=10, t=40, b=10), xaxis_title="t (s)")
        cols[k % 2].plotly_chart(fig, key=f"trend_{tag}")


def impact_view(snap: Snapshot) -> None:
    st.subheader("Detected (from monitoring)")
    st.caption("The twin assumes the firewall holds for detected failures.")
    if not snap.hypotheses:
        st.write("Nothing suspected right now.")
    for h in snap.hypotheses:
        with st.expander(f"{h['node']}: {label(h['mode'])} ({h['confidence']})", expanded=True):
            st.write(f"Evidence: {h['evidence']}")
            show_impact(from_dict(h["impact"]))


@st.fragment(run_every=1 if auto else None)
def live() -> None:
    snap = snapshot(run_db(run_id), G)
    header(snap)
    tabs = st.tabs(["Overview", "Graph", "Sensors", "Impact", "Map"])
    with tabs[0]:
        overview(snap)
    with tabs[1]:
        graph_view(snap)
    with tabs[2]:
        sensors_view(snap)
    with tabs[3]:
        impact_view(snap)
    with tabs[4]:
        st.caption(f"Both locations are fictional. Link is "
                   f"{'up' if snap.link == 'fresh' else 'down or unknown'} as far as the twin "
                   f"can tell (stale after {config.STALE_S:g} s).")
        st.plotly_chart(map_figure(snap), key="map", config={"displaylogo": False})


live()
