"""C2000G2 power station device tests.

.. moduleauthor:: kb1ibt

The frames are real A1783 captures with the serial numbers, the ``fe``
timestamps and the ``fd`` transaction ids replaced by placeholders.
"""

from datetime import datetime

import pytest

from SolixBLE.constructs import Parameters
from SolixBLE.devices.c1000g2 import (
    DisplayLanguage,
    DisplayPlan,
    TariffType,
    TouPeriod,
)
from SolixBLE.devices.c2000g2 import (
    C2000G2,
    AcInputState,
    BmsFault,
    DeviceEventType,
    OtaBlockReason,
)
from SolixBLE.states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus

#: A c421 from MainMcu v1.2.1.6 (``_0009`` era), a BP2000 attached at 42 %,
#: idle, mains unplugged (AC input auto-off), outage alert on.
C421_0009 = "a10131a221062011415043444b4b453030303030303030303100054131373833060102010001a30e040000010108070064cc00580200a4220400000000b0043c00000000000000003c000300010000015f050000000000000a00a50604130064e800a60a040000000000006e1464a70704000000000000a80404000000aa0404000000ab0404010000ac0404000000ae0404000000b20404000000c02c0411415043444b4a4d30303030303030303031010303090113002ae801010001000a41313738335f326b5768ce2c0410000000000000000000000000000000000111000000000000000000000000000000000000000000000000d9230400000a5f0503030012011215031518000000a810af6affffffff0000000000000000da18048100000000000000000001e00138047f0101013804e001dc06040000000000f91d0406010201060201000000000000000000030309010303090100030300fa150401010101001f3500000000000000000000000000fd0e0031373637323235363030303030fe050300b95569"  # noqa: E501

#: The same snapshot as C421_0009, as the reply to a 4100 poll.
C900_0009 = "00" + C421_0009

#: A c421 from MainMcu v1.2.1.1 (26-byte settings), charging from mains at
#: 1211 W with the AC output on.
C421_0005 = "a10131a221062011415043444b4b453030303030303030303100054131373833010102010001a30e040200010108070064cc00580200a41b0400000000b0043c00000000000000002c01020001000101640500a506042002580000a60a040000bb040000060058a7070401000001bb04a80404000000aa0404000000ab0404000000ac0404000000ae0404000000b20404000000c02c0411415043444b4a4d3030303030303030303101020209012000550001010001000a41313738335f326b5768ce2c0410000000000000000000000000000000000111000000000000000000000000000000000000000000000000d91a040000196405000000009c9d886aacab886a0000000000000000da18048100000000000000000001e00138047f0101013804e001dc06040000000000f91d0401010201060201000000000006020100020209010202090106000300fa150401010101001f0700000000000000000000000000fd0e0031373637323235363030303030fe050300b95569"  # noqa: E501

#: A c490 device summary on schema ``charging_pps_series_c_0009``.
C490_0009 = "a10131a2560204320538b710400d72b0010a200000000075401d61894800005212000100013c0000010001000000008000000010de0718d83e20d33228e80730147a20030d020d020d030d020d030d020d030d040d040d040d030d030d050d040d050d820108720b730b6c0b770b9001e8079801de07a001df07a801c807b001ef02b80100c0010fc80103d001c503d80100e201200000000000000000000000000000000000000000000000000000000000000000e80100f00110f8010080020072b0010a200000000075101861890000007d01000000012c00000000000000000080000000109c0118c31320f21028e80730067a20a90ca90caa0ca80ca90ca90ca90ca90caa0ca90ca90caa0cac0cab0cac0cac0c8201086a0b700b6f0b6d0b9001ab0398018c01a001a501a8019b01b0018e03b80100c00110c80100d001c303d80101e201200000000000000000000000000000000000000000000000000000000000000000e80103f00110f801008002007a1b088d0f1002189504208604280330033800400048005000580060007a1b088d0f100218860420860428083009380040004800500058006000920110080010001800200028003000380040009a011e088c9a0210af0218b5d00520bff70228aa8c0130a70738838c0140afe401a2011608ee01100018e40220c101281330003800400048ee01aa011308001000183b2000280030003800400348ee01b001f8f602ba01190864082a1000180020002800302b380040ee2848c00950ca02c20127080c10041801200028023000380040004800500058006000680070007800800100880100900100a31c046368617267696e675f7070735f7365726965735f635f3030303900"  # noqa: E501

