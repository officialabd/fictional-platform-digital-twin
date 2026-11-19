"""What the dashboard shows, read from twin.db. No Streamlit here, so it can be tested."""

import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from twin import config
from twin.model import tags
from twin.store import DB_NAME, RUNS_DIR, Latest, TwinStore

# Worst first. A node shows the worst status it has.
ORDER = ["alarm", "warning", "impacted", "stale", "info", "ok", "no_data"]
COLORS = {
    "alarm": "#d64545",
    "warning": "#e3a21a",
    "impacted": "#9b59b6",
    "stale": "#8a8f98",
    "info": "#3b82c4",
    "ok": "#2e9d5b",
    "no_data": "#c9ccd1",
}
LABELS = {
    "alarm": "Alarm",
    "warning": "Warning",
    "impacted": "Suspected impact",
    "stale": "Stale data",
    "info": "Info",
    "ok": "Normal",
    "no_data": "No data / not measured",
}


def runs() -> list[str]:
    """Run ids that have a twin.db, newest first."""
    if not RUNS_DIR.exists():
        return []
    found = [p for p in RUNS_DIR.iterdir() if (p / DB_NAME).exists()]
    return [p.name for p in sorted(found, key=lambda p: (p / DB_NAME).stat().st_mtime,
                                   reverse=True)]


def worst(statuses) -> str:
    return min(statuses, key=ORDER.index, default="no_data")


@dataclass
class Snapshot:
    now: float
    latest: dict[str, Latest]
    gaps: dict[str, int]
    flags: list[dict]
    hypotheses: list[dict]
    sim_ts: float | None
    node_status: dict[str, str] = field(default_factory=dict)

    @property
    def last_data_age(self) -> float | None:
        if not self.latest:
            return None
        return self.now - max(item.received_at for item in self.latest.values())

    @property
    def link(self) -> str:
        """fresh, lost, or none (nothing received yet)."""
        age = self.last_data_age
        if age is None:
            return "none"
        return "fresh" if age <= config.STALE_S else "lost"

    def tag_status(self, tag: str) -> str:
        return self.node_status.get(tag, "no_data")


def snapshot(path: Path, G: nx.DiGraph, now: float | None = None) -> Snapshot:
    store = TwinStore(path, read_only=True)
    try:
        snap = Snapshot(now or time.time(), store.latest(), store.gaps(config.TICK_S),
                        store.flags(), store.hypotheses(), store.max_ts())
    finally:
        store.close()
    snap.node_status = node_status(G, snap)
    return snap


def node_status(G: nx.DiGraph, snap: Snapshot) -> dict[str, str]:
    found: dict[str, set[str]] = {n: set() for n in G}
    for tag in tags(G):
        item = snap.latest.get(tag)
        if item is None:
            continue
        found[tag].add("stale" if item.age(snap.now) > config.STALE_S else "ok")
    for flag in snap.flags:
        if flag["node"] in found:
            found[flag["node"]].add(flag["severity"])
    for hyp in snap.hypotheses:
        for impact in hyp["impact"]["impacts"]:
            if impact["effect"] != "reachable" and impact["node"] in found:
                found[impact["node"]].add("impacted")
        if hyp["node"] in found:
            found[hyp["node"]].add("alarm")
    return {n: worst(s) for n, s in found.items()}
