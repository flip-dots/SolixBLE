"""C2000(X) Gen 2 power station model.

.. moduleauthor:: kb1ibt

"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Array,
    BitsInteger,
    BitStruct,
    Bytes,
    Const,
    Container,
    ExprAdapter,
    Flag,
    FlagsEnum,
    Int8sb,
    Int8ub,
    Int16ul,
    Int32ul,
    Optional,
    Padding,
    PascalString,
    Struct,
    this,
)

from SolixBLE.const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
    TELEMETRY_PATTERN_A,
)
from SolixBLE.constructs import (
    PacketCommand,
    ParameterDict,
    Parameters,
    SummaryPayload,
    WeekdayMask,
)
from SolixBLE.devices.c1000g2 import (
    C1000G2,
    CMD_AC_OUTPUT,
    CMD_DC_OUTPUT,
    CMD_SUBSCRIBE,
    PARAMETERS_SUBSCRIBE,
)
from SolixBLE.devices.c2000g2_summary import SUMMARY_MAPS
from SolixBLE.parsing import SummaryField, name_summary, walk_protobuf
from SolixBLE.protocols import EncryptedOuter
from SolixBLE.states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus
from SolixBLE.utilities import _parse_guarded

_LOGGER = logging.getLogger(__name__)


class DisplayLanguage(Enum):
    """The language of the device's display."""

    #: The language is unknown.
    UNKNOWN = -1

    #: English.
    ENGLISH = 0

    #: Chinese.
    CHINESE = 1

    #: French.
    FRENCH = 2

    #: German.
    GERMAN = 3

    #: Japanese.
    JAPANESE = 4


class AcInputState(Enum):
    """Whether the device takes power from the AC input."""

    #: The state is unknown.
    UNKNOWN = -1

    #: AC input is accepted.
    ACCEPTED = 0

    #: AC input is switched off, so loads run from the battery only.
    DISABLED = 1

    #: AC input is off on its own: mains is unplugged or the main battery is
    #: at its discharge floor.
    AUTO_OFF = 2


class BmsFault(Enum):
    """A battery fault reported by the device."""

    #: The fault is unknown.
    UNKNOWN = -1

    #: No fault.
    NONE = 0

    #: Discharge over-temperature.
    DISCHARGE_OVER_TEMPERATURE = 1

    #: Discharge low temperature.
    DISCHARGE_LOW_TEMPERATURE = 2

    #: Low battery.
    LOW_BATTERY = 3

    #: Battery management system communication error.
    BMS_COMMUNICATION = 4

    #: Over-current.
    OVER_CURRENT = 5

    #: MOSFET over-temperature.
    MOS_OVER_TEMPERATURE = 6

    #: Pre-discharge MOSFET fault.
    PRE_DISCHARGE_MOS = 7

    #: Charge MOSFET fault.
    CHARGE_MOS = 8

    #: Discharge MOSFET fault.
    DISCHARGE_MOS = 9


class TariffType(Enum):
    """A time-of-use tariff period."""

    #: The tariff is unknown.
    UNKNOWN = -1

    #: No tariff period is active.
    NONE = 0

    #: Peak.
    PEAK = 1

    #: Mid-peak.
    MID_PEAK = 2

    #: Off-peak.
    OFF_PEAK = 3


class DeviceEventType(Enum):
    """An event the device reports on its own."""

    #: The event is unknown.
    UNKNOWN = -1

    #: A Storm Guard backup window started.
    STORM_GUARD_START = 0x07

    #: A Storm Guard backup window ended.
    STORM_GUARD_END = 0x08

    #: A Fast Charging Plan window started.
    FAST_CHARGING_PLAN_START = 0x0A

    #: A Fast Charging Plan window ended.
    FAST_CHARGING_PLAN_END = 0x0B

    #: The main battery is at 1 % or below.
    BATTERY_CRITICAL = 0x50

    #: The main battery is at 10 % or below.
    BATTERY_LOW = 0x52

    #: The AC output timer ran out.
    AC_TIMER_EXPIRED = 0x55

    #: The DC (car socket) output timer ran out.
    DC_TIMER_EXPIRED = 0x56

    #: The AC grid was lost.
    GRID_LOSS = 0x59


class OtaBlockReason(Enum):
    """Why the device would refuse a firmware update."""

    #: The reason is unknown.
    UNKNOWN = -1

    #: Nothing blocks an update.
    NONE = 0

    #: A battery is below 6 %.
    LOW_BATTERY = 2

    #: The battery level can't be read, and mains must be plugged in.
    CONNECT_AC = 4


@dataclass(frozen=True)
class TouPeriod:
    """One period of a time-of-use plan, in whole hours.

    :param tariff: Tariff of the period.
    :param start_hour: First hour of the period, 0-23.
    :param end_hour: Hour the period ends, 1-24.
    """

    tariff: TariffType
    start_hour: int
    end_hour: int


@dataclass(frozen=True)
class DisplayPlan:
    """The display's clock screen and its day / night schedule.

    :param screensaver_enabled: Whether the clock screensaver shows.
    :param clock_theme: Clock theme, 1-based as the app numbers them.
    :param clock_24h: Whether the clock shows 24-hour time.
    :param day_start: Start of the day period, minutes from midnight.
    :param day_end: End of the day period, minutes from midnight.
    :param weekdays: Days the schedule applies, 0 Monday to 6 Sunday.
    :param night_enabled: Whether a separate night period is set.
    :param day_brightness: Day brightness in % (5 or 20).
    :param night_brightness: Night brightness in % (5 or 20).
    :param night_start: Start of the night period, minutes from midnight.
    :param night_end: End of the night period, minutes from midnight.
    """

    screensaver_enabled: bool
    clock_theme: int
    clock_24h: bool
    day_start: int
    day_end: int
    weekdays: frozenset[int]
    night_enabled: bool
    day_brightness: int
    night_brightness: int
    night_start: int
    night_end: int


@dataclass(frozen=True)
class DeviceEvent:
    """An event the device reported on its own.

    :param event: The event.
    :param code: The raw event code.
    :param start: Start of the window the event reports, if any.
    :param end: End of the window the event reports, if any.
    :param battery_percentage: Battery percentage at a grid loss, else None.
    :param received: When the event arrived.
    """

    event: DeviceEventType
    code: int
    start: datetime | None
    end: datetime | None
    battery_percentage: int | None
    received: datetime


VERSION_QUAD = ExprAdapter(
    Bytes(4),
    decoder=lambda obj, _: f"{obj[3]}.{obj[2]}.{obj[1]}.{obj[0]}",
    encoder=lambda obj, _: bytes(int(part) for part in reversed(obj.split("."))),
)
"""
A version packed as 4 bytes with the last digit first (``06 01 02 01``
decodes to ``"1.2.1.6"``).
"""

PORT_STATUS_POWER = Struct(
    "status" / Int8ub,
    "power" / Int16ul,
)
"""
A port's status and power (W): the USB-A/C ports, the DC output and the
DC input.
"""

A2_INFO = Struct(
    "protocol_version" / Int8ub,
    "serial_number" / PascalString(Int8ub, "ascii"),
    "device_category" / Int8ub,
    "part_number" / PascalString(Int8ub, "ascii"),
    "firmware_version" / VERSION_QUAD,
    "model_variant" / Int8ub,
    "max_battery_num" / Int8ub,
)
"""
Basic info (``a2``): protocol version, serial number, a reserved byte, part
number, controller firmware, model variant and the expansion slot count.
"""

A3_STATUS = Struct(
    "work_status" / Int8ub,
    "error_code" / Int8ub,
    "package_count" / Int8ub,
    "package_use_count" / Int8ub,
    "max_input_power" / Int16ul,
    "upgrade_progress" / Int8ub,
    "wifi_signal_strength" / Int8ub,
    "mtu_size" / Int16ul,
    "silent_recharge_power" / Optional(Int16ul),
    "weak_light_lock_flag" / Optional(Int8ub),
)
"""
Status (``a3``). The last two fields are absent on firmware that predates
them.
"""

A4_FLAGS = BitStruct(
    Padding(4),
    "ac_input_state" / BitsInteger(2),
    "outage_alert_enabled" / Flag,
    Padding(1),
)
"""The settings flag byte (``a4[31]``): the AC input state and the outage alert."""

