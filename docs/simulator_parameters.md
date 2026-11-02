# Simulator Parameters

v1 Oct 27, 2026 · @Abd. Updated Oct 28, 2026 to the values in `src/simulator/config.py` (changes marked **v2**).

## Purpose

Proposed values for every simulator parameter the Fictional Platform doc leaves open: vessel sizes, valve capacities, setpoints, tuning, noise and initial state. They are derived from the doc's normal rates, normal ranges and trip limits, and are proposals to check, not facts. They go in the simulator's own config (src/simulator/config.py), never in data/nodes.csv.

Given by the platform doc: 60 m3/h oil, 30 m3/h water, 20,000 Sm3/h gas, separator at 20 barg and 60 °C, LT201 setpoint 50%, all trip limits, PSV at 30 barg, instrument air limit 4.5 barg, and the normal range of all 29 sensors.

## Vessels

The separator is 40 m3, which gives typical retention times and trip timings fast enough to demo.

| Item | Proposal | Reasoning |
| --- | --- | --- |
| Separator volume | 40 m3 (about 2.5 m diameter x 8 m long) | At 50% oil level and 32% interface: oil retention about 7 min, water about 25 min |
| Level model | LT202 = water volume / 40 x 100; LT201 = (water + oil) / 40 x 100 | Level is linear in volume, ignoring the round tank shape |
| Gas space | 40 m3 minus liquid volume, about 20 m3 normally |  |
| Gas pressure | Pressure (bara) = gas held (Sm3) / gas space (m3) | Ideal gas at constant temperature; 21 bara x 20 m3 = 420 Sm3 held |
| Scrubber | 1 m3 liquid capacity, normal level 20% |  |

Resulting timings:

- Oil outlet fully closed: LT201 goes from 50% to 90% (LSHH trip) in about 16 min.
- Gas outlet blocked: PT201 goes from 20 to 27 barg (trip) in about 25 s, and reaches the PSV at 30 barg in about 36 s.

## Inflow split

The choke sets total liquid inflow, which splits into fixed shares of oil, water and gas.

- Liquid inflow FT101 = 1.5 m3/h x HV101 opening %. At the normal 60% that is 90 m3/h. Zero when SDV101 is closed.
- Liquid splits 2/3 oil, 1/3 water: 60 and 30 m3/h.
- Gas inflow = 333 Sm3 per m3 of oil: 20,000 Sm3/h.

## Valves

Each valve's normal opening delivers the doc's normal flow; flow is linear in opening, and gas valves also scale with separator pressure.

| Valve | Capacity at 100% open | Normal opening | Notes |
| --- | --- | --- | --- |
| HV101 | 150 m3/h | 60% (manual) |  |
| LV201 | 120 m3/h | 50% | Flow is 0 if the export pumps are stopped (blocked outlet) |
| LV202 | 60 m3/h | 50% |  |
| PV201 | 40,000 Sm3/h x (bara / 21) | 50% | If the compressor is stopped, the gas goes on to the flare |
| BDV201 | 5,000 Sm3/h x (bara / 21) | Closed | Takes the separator near 0 barg in about 2 to 3 min |
| FV401 | 20,000 Sm3/h recycle | About 12% |  |
| PSV | 25,000 Sm3/h x (bara / 31) | Closed | Opens at 30 barg, reseats at 28 barg. No cyber input |
| SDV101 | On/off | Open |  |

- Control valves move at most 10% per second.
- SDV101 and BDV201 make a full stroke in 2 s.
- When PT901 is below 4.5 barg, every pneumatic valve goes to its fail position, whatever the DCS or SIS commands.

## Control loops

All five DCS loops are PI controllers in velocity form (the output moves by a step each tick, so saturation cannot wind up the integral), run once per 1 s tick.

| Loop | Setpoint | When the reading is high | Kp | Ti |
| --- | --- | --- | --- | --- |
| PV201 on PT201 | 20 barg | Open more | 5 %/bar | 30 s |
| LV201 on LT201 | 50% (from the doc) | Open more | 2 %/% | **v2** 1200 s (was 300 s) |
| LV202 on LT202 | 32% | Open more | 2 %/% | **v2** 1200 s (was 300 s) |
| P501 on PT501 | 60 barg | Slow down | **v2** 0.5 %/bar (was 2) | 10 s |
| FV401 on FT401 | 21,000 Sm3/h minimum | Opens when flow is low | **v2** 0.002 %/(Sm3/h) (was 0.005) | 5 s |

The anti-surge minimum is a fixed number, a simplification of a surge line calculated from PT401 and PT402.

**v2 tuning changes, found in testing:**

