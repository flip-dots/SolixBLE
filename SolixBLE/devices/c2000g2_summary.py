"""Field maps for the C2000 Gen 2 ``c490`` device-summary post.

.. moduleauthor:: kb1ibt

The post is a protobuf message built against a schema the device names in
the frame. Each map names the fields of one schema revision by walker
``.path``; ``#1`` marks the second occurrence of a repeated field, which is
the expansion battery's slot. Paths a map doesn't name keep their ``.path``.
"""

from SolixBLE.parsing import SummaryField

#: Energy counters advance one count per 0.9 Wh.
WH_PER_COUNT = 0.9

#: Expansion battery slot marker and the suffix its fields are named with.
EXPANSION_SLOT = "#1"
EXPANSION_SUFFIX = "_expansion"


def _packs(block: str, fields: dict[str, SummaryField]) -> dict[str, SummaryField]:
    """Name a per-pack block's fields for the main and the expansion slot.

    :param block: The block's path, e.g ``.14``.
    :param fields: Subfield path -> field, named for the main pack.
    :returns: Both slots' paths -> fields.
    """
    named: dict[str, SummaryField] = {}
    for sub, field in fields.items():
        named[f"{block}{sub}"] = field
        named[f"{block}{EXPANSION_SLOT}{sub}"] = SummaryField(
            field.name + EXPANSION_SUFFIX,
            field.factor,
            field.array,
            field.signed,
        )
    return named


def _usage_bin(block: str, prefix: str) -> dict[str, SummaryField]:
    """Name one usage bin's on-time and energy counters.

    :param block: The bin's path, e.g ``.19``.
    :param prefix: The prefix its field names take, e.g ``tou_``.
    :returns: The bin's paths -> fields.
    """
    return {
        f"{block}.1": SummaryField(f"{prefix}ac_discharge_posts"),
        f"{block}.2": SummaryField(f"{prefix}ac_charge_posts"),
        f"{block}.3": SummaryField(f"{prefix}ac_input_energy", WH_PER_COUNT),
        f"{block}.4": SummaryField(f"{prefix}ac_output_energy", WH_PER_COUNT),
        f"{block}.5": SummaryField(f"{prefix}dc_discharge_posts"),
        f"{block}.6": SummaryField(f"{prefix}dc_charge_posts"),
        f"{block}.7": SummaryField(f"{prefix}dc_input_energy", WH_PER_COUNT),
        f"{block}.8": SummaryField(f"{prefix}dc_output_energy", WH_PER_COUNT),
    }


