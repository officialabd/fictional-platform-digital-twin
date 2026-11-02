"""Mass balance model of the platform: Purdue level 0.

Valves set the flows, and the flows change what is inside each vessel. Flows are in m3/h or Sm3/h.
This module only knows the true state. Noise and spoofing happen later, in sensors.py.
"""

from dataclasses import dataclass, field

from simulator import config


def _normal_positions() -> dict[str, float]:
    loop_outputs = {actuator: loop.normal_output_pct for actuator, loop in config.LOOPS.items()}
    return {"HV101": config.HV101_NORMAL_PCT, "SDV101": 100.0, "BDV201": 0.0, **loop_outputs}


def _normal_gas_sm3() -> float:
    gas_space_m3 = config.SEPARATOR_M3 - config.NORMAL_OIL_M3 - config.NORMAL_WATER_M3
    return config.NORMAL_PRESSURE_BARA * gas_space_m3


@dataclass
class ProcessState:
    """The true state of the plant. The defaults are the steady state, so nothing jumps at t=0."""

    oil_m3: float = config.NORMAL_OIL_M3
    water_m3: float = config.NORMAL_WATER_M3
    gas_sm3: float = field(default_factory=_normal_gas_sm3)
    scrubber_m3: float = config.SCRUBBER_NORMAL_M3
    separator_temp_c: float = config.SEPARATOR_TEMP_C
    air_barg: float = config.AIR_NORMAL_BARG
    air_supply_ok: bool = True
    positions: dict[str, float] = field(default_factory=_normal_positions)
    compressor_running: bool = True
    pumps_running: bool = True
    psv_open: bool = False
    gas_lel: dict[str, float] = field(
        default_factory=lambda: {"GD801": config.NORMAL_GAS_LEL, "GD802": config.NORMAL_GAS_LEL}
    )
    fire: bool = False

    @property
    def liquid_m3(self) -> float:
        return self.oil_m3 + self.water_m3

    @property
    def gas_space_m3(self) -> float:
        return max(config.SEPARATOR_M3 - self.liquid_m3, config.MIN_GAS_SPACE_M3)

    @property
    def pressure_bara(self) -> float:
        # Ideal gas at constant temperature
        return self.gas_sm3 / self.gas_space_m3

    @property
    def pressure_barg(self) -> float:
        return self.pressure_bara - config.ATM_BAR

    @property
    def level_pct(self) -> float:
        return self.liquid_m3 / config.SEPARATOR_M3 * 100

    @property
    def water_level_pct(self) -> float:
        return self.water_m3 / config.SEPARATOR_M3 * 100

    @property
    def scrubber_pct(self) -> float:
        return self.scrubber_m3 / config.SCRUBBER_M3 * 100


@dataclass(frozen=True)
class Flows:
    inflow: float
    oil_in: float
    water_in: float
    gas_in: float
    oil_out: float
    water_out: float
    gas_through_pv: float
    gas_through_bdv: float
    gas_through_psv: float
    compressor: float
    flare: float

    @property
    def gas_out(self) -> float:
        return self.gas_through_pv + self.gas_through_bdv + self.gas_through_psv


def compute_flows(state: ProcessState) -> Flows:
    opening = {name: pct / 100 for name, pct in state.positions.items()}
    inflow = config.CHOKE_M3H_PER_PCT * state.positions["HV101"] * opening["SDV101"]
    oil_in = inflow * config.OIL_SHARE
    water_in = inflow - oil_in

    pressure_factor = state.pressure_bara / config.GAS_REF_BARA
    gas_through_pv = config.PV201_SM3H * opening["PV201"] * pressure_factor
    gas_through_bdv = config.BDV201_SM3H * opening["BDV201"] * pressure_factor
    gas_through_psv = 0.0
    if state.psv_open:
        gas_through_psv = config.PSV_SM3H * state.pressure_bara / config.PSV_REF_BARA

    gas_after_fuel = max(gas_through_pv - config.FUEL_GAS_SM3H, 0.0)
    flare = config.FLARE_PURGE_SM3H + gas_through_bdv + gas_through_psv
    if state.compressor_running:
        compressor = gas_after_fuel + config.FV401_SM3H * opening["FV401"]
    else:
        # A stopped compressor sends the gas through PV201 to the flare (a simplification), so
        # pressure stays controlled and "degraded with flaring" differs from a full shutdown.
        flare += gas_after_fuel
        compressor = 0.0

    # There is no buffer tank before the pumps, so stopped pumps block the oil outlet
    pumping = state.positions["P501"] > 0

    return Flows(
        inflow=inflow,
        oil_in=oil_in,
        water_in=water_in,
        gas_in=oil_in * config.GAS_SM3_PER_M3_OIL,
        oil_out=config.LV201_M3H * opening["LV201"] if pumping else 0.0,
        water_out=config.LV202_M3H * opening["LV202"],
        gas_through_pv=gas_through_pv,
        gas_through_bdv=gas_through_bdv,
        gas_through_psv=gas_through_psv,
        compressor=compressor,
        flare=flare,
    )


def move_actuators(
    state: ProcessState, targets: dict[str, float], stuck: set[str], dt: float
) -> None:
    """Move each actuator toward its target, no faster than its stroke rate."""
    for name, target in targets.items():
        if name in stuck:
            continue
        if name == "P501" and not state.pumps_running:
            target = 0.0
        if name in config.SHUTDOWN_VALVES:
            max_step = config.SHUTDOWN_VALVE_PCT_PER_S * dt
        else:
            max_step = config.CONTROL_VALVE_PCT_PER_S * dt
        current = state.positions[name]
        state.positions[name] = current + max(-max_step, min(max_step, target - current))


