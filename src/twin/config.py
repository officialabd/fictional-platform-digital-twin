"""Twin settings. Facility knowledge is copied from the facility doc, never from the simulator."""

# Graph nodes with a special role
FIREWALL = "IT_OT_Firewall"
DIGITAL_TWIN = "Digital_Twin"
SATELLITE_LINK = "Satellite_Link"

# How readings reach shore (facility doc, data flow). Any of these down blinds the twin.
# Not taken from the network edges: SCADA -> EWS -> Firewall is also a path in the graph,
# but it is the vendor session's return path, not the data path.
DATA_PATH = ["SCADA_Server", "Historian", "IT_OT_Firewall", "Satellite_Link", "Digital_Twin"]

# Which sensors drive each control loop, keyed by the actuator (facility doc, actuator table).
# The graph says which controller reads a sensor, not which loop uses it. Rule 1 needs that.
LOOP_INPUTS = {
    "PV201": {"PT201"},
    "LV201": {"LT201"},
    "LV202": {"LT202"},
    "FV401": {"FT401", "PT401", "PT402"},
    "P501": {"PT501"},
}

# What each SIS input protects (facility doc, trip table). Rule 2 needs it.
FULL_SHUTDOWN = {"SDV101", "BDV201", "Compressor", "Export_Pumps"}
TRIP_TARGETS = {
    "PT201": {"SDV101", "BDV201"},
    "LSHH201": {"SDV101"},
    "LT301": {"Compressor"},
    "GD801": FULL_SHUTDOWN,
    "GD802": FULL_SHUTDOWN,
    "FD801": FULL_SHUTDOWN,
}

# Data sync
TICK_S = 1.0  # the platform historian stores one reading per tag per second
STALE_S = 5.0  # wall seconds without a new reading before a tag counts as stale

# Monitoring. Persistence is in simulated seconds: a check must hold this long to raise a flag.
RANGE_PERSIST_S = 10
PHYSICS_PERSIST_S = 30
FROZEN_READINGS = 30  # a noisy sensor repeating the exact same value this many times
JUMP_FRACTION = 0.5  # change in one second, as a fraction of the normal range width
JUMP_HOLD_S = 30  # how long a jump flag stays up
CLEAR_HOLD_S = 60  # a flag clears only after its check has been false this long
NEAR_TRIP_FRACTION = 0.9

# SIS trip limits (facility doc, trip table)
TRIP_LIMITS = {"PT201": 27.0, "LT301": 70.0, "GD801": 60.0, "GD802": 60.0}

# Control loops with one input: actuator -> (input tag, direction, normal output %).
# Direction +1: input above setpoint opens the actuator more. FV401 (three inputs) is left out.
LOOPS = {
    "PV201": ("PT201", +1, 50.0),
    "LV201": ("LT201", +1, 50.0),
    "LV202": ("LT202", +1, 50.0),
    "P501": ("PT501", -1, 75.0),
}
LOOP_MARGIN_PCT = 10.0  # how far past normal output counts as "pushing the wrong way"
PNEUMATIC = {"SDV101", "PV201", "LV201", "LV202", "BDV201", "FV401"}
AIR_MIN_BARG = 4.5  # below this, pneumatic valves go to their fail position

# Physics checks
GAS_VALVE_LOW_PCT = 35.0  # PV201 this far closed should make the pressure rise
PRESSURE_RISE_BAR_PER_MIN = 0.2
FLARE_HIGH_SM3H = 1000.0
COMPRESSOR_RUNNING_MW = 1.0
VALVE_OPEN_PCT = 50.0
INFLOW_PRESENT_M3H = 45.0
LIQUID_IMBALANCE_M3H = 10.0  # inflow minus outflows, averaged over the window
LEVEL_PCT_PER_MIN_PER_M3H = 1 / 23  # how fast the separator levels move per m3/h of imbalance
WINDOW_S = 60

# Map (fictional locations)
MAP_PLATFORM = (45.20, -48.40)
MAP_ONSHORE = (47.10, -52.90)