_COMMON: dict[str, SummaryField] = {
    **_packs(
        ".14",
        {
            ".1": SummaryField("pack_status", array="u8"),
        },
    ),
    ".14.3": SummaryField("cumulative_charge", 0.1),
    ".14.4": SummaryField("cumulative_discharge", 0.1),
    **_packs(
        ".15",
        {
            ".1": SummaryField("bms_version"),
            ".3": SummaryField("battery_voltage", 0.1),
            ".4": SummaryField("bus_voltage", 0.1),
            ".5": SummaryField("stage_a_state"),
            ".6": SummaryField("stage_b_state"),
            ".8": SummaryField("bms_flags_3f"),
            ".9": SummaryField("bms_flags_43"),
            ".10": SummaryField("bms_flags_47"),
            ".11": SummaryField("bms_flags_4b"),
            ".12": SummaryField("bms_flags_4f"),
        },
    ),
    ".6.7": SummaryField("ac_input_lost_posts"),
    ".6.8": SummaryField("ac_input_loss_count"),
    **_usage_bin(".18", "tou_"),
    **_usage_bin(".19", ""),
    **_usage_bin(".20", "storm_guard_"),
    ".20.9": SummaryField("storm_guard_schedule_active_posts"),
    **_usage_bin(".21", "fast_charging_plan_"),
    ".21.9": SummaryField("fast_charging_plan_schedule_active_posts"),
    ".22": SummaryField("uptime_ticks"),
    ".23.1": SummaryField("battery_percentage"),
    ".23.1#1": SummaryField("battery_percentage_expansion"),
    ".23.2": SummaryField("power_out"),
    ".23.3": SummaryField("ac_power_out"),
    ".23.4": SummaryField("power_in"),
    ".23.5": SummaryField("dc_input_power"),
    ".23.6": SummaryField("dc_input_voltage", 0.01),
    ".23.7": SummaryField("bus_pack_status"),
    ".23.8": SummaryField("time_remaining", 0.1),
    ".23.9": SummaryField("mcu_version"),
    ".23.10": SummaryField("module_version"),
    ".24.1": SummaryField("session_number"),
    ".24.2": SummaryField("screen_menu_use_count"),
    ".24.3": SummaryField("screen_setting_switch_count"),
    ".24.4": SummaryField("display_mode_low_tally"),
    ".24.5": SummaryField("display_mode_medium_tally"),
    ".24.6": SummaryField("display_mode_high_tally"),
    ".24.7": SummaryField("ac_charging_power_low_tally"),
    ".24.8": SummaryField("ac_charging_power_medium_tally"),
    ".24.9": SummaryField("ac_charging_power_high_tally"),
    ".24.10": SummaryField("ac_fast_charge_on_tally"),
    ".24.11": SummaryField("ac_fast_charge_off_tally"),
    ".24.12": SummaryField("port_memory_on_tally"),
    ".24.13": SummaryField("port_memory_off_tally"),
    ".24.14": SummaryField("setting_change_count"),
    ".24.15": SummaryField("display_mode_change_count"),
    ".24.16": SummaryField("ac_charging_power_change_count"),
    ".24.17": SummaryField("ac_fast_charge_change_count"),
    ".24.18": SummaryField("port_memory_change_count"),
}

_FIELDS_0005: dict[str, SummaryField] = {
    ".1": SummaryField("encoder_model"),
    ".2": SummaryField("encoder_reserved"),
    **_COMMON,
}
"""``charging_pps_series_c_0005``: the schema through firmware v1.2.1.1.

Its expansion slot repeats the main pack's ``.14`` counters, and the main
pack's ``.14.2`` / ``.5`` / ``.6`` read 0, so those keep their ``.path``.
"""

_FIELDS_0009: dict[str, SummaryField] = {
    **_COMMON,
    ".14#1.3": SummaryField("cumulative_charge_expansion", 0.1),
    ".14#1.4": SummaryField("cumulative_discharge_expansion", 0.1),
    **_packs(
        ".14",
        {
            ".2": SummaryField("raw_soc", 0.1),
            ".5": SummaryField("battery_health", 0.1),
            ".6": SummaryField("cycle_count"),
            ".15": SummaryField("cell_voltages", array="u16le"),
            ".16": SummaryField("temperatures", array="u16le"),
            ".18": SummaryField("displayed_soc", 0.1),
            ".19": SummaryField("estimated_soc", 0.1),
            ".20": SummaryField("max_cell_soc_integral", 0.1),
            ".21": SummaryField("min_cell_soc_integral", 0.1),
            ".22": SummaryField("learned_capacity", 0.1),
            ".23": SummaryField("cell_balancing"),
            ".24": SummaryField("soc_reserve", 0.1),
            ".25": SummaryField("counter_page"),
            ".26": SummaryField("counter_page_hours"),
            ".27": SummaryField("capacity_learn_armed"),
            ".28": SummaryField("pack_reserved"),
            ".29": SummaryField("battery_current", 0.01, signed=True),
            ".30": SummaryField("port_status_bits"),
            ".31": SummaryField("bms_power_in"),
            ".32": SummaryField("bms_power_out"),
        },
    ),
}
"""``charging_pps_series_c_0009``: the schema from firmware v1.2.1.6.

Each pack block gains the state-of-charge cluster, health, cells,
temperatures, capacity learning and live current and power, and the
expansion slot carries its own coulomb counters.
"""

SUMMARY_MAPS: dict[str, dict[str, SummaryField]] = {
    "charging_pps_series_c_0005": _FIELDS_0005,
    "charging_pps_series_c_0009": _FIELDS_0009,
}
"""Field map for each ``c490`` schema revision, keyed by the frame's schema name."""