#: A c490 device summary on schema ``charging_pps_series_c_0005``.
C490_0005 = "a10131a25801040a0541313736331200320538b210400c722e0a200000040075011de1884900005211010000003c00000100010000000080000000100018b53a20b62f28003000722e0a200000040075111861890100007d01000000002c00000000000000000080000000100018b53a20b62f280030007a1b08820f100218a50420a504280830093800400048005000580060007a1b08820f100218960420a50428033003380040004800500058006000920110080010001800200028003000380040009a011d08b1960210ea01189de40420bff70228d66e30a70738838c0140b59e01a2011608ee01100018e40220c101281330003800400048ee01aa01130800100018002000280030003800400048ee01b001f2d302ba0119085b08551000180020ba092800302b3802400548bb0950b202c20127080a10031801200028023000380040004800500058006000680070007800800100880100900100a31c046368617267696e675f7070735f7365726965735f635f3030303500"  # noqa: E501

#: C490_0009 renamed to a schema no field map knows.
C490_UNKNOWN_SCHEMA = C490_0009.replace(b"_0009".hex(), b"_9999".hex())

#: Epochs of the Fast Charging Plan windows the frames above store.
PLAN_START = 0x6AAF10A8
PLAN_0005_START = 0x6A889D9C
PLAN_0005_END = 0x6A88ABAC

#: Firmware-update readiness replies to 4089, allowed and blocked.
OTA_REPLY_ALLOWED = "00a10131a2020101a3020100a4020128a502010fa602010ffd1000313736373232353630303030300000"  # noqa: E501
OTA_REPLY_BLOCKED = "00a10131a2020100a3020102a4020128a502010fa602010ffd1000313736373232353630303030300000"  # noqa: E501

#: Clock-screen read reply to 4092, for a theme with no name.
THEME_NAME_REPLY = "00a10131a211048100000000000000000001e00138047fa30104"

########################
# Test device commands #
########################

# See test_send_command() in test_commands.py.

