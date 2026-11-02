# Fictional Platform Digital Twin

If part of an offshore platform is attacked or fails, what else breaks, and what should the operator do?

Two programs live in this repo, and data flows one way between them:

- `src/simulator` plays the platform (Purdue levels 0 to 3) and publishes sensor readings.
- `src/twin` watches those readings and reasons about the platform. So far it holds the graph model.
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
