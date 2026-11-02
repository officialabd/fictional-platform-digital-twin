"""The two databases of a run, kept in separate files so they can never be mixed up.

sim.db plays the platform historian: reported readings only, which is what gets sent to shore.
truth.db is the truth log: true values and events, used only in the Week 10 validation.
The twin must never open either of them.
"""

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from shared.messages import Reading


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    # A commit every tick needs to be cheap. A lost run can simply be run again.
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


class Historian:
    def __init__(self, run_dir: Path) -> None:
        self.db = _connect(run_dir / "sim.db")
        self.db.execute(
            "CREATE TABLE readings (id INTEGER PRIMARY KEY, tag TEXT, ts REAL, value REAL)"
        )

    def store(self, ts: float, readings: dict[str, float]) -> None:
        self.db.executemany(
            "INSERT INTO readings (tag, ts, value) VALUES (?, ?, ?)",
            [(tag, ts, value) for tag, value in readings.items()],
        )
        self.db.commit()

    def rows_after(self, row_id: int, limit: int) -> list[tuple[int, Reading]]:
        rows = self.db.execute(
            "SELECT id, tag, ts, value FROM readings WHERE id > ? ORDER BY id LIMIT ?",
            (row_id, limit),
        ).fetchall()
        return [(row[0], Reading(row[1], row[2], row[3])) for row in rows]

    def last_row_id(self) -> int:
        return self.db.execute("SELECT COALESCE(MAX(id), 0) FROM readings").fetchone()[0]

    def close(self) -> None:
        self.db.close()


class TruthLog:
    def __init__(self, run_dir: Path) -> None:
        self.db = _connect(run_dir / "truth.db")
        self.db.executescript("""
            CREATE TABLE truth (tag TEXT, ts REAL, value REAL);
            CREATE TABLE events (ts REAL, kind TEXT, detail TEXT);
        """)

    def record(self, ts: float, true: dict[str, float], events: Iterable[tuple[str, str]]) -> None:
        self.db.executemany(
            "INSERT INTO truth VALUES (?, ?, ?)",
            [(tag, ts, value) for tag, value in true.items()],
        )
        self.db.executemany(
            "INSERT INTO events VALUES (?, ?, ?)",
            [(ts, kind, detail) for kind, detail in events],
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