C2000G2_TEST_COMMANDS = [
    pytest.param(
        C2000G2,
        "_post_connect",
        [],
        [("4100", "a10121"), ("4057", "a10121a2020101")],
        id="c2000g2_subscribe_and_stream",
    ),
    pytest.param(
        C2000G2,
        "turn_display_on",
        [],
        [("4103", "a10121a2020101")],
        id="c2000g2_display_on",
    ),
    pytest.param(
        C2000G2,
        "turn_display_off",
        [],
        [("4103", "a10121a2020100")],
        id="c2000g2_display_off",
    ),
    pytest.param(
        C2000G2,
        "set_display_mode",
        [LightStatus.LOW],
        [("4103", "a10121a3020101")],
        id="c2000g2_display_mode_low",
    ),
    pytest.param(
        C2000G2,
        "set_display_mode",
        [LightStatus.OFF],
        [("4103", "a10121a2020100")],
        id="c2000g2_display_mode_off",
    ),
    pytest.param(
        C2000G2,
        "set_display_mode",
        [LightStatus.SOS],
        ValueError,
        id="c2000g2_display_mode_sos",
    ),
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.S60],
        [("4103", "a10121a403023c00")],
        id="c2000g2_display_timeout_60",
    ),
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.UNKNOWN],
        ValueError,
        id="c2000g2_display_timeout_unknown",
    ),
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.S10],
        [("4103", "a10121a403020a00")],
        id="c2000g2_display_timeout_10",
    ),
    pytest.param(
        C2000G2,
        "set_display_language",
        [DisplayLanguage.JAPANESE],
        [("4103", "a10121a9020104")],
        id="c2000g2_display_language",
    ),
    pytest.param(
        C2000G2,
        "set_display_language",
        [DisplayLanguage.UNKNOWN],
        ValueError,
        id="c2000g2_display_language_unknown",
    ),
    pytest.param(
        C2000G2,
        "set_display_plan",
        [None],
        ValueError,
        id="c2000g2_display_plan_before_telemetry",
    ),
    pytest.param(
        C2000G2,
        "set_max_battery_percentage",
        [95],
        [("4103", "a10121aa02015f")],
        id="c2000g2_max_battery",
    ),
    pytest.param(
        C2000G2,
        "set_max_battery_percentage",
        [101],
        ValueError,
        id="c2000g2_max_battery_out_of_range",
    ),
    pytest.param(
        C2000G2,
        "set_min_battery_percentage",
        [5],
        [("4103", "a10121ab020105")],
        id="c2000g2_min_battery",
    ),
    pytest.param(
        C2000G2,
        "set_ac_timer",
        [1200],
        [("4101", "a10121a30503b0040000")],
        id="c2000g2_ac_timer",
    ),
    pytest.param(
        C2000G2,
        "set_dc_timer",
        [7200],
        [("4102", "a10121a30503201c0000")],
        id="c2000g2_dc_timer",
    ),
    pytest.param(
        C2000G2,
        "set_ac_charging_power",
        [1200],
        [("4101", "a10121a40302b004")],
        id="c2000g2_ac_charging_power",
    ),
    pytest.param(
        C2000G2,
        "set_ac_charging_power",
        [0],
        ValueError,
        id="c2000g2_ac_charging_power_zero",
    ),
    pytest.param(
        C2000G2,
        "turn_ac_fast_charge_on",
        [],
        [("4101", "a10121a7020101")],
        id="c2000g2_fast_charge_on",
    ),
    pytest.param(
        C2000G2,
        "turn_ac_fast_charge_off",
        [],
        [("4101", "a10121a7020100")],
        id="c2000g2_fast_charge_off",
    ),
    pytest.param(
        C2000G2,
        "turn_ac_input_off",
        [],
        [("4101", "a10121ab03020100")],
        id="c2000g2_ac_input_off",
    ),
    pytest.param(
        C2000G2,
        "turn_ac_input_on",
        [],
        [("4101", "a10121ab03020000")],
        id="c2000g2_ac_input_on",
    ),
    pytest.param(
        C2000G2,
        "turn_outage_alert_on",
        [],
        [("4103", "a10121b0020101")],
        id="c2000g2_outage_alert_on",
    ),
    pytest.param(
        C2000G2,
        "turn_outage_alert_off",
        [],
        [("4103", "a10121b0020100")],
        id="c2000g2_outage_alert_off",
    ),
    pytest.param(
        C2000G2,
        "turn_fast_charging_plan_on",
        [],
        [("405e", "a10121a3020103a4020100a5020101")],
        id="c2000g2_fast_charging_plan_on",
    ),
    pytest.param(
        C2000G2,
        "turn_fast_charging_plan_off",
        [],
        [("405e", "a10121a3020103a4020100a5020100")],
        id="c2000g2_fast_charging_plan_off",
    ),
    pytest.param(
        C2000G2,
        "turn_storm_guard_on",
        [],
        [("405e", "a10121a3020103a4020101a5020101")],
        id="c2000g2_storm_guard_on",
    ),
    pytest.param(
        C2000G2,
        "turn_storm_guard_off",
        [],
        [("405e", "a10121a3020103a4020101a5020100")],
        id="c2000g2_storm_guard_off",
    ),
    pytest.param(
        C2000G2,
        "set_fast_charging_plan_window",
        [datetime.fromtimestamp(1767225600)],  # noqa: DTZ006
        [("405e", "a10121a3020103a4020100a5020101a6020101a70b04640000b95569ffffffff")],
        id="c2000g2_fast_charging_plan_window_no_end",
    ),
    pytest.param(
        C2000G2,
        "set_fast_charging_plan_window",
        [
            datetime.fromtimestamp(1767225600),  # noqa: DTZ006
            datetime.fromtimestamp(1767225600),  # noqa: DTZ006
        ],
        ValueError,
        id="c2000g2_fast_charging_plan_window_empty",
    ),
]

C2000G2_TEST_COMMANDS_RESPONSES = [
    pytest.param(
        C2000G2,
        "get_status_update",
        [],
        [("4100", "a10121")],
        [("03010f", "c900", C900_0009)],
        Parameters.parse(bytes.fromhex(C900_0009)),
        id="c2000g2_status_update",
    ),
    pytest.param(
        C2000G2,
        "get_status_update",
        [],
        [("4100", "a10121")],
        [("03010f", "c900", None)],
        TimeoutError,
        id="c2000g2_status_update_timeout",
    ),
    pytest.param(
        C2000G2,
        "get_ota_status",
        [],
        [("4089", "a10121")],
        [("03010f", "c889", OTA_REPLY_ALLOWED)],
        True,
        id="c2000g2_ota_allowed",
    ),
    pytest.param(
        C2000G2,
        "get_ota_status",
        [],
        [("4089", "a10121")],
        [("03010f", "c889", OTA_REPLY_BLOCKED)],
        False,
        id="c2000g2_ota_blocked",
    ),
    pytest.param(
        C2000G2,
        "get_display_theme_name",
        [],
        [("4092", "a10121")],
        [("03010f", "c892", THEME_NAME_REPLY)],
        "",
        id="c2000g2_theme_name_empty",
    ),
]

######################
# Test device values #
######################

# See test_values() in test_devices.py.

