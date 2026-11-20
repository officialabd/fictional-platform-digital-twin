"""Impact rules, one test per rule, then the four scenarios end to end."""

import pytest

from twin.impact import Effect, Mode, analyze, modes_for
from twin.model import load_graph


@pytest.fixture(scope="module")
def G():
    return load_graph()


def effects(result, node):
    return {i.effect for i in result.impacts if i.node == node}


def by_rule(result, rule):
    return {(i.node, i.effect) for i in result.impacts if i.rule == rule}


def test_mode_must_fit_the_node_type(G):
    with pytest.raises(ValueError):
        analyze(G, "PT201", Mode.DOWN)
    with pytest.raises(ValueError):
        analyze(G, "Nope", Mode.DOWN)
    assert modes_for("controller") == [Mode.DOWN, Mode.COMPROMISED]


def test_rule_1_only_the_loops_that_use_the_sensor(G):
    r = analyze(G, "LT201", Mode.WRONG_READINGS)
    assert ("DCS_Separation", Effect.LOSS_OF_CONTROL) in by_rule(r, "1")
    assert by_rule(r, "4") == {("LV201", Effect.LOSS_OF_CONTROL)}


def test_rule_1_monitoring_sensor_costs_no_loop(G):
    r = analyze(G, "TT201", Mode.WRONG_READINGS)
    assert r.damage == []


def test_rule_2_only_the_trips_that_use_the_sensor(G):
    r = analyze(G, "LT301", Mode.WRONG_READINGS)
    assert ("SIS", Effect.LOSS_OF_PROTECTION) in by_rule(r, "2")
    assert by_rule(r, "6") == {("Compressor", Effect.LOSS_OF_PROTECTION)}
    assert by_rule(r, "5") == set()


def test_rule_3_down_controller_hides_its_tags(G):
    r = analyze(G, "DCS_Export", Mode.DOWN)
    hidden = {n for n, e in by_rule(r, "3")}
    assert hidden == {"PT501", "FT501", "VT501", "JT901", "PT901", "P501"}


def test_rule_3_down_sis_does_not_hide_pt201(G):
    r = analyze(G, "SIS", Mode.DOWN)
    assert "PT201" not in {n for n, _ in by_rule(r, "3")}
    assert "LT301" in {n for n, _ in by_rule(r, "3")}


def test_rule_4_down_controller_loses_every_actuator(G):
    r = analyze(G, "DCS_Separation", Mode.DOWN)
    assert {n for n, _ in by_rule(r, "4")} == {"HV101", "PV201", "LV201", "LV202"}


def test_rules_5_and_6_down_sis(G):
    r = analyze(G, "SIS", Mode.DOWN)
    assert {n for n, _ in by_rule(r, "5")} == {"SDV101", "BDV201"}
    assert {n for n, _ in by_rule(r, "6")} == {"Compressor", "Export_Pumps"}


def test_loss_of_protection_does_not_spread(G):
    r = analyze(G, "SIS", Mode.DOWN)
    assert not any(i.effect == Effect.PROCESS_IMPACT for i in r.impacts)


def test_rule_7_and_8_actuator_disturbs_downstream(G):
    r = analyze(G, "FV401", Mode.LOST_CONTROL)
    assert by_rule(r, "7") == {("Compressor", Effect.PROCESS_IMPACT)}
    assert by_rule(r, "8") == set()  # nothing downstream of the compressor


def test_rule_9_one_level_upstream_then_rule_8(G):
    r = analyze(G, "Compressor", Mode.STOPPED)
    assert by_rule(r, "9") == {("Scrubber", Effect.PROCESS_IMPACT)}
    assert "Separator" not in r.nodes()  # backflow stops after one level


def test_rules_10_and_11_utility_lost(G):
    r = analyze(G, "Power_Gen", Mode.LOST)
    assert ("Compressor", Effect.STOPPED) in by_rule(r, "11")
    assert ("Instrument_Air", Effect.LOST) in by_rule(r, "11")
    assert ("PV201", Effect.LOSS_OF_CONTROL) in by_rule(r, "10")


def test_rule_12_sensors_never_take_damage(G):
    r = analyze(G, "Separator", Mode.STOPPED)
    sensors = {n for n, t in G.nodes(data="type") if t == "sensor"}
    assert not r.nodes() & sensors


def test_rule_13_firewall_blocks_or_not(G):
    held = analyze(G, "Corporate_IT", Mode.COMPROMISED, firewall_holds=True)
    assert held.nodes() == {"Vendor_Gateway", "Satellite_Link", "Digital_Twin", "IT_OT_Firewall"}
    open_ = analyze(G, "Corporate_IT", Mode.COMPROMISED, firewall_holds=False)
    assert {"EWS", "SIS", "Historian"} <= open_.nodes()


def test_compromised_gives_reach_only(G):
    r = analyze(G, "EWS", Mode.COMPROMISED)
    assert r.damage == [] and r.visibility == []
    assert {"DCS_Separation", "SIS"} <= r.nodes()


def test_path_is_rebuilt_back_to_the_start(G):
    r = analyze(G, "PT201", Mode.WRONG_READINGS)
    assert r.path_to("Compressor") == [
        "PT201", "DCS_Separation", "PV201", "Separator", "Scrubber", "Compressor"]


def test_result_is_json_ready(G):
    d = analyze(G, "PT201", Mode.WRONG_READINGS).to_dict()
    assert d["mode"] == "wrong_readings" and d["impacts"][0]["effect"] == "loss_of_control"


# Scenarios (Scenarios doc, option B each time)


def test_scenario_1_it_ransomware(G):
    reach = analyze(G, "Corporate_IT", Mode.COMPROMISED, firewall_holds=True)
    ot = {n for n, layer in G.nodes(data="layer") if layer <= 3}
    assert not reach.nodes() & ot
    cut = analyze(G, "Satellite_Link", Mode.DOWN)
    assert cut.damage == []
    tags = {n for n, t in G.nodes(data="type") if t in ("sensor", "actuator")}
    assert cut.nodes({Effect.LOSS_OF_VIEW}) >= tags


def test_scenario_2_spoof_pt201(G):
    r = analyze(G, "PT201", Mode.WRONG_READINGS)
    assert effects(r, "PV201") == {Effect.LOSS_OF_CONTROL}
    assert {"Separator", "Scrubber", "Compressor", "Flare"} <= r.nodes({Effect.PROCESS_IMPACT})
    assert r.nodes({Effect.LOSS_OF_PROTECTION}) == {"SIS", "SDV101", "BDV201"}


def test_scenario_3_vendor_remote_access(G):
    reach = analyze(G, "Vendor_Gateway", Mode.COMPROMISED, firewall_holds=False)
    assert {"EWS", "DCS_Separation", "SIS", "SCADA_Server", "HMI", "Historian"} <= reach.nodes()
    damage = analyze(G, "LV201", Mode.LOST_CONTROL)
    assert {"Separator", "Scrubber", "Compressor"} <= damage.nodes({Effect.PROCESS_IMPACT})


def test_scenario_4_satellite_link_loss(G):
    r = analyze(G, "Satellite_Link", Mode.DOWN)
    assert r.damage == [] and r.reach == []
    assert "DCS_Separation" in r.nodes({Effect.LOSS_OF_VIEW})


def test_historian_down_also_blinds_the_twin(G):
    r = analyze(G, "Historian", Mode.DOWN)
    assert "PT201" in r.nodes({Effect.LOSS_OF_VIEW})


def test_hmi_down_does_not_blind_the_twin(G):
    r = analyze(G, "HMI", Mode.DOWN)
    assert r.visibility == []