- LV201 and LV202 with Ti 300 s overshot badly: a level is an integrating process, and with Kp 2 its closed loop time constant is about 600 s, so Ti must be several times that. Ti 1200 s gives a damped response. With Ti 300 s a setpoint change to 88% overshot straight to the LSHH201 trip.
- P501 with Kp 2 %/bar oscillated: PT501 responds to speed within the same tick (about 1.07 bar per %), so the loop gain was above 1. Kp 0.5 keeps it near 0.5.
- FV401 with Kp 0.005 had a loop gain of about 1 for the same reason (200 Sm3/h per %) and amplified FT401 noise into swings outside its normal range. Kp 0.002 fixes it.

## Other equipment models

Every remaining sensor gets a simple rule that holds it inside its normal range in steady state and moves it the right way in a fault.

| Area | Proposal |
| --- | --- |
| Fuel gas | 1,500 Sm3/h taken off after the scrubber. FT401 = 20,000 - 1,500 + recycle, about 21,000 Sm3/h |
| Compressor | PT401 = PT201 - 1 bar, never below 0. PT402 = 70 barg while running. JT401 = 4.0 MW x FT401 / 21,000. TT401 120 °C. VT401 2.5 mm/s, plus 3 when LT301 is above 50% (liquid reaching the machine) |
| Scrubber liquid | Normally 0.05 m3/h in, drained in proportion to level. When LT201 is above 80%, carryover adds 5 m3/h per 10% of level. This gives the scenario 2 cascade: separator high, scrubber high (70%), compressor trip |
| Export pumps | PT501 = PT201 + 40 x (speed / 75)^2, so 75% speed gives 60 barg. FT501 = FT202. Stopped pumps block the oil outlet. VT501 2 mm/s. Pump power 0.8 MW x (speed / 75)^3 |
| Water treatment | FT601 = FT203. AT601 = 15 mg/L, plus 3 for each % LT202 is below 25 (low interface lets oil escape with the water) |
| Manifold | PT101 = 55 - 10 x (FT101 / 90): 45 barg normal, 55 when shut in. TT101 65 °C |
| Separator temperature | TT201 60 °C while fluid flows. With no inflow it cools toward 25 °C, time constant 30 min |
| Flare | FT701 = 100 Sm3/h purge, plus BDV201 and PSV flows, plus the PV201 gas when the compressor is stopped |
| Power | JT901 = 3.0 MW base + JT401 + pump power, about 7.8 MW normally. Stays up on diesel unless a fault takes it down |
| Instrument air | PT901 7.5 barg. On power loss it falls 0.5 bar/min, reaching 4.5 barg after about 6 min |
| Gas and fire detectors | GD801 and GD802 around 1 %LEL. FD801 off. They change only when a fault is injected |
| Noise | Random noise with a spread of 2% of each sensor's normal range width, e.g. PT201 0.08 barg, FT201 80 Sm3/h. On/off switches get none |
| Initial state | Start at the steady state above, each controller output at its normal value, so nothing jumps on the first tick |
| Units | Pressure calculated in bara internally, reported in barg |

## Steady state check

The proposed values balance: liquid in 90 m3/h = 60 oil + 30 water out, gas in 20,000 Sm3/h = gas out, and every sensor sits inside its normal range.

## Gaps outside the simulator

Three gaps sit in the graph and the fault list rather than in the simulator's physics. Tamper is built. The two graph changes are still proposals: they belong to the twin's graph model, not to the simulator.

| Gap | Proposal |
| --- | --- |
| PSV not in the graph | Add node PSV201 (mechanical protection, Level 0) with edge PSV201 acts\_on Separator. No controller, no instrument air |
| No power to the cyber systems | Add Power\_Gen supplies edges to the 3 DCS, SIS, SCADA, HMI, EWS, Historian, firewall and satellite link. Give the DCS and SIS a battery backup (UPS) of about 30 min |
| Vendor access scenario has no fault type | Add a fifth fault type, tamper: change a setpoint, force a controller output, or switch off an SIS trip (Triton style) |

## Simplifications and open choices

These simplifications go in the architecture doc:

- Level is linear in volume.
- Valves are linear and ignore pressure drop, except the gas valves.
- Gas follows the ideal gas law at constant temperature.
- The anti-surge minimum flow is fixed.
- There is no buffer tank before the export pumps.

Open choices:

- [x] Is the plant fast enough to demo? Decided: keep the physics, run faster than real time with `--speed` (20x for the demo).
- [x] Should a stopped compressor block the gas outlet? Decided: no. Gas diverts through PV201 to the flare and pressure stays controlled, so "degraded with flaring" stays distinct from "full shutdown".
- [x] Accept tamper as the fifth fault type? Accepted.

**v2 additions:** the SIS reads reported values, so it is fooled by the same spoof as the DCS (PT201 feeds both on purpose). A spoof reports a chosen value but keeps live looking noise, so a flat line does not give it away. A controller that goes offline stops reporting its tags; SIS tags still reach SCADA over the SIS link. HV101 is executed by DCS_Separation and stays in place if it goes offline. Power loss is not simulated (it is covered by the impact analysis only).