A4_SETTINGS = Struct(
    "ac_timer_remaining" / Int32ul,
    "ac_charging_power" / Int16ul,
    "ac_frequency" / Int8ub,
    "power_saving_mode_enabled" / Flag,
    "dc_timer_remaining" / Int32ul,
    "dc_power_saving_mode_enabled" / Flag,
    "device_timeout" / Int16ul,
    "display_timeout" / Int16ul,
    "display_mode" / Int8ub,
    Padding(1),
    "temperature_unit_fahrenheit" / Flag,
    "ac_fast_charge_enabled" / Flag,
    "is_display_on" / Flag,
    "port_memory_enabled" / Flag,
    "max_battery_percentage" / Int8ub,
    "min_battery_percentage" / Int8ub,
    "display_language" / Int8ub,
    "flags" / Optional(Struct(Padding(5), "flags" / A4_FLAGS, Padding(1))),
)
"""
Settings (``a4``): 26 bytes, plus a 7-byte tail holding the flag byte on
firmware from v1.2.1.6.
"""

A5_BATTERY = Struct(
    "temperature" / Int8sb,
    "charge_discharge_status" / Int8ub,
    "battery_percentage" / Int8ub,
)
"""Main battery (``a5``): temperature (C), port-flow code and state of charge."""

A6_POWER = Struct(
    "power_out" / Int16ul,
    "ac_power_in" / Int16ul,
    "dc_power_in" / Int16ul,
    "time_remaining" / Int16ul,
    "battery_percentage" / Int8ub,
)
"""
Power totals (``a6``): output, AC input and DC input (W), time to full or
empty (0.1 h) and the main battery's state of charge.
"""

A7_AC = Struct(
    "output" / PORT_STATUS_POWER,
    "input_status" / Int8ub,
    "input_power" / Int16ul,
)
"""
AC ports (``a7``): the output's status and power, whether the mains lead is
plugged in (2 with Battery-Only Power on), and the input power (W).
"""

C0_EXPANSION = Struct(
    "serial_number" / PascalString(Int8ub, "ascii"),
    "number" / Int8ub,
    "version" / VERSION_QUAD,
    "temperature" / Int8sb,
    "charge_discharge_status" / Int8ub,
    "battery_percentage" / Int8ub,
    "main_health" / Int8ub,
    "blink" / Int8ub,
    "output_on" / Flag,
    "error_code" / Int8ub,
    "connected" / Flag,
    "balance" / Int8ub,
    "type" / PascalString(Int8ub, "ascii"),
)
"""
Expansion battery (``c0``), emitted with or without a pack attached; its
values hold only while ``connected`` is set.
"""

D9_TOU = Struct(
    "active_tariff" / Int8ub,
    "tou_mode" / Int8ub,
    "reserve_battery_percentage" / Int8ub,
    "max_battery_percentage" / Int8ub,
    "min_battery_percentage" / Int8ub,
    "period_count" / Int8ub,
    "periods"
    / Array(
        this.period_count,
        Struct("tariff" / Int8ub, "start_hour" / Int8ub, "end_hour" / Int8ub),
    ),
    "backup"
    / Optional(
        Struct(
            "active_type" / Int8ub,
            "fast_charging_plan_enabled" / Flag,
            "storm_guard_enabled" / Flag,
            "fast_charging_plan_start" / Int32ul,
            "fast_charging_plan_end" / Int32ul,
            "backup_window_start" / Int32ul,
            "backup_window_end" / Int32ul,
        ),
    ),
)
"""
Time-of-use plan (``d9``), then the backup-plan tail: the running window's
type, each plan's switch, the Fast Charging Plan's stored window and the
running window (0 when none runs).
"""

DA_DISPLAY_PLAN = Struct(
    "screensaver_and_theme" / Int8ub,
    "theme_download_state" / Int8ub,
    "theme_id" / Int32ul,
    "theme_size" / Int32ul,
    "clock_24h" / Flag,
    "day_start" / Int16ul,
    "day_end" / Int16ul,
    "weekdays" / WeekdayMask,
    "night_enabled" / Flag,
    "day_brightness_level" / Int8ub,
    "night_brightness_level" / Int8ub,
    "night_start" / Int16ul,
    "night_end" / Int16ul,
)
"""
Clock screen (``da``): bit 7 of ``screensaver_and_theme`` is the
screensaver switch and the low bits the theme; times are minutes from
midnight.
"""

DC_FAULT = Struct(
    "fault" / Int8ub,
    "fault_time" / Int32ul,
)
"""
Output-memory fault (``dc``): the battery fault blocking the restore and
when the outputs are due back, both 0 while there is none.
"""

F9_VERSIONS = Struct(
    "controller" / VERSION_QUAD,
    "sub_controller" / VERSION_QUAD,
    "mppt" / VERSION_QUAD,
    "inverter" / VERSION_QUAD,
    "bms" / VERSION_QUAD,
    "expansion_bms" / VERSION_QUAD,
    "module" / VERSION_QUAD,
)
"""Firmware versions (``f9``), seven slots."""

FA_CAPABILITIES = Struct(
    "ac_energy_mode" / Flag,
    "car_charge_mode" / Flag,
    "parallel_upgrade" / Flag,
    "get_upgrade_info" / Flag,
    Padding(1),
    "features"
    / FlagsEnum(
        Int8ub,
        transaction_id=0x01,
        memory_switch=0x02,
        backup_disaster=0x04,
        upgrade_record=0x08,
        screen_time_period=0x10,
        output_status=0x20,
        charging_limits=0x40,
        set_country_code=0x80,
    ),
    "more_features"
    / FlagsEnum(
        Int8ub,
        pps_tou=0x01,
        memory_switch_two=0x02,
        silent_recharge=0x04,
        outage_alert=0x08,
        ac_input_disable=0x10,
    ),
)
"""
Capability flags (``fa``), named as the app names them without their
``support`` prefix.
"""

#: The capability flags that take a whole byte each.
CAPABILITY_BYTES = (
    "ac_energy_mode",
    "car_charge_mode",
    "parallel_upgrade",
    "get_upgrade_info",
)

EVENT_CODE = Int8ub
"""An event report's or event push's code (``a2``)."""

EPOCH = Int32ul
"""A window's start or end in an event report (``a3`` / ``a4``)."""

#: Realtime stream latch: ``a2`` 1 starts the ``c421`` pushes.
CMD_REALTIME = "4057"

PARAMETERS_REALTIME_ON = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": 1,
    },
}

#: The AC and DC groups take their auto-off timer at a3 as a u32 of seconds.
PARAMETERS_TIMER = {
    "a1": {
        "value": "21",
    },
    "a3": {
        "type": 3,
        # _to_bytes passes keyword arguments by the lambda's parameter names
        "value": lambda seconds: Int32ul.build(seconds),  # noqa: PLW0108
    },
}

#: The AC group takes its charging power limit at a4 as a u16 of watts.
PARAMETERS_AC_CHARGING_POWER = {
    "a1": {
        "value": "21",
    },
    "a4": {
        "type": 2,
        "value": lambda watts: Int16ul.build(watts),  # noqa: PLW0108
    },
}

#: Largest AC charging power limit the 16-bit field can carry (W).
MAX_AC_CHARGING_POWER_FIELD = 0xFFFF

PARAMETERS_AC_FAST_CHARGE = {
    "a1": {
        "value": "21",
    },
    "a7": {
        "type": 1,
        "value": lambda on: 1 if on else 0,
    },
}

#: The AC group switches the AC input off with ab = 1 (a u16).
PARAMETERS_AC_INPUT = {
    "a1": {
        "value": "21",
    },
    "ab": {
        "type": 2,
        "value": lambda off: Int16ul.build(1 if off else 0),
    },
}

#: System group: display, SoC limits, language and the outage alert.
CMD_SYSTEM = "4103"

PARAMETERS_DISPLAY = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda on: 1 if on else 0,
    },
}

PARAMETERS_DISPLAY_MODE = {
    "a1": {
        "value": "21",
    },
    "a3": {
        "type": 1,
        "value": lambda mode: mode,
    },
}

#: The display timeout is a u16 of seconds.
PARAMETERS_DISPLAY_TIMEOUT = {
    "a1": {
        "value": "21",
    },
    "a4": {
        "type": 2,
        "value": lambda seconds: Int16ul.build(seconds),  # noqa: PLW0108
    },
}

PARAMETERS_DISPLAY_LANGUAGE = {
    "a1": {
        "value": "21",
    },
    "a9": {
        "type": 1,
        "value": lambda language: language,
    },
}

PARAMETERS_MAX_BATTERY = {
    "a1": {
        "value": "21",
    },
    "aa": {
        "type": 1,
        "value": lambda percentage: percentage,
    },
}

