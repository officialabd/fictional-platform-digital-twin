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
