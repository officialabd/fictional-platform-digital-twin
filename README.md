# Fictional Platform Digital Twin

If part of an offshore platform is attacked or fails, what else breaks, and what should the operator do?

Two programs live in this repo, and data flows one way between them:

- `src/simulator` plays the platform (Purdue levels 0 to 3) and publishes sensor readings.
- `src/twin` watches those readings and reasons about the platform: graph model, data sync,
  monitoring, impact analysis and a Streamlit dashboard.
- `src/shared` holds only the message format.

The simulator and the twin never import each other, and the twin never sees true values.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

## Run the simulator

Start the MQTT broker, then the simulator:

```
docker compose up -d
python -m simulator.main --scenario spoof_pt201 --speed 20 --duration 900
```

Each run gets its own folder in `runs/`:

- `sim.db` is the platform historian: the reported readings, which are what gets sent to shore.
- `truth.db` holds the true values and events, used only for validation.

If the broker is not reachable the run still finishes and stores everything, it just sends nothing.

### Simulator layout

| File | Job |
| --- | --- |
| `config.py` | Every setting. The reasoning is in `docs/simulator_parameters.md` |
| `process.py` | Mass balance: valves set flows, flows change levels and pressures |
| `sensors.py` | True value to reported value: noise and spoofing |
| `control.py` | DCS control loops and SIS trips |
| `faults.py`, `scenarios.py` | What can go wrong, and the named schedules that switch it on |
| `plant.py` | Wires the parts above into one tick |
| `storage.py` | Historian and truth log |
| `forwarder.py` | Store and forward: resends what the broker has not acknowledged |
| `mqtt_link.py` | The MQTT connection |
| `main.py` | Command line and tick loop |

## Run the twin

Start order matters: the twin only receives readings published after it connects.

```
docker compose up -d
python -m twin.service --run-id demo2
python -m simulator.main --run-id demo2 --scenario spoof_pt201 --speed 20 --duration 900
streamlit run src/twin/dashboard/app.py
```

Use the same `--run-id` for the twin and the simulator, so Week 10 validation can pair them.
At `--speed 20` a 900 s run lasts 45 s, so open the dashboard before starting the simulator,
or use a lower speed, to watch it live.

After a link loss the backlog arrives in order but slower than real time. The twin estimates
how far behind live it is (from the data pace before the outage) and shows a "catching up"
warning until it is current.
The twin writes `runs/twin/<run-id>/twin.db`: every reading it received (duplicates dropped),
plus the flags and suspected failures from monitoring. It never opens `sim.db` or `truth.db`.

To draw the asset graph on its own: `python -m twin.main`.

### Twin layout

| File | Job |
| --- | --- |
| `config.py` | Twin settings and facility knowledge (loop inputs, trip targets, thresholds, map) |
| `model.py` | Loads the asset graph from `data/` |
| `impact.py` | Impact analysis: given a node and how it fails, what else is affected (Rules 1 to 13, plus V) |
| `sync.py` | MQTT subscriber |
| `store.py` | twin.db: readings, flags, suspected failures |
| `monitoring.py` | Range, trip, stale, frozen, jump and physics checks; suspected failures |
| `service.py` | Runs sync and monitoring, records to twin.db |
| `dashboard/` | Streamlit app: overview, graph with what-if, sensors, impact, map |
| `graph_builder.py`, `graph_visualizer.py`, `edge_router.py` | Build and draw the graph |

## Message format

One message per reading on topic `platform/<TAG>`, QoS 1. `ts` is simulated seconds since the run started.

```json
{"tag": "LT201", "ts": 412.0, "value": 51.3}
```

## Tests

```
pytest
ruff check src tests
```
