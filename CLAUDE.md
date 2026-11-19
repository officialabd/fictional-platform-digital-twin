# Project context
Internship project: a digital twin of a fictional offshore oil and gas platform.

# Architecture
Two programs in one repo. Data flows one way: simulator to twin.

Simulator (plays Purdue Levels 0 to 3), 1 second tick:
1. Process model: simple mass balance. Valves set flows, flows change levels and pressures.
2. DCS and SIS: 5 control loops (PV201, LV201, LV202, FV401, P501) and 5 safety trips from the facility doc.
3. Sensors: true state + noise = reported value. Each sensor keeps a true and a reported value.
4. Fault injector: spoofed reading, stuck valve, controller offline, link down.
Output: tag, timestamp, reported value. True values go to a separate truth log, used only in Week 10 validation.

Transport (decided): MQTT via a Mosquitto broker, paho-mqtt 2.x.
- The simulator stores every reading in its historian (sim.db), then publishes. A forwarded marker moves only on broker PUBACK (QoS 1). Link down = stop publishing; on recovery, resend everything past the marker with original timestamps.
- Topic per tag: platform/<TAG>. Payload: JSON {tag, ts, value}. ts is simulated seconds. A resend can duplicate, so the twin must ignore duplicates.
Keep on purpose: PT201 feeds both DCS and SIS (Week 7 spoofing scenario). Instrument air below 4.5 barg sends every pneumatic valve to its fail position.

Twin, six parts: data sync, graph model (exists), monitoring, impact analysis, dashboard (Streamlit), advisor (LLM).

# Hard rules
- src/simulator and src/twin never import each other. src/shared holds only the message format.
- The twin never sees true values.
- Scenarios are switched on in the simulator, never from the dashboard.
- The twin never sends commands back. The advisor only suggests; a human approves.
- The simulator has its own config (setpoints, trip limits, initial state, noise) and does not read data/nodes.csv. The only thing shared is tag names.
- Synthetic data only. No company material in the repo. Secrets in .env, which is gitignored.

# Target layout
data/, src/simulator/, src/twin/ (existing code moves here), src/shared/, runs/ (gitignored output), tests/, docs/

# Open questions
1. Impact rule per edge type: which way damage spreads (arrows follow meaning, not damage).
2. Impacts outside the graph, e.g. precautionary shutdown after loss of visibility.
3. Which LLM for the advisor, and whether an external API is acceptable.

# How to work with me
- Concise, direct, no fluff. No em dashes.
- Correct me when I'm wrong. Show alternatives and blind spots.
- I'm new to digital twins. Go step by step, let me make the design decisions, and check my reasoning rather than handing me finished designs.

# Context:
- Google Drive Docs/Files/Folders/Sub-folders: https://drive.google.com/drive/folders/1Ob_8oZLKPuQn_lzhuSqDEze8E8XIVf_l