PARAMETERS_MIN_BATTERY = {
    "a1": {
        "value": "21",
    },
    "ab": {
        "type": 1,
        "value": lambda percentage: percentage,
    },
}

PARAMETERS_OUTAGE_ALERT = {
    "a1": {
        "value": "21",
    },
    "b0": {
        "type": 1,
        "value": lambda on: 1 if on else 0,
    },
}

#: Highest battery percentage for the charge cap and discharge floor.
MAX_PERCENTAGE = 100

#: Backup-plan group: a3 = 3 selects the backup plans, a4 the plan and a5
#: switches it.
CMD_BACKUP = "405e"
BACKUP_GROUP = 3
BACKUP_FAST_CHARGING_PLAN = 0
BACKUP_STORM_GUARD = 1

PARAMETERS_BACKUP_SWITCH = {
    "a1": {
        "value": "21",
    },
    "a3": {
        "type": 1,
        "value": BACKUP_GROUP,
    },
    "a4": {
        "type": 1,
        "value": lambda plan: plan,
    },
    "a5": {
        "type": 1,
        "value": lambda on: 1 if on else 0,
    },
}

#: One backup plan record as the app writes it: a 100 the device reads, a byte
#: it ignores, then the window's start and end epochs.
BACKUP_PLAN_RECORD = Struct(
    Const(100, Int8ub),
    Const(0, Int8ub),
    "start" / Int32ul,
    "end" / Int32ul,
)

#: The Fast Charging Plan switched on with one window (a6 = 1 plan, a7 the
#: plan record).
PARAMETERS_BACKUP_WINDOW = {
    "a1": {
        "value": "21",
    },
    "a3": {
        "type": 1,
        "value": BACKUP_GROUP,
    },
    "a4": {
        "type": 1,
        "value": BACKUP_FAST_CHARGING_PLAN,
    },
    "a5": {
        "type": 1,
        "value": 1,
    },
    "a6": {
        "type": 1,
        "value": 1,
    },
    "a7": {
        "type": 4,
        "value": lambda start, end: BACKUP_PLAN_RECORD.build(
            {"start": start, "end": end},
        ),
    },
}

#: Epoch the device sends for a window with no end.
NO_END = 0xFFFFFFFF

#: Clock-screen group: the app writes only the tags that change.
CMD_DISPLAY_PLAN = "4091"

#: Clock-screen read and its reply, which names the clock theme.
CMD_DISPLAY_THEME_NAME = "4092"
CMD_RESPONSE_DISPLAY_THEME_NAME = "c892"

#: Firmware-update readiness read and its reply.
CMD_OTA_STATUS = "4089"
CMD_RESPONSE_OTA_STATUS = "c889"

#: Telemetry reply drawn by the subscribe command when it is used as a poll.
CMD_RESPONSE_GET_STATUS = "c900"

#: Message types the device pushes on its own: the event report, the event
#: push, the firmware-update readiness and the device summary.
MSGTYPE_EVENT_REPORT = 0x425
MSGTYPE_EVENT_PUSH = 0x403
MSGTYPE_OTA_STATUS = 0x489
MSGTYPE_SUMMARY = 0x490

#: Work status while a firmware update runs; absent from ChargingStatus.
WORK_STATUS_UPDATING = 5

#: Time remaining (0.1 h) that means there is no estimate: the battery's
#: 0xFFFF minutes, scaled.
NO_ESTIMATE = 10923

#: Display brightness percentages by the level the device stores (0 or 1).
DISPLAY_PLAN_BRIGHTNESS = (5, 20)

#: Minutes in a day, the latest a display period may end.
MINUTES_PER_DAY = 1440

#: Largest clock theme number the a2 low bits can carry.
MAX_CLOCK_THEME = 0x80

#: Screensaver switch bit of the clock screen's theme byte.
SCREENSAVER_BIT = 0x80

#: Watt-hours per kWh, and the kWh digits the 0.1 Wh energy counters carry.
WH_PER_KWH = 1000.0
KWH_DIGITS = 4


def _epoch(value: int) -> datetime | None:
    """Read a u32 epoch the way the device reports windows.

    :param value: The epoch.
    :returns: The local time, or None for 0 (no window) and for no end.
    """
    if value in (0, NO_END):
        return None
    return datetime.fromtimestamp(value)  # noqa: DTZ006  # naive local, as the base device


#: The 4091 tag, type and encoder of each display plan setting: the fields it
#: carries, its type byte, and the value it sends. a2 holds both the
#: screensaver (bit 7) and the clock theme (the low bits, 0-based).
DisplayPlanTag = tuple[tuple[str, ...], int, Callable[[DisplayPlan], int | bytes]]

DISPLAY_PLAN_TAGS: dict[str, DisplayPlanTag] = {
    "a2": (
        ("screensaver_enabled", "clock_theme"),
        1,
        lambda plan: (
            (SCREENSAVER_BIT if plan.screensaver_enabled else 0)
            | (plan.clock_theme - 1)
        ),
    ),
    "a7": (("clock_24h",), 1, lambda plan: 1 if plan.clock_24h else 0),
    "a8": (("day_start",), 2, lambda plan: Int16ul.build(plan.day_start)),
    "a9": (("day_end",), 2, lambda plan: Int16ul.build(plan.day_end)),
    "aa": (("weekdays",), 1, lambda plan: WeekdayMask.build(plan.weekdays)),
    "ab": (("night_enabled",), 1, lambda plan: 1 if plan.night_enabled else 0),
    "ac": (
        ("day_brightness",),
        1,
        lambda plan: DISPLAY_PLAN_BRIGHTNESS.index(plan.day_brightness),
    ),
    "ad": (
        ("night_brightness",),
        1,
        lambda plan: DISPLAY_PLAN_BRIGHTNESS.index(plan.night_brightness),
    ),
    "ae": (("night_start",), 2, lambda plan: Int16ul.build(plan.night_start)),
    "af": (("night_end",), 2, lambda plan: Int16ul.build(plan.night_end)),
}


def _validate_display_plan(plan: DisplayPlan) -> None:
    """Range-check a display plan before it is sent.

    :param plan: The display plan.
    :raises ValueError: If a setting is out of range.
    """
    minutes = (plan.day_start, plan.day_end, plan.night_start, plan.night_end)
    if not all(0 <= value <= MINUTES_PER_DAY for value in minutes):
        msg = f"Display periods must be 0-{MINUTES_PER_DAY} minutes from midnight"
        raise ValueError(msg)
    if not 1 <= plan.clock_theme <= MAX_CLOCK_THEME:
        msg = f"Clock theme must be 1-{MAX_CLOCK_THEME}"
        raise ValueError(msg)
    if not plan.weekdays <= frozenset(range(7)):
        msg = "Weekdays must be 0 (Monday) to 6 (Sunday)"
        raise ValueError(msg)
    brightness = (plan.day_brightness, plan.night_brightness)
    if not all(value in DISPLAY_PLAN_BRIGHTNESS for value in brightness):
        msg = f"Display brightness must be one of {DISPLAY_PLAN_BRIGHTNESS} %"
        raise ValueError(msg)


def _validate_percentage(percentage: int) -> None:
    """Range-check a charge cap or discharge floor.

    :param percentage: Battery percentage.
    :raises ValueError: If out of range.
    """
    if not 0 <= percentage <= MAX_PERCENTAGE:
        msg = f"Percentage must be 0-{MAX_PERCENTAGE}"
        raise ValueError(msg)


def _charging_status(code: int) -> ChargingStatus:
    """Map a flow code to a charging status.

    :param code: The device's flow code.
    :returns: The status, or UNKNOWN for a code outside the enum.
    """
    try:
        return ChargingStatus(code)
    except ValueError:
        return ChargingStatus.UNKNOWN


