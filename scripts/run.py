"""Start one run: the twin service, then the simulator, under one date-time run id.

Example: python scripts/run.py --scenario spoof_pt201 --speed 20 --duration 900

Both programs run as separate processes and this script imports neither, so they stay apart.
The twin is stopped a few seconds after the simulator ends. Results land in runs/<run-id>/.
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"
READY_TIMEOUT_S = 15.0
DRAIN_S = 3.0  # time for the twin to take in the last readings


def wait_for_twin(twin: subprocess.Popen, db: Path) -> bool:
    """The twin creates twin.db once it is subscribed."""
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if db.exists():
            return True
        if twin.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the twin and the simulator together")
    parser.add_argument("--scenario", default="normal")
    parser.add_argument("--speed", default="20", help="simulated seconds per second")
    parser.add_argument("--duration", default="900", help="simulated seconds")
    parser.add_argument("--seed", help="fix the sensor noise, to repeat a run exactly")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--broker-host", default="localhost")
    parser.add_argument("--broker-port", default="1883")
    args = parser.parse_args()

    broker = ["--broker-host", args.broker_host, "--broker-port", args.broker_port]
    sim = [sys.executable, "-m", "simulator.main", "--run-id", args.run_id,
           "--scenario", args.scenario, "--speed", args.speed, "--duration", args.duration,
           *broker]
    if args.seed is not None:
        sim += ["--seed", args.seed]

    print(f"run {args.run_id}", flush=True)
    twin = subprocess.Popen([sys.executable, "-m", "twin.service", "--run-id", args.run_id,
                             *broker])
    try:
        if not wait_for_twin(twin, RUNS_DIR / args.run_id / "twin.db"):
            stop(twin)
            sys.exit("the twin did not start, see its message above")
        code = subprocess.run(sim).returncode
        time.sleep(DRAIN_S)
    except KeyboardInterrupt:
        code = 1  # Ctrl+C reaches both programs too, and each stops cleanly
    finally:
        stop(twin)
    print(f"run {args.run_id} finished, results in {RUNS_DIR / args.run_id}")
    sys.exit(code)


if __name__ == "__main__":
    main()
