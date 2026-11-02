"""Run the platform simulator and publish its readings over MQTT.

Example: python -m simulator.main --scenario spoof_pt201 --speed 20 --duration 900
"""

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

from simulator import config
from simulator.forwarder import Forwarder
from simulator.mqtt_link import MqttLink
from simulator.plant import Plant
from simulator.scenarios import SCENARIOS
from simulator.storage import Historian, TruthLog

log = logging.getLogger("simulator")

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"
FLUSH_TIMEOUT_S = 10.0


def run(
    plant: Plant,
    historian: Historian,
    truth: TruthLog,
    forwarder: Forwarder,
    duration_s: int,
    speed: float,
) -> None:
    start = time.monotonic()
    link_down = False
    for step in range(duration_s):
        t = step * config.TICK_S
        tick = plant.step(t)
        historian.store(t, tick.visible)
        truth.record(t, tick.true, tick.events)
        for event in tick.events:
            log.info("t=%.0f %s %s", t, event.kind, event.detail)

        link_down = tick.link_down
        forwarder.tick(link_down)

        # Hold the pace against the clock, so a slow tick does not add up over the run
        delay = start + (step + 1) * config.TICK_S / speed - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    if not link_down:
        forwarder.flush(FLUSH_TIMEOUT_S)


def main() -> None:
    parser = argparse.ArgumentParser(description="Platform simulator")
    parser.add_argument("--scenario", default="normal", choices=sorted(SCENARIOS))
    parser.add_argument("--speed", type=float, default=1.0, help="simulated seconds per second")
    parser.add_argument("--duration", type=int, default=3600, help="simulated seconds")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--broker-host", default="localhost")
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--seed", type=int, help="fix the sensor noise, to repeat a run exactly")
    args = parser.parse_args()

    if args.speed <= 0:
        parser.error("--speed must be above 0")
    run_dir = RUNS_DIR / args.run_id
    if run_dir.exists():
        parser.error(f"run {args.run_id} already exists, choose another --run-id")
    run_dir.mkdir(parents=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info(
        "run %s: scenario %s, %d s at %gx", args.run_id, args.scenario, args.duration, args.speed
    )

    plant = Plant(SCENARIOS[args.scenario], seed=args.seed)
    historian = Historian(run_dir)
    truth = TruthLog(run_dir)
    link = MqttLink(args.broker_host, args.broker_port, client_id=f"sim-{args.run_id}")
    try:
        run(plant, historian, truth, Forwarder(historian, link), args.duration, args.speed)
    except KeyboardInterrupt:
        log.info("stopped")
    finally:
        link.close()
        truth.close()
        historian.close()


if __name__ == "__main__":
    main()
