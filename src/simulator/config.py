"""Simulator settings. The reasoning behind the numbers is in docs/simulator_parameters.md.

The simulator owns these values and never reads data/nodes.csv. Tag names are the only thing it
has in common with the twin. Units are part of each name: barg is gauge pressure, bara absolute.
"""

from dataclasses import dataclass
from enum import StrEnum

TICK_S = 1.0
ATM_BAR = 1.0  # bara = barg + 1

# Separator
SEPARATOR_M3 = 40.0
MIN_GAS_SPACE_M3 = 0.5  # keeps pressure finite if the vessel overfills
NORMAL_OIL_M3 = 7.2  # gives LT201 50% (total liquid) with LT202 32% (water)
NORMAL_WATER_M3 = 12.8
NORMAL_PRESSURE_BARA = 21.0
LSHH201_PCT = 90.0

# Inflow: the choke sets total liquid inflow, which splits into fixed shares
CHOKE_M3H_PER_PCT = 1.5
HV101_NORMAL_PCT = 60.0  # operator setpoint, executed by DCS_Separation
HV101_CONTROLLER = "DCS_Separation"
OIL_SHARE = 2 / 3
GAS_SM3_PER_M3_OIL = 20000 / 60
MIN_FLOWING_M3H = 1.0  # below this the separator counts as shut in and cools down

# Valve capacities at 100% open. Gas flows also scale with separator pressure.
LV201_M3H = 120.0
LV202_M3H = 60.0
PV201_SM3H = 40000.0
BDV201_SM3H = 5000.0
FV401_SM3H = 20000.0
PSV_SM3H = 25000.0
GAS_REF_BARA = 21.0
PSV_REF_BARA = 31.0
PSV_OPEN_BARG = 30.0
PSV_RESEAT_BARG = 28.0

CONTROL_VALVE_PCT_PER_S = 10.0
SHUTDOWN_VALVE_PCT_PER_S = 50.0  # full stroke in 2 s
SHUTDOWN_VALVES = {"SDV101", "BDV201"}

# Where an actuator goes on loss of instrument air or of its controller (facility doc).
# HV101 stays in place, so it is not listed. P501 is an electric drive, so air does not move it.
FAIL_POSITION_PCT = {
    "SDV101": 0.0,
    "PV201": 100.0,
    "LV201": 0.0,
    "LV202": 0.0,
    "BDV201": 100.0,
    "FV401": 100.0,
    "P501": 0.0,
}
PNEUMATIC_VALVES = set(FAIL_POSITION_PCT) - {"P501"}

# Instrument air
AIR_NORMAL_BARG = 7.5
AIR_MIN_BARG = 4.5
AIR_DECAY_BAR_PER_S = 0.5 / 60

# Manifold
MANIFOLD_SHUT_IN_BARG = 55.0
MANIFOLD_DROP_AT_NORMAL_FLOW_BAR = 10.0
NORMAL_INFLOW_M3H = 90.0
MANIFOLD_TEMP_C = 65.0

# Scrubber
SCRUBBER_M3 = 1.0
SCRUBBER_NORMAL_M3 = 0.2
SCRUBBER_BASE_IN_M3H = 0.05
SCRUBBER_DRAIN_PER_H = SCRUBBER_BASE_IN_M3H / SCRUBBER_NORMAL_M3
CARRYOVER_START_PCT = 80.0
CARRYOVER_M3H_PER_PCT = 0.5  # 5 m3/h for every 10% of separator level above the start

# Compressor
FUEL_GAS_SM3H = 1500.0
COMPRESSOR_POWER_MW = 4.0
COMPRESSOR_REF_SM3H = 21000.0
COMPRESSOR_DISCHARGE_BARG = 70.0
COMPRESSOR_SUCTION_DROP_BAR = 1.0
COMPRESSOR_HOT_C = 120.0
COMPRESSOR_COLD_C = 40.0
COMPRESSOR_VIBRATION_MM_S = 2.5
LIQUID_IN_COMPRESSOR_VIBRATION_MM_S = 3.0  # added once liquid starts reaching the machine
LIQUID_REACHES_COMPRESSOR_PCT = 50.0

# Export pumps
PUMP_HEAD_BAR = 40.0
PUMP_REF_SPEED_PCT = 75.0
PUMP_POWER_MW = 0.8
PUMP_VIBRATION_MM_S = 2.0

# Produced water: a low interface lets oil escape with the water
OIL_IN_WATER_NORMAL_MG_L = 15.0
OIL_IN_WATER_MG_L_PER_PCT = 3.0
OIL_ESCAPES_BELOW_LT202_PCT = 25.0