def advance(state: ProcessState, dt: float) -> None:
    """Advance the true state by one time step."""
    flows = compute_flows(state)
    hours = dt / 3600

    if not state.air_supply_ok:
        state.air_barg = max(0.0, state.air_barg - config.AIR_DECAY_BAR_PER_S * dt)

    state.oil_m3 = max(0.0, state.oil_m3 + (flows.oil_in - flows.oil_out) * hours)
    state.water_m3 = max(0.0, state.water_m3 + (flows.water_in - flows.water_out) * hours)
    overfill = state.liquid_m3 - (config.SEPARATOR_M3 - config.MIN_GAS_SPACE_M3)
    if overfill > 0:
        state.oil_m3 -= overfill

    # An open outlet cannot pull the separator below atmospheric pressure
    state.gas_sm3 = max(
        state.gas_sm3 + (flows.gas_in - flows.gas_out) * hours,
        config.ATM_BAR * state.gas_space_m3,
    )

    # The PSV is mechanical: it only responds to true pressure, no cyber input can stop it
    if state.pressure_barg >= config.PSV_OPEN_BARG:
        state.psv_open = True
    elif state.pressure_barg <= config.PSV_RESEAT_BARG:
        state.psv_open = False

    carryover = max(0.0, state.level_pct - config.CARRYOVER_START_PCT)
    scrubber_in = config.SCRUBBER_BASE_IN_M3H + carryover * config.CARRYOVER_M3H_PER_PCT
    scrubber_out = config.SCRUBBER_DRAIN_PER_H * state.scrubber_m3
    state.scrubber_m3 += (scrubber_in - scrubber_out) * hours
    state.scrubber_m3 = min(max(state.scrubber_m3, 0.0), config.SCRUBBER_M3)

    if flows.inflow > config.MIN_FLOWING_M3H:
        target_c, tau_s = config.SEPARATOR_TEMP_C, config.HEATING_TAU_S
    else:
        target_c, tau_s = config.AMBIENT_TEMP_C, config.COOLING_TAU_S
    state.separator_temp_c += (target_c - state.separator_temp_c) * dt / tau_s


def true_values(state: ProcessState) -> dict[str, float]:
    """The true value of every tag: all 29 sensors and all 8 actuator positions."""
    flows = compute_flows(state)
    separator_barg = state.pressure_barg
    suction_barg = max(separator_barg - config.COMPRESSOR_SUCTION_DROP_BAR, 0.0)

    running = state.compressor_running
    compressor_mw = 0.0
    if running:
        compressor_mw = config.COMPRESSOR_POWER_MW * flows.compressor / config.COMPRESSOR_REF_SM3H
    compressor_vibration = 0.0
    if running:
        compressor_vibration = config.COMPRESSOR_VIBRATION_MM_S
        if state.scrubber_pct > config.LIQUID_REACHES_COMPRESSOR_PCT:
            compressor_vibration += config.LIQUID_IN_COMPRESSOR_VIBRATION_MM_S

    pump_speed = state.positions["P501"]
    pump_ratio = pump_speed / config.PUMP_REF_SPEED_PCT
    low_interface = max(0.0, config.OIL_ESCAPES_BELOW_LT202_PCT - state.water_level_pct)

    return {
        "PT101": config.MANIFOLD_SHUT_IN_BARG
        - config.MANIFOLD_DROP_AT_NORMAL_FLOW_BAR * flows.inflow / config.NORMAL_INFLOW_M3H,
        "TT101": config.MANIFOLD_TEMP_C,
        "FT101": flows.inflow,
        "PT201": separator_barg,
        "TT201": state.separator_temp_c,
        "LT201": state.level_pct,
        "LT202": state.water_level_pct,
        "LSHH201": config.SWITCH_ON if state.level_pct >= config.LSHH201_PCT else 0.0,
        "FT201": flows.gas_through_pv,
        "FT202": flows.oil_out,
        "FT203": flows.water_out,
        "LT301": state.scrubber_pct,
        "PT401": suction_barg,
        "PT402": config.COMPRESSOR_DISCHARGE_BARG if running else suction_barg,
        "TT401": config.COMPRESSOR_HOT_C if running else config.COMPRESSOR_COLD_C,
        "FT401": flows.compressor,
        "VT401": compressor_vibration,
        "JT401": compressor_mw,
        "PT501": separator_barg + config.PUMP_HEAD_BAR * pump_ratio**2,
        "FT501": flows.oil_out,
        "VT501": config.PUMP_VIBRATION_MM_S if pump_speed > 0 else 0.0,
        "AT601": config.OIL_IN_WATER_NORMAL_MG_L + config.OIL_IN_WATER_MG_L_PER_PCT * low_interface,
        "FT601": flows.water_out,
        "FT701": flows.flare,
        "GD801": state.gas_lel["GD801"],
        "GD802": state.gas_lel["GD802"],
        "FD801": config.SWITCH_ON if state.fire else 0.0,
        "JT901": config.BASE_LOAD_MW + compressor_mw + config.PUMP_POWER_MW * pump_ratio**3,
        "PT901": state.air_barg,
        **state.positions,
    }
