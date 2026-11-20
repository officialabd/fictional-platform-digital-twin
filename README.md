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

## Run

Start the broker and the dashboard once, then start as many runs as you like:

```
docker compose up -d
streamlit run src/twin/dashboard/app.py
python scripts/run.py --scenario spoof_pt201 --speed 20 --duration 900
```

`scripts/run.py` names the run after the date and time (e.g. `20261120-143000`), starts the twin,
waits until it is subscribed, then starts the simulator, and stops the twin when the run ends.
`--run-id` overrides the name. Pick the run in the dashboard sidebar (newest first; reload the
page to see a new run).

At `--speed 20` a 900 s run lasts 45 s. Use a lower speed to watch it live.

Each run gets one folder, `runs/<run-id>/`:

| File | Written by | Holds |
| --- | --- | --- |
| `sim.db` | simulator | Platform historian: the reported readings, which are what gets sent to shore |
| `truth.db` | simulator | True values and events, used only for Week 10 validation |
| `twin.db` | twin | Every reading the twin received (duplicates dropped), its flags and suspected failures |

The twin never opens `sim.db` or `truth.db`.

### Run each side by hand

The twin only receives readings published after it connects, so start it first, with the same id:

```
python -m twin.service --run-id demo
python -m simulator.main --run-id demo --scenario spoof_pt201 --speed 20 --duration 900
```

The simulator alone also works. If the broker is not reachable the run still finishes and stores
everything, it just sends nothing.

### Simulator layout

| File | Job |
| --- | --- |
| `config.py` | Every setting. The reasoning is in `docs/simulator_parameters_explanation.md` (kept outside git) |
| `process.py` | Mass balance: valves set flows, flows change levels and pressures |
| `sensors.py` | True value to reported value: noise and spoofing |
| `control.py` | DCS control loops and SIS trips |
| `faults.py`, `scenarios.py` | What can go wrong, and the named schedules that switch it on |
| `plant.py` | Wires the parts above into one tick |
| `storage.py` | Historian and truth log |
| `forwarder.py` | Store and forward: resends what the broker has not acknowledged |
| `mqtt_link.py` | The MQTT connection |
| `main.py` | Command line and tick loop |

## Twin

After a link loss the backlog arrives in order but slower than real time. The twin estimates
how far behind live it is (from the data pace before the outage) and shows a "catching up"
warning until it is current.

To draw the asset graph on its own: `python -m twin.main` (writes `outputs/asset_graph.html`).

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
| `main.py` | Draws the asset graph as an HTML page |
| `graph_builder.py`, `graph_visualizer.py`, `edge_router.py`, `graph_click.js` | Build and draw the graph |
| `load_neo4j.py` | Copies the graph into Neo4j (optional, needs `NEO4J_PASSWORD` in `.env`) |

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
