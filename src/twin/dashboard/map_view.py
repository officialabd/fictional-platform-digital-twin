"""Map view: the platform, the onshore control room, and the satellite link between them.

Both locations are made up (twin config). The link color is what the twin knows about its data:
fresh, lost, or nothing received yet.
"""

import plotly.graph_objects as go

from twin import config
from twin.dashboard.status import COLORS, Snapshot

LINK_COLORS = {"fresh": COLORS["ok"], "lost": COLORS["alarm"], "none": COLORS["no_data"]}
LINK_TEXT = {"fresh": "data arriving", "lost": "no data", "none": "nothing received yet"}


def map_figure(snap: Snapshot) -> go.Figure:
    (plat_lat, plat_lon), (shore_lat, shore_lon) = config.MAP_PLATFORM, config.MAP_ONSHORE
    age = snap.last_data_age
    age_text = "never" if age is None else f"{age:.0f} s ago"
    alarms = sum(f["severity"] == "alarm" for f in snap.flags)
    warnings = sum(f["severity"] == "warning" for f in snap.flags)
    link = snap.link

    fig = go.Figure()
    fig.add_trace(go.Scattermap(
        lat=[plat_lat, shore_lat], lon=[plat_lon, shore_lon], mode="lines",
        line=dict(width=4, color=LINK_COLORS[link]),
        hovertext=f"Satellite link: {LINK_TEXT[link]}", hoverinfo="text", name="Satellite link",
    ))
    fig.add_trace(go.Scattermap(
        lat=[plat_lat], lon=[plat_lon], mode="markers+text",
        marker=dict(size=18, color=COLORS["alarm"] if alarms else COLORS["ok"]),
        text=["Platform (fictional)"], textposition="bottom right",
        hovertext=(f"Platform<br>alarms: {alarms}, warnings: {warnings}"
                   f"<br>newest reading: {age_text}"),
        hoverinfo="text", name="Platform",
    ))
    fig.add_trace(go.Scattermap(
        lat=[shore_lat], lon=[shore_lon], mode="markers+text",
        marker=dict(size=14, color=COLORS["info"]),
        text=["Onshore control room and twin (fictional)"], textposition="top right",
        hovertext="Onshore: digital twin and dashboard", hoverinfo="text", name="Onshore",
    ))
    fig.update_layout(
        map=dict(style="carto-positron", zoom=5,
                 center=dict(lat=(plat_lat + shore_lat) / 2, lon=(plat_lon + shore_lon) / 2)),
        margin=dict(l=0, r=0, t=0, b=0), height=520, showlegend=False,
    )
    return fig
