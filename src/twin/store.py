"""twin.db: everything the twin received and concluded. This is the twin log for Week 10.

Only the twin service writes. The dashboard opens it read only.
"""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from shared.messages import Reading

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs" / "twin"
DB_NAME = "twin.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    tag TEXT NOT NULL, ts REAL NOT NULL, value REAL NOT NULL, received_at REAL NOT NULL,
    PRIMARY KEY (tag, ts)
);
CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY, node TEXT NOT NULL, check_name TEXT NOT NULL,
    severity TEXT NOT NULL, detail TEXT NOT NULL,
    since_ts REAL, since_wall REAL NOT NULL, cleared_ts REAL, cleared_wall REAL
);
CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY, node TEXT NOT NULL, mode TEXT NOT NULL, evidence TEXT NOT NULL,
    confidence TEXT NOT NULL, impact TEXT NOT NULL,
    since_ts REAL, since_wall REAL NOT NULL, cleared_ts REAL, cleared_wall REAL
);
"""


@dataclass(frozen=True)
class Latest:
    tag: str
    ts: float  # highest simulated ts received
    value: float  # value at that ts
    received_at: float  # wall time a new reading of this tag last arrived

    def age(self, now: float) -> float:
        return now - self.received_at


def run_db(run_id: str) -> Path:
    return RUNS_DIR / run_id / DB_NAME


class TwinStore:
    def __init__(self, path: Path, read_only: bool = False) -> None:
        self.path = Path(path)
        if read_only:
            self.db = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True,
                                      check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path)
            self.db.execute("PRAGMA journal_mode=WAL")  # the dashboard reads while we write
            self.db.executescript(SCHEMA)
        self.db.row_factory = sqlite3.Row

    def close(self) -> None:
        self.db.close()

    def commit(self) -> None:
        self.db.commit()

    # Readings

    def add_reading(self, reading: Reading, received_at: float) -> bool:
        """False when the reading is a duplicate (a resend after a link loss)."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO readings VALUES (?, ?, ?, ?)",
            (reading.tag, reading.ts, reading.value, received_at),
        )
        return cur.rowcount == 1

    def latest(self) -> dict[str, Latest]:
        rows = self.db.execute("""
            SELECT r.tag, r.ts, r.value, m.received_at FROM readings r
            JOIN (SELECT tag, MAX(ts) AS ts, MAX(received_at) AS received_at
                  FROM readings GROUP BY tag) m ON r.tag = m.tag AND r.ts = m.ts
        """).fetchall()
        return {r["tag"]: Latest(r["tag"], r["ts"], r["value"], r["received_at"]) for r in rows}

    def history(self, tags: list[str], since_ts: float = 0.0) -> list[sqlite3.Row]:
        marks = ",".join("?" * len(tags))
        return self.db.execute(
            f"SELECT tag, ts, value FROM readings WHERE tag IN ({marks}) AND ts >= ? "
            "ORDER BY ts", (*tags, since_ts),
        ).fetchall()

    def gaps(self, tick_s: float = 1.0) -> dict[str, int]:
        """Missing readings per tag between its first and latest ts."""
        rows = self.db.execute(
            "SELECT tag, MIN(ts) AS lo, MAX(ts) AS hi, COUNT(*) AS n FROM readings GROUP BY tag"
        ).fetchall()
        return {r["tag"]: round((r["hi"] - r["lo"]) / tick_s) + 1 - r["n"] for r in rows}

    def max_ts(self) -> float | None:
        return self.db.execute("SELECT MAX(ts) FROM readings").fetchone()[0]

    # Flags and hypotheses

    def open_flag(self, node, check, severity, detail, ts, wall) -> int:
        cur = self.db.execute(
            "INSERT INTO flags (node, check_name, severity, detail, since_ts, since_wall) "
            "VALUES (?, ?, ?, ?, ?, ?)", (node, check, severity, detail, ts, wall))
        return cur.lastrowid

    def close_flag(self, flag_id: int, ts, wall) -> None:
        self.db.execute("UPDATE flags SET cleared_ts = ?, cleared_wall = ? WHERE id = ?",
                        (ts, wall, flag_id))

    def open_hypothesis(self, node, mode, evidence, confidence, impact: dict, ts, wall) -> int:
        cur = self.db.execute(
            "INSERT INTO hypotheses (node, mode, evidence, confidence, impact, since_ts, "
            "since_wall) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (node, mode, evidence, confidence, json.dumps(impact), ts, wall))
        return cur.lastrowid

    def update_hypothesis(self, hyp_id: int, evidence: str, confidence: str) -> None:
        self.db.execute("UPDATE hypotheses SET evidence = ?, confidence = ? WHERE id = ?",
                        (evidence, confidence, hyp_id))

    def close_hypothesis(self, hyp_id: int, ts, wall) -> None:
        self.db.execute("UPDATE hypotheses SET cleared_ts = ?, cleared_wall = ? WHERE id = ?",
                        (ts, wall, hyp_id))

    def flags(self, active_only: bool = True) -> list[dict]:
        where = "WHERE cleared_wall IS NULL" if active_only else ""
        rows = self.db.execute(f"SELECT * FROM flags {where} ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def hypotheses(self, active_only: bool = True) -> list[dict]:
        where = "WHERE cleared_wall IS NULL" if active_only else ""
        rows = self.db.execute(f"SELECT * FROM hypotheses {where} ORDER BY id DESC").fetchall()
        return [dict(r) | {"impact": json.loads(r["impact"])} for r in rows]
