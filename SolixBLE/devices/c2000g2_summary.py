"""Field maps for the C2000 G2 ``c490`` device-summary post.

.. moduleauthor:: kb1ibt

The post is a protobuf message the device builds against a schema it fetches
from the vendor cloud, and it names that schema in the frame. Each map below
names the fields of one schema revision by walker ``.path``; ``#1`` marks the
second occurrence of a repeated field, which is the expansion battery's slot.
"""

from ..parsing import SummaryField

_FIELDS_0005: dict[str, SummaryField] = {
    ".14.3": SummaryField("cumulative_charge_ah", 0.1),
    ".14.4": SummaryField("cumulative_discharge_ah", 0.1),
    ".15.1": SummaryField("bms_version"),
    ".15.3": SummaryField("battery_voltage", 0.1),
    ".15.4": SummaryField("bus_voltage", 0.1),
    ".15#1.1": SummaryField("exp_1_bms_version"),
    ".15#1.3": SummaryField("exp_1_battery_voltage", 0.1),
    ".15#1.4": SummaryField("exp_1_bus_voltage", 0.1),
    ".19.1": SummaryField("ac_discharge_active_posts"),
    ".19.2": SummaryField("ac_charge_active_posts"),
    ".19.3": SummaryField("ac_charge_energy_wh", 0.9),
    ".19.4": SummaryField("ac_discharge_energy_wh", 0.9),
    ".19.5": SummaryField("dc_discharge_active_posts"),
    ".19.6": SummaryField("dc_charge_active_posts"),
    ".19.7": SummaryField("dc_charge_energy_wh", 0.9),
    ".19.8": SummaryField("dc_discharge_energy_wh", 0.9),
    ".22": SummaryField("uptime_ticks"),
    ".23.1": SummaryField("battery_soc"),
    ".23.1#1": SummaryField("exp_1_soc"),
    ".23.2": SummaryField("output_power_total"),
    ".23.3": SummaryField("ac_output_power"),
    ".23.4": SummaryField("input_power_total"),
    ".23.5": SummaryField("dc_input_power_total"),
    ".23.6": SummaryField("dc_input_voltage", 0.01),
    ".23.7": SummaryField("working_status"),
    ".23.8": SummaryField("remaining_time_hours", 0.1),
    ".23.9": SummaryField("mcu_version"),
    ".23.10": SummaryField("module_version"),
}
"""``charging_pps_series_c_0005``: the schema through firmware v1.2.1.1."""

_FIELDS_0009: dict[str, SummaryField] = {
    **_FIELDS_0005,
    ".14.2": SummaryField("pack_soc_raw", 0.1),
    ".14.15": SummaryField("cell_voltage", array="u16le"),
    ".14.16": SummaryField("pack_temp", array="u16le"),
    ".14.18": SummaryField("pack_soc", 0.1),
    ".14#1.2": SummaryField("exp_1_pack_soc_raw", 0.1),
    ".14#1.3": SummaryField("exp_1_cumulative_charge_ah", 0.1),
    ".14#1.4": SummaryField("exp_1_cumulative_discharge_ah", 0.1),
    ".14#1.15": SummaryField("exp_1_cell_voltage", array="u16le"),
    ".14#1.16": SummaryField("exp_1_pack_temp", array="u16le"),
    ".14#1.18": SummaryField("exp_1_pack_soc", 0.1),
}
"""``charging_pps_series_c_0009``: from firmware v1.2.1.6, a superset of ``_0005``.

The per-pack block gains the raw and displayed state of charge, the 16 cell
voltages and 4 pack temperatures, and the expansion battery's own coulomb
counters (which mirror the main pack on ``_0005``).
"""

SUMMARY_MAPS: dict[str, dict[str, SummaryField]] = {
    "charging_pps_series_c_0005": _FIELDS_0005,
    "charging_pps_series_c_0009": _FIELDS_0009,
}
"""Field map for each ``c490`` schema revision, keyed by the frame's schema name."""