C2000G2_TEST_VALUES = [
    pytest.param(
        C2000G2,
        C421_0009,
        {
            "serial_number": "APCDKKE0000000001",
            "part_number": "A1783",
            "software_version": "1.2.1.6",
            "software_version_controller": "0.1.2.6",
            "software_version_inverter": "0.0.0.0",  # noqa: S104  # a version, not an address
            "software_version_bms": "1.9.3.3",
            "software_version_module": "0.3.3.0",
            "capabilities": frozenset(
                {
                    "ac_energy_mode",
                    "car_charge_mode",
                    "parallel_upgrade",
                    "get_upgrade_info",
                    "transaction_id",
                    "memory_switch",
                    "backup_disaster",
                    "upgrade_record",
                    "screen_time_period",
                    "pps_tou",
                    "silent_recharge",
                    "ac_input_disable",
                },
            ),
            "temperature": 19,
            "battery_percentage": 100,
            "battery_health": -1,
            "charging_status": ChargingStatus.IDLE,
            "charging_status_main": ChargingStatus.IDLE,
            "firmware_updating": False,
            "time_remaining": 523.0,
            "hours_remaining": 19.0,
            "days_remaining": 21,
            "max_battery_percentage": 95,
            "min_battery_percentage": 5,
            "memory_switch_error": BmsFault.NONE,
            "memory_switch_error_time": None,
            "num_expansion": 1,
            "serial_number_expansion": "APCDKJM0000000001",
            "temperature_expansion": 19,
            "battery_percentage_expansion": 42,
            "battery_health_expansion": -1,
            "expansion_output_on": True,
            "software_version_expansion": "1.9.3.3",
            "power_out": 0,
            "ac_power_in": 0,
            "ac_output": PortStatus.NOT_CONNECTED,
            "ac_power_out": 0,
            "ac_input_port": PortStatus.NOT_CONNECTED,
            "ac_input_state": AcInputState.AUTO_OFF,
            "dc_input_port": PortStatus.NOT_CONNECTED,
            "solar_port": PortStatus.NOT_CONNECTED,
            "dc_input_power": 0,
            "solar_power_in": 0,
            "usb_port_c1": PortStatus.NOT_CONNECTED,
            "usb_c1_power": 0,
            "usb_port_c2": PortStatus.OUTPUT,
            "usb_c2_power": 0,
            "usb_port_c3": PortStatus.NOT_CONNECTED,
            "usb_port_a1": PortStatus.NOT_CONNECTED,
            "dc_output": PortStatus.NOT_CONNECTED,
            "dc_power_out": 0,
            "max_input_power": 1800,
            "ac_timer_remaining": 0,
            "ac_timer": None,
            "dc_timer_remaining": 0,
            "dc_timer": None,
            "ac_charging_power": 1200,
            "ac_frequency": 60,
            "ac_fast_charge_enabled": False,
            "power_saving_mode_enabled": False,
            "dc_power_saving_mode_enabled": False,
            "port_memory_enabled": True,
            "device_timeout": 0,
            "is_display_on": False,
            "display_mode": LightStatus.HIGH,
            "display_timeout": 60,
            "display_language": DisplayLanguage.ENGLISH,
            "outage_alert_enabled": True,
            "display_plan": DisplayPlan(
                screensaver_enabled=True,
                clock_theme=2,
                clock_24h=True,
                day_start=480,
                day_end=1080,
                weekdays=frozenset(range(7)),
                night_enabled=True,
                day_brightness=20,
                night_brightness=20,
                night_start=1080,
                night_end=480,
            ),
            "tou_enabled": False,
            "active_tariff": TariffType.NONE,
            "reserve_battery_percentage": 10,
            "tou_periods": [
                TouPeriod(TariffType.OFF_PEAK, 0, 18),
                TouPeriod(TariffType.PEAK, 18, 21),
                TouPeriod(TariffType.OFF_PEAK, 21, 24),
            ],
            "fast_charging_plan_enabled": False,
            "storm_guard_enabled": False,
            "fast_charging_plan_window": (
                datetime.fromtimestamp(PLAN_START),  # noqa: DTZ006
                None,
            ),
            "backup_window": None,
            "last_event": None,
            "ota_allowed": None,
            "ota_block_reason": OtaBlockReason.UNKNOWN,
            "summary": {},
            "summary_schema": None,
            "ac_charged_energy": None,
            "dc_input_voltage": None,
        },
        id="c2000g2_0009_idle",
    ),
    pytest.param(
        C2000G2,
        C421_0005,
        {
            "software_version": "1.2.1.1",
            "software_version_inverter": "0.1.2.6",
            "software_version_module": "0.3.0.6",
            "software_version_expansion": "1.9.2.2",
            "temperature": 32,
            "battery_percentage": 88,
            "battery_percentage_expansion": 85,
            "charging_status": ChargingStatus.CHARGING,
            "charging_status_main": ChargingStatus.CHARGING,
            "time_remaining": 0.6,
            "hours_remaining": 0.6,
            "days_remaining": 0,
            "ac_output": PortStatus.OUTPUT,
            "ac_power_in": 1211,
            "ac_input_port": PortStatus.INPUT,
            "ac_input_state": AcInputState.UNKNOWN,
            "outage_alert_enabled": None,
            "display_mode": LightStatus.MEDIUM,
            "display_timeout": 300,
            "is_display_on": True,
            "max_battery_percentage": 100,
            "reserve_battery_percentage": 25,
            "tou_periods": [],
            "fast_charging_plan_window": (
                datetime.fromtimestamp(PLAN_0005_START),  # noqa: DTZ006
                datetime.fromtimestamp(PLAN_0005_END),  # noqa: DTZ006
            ),
        },
        id="c2000g2_0005_ac_charging",
    ),
]

