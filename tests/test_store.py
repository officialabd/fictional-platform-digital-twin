"""twin.db: duplicates, out of order resends, gaps, read only access."""

import sqlite3

import pytest

from shared.messages import Reading
from twin.store import TwinStore
from twin.sync import parse


@pytest.fixture
def store(tmp_path):
    s = TwinStore(tmp_path / "twin.db")
    yield s
    s.close()


def test_duplicate_reading_is_dropped(store):
    assert store.add_reading(Reading("PT201", 5.0, 20.1), received_at=100.0)
    assert not store.add_reading(Reading("PT201", 5.0, 20.1), received_at=200.0)
    assert store.latest()["PT201"].received_at == 100.0


def test_latest_is_the_highest_ts_not_the_last_to_arrive(store):
    store.add_reading(Reading("PT201", 10.0, 21.0), received_at=100.0)
    store.add_reading(Reading("PT201", 4.0, 19.0), received_at=101.0)  # late resend
    latest = store.latest()["PT201"]
    assert (latest.ts, latest.value) == (10.0, 21.0)
    assert latest.age(now=106.0) == 5.0  # any new reading counts as fresh


def test_gaps_count_missing_ticks(store):
    for ts in (1, 2, 3, 7, 8):
        store.add_reading(Reading("LT201", float(ts), 50.0), received_at=0.0)
    assert store.gaps() == {"LT201": 3}
    for ts in (4, 5, 6):  # backfill after the link comes back
        store.add_reading(Reading("LT201", float(ts), 50.0), received_at=1.0)
    assert store.gaps() == {"LT201": 0}


def test_flags_and_hypotheses_open_and_close(store):
    flag = store.open_flag("PT201", "range", "warning", "above 22", ts=5.0, wall=1.0)
    hyp = store.open_hypothesis("PT201", "wrong_readings", "flare", "medium", {"a": 1}, 5.0, 1.0)
    assert len(store.flags()) == 1 and store.hypotheses()[0]["impact"] == {"a": 1}
    store.close_flag(flag, ts=9.0, wall=2.0)
    store.close_hypothesis(hyp, ts=9.0, wall=2.0)
    assert store.flags() == [] and store.hypotheses() == []
    assert len(store.flags(active_only=False)) == 1


def test_read_only_store_cannot_write(store, tmp_path):
    store.add_reading(Reading("PT201", 1.0, 20.0), received_at=0.0)
    store.commit()
    reader = TwinStore(tmp_path / "twin.db", read_only=True)
    assert "PT201" in reader.latest()
    with pytest.raises(sqlite3.OperationalError):
        reader.add_reading(Reading("PT201", 2.0, 20.0), received_at=0.0)
    reader.close()


def test_bad_payload_is_skipped():
    assert parse(b"garbage") is None
    assert parse(b'{"tag": "PT201", "ts": 1.0, "value": 20.0}') == Reading("PT201", 1.0, 20.0)


def test_recorder_stores_a_suspected_failure_with_its_impact(store):
    from twin.impact import Mode
    from twin.model import load_graph
    from twin.monitoring import Event
    from twin.service import Recorder

    recorder = Recorder(load_graph(), store)
    recorder.apply([Event("flag_open", "PT201", 151.0, "valve_vs_pressure", "alarm", "x"),
                    Event("hyp_open", "PT201", 151.0, mode=Mode.WRONG_READINGS,
                          evidence="PT201 valve_vs_pressure", confidence="medium")], wall=1.0)
    hyp = store.hypotheses()[0]
    assert hyp["mode"] == "wrong_readings"
    assert any(i["node"] == "Compressor" for i in hyp["impact"]["impacts"])
    recorder.apply([Event("flag_close", "PT201", 300.0, "valve_vs_pressure"),
                    Event("hyp_close", "PT201", 300.0, mode=Mode.WRONG_READINGS)], wall=2.0)
    assert store.flags() == [] and store.hypotheses() == []
