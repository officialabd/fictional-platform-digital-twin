import csv
from pathlib import Path

import pytest

NODES_CSV = Path(__file__).resolve().parents[1] / "data" / "nodes.csv"


@pytest.fixture(scope="session")
def node_rows() -> dict[str, dict]:
    """The graph's nodes. Only tests compare against these, the simulator never reads them."""
    with open(NODES_CSV, newline="", encoding="utf-8-sig") as f:
        return {row["id"]: row for row in csv.DictReader(f)}
