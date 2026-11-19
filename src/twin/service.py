"""The twin service: data sync and monitoring, writing everything to twin.db.

Start it before the simulator, with the same run id:
    python -m twin.service --run-id demo2
    python -m simulator.main --run-id demo2 --scenario spoof_pt201 --speed 20 --duration 900
"""

import argparse
import logging
import time

import networkx as nx

from twin.impact import analyze
from twin.model import load_graph
from twin.monitoring import Event, Monitor
from twin.store import TwinStore, run_db
from twin.sync import Subscriber

log = logging.getLogger("twin")

LOOP_S = 0.2
WALL_STEP_S = 1.0


class Recorder:
    """Writes monitoring events to the store. A new hypothesis gets its impact analysis."""

    def __init__(self, G: nx.DiGraph, store: TwinStore) -> None:
        self.G = G
        self.store = store
        self.flag_ids: dict[tuple[str, str], int] = {}
        self.hyp_ids: dict[tuple[str, str], int] = {}

    def apply(self, events: list[Event], wall: float) -> None:
        for e in events:
            if e.kind == "flag_open":
                self.flag_ids[(e.node, e.check)] = self.store.open_flag(
                    e.node, e.check, e.severity, e.detail, e.ts, wall)
                log.info("t=%s flag %s %s: %s", e.ts, e.node, e.check, e.detail)
            elif e.kind == "flag_update":
                self.store.update_flag(self.flag_ids[(e.node, e.check)], e.detail)
            elif e.kind == "flag_close":
                self.store.close_flag(self.flag_ids.pop((e.node, e.check)), e.ts, wall)
            elif e.kind == "hyp_open":
                # The twin cannot know whether the firewall held, so it assumes it did
                impact = analyze(self.G, e.node, e.mode, firewall_holds=True).to_dict()
                self.hyp_ids[(e.node, e.mode)] = self.store.open_hypothesis(
                    e.node, e.mode, e.evidence, e.confidence, impact, e.ts, wall)
                log.info("t=%s suspected %s %s (%s): %s", e.ts, e.node, e.mode, e.confidence,
                         e.evidence)
            elif e.kind == "hyp_update":
                self.store.update_hypothesis(self.hyp_ids[(e.node, e.mode)], e.evidence,
                                             e.confidence)
            elif e.kind == "hyp_close":
                self.store.close_hypothesis(self.hyp_ids.pop((e.node, e.mode)), e.ts, wall)
                log.info("t=%s cleared %s %s", e.ts, e.node, e.mode)


def run(sub: Subscriber, store: TwinStore, monitor: Monitor, recorder: Recorder) -> None:
    last_wall_step = 0.0
    while True:
        events = []
        # Oldest first, so a backfill after a link loss is checked in order
        for reading, at in sorted(sub.drain(), key=lambda item: item[0].ts):
            if store.add_reading(reading, at):  # False for a duplicate
                events += monitor.feed(reading, at)
        now = time.time()
        if now - last_wall_step >= WALL_STEP_S:
            events += monitor.wall_step(now)
            last_wall_step = now
        recorder.apply(events, now)
        store.commit()
        time.sleep(LOOP_S)


def main() -> None:
    parser = argparse.ArgumentParser(description="Twin service: data sync and monitoring")
    parser.add_argument("--run-id", required=True, help="the same id the simulator run uses")
    parser.add_argument("--broker-host", default="localhost")
    parser.add_argument("--broker-port", type=int, default=1883)
    args = parser.parse_args()

    path = run_db(args.run_id)
    if path.exists():
        parser.error(f"{path} already exists, choose another --run-id")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    G = load_graph()
    store = TwinStore(path)
    sub = Subscriber(args.broker_host, args.broker_port, client_id=f"twin-{args.run_id}")
    log.info("twin for run %s, writing %s", args.run_id, path)
    try:
        run(sub, store, Monitor(G), Recorder(G, store))
    except KeyboardInterrupt:
        log.info("stopped")
    finally:
        sub.close()
        store.commit()
        store.close()


if __name__ == "__main__":
    main()