class C2000G2(C1000G2):
    """
    C2000(X) Gen 2 Power Station.

    Use this class to connect, monitor and control a Gen 2 C2000(X) power
    station. This model is also known as the A1783.

    .. note::
       :collapsible: closed

       The device negotiates on the encrypted outer protocol. On connect it
       is subscribed (``4100``) and its realtime stream (``4057``) is
       started, so it pushes every change.

       It also posts a ``c490`` device summary about every nine minutes, a
       protobuf decoded into :attr:`summary` against the schema the frame
       names. The post can't be requested, and the device sends it only
       after it has reached the vendor cloud, so a unit kept off the network
       may never post one.
    """

    _OUTER_HINT = EncryptedOuter

    def __init__(
        self,
        ble_device: BLEDevice,
        advertisement: AdvertisementData | None = None,
        client_token: str | None = None,
    ) -> None:
        """Initialise device object. Does not connect automatically.

        :param ble_device: The bleak device to wrap.
        :param advertisement: The device's scan result, if available.
        :param client_token: Sent in the ECDH path's registration.
        """
        super().__init__(ble_device, advertisement, client_token)
        self._summary: dict[str, object] = {}
        self._summary_schema: str | None = None
        self._last_summary_timestamp: datetime | None = None
        self._unmapped_summary_schemas: set[str | None] = set()
        self._last_event: DeviceEvent | None = None
        self._ota_allowed: bool | None = None
        self._ota_block_reason = OtaBlockReason.UNKNOWN

    ###############
    # Device info #
    ###############

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        info = self._tag("a2", A2_INFO)
        return DEFAULT_METADATA_STRING if info is None else info.serial_number

    @property
    def part_number(self) -> str:
        """Device part number.

        .. note::
           Firmware v1.2.1.x reports ``A1783`` on every C-series Gen 2 model.

        :returns: Device part number or default str value.
        """
        info = self._tag("a2", A2_INFO)
        return DEFAULT_METADATA_STRING if info is None else info.part_number

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        versions = self._tag("f9", F9_VERSIONS)
        return DEFAULT_METADATA_STRING if versions is None else versions.controller

    @property
    def software_version_controller(self) -> str:
        """Software version of the controller (the DC-DC stage).

        :returns: Firmware version or default str value.
        """
        versions = self._tag("f9", F9_VERSIONS)
        return DEFAULT_METADATA_STRING if versions is None else versions.sub_controller

    @property
    def software_version_inverter(self) -> str:
        """Software version of the inverter (the AC-DC stage).

        .. note::
           Reads 0.0.0.0 whenever the inverter is not energised, so a zero
           here means idle rather than absent.

        :returns: Firmware version or default str value.
        """
        versions = self._tag("f9", F9_VERSIONS)
        return DEFAULT_METADATA_STRING if versions is None else versions.inverter

    @property
    def software_version_bms(self) -> str:
        """Software version of the main battery's management system.

        :returns: Firmware version or default str value.
        """
        versions = self._tag("f9", F9_VERSIONS)
        return DEFAULT_METADATA_STRING if versions is None else versions.bms

    @property
    def software_version_module(self) -> str:
        """Software version of the wireless module.

        :returns: Firmware version or default str value.
        """
        versions = self._tag("f9", F9_VERSIONS)
        return DEFAULT_METADATA_STRING if versions is None else versions.module

    @property
    def capabilities(self) -> frozenset[str]:
        """Optional features the firmware declares it supports.

        .. note::
           :collapsible: closed

           The names are the app's capability flags without their ``support``
           prefix (e.g ``pps_tou``, ``ac_input_disable``). They are constants
           of each firmware build.

        :returns: Names of the supported features, empty without data.
        """
        flags = self._tag("fa", FA_CAPABILITIES)
        if flags is None:
            return frozenset()

        names = {name for name in CAPABILITY_BYTES if flags[name]}
        for group in (flags.features, flags.more_features):
            names |= {
                name
                for name, on in group.items()
                if on is True and not name.startswith("_")
            }
        return frozenset(names)

    ###########
    # Battery #
    ###########

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        battery = self._tag("a5", A5_BATTERY)
        return DEFAULT_METADATA_INT if battery is None else battery.temperature

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        .. note::
           The main battery's state of charge. The power totals report the
           same value.

        :returns: Percentage charge of battery or default int value.
        """
        battery = self._tag("a5", A5_BATTERY)
        return DEFAULT_METADATA_INT if battery is None else battery.battery_percentage

    @property
    def battery_health(self) -> int:
        """Battery health.

        .. note::
           :collapsible: closed

           Read from the device summary (see :attr:`summary`), the only place
           the device reports the whole value, so it stays unknown until a
           summary from firmware v1.2.1.6 or later arrives.

        :returns: Percentage battery health or default int value.
        """
        return self._summary_percentage("battery_health")

    @property
    def charging_status(self) -> ChargingStatus:
        """Whether the battery is charging, discharging or idle.

        .. note::
           :collapsible: closed

           Follows the port powers: charging while input exceeds output,
           discharging while anything is drawn. It reads whichever battery
           is on the bus, main or expansion, and changes 2-3 s ahead of
           :attr:`charging_status_main`.

        :returns: Charging status, or UNKNOWN if there is no data.
        """
        battery = self._tag("a5", A5_BATTERY)
        if battery is None:
            return ChargingStatus.UNKNOWN

        code: int = battery.charge_discharge_status
        expansion = self._expansion()
        if code == 0 and expansion is not None:
            code = expansion.charge_discharge_status
        return _charging_status(code)

    @property
    def charging_status_main(self) -> ChargingStatus:
        """Whether the main battery's current is charging or discharging it.

        .. note::
           :collapsible: closed

           Follows the main battery's current (0.3 A for about 2 s), so it
           lags :attr:`charging_status` by 2-3 s and reads IDLE while the
           expansion battery carries the load. A firmware update puts it in a
           state outside the enum; see :attr:`firmware_updating`.

        :returns: Charging status, or UNKNOWN if there is no data.
        """
        status = self._tag("a3", A3_STATUS)
        if status is None:
            return ChargingStatus.UNKNOWN
        return _charging_status(status.work_status)

    @property
    def firmware_updating(self) -> bool | None:
        """Whether a firmware update is in progress.

        :returns: True while updating, else False, or default bool value if
            there is no data.
        """
        status = self._tag("a3", A3_STATUS)
        if status is None:
            return DEFAULT_METADATA_BOOL
        work_status: int = status.work_status
        return work_status == WORK_STATUS_UPDATING

    @property
    def time_remaining(self) -> float:
        """Time remaining to full or empty, in hours.

        Counts down to full while input exceeds output, else to empty.

        :returns: Hours remaining, or default float value if there is no data
            or no estimate.
        """
        power = self._tag("a6", A6_POWER)
        if power is None or power.time_remaining == NO_ESTIMATE:
            return DEFAULT_METADATA_FLOAT
        tenths: int = power.time_remaining
        return tenths / 10.0

    @property
    def hours_remaining(self) -> float:
        """Time remaining to full/empty, with whole days overflowed out.

        :returns: Hours remaining, or default float value if there is no data.
        """
        if self.time_remaining == DEFAULT_METADATA_FLOAT:
            return DEFAULT_METADATA_FLOAT
        return round(divmod(self.time_remaining, 24)[1], 1)

    @property
    def days_remaining(self) -> int:
        """Time remaining to full/empty, whole days only.

        :returns: Days remaining, or default int value if there is no data.
        """
        if self.time_remaining == DEFAULT_METADATA_FLOAT:
            return DEFAULT_METADATA_INT
        return int(divmod(self.time_remaining, 24)[0])

    @property
    def max_battery_percentage(self) -> int:
        """Maximum charge percentage.

        :returns: Battery charge percentage upper limit or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return (
            DEFAULT_METADATA_INT
            if settings is None
            else settings.max_battery_percentage
        )

    @property
    def min_battery_percentage(self) -> int:
        """Minimum charge percentage.

        :returns: Battery charge percentage lower limit or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return (
            DEFAULT_METADATA_INT
            if settings is None
            else settings.min_battery_percentage
        )

    @property
    def memory_switch_error(self) -> BmsFault:
        """Battery fault that stopped the outputs returning after a restart.

        :returns: The fault, NONE while there is none, or UNKNOWN.
        """
        fault = self._tag("dc", DC_FAULT)
        if fault is None:
            return BmsFault.UNKNOWN
        try:
            return BmsFault(fault.fault)
        except ValueError:
            return BmsFault.UNKNOWN

    @property
    def memory_switch_error_time(self) -> datetime | None:
        """When the outputs are due to return after :attr:`memory_switch_error`.

        :returns: Local time, or None while there is no fault.
        """
        fault = self._tag("dc", DC_FAULT)
        return None if fault is None else _epoch(fault.fault_time)

    #####################
    # Expansion battery #
    #####################

    @property
    def num_expansion(self) -> int:
        """Number of expansion batteries.

        .. note::
           The expansion block is sent whether or not a pack is attached; the
           C2000 Gen 2 has one expansion slot.

        :returns: Number of expansion batteries or default int value.
        """
        if self._tag("c0", C0_EXPANSION) is None:
            return DEFAULT_METADATA_INT
        return 0 if self._expansion() is None else 1

    @property
    def serial_number_expansion(self) -> str:
        """Serial number of the expansion battery.

        :returns: Serial number, or default str value if no pack is attached.
        """
        expansion = self._expansion()
        return DEFAULT_METADATA_STRING if expansion is None else expansion.serial_number

    @property
    def temperature_expansion(self) -> int:
        """Temperature of the expansion battery (C).

        :returns: Temperature in degrees C, or default int value if no pack is
            attached.
        """
        expansion = self._expansion()
        return DEFAULT_METADATA_INT if expansion is None else expansion.temperature

    @property
    def battery_percentage_expansion(self) -> int:
        """Battery percentage of the expansion battery.

        :returns: Percentage charge, or default int value if no pack is attached.
        """
        expansion = self._expansion()
        return (
            DEFAULT_METADATA_INT if expansion is None else expansion.battery_percentage
        )

    @property
    def battery_health_expansion(self) -> int:
        """Battery health of the expansion battery.

        .. note::
           Read from the device summary, like :attr:`battery_health`.

        :returns: Percentage battery health or default int value.
        """
        if self._expansion() is None:
            return DEFAULT_METADATA_INT
        return self._summary_percentage("battery_health_expansion")

    @property
    def expansion_output_on(self) -> bool | None:
        """Whether the expansion battery's output is switched on.

        .. note::
           This is the state the pack reports. Switching it off doesn't stick:
           the pack closes its output again within about two seconds.

        :returns: True if on, False if off, or None if no pack is attached.
        """
        expansion = self._expansion()
        if expansion is None:
            return None
        output_on: bool = expansion.output_on
        return output_on

    @property
    def software_version_expansion(self) -> str:
        """Software version of the expansion battery.

        :returns: Firmware version, or default str value if no pack is attached.
        """
        expansion = self._expansion()
        return DEFAULT_METADATA_STRING if expansion is None else expansion.version

    #########
    # Power #
    #########

    @property
    def power_out(self) -> int:
        """Total Power Out (watts).

        :returns: Total power out or default int value.
        """
        power = self._tag("a6", A6_POWER)
        return DEFAULT_METADATA_INT if power is None else power.power_out

    @property
    def ac_power_in(self) -> int:
        """AC Power In (watts).

        :returns: Total AC power in or default int value.
        """
        power = self._tag("a6", A6_POWER)
        return DEFAULT_METADATA_INT if power is None else power.ac_power_in

    @property
    def ac_output(self) -> PortStatus:
        """AC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of the AC port.
        """
        ac = self._tag("a7", A7_AC)
        return PortStatus.UNKNOWN if ac is None else PortStatus(ac.output.status)

    @property
    def ac_power_out(self) -> int:
        """AC Power Out (watts).

        :returns: Total AC power out or default int value.
        """
        ac = self._tag("a7", A7_AC)
        return DEFAULT_METADATA_INT if ac is None else ac.output.power

    @property
    def ac_input_port(self) -> PortStatus:
        """AC input (mains) status.

        PortStatus.INPUT signifies the mains lead is plugged in, NOT_CONNECTED
        that it is not. Presence only; it does not imply current is flowing,
        and :attr:`ac_input_state` says whether the device takes the power.

        :returns: Status of the AC input.
        """
        ac = self._tag("a7", A7_AC)
        return (
            PortStatus.UNKNOWN
            if ac is None
            else PortStatus.from_input_only(ac.input_status)
        )

    @property
    def ac_input_state(self) -> AcInputState:
        """Whether the device takes power from the AC input.

        .. note::
           Switched off, the AC input comes back on by itself when the main
           battery reaches its discharge floor or mains is unplugged.

        :returns: AC input state, or UNKNOWN (also on firmware that doesn't
            report it).
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None or settings.flags is None:
            return AcInputState.UNKNOWN
        try:
            return AcInputState(settings.flags.flags.ac_input_state)
        except ValueError:
            return AcInputState.UNKNOWN

    @property
    def dc_input_port(self) -> PortStatus:
        """DC input (XT-60i) port status.

        The one DC input port, whatever is plugged into it: a solar array, the
        12 V car-socket adapter or the Alternator Charger.

        PortStatus.INPUT signifies a source is present, NOT_CONNECTED that the
        port is empty. Presence only; it does not imply current is flowing.

        :returns: Status of the DC input port.
        """
        port = self._tag("a8", PORT_STATUS_POWER)
        return (
            PortStatus.UNKNOWN
            if port is None
            else PortStatus.from_input_only(port.status)
        )

    @property
    def solar_port(self) -> PortStatus:
        """Alias of :attr:`dc_input_port`, which takes more than a solar array.

        :returns: Status of the DC input port.
        """
        return self.dc_input_port

    @property
    def dc_input_power(self) -> int:
        """DC input (XT-60i) power in (watts).

        .. note::
           Reads 0 while the battery is above its charge cap, even with a
           source attached.

        :returns: DC input power or default int value.
        """
        port = self._tag("a8", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

    @property
    def solar_power_in(self) -> int:
        """Alias of :attr:`dc_input_power`, which takes more than a solar array.

        :returns: DC input power or default int value.
        """
        return self.dc_input_power

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        port = self._tag("aa", PORT_STATUS_POWER)
        return PortStatus.UNKNOWN if port is None else PortStatus(port.status)

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        port = self._tag("aa", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        port = self._tag("ab", PORT_STATUS_POWER)
        return PortStatus.UNKNOWN if port is None else PortStatus(port.status)

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        port = self._tag("ab", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        port = self._tag("ac", PORT_STATUS_POWER)
        return PortStatus.UNKNOWN if port is None else PortStatus(port.status)

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power (watts).

        :returns: USB port C3 power or default int value.
        """
        port = self._tag("ac", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        port = self._tag("ae", PORT_STATUS_POWER)
        return PortStatus.UNKNOWN if port is None else PortStatus(port.status)

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        port = self._tag("ae", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

    @property
    def dc_output(self) -> PortStatus:
        """DC (car socket) Port Status.

        :returns: Status of the DC output port.
        """
        port = self._tag("b2", PORT_STATUS_POWER)
        return PortStatus.UNKNOWN if port is None else PortStatus(port.status)

    @property
    def dc_power_out(self) -> int:
        """DC (car socket) Power Out (watts).

        :returns: DC power out or default int value.
        """
        port = self._tag("b2", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

    @property
    def max_input_power(self) -> int:
        """Most charge-input power the unit can draw (W).

        :returns: Maximum input power in watts, or default int value if there
            is no data.
        """
        status = self._tag("a3", A3_STATUS)
        return DEFAULT_METADATA_INT if status is None else status.max_input_power

    ############
    # Settings #
    ############

    @property
    def ac_timer_remaining(self) -> int:
        """Time remaining on AC timer.

        :returns: Seconds remaining or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return DEFAULT_METADATA_INT if settings is None else settings.ac_timer_remaining

    @property
    def ac_timer(self) -> datetime | None:
        """Timestamp of AC timer.

        :returns: Timestamp of when AC timer expires or None.
        """
        if self.ac_timer_remaining not in (DEFAULT_METADATA_INT, 0):
            now = datetime.now()  # noqa: DTZ005  # naive local, as the base device
            return now + timedelta(seconds=self.ac_timer_remaining)
        return None

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC (car socket) timer.

        :returns: Seconds remaining or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return DEFAULT_METADATA_INT if settings is None else settings.dc_timer_remaining

    @property
    def dc_timer(self) -> datetime | None:
        """Timestamp of DC (car socket) timer.

        :returns: Timestamp of when DC timer expires or None.
        """
        if self.dc_timer_remaining not in (DEFAULT_METADATA_INT, 0):
            now = datetime.now()  # noqa: DTZ005  # naive local, as the base device
            return now + timedelta(seconds=self.dc_timer_remaining)
        return None

    @property
    def ac_charging_power(self) -> int:
        """Configured AC charging power limit in watts.

        :returns: AC charging power limit or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return DEFAULT_METADATA_INT if settings is None else settings.ac_charging_power

    @property
    def ac_frequency(self) -> int:
        """AC output frequency (Hz).

        :returns: Frequency in Hz, or default int value if there is no data.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return DEFAULT_METADATA_INT if settings is None else settings.ac_frequency

    @property
    def ac_fast_charge_enabled(self) -> bool | None:
        """Whether ultrafast AC charging is enabled.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = settings.ac_fast_charge_enabled
        return enabled

    @property
    def power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled on the AC output.

        .. note::
           Enabled, the AC output switches itself off below 14 W.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = settings.power_saving_mode_enabled
        return enabled

    @property
    def dc_power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled on the DC (car socket) output.

        .. note::
           Enabled, the DC output switches itself off below 3 W.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = settings.dc_power_saving_mode_enabled
        return enabled

    @property
    def port_memory_enabled(self) -> bool | None:
        """Whether output ports return to their previous state after a restart.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = settings.port_memory_enabled
        return enabled

    @property
    def device_timeout(self) -> int:
        """Configured device timeout in minutes.

        :returns: Configured device timeout (0 for never) or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return DEFAULT_METADATA_INT if settings is None else settings.device_timeout

    @property
    def is_display_on(self) -> bool | None:
        """Whether the LCD display is on.

        :returns: True if on, False if off, or default bool value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None:
            return DEFAULT_METADATA_BOOL
        is_display_on: bool = settings.is_display_on
        return is_display_on

    @property
    def display_mode(self) -> LightStatus:
        """Configured display brightness level.

        :returns: Display brightness as LightStatus (LOW/MEDIUM/HIGH) or UNKNOWN.
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None:
            return LightStatus.UNKNOWN
        try:
            return LightStatus(settings.display_mode)
        except ValueError:
            return LightStatus.UNKNOWN

    @property
    def display_timeout(self) -> int:
        """Display timeout limit in seconds.

        :returns: Display timeout in seconds (0 for never) or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return DEFAULT_METADATA_INT if settings is None else settings.display_timeout

    @property
    def display_language(self) -> DisplayLanguage:
        """Language of the display.

        :returns: Display language or UNKNOWN.
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None:
            return DisplayLanguage.UNKNOWN
        try:
            return DisplayLanguage(settings.display_language)
        except ValueError:
            return DisplayLanguage.UNKNOWN

    @property
    def outage_alert_enabled(self) -> bool | None:
        """Whether the device alerts when the AC grid is lost.

        :returns: True if enabled, False if disabled, or default bool value
            (also on firmware that doesn't report it).
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None or settings.flags is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = settings.flags.flags.outage_alert_enabled
        return enabled

    @property
    def display_plan(self) -> DisplayPlan | None:
        """The display's clock screen and its day / night schedule.

        :returns: The display plan, or None without data.
        """
        plan = self._tag("da", DA_DISPLAY_PLAN)
        if plan is None:
            return None

        return DisplayPlan(
            screensaver_enabled=bool(plan.screensaver_and_theme & SCREENSAVER_BIT),
            clock_theme=(plan.screensaver_and_theme & ~SCREENSAVER_BIT) + 1,
            clock_24h=plan.clock_24h,
            day_start=plan.day_start,
            day_end=plan.day_end,
            weekdays=plan.weekdays,
            night_enabled=plan.night_enabled,
            day_brightness=DISPLAY_PLAN_BRIGHTNESS[plan.day_brightness_level & 1],
            night_brightness=DISPLAY_PLAN_BRIGHTNESS[plan.night_brightness_level & 1],
            night_start=plan.night_start,
            night_end=plan.night_end,
        )

    ###################
    # Time of use and #
    # backup plans    #
    ###################

    @property
    def tou_enabled(self) -> bool | None:
        """Whether the time-of-use plan is switched on.

        :returns: True if on, False if off, or default bool value.
        """
        tou = self._tag("d9", D9_TOU)
        return DEFAULT_METADATA_BOOL if tou is None else bool(tou.tou_mode)

    @property
    def active_tariff(self) -> TariffType:
        """Tariff of the time-of-use period in force.

        .. note::
           A period is in force only while the device is bound to an Anker
           account and on WiFi, has AC input and the clock is inside one of
           :attr:`tou_periods`; otherwise this reads NONE.

        :returns: Active tariff, NONE, or UNKNOWN.
        """
        tou = self._tag("d9", D9_TOU)
        if tou is None:
            return TariffType.UNKNOWN
        try:
            return TariffType(tou.active_tariff)
        except ValueError:
            return TariffType.UNKNOWN

    @property
    def reserve_battery_percentage(self) -> int:
        """Battery percentage the time-of-use plan keeps in reserve.

        :returns: Reserve percentage or default int value.
        """
        tou = self._tag("d9", D9_TOU)
        return DEFAULT_METADATA_INT if tou is None else tou.reserve_battery_percentage

    @property
    def tou_periods(self) -> list[TouPeriod]:
        """Periods of the time-of-use plan.

        :returns: The periods in the order stored, empty without data.
        """
        tou = self._tag("d9", D9_TOU)
        if tou is None:
            return []

        periods = []
        for period in tou.periods:
            try:
                tariff = TariffType(period.tariff)
            except ValueError:
                tariff = TariffType.UNKNOWN
            periods.append(TouPeriod(tariff, period.start_hour, period.end_hour))
        return periods

    @property
    def fast_charging_plan_enabled(self) -> bool | None:
        """Whether the Fast Charging Plan (a scheduled backup charge) is on.

        :returns: True if on, False if off, or default bool value.
        """
        backup = self._backup()
        if backup is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = backup.fast_charging_plan_enabled
        return enabled

    @property
    def storm_guard_enabled(self) -> bool | None:
        """Whether Storm Guard (a backup charge ahead of severe weather) is on.

        :returns: True if on, False if off, or default bool value.
        """
        backup = self._backup()
        if backup is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = backup.storm_guard_enabled
        return enabled

    @property
    def fast_charging_plan_window(
        self,
    ) -> tuple[datetime | None, datetime | None] | None:
        """Start and end of the window the Fast Charging Plan stores.

        :returns: (start, end) local times, an end of None meaning no end, or
            None without data or with no window stored.
        """
        backup = self._backup()
        if backup is None:
            return None
        start = _epoch(backup.fast_charging_plan_start)
        end = _epoch(backup.fast_charging_plan_end)
        return (start, end) if start is not None else None

    @property
    def backup_window(self) -> tuple[datetime | None, datetime | None] | None:
        """Start and end of the backup window running now, from either plan.

        :returns: (start, end) local times, an end of None meaning no end, or
            None while no window runs.
        """
        backup = self._backup()
        if backup is None:
            return None
        start = _epoch(backup.backup_window_start)
        end = _epoch(backup.backup_window_end)
        return (start, end) if start is not None else None

    ##########
    # Pushes #
    ##########

    @property
    def last_event(self) -> DeviceEvent | None:
        """The latest event the device reported on its own.

        .. note::
           :collapsible: closed

           The device reports when a Storm Guard or Fast Charging Plan window
           starts or ends, when the AC grid is lost, when the main battery
           falls to 10 % and to 1 %, and when an output timer runs out. Each
           new event runs the state change callbacks.

        :returns: The latest event, or None until one arrives.
        """
        return self._last_event

    @property
    def ota_allowed(self) -> bool | None:
        """Whether the device would accept a firmware update now.

        Pushed by the device when it changes, and read with
        :meth:`get_ota_status`.

        :returns: True if allowed, False if not, or None until reported.
        """
        return self._ota_allowed

    @property
    def ota_block_reason(self) -> OtaBlockReason:
        """Why the device would refuse a firmware update.

        :returns: The reason, NONE when allowed, or UNKNOWN until reported.
        """
        return self._ota_block_reason

    ##################
    # Device summary #
    ##################

    @property
    def summary(self) -> dict[str, object]:
        """Fields from the latest device summary.

        .. note::
           :collapsible: closed

           The device posts a protobuf summary about every nine minutes,
           against a schema it names in the frame. Fields of a known schema
           appear under their names with scaling applied, the expansion
           battery's with an ``_expansion`` suffix; anything else is kept
           under its protobuf ``.path``. The summary can't be requested, so
           this stays empty until one arrives.

        :returns: Mapping of field name to value.
        """
        return self._summary

    @property
    def summary_schema(self) -> str | None:
        """The schema name of the latest device summary.

        :returns: The schema name, or None until a summary has been received.
        """
        return self._summary_schema

    @property
    def last_summary_update(self) -> datetime | None:
        """Timestamp of the last device summary.

        :returns: Timestamp of the last summary or None.
        """
        return self._last_summary_timestamp

    @property
    def ac_charged_energy(self) -> float | None:
        """Total energy charged through the AC input in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_input_energy")

    @property
    def dc_charged_energy(self) -> float | None:
        """Total energy charged through the DC input in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_input_energy")

    @property
    def ac_output_energy(self) -> float | None:
        """Total energy discharged through the AC output in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_output_energy")

    @property
    def dc_output_energy(self) -> float | None:
        """Total energy discharged through the DC and USB outputs in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_output_energy")

    @property
    def dc_input_voltage(self) -> float | None:
        """Voltage at the DC (XT-60i) input in volts.

        Reported in the device summary, so it is at most about nine minutes old.

        :returns: Voltage in V, or None until a summary has been received.
        """
        value = self._summary.get("dc_input_voltage")
        return float(value) if isinstance(value, (int, float)) else None

    ############
    # Commands #
    ############

    async def turn_display_on(self) -> None:
        """Turn the display on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_SYSTEM, parameters=PARAMETERS_DISPLAY, on=True)

    async def turn_display_off(self) -> None:
        """Turn the display off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_DISPLAY,
            on=False,
        )

    async def set_display_mode(self, mode: LightStatus) -> None:
        """Set the status/mode of the LCD display.

        .. note::
           The device keeps the display switch and its brightness as separate
           settings, so OFF turns the display off and LOW/MEDIUM/HIGH set the
           brightness without changing the switch.

        :param mode: Mode/status to set display to (off/low/med/high).
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode in (LightStatus.UNKNOWN, LightStatus.SOS):
            msg = f"You cannot set the display brightness status to {mode.name}"
            raise ValueError(msg)
        if mode is LightStatus.OFF:
            await self.turn_display_off()
            return

        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_DISPLAY_MODE,
            mode=mode.value,
        )

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:  # noqa: ASYNC109  # shared device API
        """Set the display timeout.

        :param timeout: Timeout to set the display to; S0 keeps it on.
        :raises ValueError: If requested timeout is UNKNOWN.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if timeout is DisplayTimeout.UNKNOWN:
            msg = "You cannot set the display timeout to unknown"
            raise ValueError(msg)

        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_DISPLAY_TIMEOUT,
            seconds=timeout.value,
        )

    async def set_display_language(self, language: DisplayLanguage) -> None:
        """Set the language of the display.

        :param language: Language to set.
        :raises ValueError: If the language is UNKNOWN.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if language is DisplayLanguage.UNKNOWN:
            msg = "You cannot set the display language to unknown"
            raise ValueError(msg)

        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_DISPLAY_LANGUAGE,
            language=language.value,
        )

    async def set_display_plan(self, plan: DisplayPlan) -> None:
        """Change the display's clock screen and its day / night schedule.

        Only the settings that differ from :attr:`display_plan` are sent, as
        the app does, so build the plan from the current one, e.g.
        ``dataclasses.replace(device.display_plan, clock_24h=False)``.

        .. note::
           Switching the night period off makes the device move the day
           period's end to where the night period ended.

        :param plan: The display plan to set.
        :raises ValueError: If there is no display plan yet or a setting is
            out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        current = self.display_plan
        if current is None:
            msg = "No display plan has been received from the device yet"
            raise ValueError(msg)
        _validate_display_plan(plan)

        parameters: dict[str, dict[str, object]] = {"a1": {"value": "21"}}
        for tag, (fields, data_type, encode) in DISPLAY_PLAN_TAGS.items():
            if any(getattr(plan, f) != getattr(current, f) for f in fields):
                parameters[tag] = {"type": data_type, "value": encode(plan)}
        if len(parameters) == 1:
            return

        await self._send_command(cmd=CMD_DISPLAY_PLAN, parameters=parameters)

    async def set_max_battery_percentage(self, percentage: int) -> None:
        """Set the charge cap, above which the device stops charging.

        .. warning::
           The firmware accepts any percentage, not only the 80-100 the app
           offers. Setting it very low leaves the battery nearly empty.

        :param percentage: Charge cap, 0-100.
        :raises ValueError: If the percentage is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        _validate_percentage(percentage)
        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_MAX_BATTERY,
            percentage=percentage,
        )

    async def set_min_battery_percentage(self, percentage: int) -> None:
        """Set the discharge floor, below which the device stops discharging.

        .. warning::
           The firmware accepts any percentage, not only the 1-20 the app
           offers. The floor also picks which battery the C2000 Gen 2 runs
           from: an expansion battery below it is left unused.

        :param percentage: Discharge floor, 0-100.
        :raises ValueError: If the percentage is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        _validate_percentage(percentage)
        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_MIN_BATTERY,
            percentage=percentage,
        )

    async def set_ac_timer(self, seconds: int) -> None:
        """Set the AC auto-off timer.

        :param seconds: Seconds until AC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_TIMER,
            seconds=seconds,
        )

    async def set_dc_timer(self, seconds: int) -> None:
        """Set the DC (car socket) auto-off timer.

        :param seconds: Seconds until DC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_DC_OUTPUT,
            parameters=PARAMETERS_TIMER,
            seconds=seconds,
        )

    async def set_ac_charging_power(self, watts: int) -> None:
        """Set the AC charging power limit in watts.

        .. note::
           :collapsible: closed

           The firmware takes any 16-bit value, so the only bound applied is
           the device's reported :attr:`max_input_power` once telemetry has
           arrived. The app offers 500-1800 W in steps of 100.

        :param watts: AC charging power limit, 1 up to :attr:`max_input_power`.
        :raises ValueError: If power value is out of valid range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        ceiling = (
            self.max_input_power
            if self.max_input_power > 0
            else MAX_AC_CHARGING_POWER_FIELD
        )
        if not 1 <= watts <= ceiling:
            msg = f"AC charging power must be between 1 and {ceiling} W"
            raise ValueError(msg)

        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_AC_CHARGING_POWER,
            watts=watts,
        )

    async def turn_ac_fast_charge_on(self) -> None:
        """Turn ultrafast AC charging on.

        .. note::
           While a time-of-use tariff period is in force the device ignores
           this; :attr:`ac_fast_charge_enabled` shows whether it took.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_AC_FAST_CHARGE,
            on=True,
        )

    async def turn_ac_fast_charge_off(self) -> None:
        """Turn ultrafast AC charging off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_AC_FAST_CHARGE,
            on=False,
        )

    async def turn_ac_input_on(self) -> None:
        """Take power from the AC input again.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_AC_INPUT,
            off=False,
        )

    async def turn_ac_input_off(self) -> None:
        """Stop taking power from the AC input, so loads run from the battery.

        .. note::
           The device turns the AC input back on by itself when the main
           battery reaches its discharge floor and when mains is unplugged;
           :attr:`ac_input_state` shows it.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_AC_INPUT,
            off=True,
        )

    async def turn_outage_alert_on(self) -> None:
        """Turn the alert for a lost AC grid on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_OUTAGE_ALERT,
            on=True,
        )

    async def turn_outage_alert_off(self) -> None:
        """Turn the alert for a lost AC grid off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_OUTAGE_ALERT,
            on=False,
        )

    async def turn_fast_charging_plan_on(self) -> None:
        """Turn the Fast Charging Plan on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_BACKUP,
            parameters=PARAMETERS_BACKUP_SWITCH,
            plan=BACKUP_FAST_CHARGING_PLAN,
            on=True,
        )

    async def turn_fast_charging_plan_off(self) -> None:
        """Turn the Fast Charging Plan off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_BACKUP,
            parameters=PARAMETERS_BACKUP_SWITCH,
            plan=BACKUP_FAST_CHARGING_PLAN,
            on=False,
        )

    async def set_fast_charging_plan_window(
        self,
        start: datetime,
        end: datetime | None = None,
    ) -> None:
        """Turn the Fast Charging Plan on for a window.

        :attr:`fast_charging_plan_window` shows the stored window, and
        :attr:`backup_window` the window while it runs.

        :param start: Start of the window.
        :param end: End of the window, or None for no end.
        :raises ValueError: If the window ends before it starts.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        start_epoch = int(start.timestamp())
        end_epoch = NO_END if end is None else int(end.timestamp())
        if end_epoch <= start_epoch:
            msg = "The Fast Charging Plan window must end after it starts"
            raise ValueError(msg)

        await self._send_command(
            cmd=CMD_BACKUP,
            parameters=PARAMETERS_BACKUP_WINDOW,
            start=start_epoch,
            end=end_epoch,
        )

    async def turn_storm_guard_on(self) -> None:
        """Turn Storm Guard on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_BACKUP,
            parameters=PARAMETERS_BACKUP_SWITCH,
            plan=BACKUP_STORM_GUARD,
            on=True,
        )

    async def turn_storm_guard_off(self) -> None:
        """Turn Storm Guard off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_BACKUP,
            parameters=PARAMETERS_BACKUP_SWITCH,
            plan=BACKUP_STORM_GUARD,
            on=False,
        )

    # The time-of-use plan (``4090``) is not settable here: the device stores
    # it over BLE, but a period takes effect only while the unit is bound to
    # an Anker account and on WiFi, so from a BLE-only client the write is
    # accepted and never acts.

    async def get_status_update(self) -> ParameterDict:
        """Request and retrieve a status update from the device.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: Dictionary containing telemetry parameters.
        """
        payload = await self._request(CMD_SUBSCRIBE, CMD_RESPONSE_GET_STATUS)
        parameters: ParameterDict = Parameters.parse(payload)
        await self._process_telemetry(parameters)
        return parameters

    async def get_ota_status(self) -> bool | None:
        """Ask the device whether it would accept a firmware update now.

        Updates :attr:`ota_allowed` and :attr:`ota_block_reason`.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: True if an update would be accepted, else False.
        """
        payload = await self._request(CMD_OTA_STATUS, CMD_RESPONSE_OTA_STATUS)
        self._process_ota_status(Parameters.parse(payload))
        self._run_state_changed_callbacks()
        return self._ota_allowed

    async def get_display_theme_name(self) -> str:
        """Read the name of the display's clock theme.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: The theme name, empty if the theme has none.
        """
        payload = await self._request(
            CMD_DISPLAY_THEME_NAME,
            CMD_RESPONSE_DISPLAY_THEME_NAME,
        )
        parameters = Parameters.parse(payload)
        # A theme with no name is sent as a bare type byte (a3 01 04)
        if "a3" not in parameters or parameters["a3"].get("type") is None:
            return ""
        name = bytes(parameters["a3"].value or b"")
        return name.rstrip(b"\x00").decode("utf-8", errors="replace")

    ############
    # Internal #
    ############

    async def _post_connect(self) -> None:
        """Subscribe to telemetry and start the realtime stream once connected.

        The device streams nothing until it is subscribed, and pushes changes
        on its own only while the realtime stream runs; on a connected link
        that stream runs until it is stopped.
        """
        await self._send_command(cmd=CMD_SUBSCRIBE, parameters=PARAMETERS_SUBSCRIBE)
        await self._send_command(cmd=CMD_REALTIME, parameters=PARAMETERS_REALTIME_ON)

    async def _request(self, cmd: str, response: str) -> bytes:
        """Send a bare request and wait for its reply.

        :param cmd: The request's command.
        :param response: The reply's command.
        :raises TimeoutError: If no response from device.
        :returns: The reply's payload.
        """
        await self._send_command(cmd=cmd, parameters=PARAMETERS_SUBSCRIBE)
        payload = await self._listen_for_packet(
            bytes.fromhex(TELEMETRY_PATTERN_A),
            bytes.fromhex(response),
        )
        if not payload:
            msg = "Timed out waiting for payload!"
            raise TimeoutError(msg)
        return payload

    def _expansion(self) -> Container | None:
        """Parse the expansion block, if a pack is attached.

        :returns: The parsed block, or None without data or with no pack.
        """
        expansion = self._tag("c0", C0_EXPANSION)
        return expansion if expansion is not None and expansion.connected else None

    def _backup(self) -> Container | None:
        """Parse the backup-plan tail of the time-of-use block.

        :returns: The parsed tail, or None without data or on firmware that
            doesn't send it.
        """
        tou = self._tag("d9", D9_TOU)
        return None if tou is None else tou.backup

    def _summary_percentage(self, name: str) -> int:
        """Read a percentage from the summary as a whole number.

        :param name: Summary field name.
        :returns: The percentage, or default int value until it is reported.
        """
        value = self._summary.get(name)
        return round(value) if isinstance(value, (int, float)) else DEFAULT_METADATA_INT

    def _summary_kwh(self, name: str) -> float | None:
        """Read an energy counter from the summary as kWh.

        :param name: Summary field name holding watt-hours.
        :returns: Energy in kWh, or None until a summary has been received.
        """
        value = self._summary.get(name)
        if not isinstance(value, (int, float)):
            return None
        return round(value / WH_PER_KWH, KWH_DIGITS)

    async def _process_session(
        self,
        cmd: bytes,
        payload: bytes,
        *,
        encrypted: bool,
    ) -> None:
        """Take the summary and the pushes, then hand the rest to the base.

        :param cmd: The command code of the packet.
        :param payload: The plain-text payload.
        :param encrypted: Whether the packet arrived encrypted.
        """
        msgtype = PacketCommand.parse(cmd).msgtype
        if msgtype not in (
            MSGTYPE_SUMMARY,
            MSGTYPE_EVENT_REPORT,
            MSGTYPE_EVENT_PUSH,
            MSGTYPE_OTA_STATUS,
        ):
            return await super()._process_session(cmd, payload, encrypted=encrypted)

        # A session push the client could decrypt proves it is authorized
        if encrypted and self._session is not None:
            self._session.on_session_push()

        if msgtype == MSGTYPE_SUMMARY:
            self._process_summary(payload)
        elif msgtype == MSGTYPE_OTA_STATUS:
            self._process_ota_status(Parameters.parse(payload))
        else:
            self._process_event(Parameters.parse(payload))
        self._run_state_changed_callbacks()
        return None

    def _process_summary(self, payload: bytes) -> None:
        """Decode a device summary into :attr:`summary`.

        :param payload: The plain-text summary payload.
        """
        post = SummaryPayload.parse(payload)
        schema = (
            bytes(post.schema.value).rstrip(b"\x00").decode("ascii")
            if post.schema is not None and post.schema.value
            else None
        )
        fields: dict[str, SummaryField] | None = (
            SUMMARY_MAPS.get(schema) if schema is not None else None
        )
        if fields is None and schema not in self._unmapped_summary_schemas:
            self._unmapped_summary_schemas.add(schema)
            _LOGGER.warning(
                f"'{self.name}' posts summary schema '{schema}', which has no "
                f"field map; its fields are kept by path only!",
            )

        fields = fields or {}
        arrays = {path: field.array for path, field in fields.items() if field.array}
        signed = {path for path, field in fields.items() if field.signed}
        raw = walk_protobuf(post.protobuf, arrays=arrays, signed=signed)
        self._summary = name_summary(raw, fields)
        self._summary_schema = schema
        self._last_summary_timestamp = datetime.now()  # noqa: DTZ005  # as last_update

    def _process_event(self, parameters: ParameterDict) -> None:
        """Record an event report or event push as :attr:`last_event`.

        :param parameters: The event's parameters.
        """
        code = self._parameter(parameters, "a2", EVENT_CODE)
        try:
            event = DeviceEventType(code)
        except ValueError:
            event = DeviceEventType.UNKNOWN

        start = end = None
        battery_percentage = None
        if event is DeviceEventType.GRID_LOSS:
            battery_percentage = self._parameter(parameters, "a3", Int8ub)
        else:
            start = self._parameter(parameters, "a3", EPOCH)
            end = self._parameter(parameters, "a4", EPOCH)

        self._last_event = DeviceEvent(
            event=event,
            code=DEFAULT_METADATA_INT if code is None else code,
            start=None if start is None else _epoch(start),
            end=None if end is None else _epoch(end),
            battery_percentage=battery_percentage,
            received=datetime.now(),  # noqa: DTZ005  # naive local, as last_update
        )

    def _process_ota_status(self, parameters: ParameterDict) -> None:
        """Record the firmware-update readiness the device reported.

        :param parameters: The readiness push or reply's parameters.
        """
        allowed = self._parameter(parameters, "a2", Int8ub)
        if allowed is not None:
            self._ota_allowed = bool(allowed)
        reason = self._parameter(parameters, "a3", Int8ub)
        if reason is not None:
            try:
                self._ota_block_reason = OtaBlockReason(reason)
            except ValueError:
                self._ota_block_reason = OtaBlockReason.UNKNOWN

    @staticmethod
    def _parameter(parameters: ParameterDict, key: str, field: Struct) -> int | None:
        """Parse one parameter of a push with the given construct.

        :param parameters: The push's parameters.
        :param key: The parameter (e.g ``"a2"``) to read.
        :param field: The construct to parse its value with.
        :returns: The value, or None if absent or too short.
        """
        if key not in parameters:
            return None
        value: int | None = _parse_guarded(parameters[key].value or b"", field)
        return value

    def _reset_session(self, reset_data: bool = True) -> None:  # noqa: FBT001, FBT002  # base signature
        """Reset negotiated variables, and the summary along with the data.

        :param reset_data: Whether the cached data is cleared too.
        """
        super()._reset_session(reset_data)
        if reset_data:
            self._summary = {}
            self._summary_schema = None
            self._last_summary_timestamp = None
