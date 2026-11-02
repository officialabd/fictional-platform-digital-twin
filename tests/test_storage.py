import sqlite3

from shared.messages import Reading
from simulator.storage import Historian, TruthLog


def test_historian_returns_rows_in_order_after_a_given_id(tmp_path):
    historian = Historian(tmp_path)
    historian.store(0.0, {"PT201": 20.0, "LT201": 50.0})
    historian.store(1.0, {"PT201": 20.1})

    assert historian.rows_after(1, limit=10) == [
        (2, Reading("LT201", 0.0, 50.0)),
        (3, Reading("PT201", 1.0, 20.1)),
    ]
    assert len(historian.rows_after(0, limit=2)) == 2
    assert historian.last_row_id() == 3
    historian.close()


def test_empty_historian_has_last_row_id_zero(tmp_path):
    historian = Historian(tmp_path)
    assert historian.last_row_id() == 0
    historian.close()


def test_truth_goes_to_its_own_file_and_never_to_the_historian(tmp_path):
    historian = Historian(tmp_path)
    truth = TruthLog(tmp_path)
    historian.store(5.0, {"PT201": 19.0})
    truth.record(5.0, {"PT201": 25.0}, [("trip", "PT201_high")])
    historian.close()
    truth.close()

    sim_db = sqlite3.connect(tmp_path / "sim.db")
    truth_db = sqlite3.connect(tmp_path / "truth.db")
    assert sim_db.execute("SELECT value FROM readings").fetchall() == [(19.0,)]
    assert truth_db.execute("SELECT * FROM truth").fetchall() == [("PT201", 5.0, 25.0)]
    assert truth_db.execute("SELECT * FROM events").fetchall() == [(5.0, "trip", "PT201_high")]
    sim_db.close()
    truth_db.close()