# Temperatures
SEPARATOR_TEMP_C = 60.0
AMBIENT_TEMP_C = 25.0
COOLING_TAU_S = 1800.0
HEATING_TAU_S = 60.0

# Flare, power and detectors
FLARE_PURGE_SM3H = 100.0
BASE_LOAD_MW = 3.0
NORMAL_GAS_LEL = 1.0


@dataclass(frozen=True)
class Loop:
    """One DCS PI loop. direction +1 opens the actuator when the reading is above setpoint."""

    controller: str
    input_tag: str
    setpoint: float
    kp: float
    ti_s: float
    direction: int
    normal_output_pct: float


# Keyed by the actuator each loop drives. LV201, LV202, FV401 and P501 were retuned in testing.
LOOPS = {
    "PV201": Loop("DCS_Separation", "PT201", 20.0, 5.0, 30.0, +1, 50.0),
    "LV201": Loop("DCS_Separation", "LT201", 50.0, 2.0, 1200.0, +1, 50.0),
    "LV202": Loop("DCS_Separation", "LT202", 32.0, 2.0, 1200.0, +1, 50.0),
    "FV401": Loop("DCS_Compression", "FT401", 21000.0, 0.002, 5.0, -1, 12.5),
    "P501": Loop("DCS_Export", "PT501", 60.0, 0.5, 10.0, -1, 75.0),
}


class SisAction(StrEnum):
    CLOSE_INLET = "close_inlet"
    BLOWDOWN = "blowdown"
    STOP_COMPRESSOR = "stop_compressor"
    STOP_PUMPS = "stop_pumps"


FULL_SHUTDOWN = frozenset(SisAction)
SWITCH_ON = 1.0  # on/off sensors report 1.0 for on and 0.0 for off


@dataclass(frozen=True)
class Trip:
    """A safety trip fires when the reading reaches the limit."""

    tag: str
    limit: float
    actions: frozenset[SisAction]


# The facility doc's five trips, with gas detection listed once per detector.
TRIPS = {
    "PT201_high": Trip("PT201", 27.0, frozenset({SisAction.CLOSE_INLET, SisAction.BLOWDOWN})),
    "LSHH201": Trip("LSHH201", SWITCH_ON, frozenset({SisAction.CLOSE_INLET})),
    "LT301_high": Trip("LT301", 70.0, frozenset({SisAction.STOP_COMPRESSOR})),
    "GD801_gas": Trip("GD801", 60.0, FULL_SHUTDOWN),
    "GD802_gas": Trip("GD802", 60.0, FULL_SHUTDOWN),
    "FD801_fire": Trip("FD801", SWITCH_ON, FULL_SHUTDOWN),
}
SIS = "SIS"

# Which controller reports each tag: the 29 sensors plus actuator feedback. These follow the
# reads edges of the graph. If a controller goes offline, its tags stop reporting.
REPORTED_BY = {
    "DCS_Separation": [
        "PT101",
        "TT101",
        "FT101",
        "PT201",
        "TT201",
        "LT201",
        "LT202",
        "FT201",
        "FT202",
        "FT203",
        "AT601",
        "FT601",
        "HV101",
        "PV201",
        "LV201",
        "LV202",
    ],
    "DCS_Compression": ["PT401", "PT402", "TT401", "FT401", "VT401", "JT401", "FT701", "FV401"],
    "DCS_Export": ["PT501", "FT501", "VT501", "JT901", "PT901", "P501"],
    SIS: ["LSHH201", "LT301", "GD801", "GD802", "FD801", "SDV101", "BDV201"],
}
TAGS = [tag for tags in REPORTED_BY.values() for tag in tags]

# Standard deviation is 2% of each sensor's normal range. Switches and actuators have no noise.
NOISE_SD = {
    "PT101": 0.2,
    "TT101": 0.2,
    "FT101": 0.2,
    "PT201": 0.08,
    "TT201": 0.2,
    "LT201": 0.4,
    "LT202": 0.3,
    "FT201": 80.0,
    "FT202": 0.2,
    "FT203": 0.2,
    "LT301": 0.4,
    "PT401": 0.08,
    "PT402": 0.2,
    "TT401": 0.4,
    "FT401": 80.0,
    "VT401": 0.06,
    "JT401": 0.02,
    "PT501": 0.2,
    "FT501": 0.2,
    "VT501": 0.04,
    "AT601": 0.4,
    "FT601": 0.2,
    "FT701": 2.0,
    "GD801": 0.1,
    "GD802": 0.1,
    "JT901": 0.06,
    "PT901": 0.02,
}