#####################################
# Test device summaries and pushes #
#####################################

# See test_c2000g2.py.

C2000G2_TEST_SUMMARIES = [
    pytest.param(
        C421_0009,
        C490_0009,
        {
            "summary_schema": "charging_pps_series_c_0009",
            "battery_health": 100,
            "battery_health_expansion": 100,
            "ac_charged_energy": 82.9917,
            "dc_charged_energy": 16.1307,
            "ac_output_energy": 43.2567,
            "dc_output_energy": 26.3079,
            "dc_input_voltage": 0.43,
        },
        {
            "battery_percentage": 100,
            "battery_percentage_expansion": 42,
            "battery_health": 100.0,
            "cycle_count": 20,
            "cumulative_charge": 802.4,
            "learned_capacity_expansion": 39.8,
            "battery_current": 0.0,
            "cell_voltages": [
                3331,
                3330,
                3330,
                3331,
                3330,
                3331,
                3330,
                3331,
                3332,
                3332,
                3332,
                3331,
                3331,
                3333,
                3332,
                3333,
            ],
            "pack_reserved": "00" * 32,
            "bms_flags_3f_expansion": 0,
            ".15.2": 2,
        },
        id="c2000g2_summary_0009",
    ),
    pytest.param(
        C421_0005,
        C490_0005,
        {
            "summary_schema": "charging_pps_series_c_0005",
            "battery_health": -1,
            "battery_health_expansion": -1,
            "ac_charged_energy": 70.5285,
            "dc_input_voltage": 0.43,
        },
        {
            "encoder_model": "A1763",
            "encoder_reserved": "",
            ".14.5": 0,
            ".15.7": 0,
        },
        id="c2000g2_summary_0005",
    ),
]

C2000G2_TEST_PUSHES = [
    pytest.param(
        "4425",
        "a10131a2020159a302045c",
        {
            "last_event.event": DeviceEventType.GRID_LOSS,
            "last_event.code": 0x59,
            "last_event.battery_percentage": 92,
            "last_event.start": None,
            "last_event.end": None,
        },
        id="c2000g2_event_grid_loss",
    ),
    pytest.param(
        "0425",
        "a10112a202010aa30504a810af6aa40504ffffffff",
        {
            "last_event.event": DeviceEventType.FAST_CHARGING_PLAN_START,
            "last_event.start": datetime.fromtimestamp(PLAN_START),  # noqa: DTZ006
            "last_event.end": None,
            "last_event.battery_percentage": None,
        },
        id="c2000g2_event_fast_charging_plan_start",
    ),
    pytest.param(
        "0425",
        "a10112a202010ba3050400000000a4050400000000",
        {
            "last_event.event": DeviceEventType.FAST_CHARGING_PLAN_END,
            "last_event.start": None,
            "last_event.end": None,
        },
        id="c2000g2_event_fast_charging_plan_end",
    ),
    pytest.param(
        "4403",
        "a10131a2020152",
        {
            "last_event.event": DeviceEventType.BATTERY_LOW,
            "last_event.code": 0x52,
            "last_event.start": None,
            "last_event.battery_percentage": None,
        },
        id="c2000g2_event_push_battery_low",
    ),
    pytest.param(
        "4489",
        "a10131a2020100a3020102a402012da502010fa602010f",
        {
            "ota_allowed": False,
            "ota_block_reason": OtaBlockReason.LOW_BATTERY,
            "last_event": None,
        },
        id="c2000g2_ota_status_push_blocked",
    ),
    pytest.param(
        "4489",
        "a10131a2020101a3020100a402012da502010fa602010f",
        {
            "ota_allowed": True,
            "ota_block_reason": OtaBlockReason.NONE,
        },
        id="c2000g2_ota_status_push_allowed",
    ),
]
