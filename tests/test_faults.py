from simulator.faults import Fault, FaultEffects, FaultKind


def test_fault_is_active_between_start_and_end():
    fault = Fault(FaultKind.LINK, "Satellite_Link", 60, end_s=120)
    assert not fault.is_active(59)
    assert fault.is_active(60)
    assert not fault.is_active(120)


def test_fault_without_an_end_stays_active():
    assert Fault(FaultKind.AIR_LOSS, "Instrument_Air", 60).is_active(100000)


def test_no_faults_means_no_effects():
    effects = FaultEffects.of([])
    assert not effects.spoofs and not effects.stuck and not effects.offline
    assert not effects.air_lost and not effects.link_down


def test_effects_collect_each_kind():
    effects = FaultEffects.of(
        [
            Fault(FaultKind.SPOOF, "PT201", 0, value=19.0),
            Fault(FaultKind.TAMPER, "LV201", 0, value=88.0),
            Fault(FaultKind.STUCK, "LV202", 0),
            Fault(FaultKind.OFFLINE, "DCS_Export", 0),
            Fault(FaultKind.AIR_LOSS, "Instrument_Air", 0),
            Fault(FaultKind.LINK, "Satellite_Link", 0),
        ]
    )
    assert effects.spoofs == {"PT201": 19.0}
    assert effects.tampered_setpoints == {"LV201": 88.0}
    assert effects.stuck == {"LV202"}
    assert effects.offline == {"DCS_Export"}
    assert effects.air_lost and effects.link_down
