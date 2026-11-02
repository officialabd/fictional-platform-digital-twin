"""Named fault schedules. Scenarios are switched on here in the simulator, never from the twin."""

from simulator.faults import Fault, FaultKind

# Every fault starts after 60 s of normal operation, so the twin has a baseline to compare with.
SCENARIOS: dict[str, list[Fault]] = {
    "normal": [],
    # Corporate IT is hit. Operators isolate the DMZ and cut the satellite link as a precaution.
    "it_ransomware": [Fault(FaultKind.LINK, "Satellite_Link", 60, end_s=360)],
    # PT201 reports a steady 19 barg, inside its normal range, while the true pressure rises.
    "spoof_pt201": [Fault(FaultKind.SPOOF, "PT201", 60, value=19.0)],
    # A vendor session reaches the engineering workstation and raises the oil level setpoint.
    "vendor_remote_access": [Fault(FaultKind.TAMPER, "LV201", 60, value=88.0)],
    "satellite_link_loss": [Fault(FaultKind.LINK, "Satellite_Link", 60, end_s=660)],
    "instrument_air_loss": [Fault(FaultKind.AIR_LOSS, "Instrument_Air", 60)],
    "dcs_separation_offline": [Fault(FaultKind.OFFLINE, "DCS_Separation", 60)],
}
