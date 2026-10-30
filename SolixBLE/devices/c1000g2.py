"""C1000(X) Gen 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
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
)

from SolixBLE.const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.constructs import PPS_M6_TOU, TOU_PERIOD, WeekdayMask
from SolixBLE.device import SolixBLEDevice
from SolixBLE.states import (
    ClockTheme,
    DisplayTimeout,
    LightStatus,
    PortStatus,
    TariffType,
    TouPeriod,
)


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


@dataclass(frozen=True)
class DisplayPlan:
    """The display's clock screen and its day / night schedule.

    :param screensaver_enabled: Whether the clock screensaver shows.
    :param clock_theme: Clock theme: THEME_1-3, or CATALOG while a downloaded
        theme shows, which can't be selected here.
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
    clock_theme: ClockTheme
    clock_24h: bool
    day_start: int
    day_end: int
    weekdays: frozenset[int]
    night_enabled: bool
    day_brightness: int
    night_brightness: int
    night_start: int
    night_end: int


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
number, controller firmware and two model bytes.
"""

A5_BATTERY = Struct(
    "temperature" / Int8sb,
    "charge_discharge_status" / Int8ub,
    "battery_percentage" / Int8ub,
    "battery_health" / Int8ub,
)
"""
Main battery (``a5``): temperature (C), port-flow code, state of charge and
a health byte.
"""

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
plugged in, and the input power (W).
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

#: Time remaining (0.1 h) that means there is no estimate: the battery's
#: 0xFFFF minutes, scaled.
NO_ESTIMATE = 10923

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

DA_DISPLAY_PLAN = Struct(
    "screensaver_and_theme" / Int8ub,
    "theme_download_state" / Int8ub,
    "theme_id" / Int32ul,
    "theme_crc" / Int32ul,
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
screensaver switch and the low 4 bits the theme; times are minutes from
midnight.
"""

#: Display brightness percentages by the level the device stores (0 or 1).
DISPLAY_PLAN_BRIGHTNESS = (5, 20)

#: Screensaver switch bit of the clock screen's theme byte.
SCREENSAVER_BIT = 0x80

#: Epoch the device sends for a window with no end.
NO_END = 0xFFFFFFFF


def epoch_to_local(value: int) -> datetime | None:
    """Read a u32 epoch the way the device reports windows.

    :param value: The epoch.
    :returns: The local time, or None for 0 (no window) and for no end.
    """
    if value in (0, NO_END):
        return None
    return datetime.fromtimestamp(value)  # noqa: DTZ006  # naive local, as the base device


#: Command sent after connecting to start the telemetry stream. Unlike the gen-1
#: models, the Gen 2 streams nothing until it receives this subscribe command.
CMD_SUBSCRIBE = 0x100

PARAMETERS_SUBSCRIBE = {
    "a1": {
        "value": "21",
    },
}

CMD_AC_OUTPUT = 0x101
CMD_DC_OUTPUT = 0x102

PARAMETERS_ON = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": 1,
    },
}

PARAMETERS_OFF = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": 0,
    },
}

#: The AC group takes its charging power limit at a4 as a u16 of watts.
PARAMETERS_AC_CHARGING_POWER = {
    "a1": {
        "value": "21",
    },
    "a4": {
        "type": 2,
        # _to_bytes passes keyword arguments by the lambda's parameter names
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

#: System group: display, SoC limits, language and the outage alert.
CMD_SYSTEM = 0x103

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

#: Highest battery percentage for the charge cap and discharge floor.
MAX_PERCENTAGE = 100


def _validate_percentage(percentage: int) -> None:
    """Range-check a charge cap or discharge floor.

    :param percentage: Battery percentage.
    :raises ValueError: If out of range.
    """
    if not 0 <= percentage <= MAX_PERCENTAGE:
        msg = f"Percentage must be 0-{MAX_PERCENTAGE}"
        raise ValueError(msg)


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

#: Backup-plan group: a3 = 3 selects the backup plans, a4 the plan and a5
#: switches it.
CMD_BACKUP = 0x05E
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

#: Time-of-use plan: a2 the mode, a5 the reserve (left out to keep the
#: current one), a6 the period count and a7 the periods. The device ignores
#: a3 and a4.
CMD_TOU_PLAN = 0x090

PARAMETERS_TOU_PLAN = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda enabled: 1 if enabled else 0,
    },
    "a5": {
        "type": 1,
        "value": lambda percentage: percentage,
    },
    "a6": {
        "type": 1,
        # _to_bytes passes keyword arguments by the lambda's parameter names
        "value": lambda records: len(records),  # noqa: PLW0108
    },
    "a7": {
        "type": 4,
        "value": lambda records: TOU_PERIOD[len(records)].build(records),
    },
}

#: Most periods a time-of-use plan holds; the device copies them into an
#: 18-byte buffer without checking.
MAX_TOU_PERIODS = 6

#: Hours in a day, the latest a time-of-use period may end.
HOURS_PER_DAY = 24

#: Tariffs a time-of-use period can take.
TOU_TARIFFS = (TariffType.PEAK, TariffType.MID_PEAK, TariffType.OFF_PEAK)


def _validate_tou_periods(periods: list[TouPeriod]) -> None:
    """Range-check time-of-use periods before they are sent.

    :param periods: The periods.
    :raises ValueError: If there are too many or one is out of range.
    """
    if len(periods) > MAX_TOU_PERIODS:
        msg = f"A time-of-use plan holds at most {MAX_TOU_PERIODS} periods"
        raise ValueError(msg)
    for period in periods:
        if period.tariff not in TOU_TARIFFS:
            msg = "A time-of-use period must be PEAK, MID_PEAK or OFF_PEAK"
            raise ValueError(msg)
        if not 0 <= period.start_hour < period.end_hour <= HOURS_PER_DAY:
            msg = (
                f"A time-of-use period must end after it starts, within "
                f"0-{HOURS_PER_DAY} hours"
            )
            raise ValueError(msg)


#: Clock-screen group: the app writes only the tags that change.
CMD_DISPLAY_PLAN = 0x091

#: Minutes in a day, the latest a display period may end.
MINUTES_PER_DAY = 1440

#: Clock themes the display plan can select.
BUILT_IN_THEMES = (ClockTheme.THEME_1, ClockTheme.THEME_2, ClockTheme.THEME_3)

#: Bits of the clock screen's theme byte the device reads as the theme; it
#: shows Theme 1 for any index past the catalog theme.
CLOCK_THEME_MASK = 0x0F

#: The 4091 tag, type and encoder of each display plan setting: the fields it
#: carries, its type byte, and the value it sends. a2 holds both the
#: screensaver (bit 7) and the clock theme's index (the low bits).
DisplayPlanTag = tuple[tuple[str, ...], int, Callable[[DisplayPlan], int | bytes]]

DISPLAY_PLAN_TAGS: dict[str, DisplayPlanTag] = {
    "a2": (
        ("screensaver_enabled", "clock_theme"),
        1,
        lambda plan: (
            (SCREENSAVER_BIT if plan.screensaver_enabled else 0)
            | plan.clock_theme.value
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


def _validate_display_plan(plan: DisplayPlan, current: DisplayPlan) -> None:
    """Range-check a display plan before it is sent.

    :param plan: The display plan.
    :param current: The device's display plan, whose clock theme may stay as
        it is even when it can't be selected.
    :raises ValueError: If a setting is out of range.
    """
    minutes = (plan.day_start, plan.day_end, plan.night_start, plan.night_end)
    if not all(0 <= value <= MINUTES_PER_DAY for value in minutes):
        msg = f"Display periods must be 0-{MINUTES_PER_DAY} minutes from midnight"
        raise ValueError(msg)
    if plan.clock_theme != current.clock_theme and (
        plan.clock_theme not in BUILT_IN_THEMES
    ):
        msg = "Clock theme must be THEME_1, THEME_2 or THEME_3"
        raise ValueError(msg)
    if not plan.weekdays <= frozenset(range(7)):
        msg = "Weekdays must be 0 (Monday) to 6 (Sunday)"
        raise ValueError(msg)
    brightness = (plan.day_brightness, plan.night_brightness)
    if not all(value in DISPLAY_PLAN_BRIGHTNESS for value in brightness):
        msg = f"Display brightness must be one of {DISPLAY_PLAN_BRIGHTNESS} %"
        raise ValueError(msg)


class C1000G2(SolixBLEDevice):
    """
    C1000(X) Gen 2 Power Station.

    Use this class to connect, monitor and control a Gen 2 C1000(X) power
    station. This model is also known as the A1763.

    The Gen 2 uses the same encryption and telemetry framing as the gen-1
    models but with different command codes: it must be sent a subscribe command
    (``4100``) after connecting before it streams any telemetry, its telemetry
    arrives on commands ``c421``/``c900``, its AC output is controlled with
    command ``4101`` and its DC output with command ``4102``. Telemetry and
    AC/DC on/off control have been confirmed on real hardware.
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    #: The Gen 2 pushes telemetry on different message types to the gen-1 models.
    _TELEMETRY_COMMANDS: tuple[int, ...] = (0x421, 0x900)

    async def _post_connect(self) -> None:
        """Subscribe to telemetry once connected.

        The Gen 2 streams no telemetry until it receives this command, so we send
        it after every (re)connection.
        """
        await self._send_command(CMD_SUBSCRIBE, PARAMETERS_SUBSCRIBE)

    async def turn_ac_on(self) -> None:
        """Turn the AC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(CMD_AC_OUTPUT, PARAMETERS_ON)

    async def turn_ac_off(self) -> None:
        """Turn the AC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(CMD_AC_OUTPUT, PARAMETERS_OFF)

    async def turn_dc_on(self) -> None:
        """Turn the DC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(CMD_DC_OUTPUT, PARAMETERS_ON)

    async def turn_dc_off(self) -> None:
        """Turn the DC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(CMD_DC_OUTPUT, PARAMETERS_OFF)

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
            CMD_SYSTEM,
            PARAMETERS_MAX_BATTERY,
            percentage=percentage,
        )

    async def set_min_battery_percentage(self, percentage: int) -> None:
        """Set the discharge floor, below which the device stops discharging.

        .. warning::
           The firmware accepts any percentage, not only the 1-20 the app
           offers. On the C2000 Gen 2 the floor also picks which battery runs:
           an expansion battery below it is left unused.

        :param percentage: Discharge floor, 0-100.
        :raises ValueError: If the percentage is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        _validate_percentage(percentage)
        await self._send_command(
            CMD_SYSTEM,
            PARAMETERS_MIN_BATTERY,
            percentage=percentage,
        )

    async def set_ac_charging_power(self, watts: int) -> None:
        """Set the AC charging power limit in watts.

        .. note::
           :collapsible: closed

           The firmware takes any 16-bit value, so the only bound applied is
           the device's reported :attr:`max_input_power` once telemetry has
           arrived. The app offers 100-1200 W in steps of 100 on a C1000 Gen 2
           and 500-1800 W on a C2000 Gen 2.

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
            CMD_AC_OUTPUT,
            PARAMETERS_AC_CHARGING_POWER,
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
            CMD_AC_OUTPUT,
            PARAMETERS_AC_FAST_CHARGE,
            on=True,
        )

    async def turn_ac_fast_charge_off(self) -> None:
        """Turn ultrafast AC charging off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_AC_OUTPUT,
            PARAMETERS_AC_FAST_CHARGE,
            on=False,
        )

    async def set_ac_timer(self, seconds: int) -> None:
        """Set the AC auto-off timer.

        :param seconds: Seconds until AC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_AC_OUTPUT,
            PARAMETERS_TIMER,
            seconds=seconds,
        )

    async def set_dc_timer(self, seconds: int) -> None:
        """Set the DC (car socket) auto-off timer.

        :param seconds: Seconds until DC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_DC_OUTPUT,
            PARAMETERS_TIMER,
            seconds=seconds,
        )

    async def turn_display_on(self) -> None:
        """Turn the display on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(CMD_SYSTEM, PARAMETERS_DISPLAY, on=True)

    async def turn_display_off(self) -> None:
        """Turn the display off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_SYSTEM,
            PARAMETERS_DISPLAY,
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
            CMD_SYSTEM,
            PARAMETERS_DISPLAY_MODE,
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
            CMD_SYSTEM,
            PARAMETERS_DISPLAY_TIMEOUT,
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
            CMD_SYSTEM,
            PARAMETERS_DISPLAY_LANGUAGE,
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
        _validate_display_plan(plan, current)

        parameters: dict[str, dict[str, object]] = {"a1": {"value": "21"}}
        for tag, (fields, data_type, encode) in DISPLAY_PLAN_TAGS.items():
            if any(getattr(plan, f) != getattr(current, f) for f in fields):
                parameters[tag] = {"type": data_type, "value": encode(plan)}
        if len(parameters) == 1:
            return

        await self._send_command(CMD_DISPLAY_PLAN, parameters)

    async def turn_fast_charging_plan_on(self) -> None:
        """Turn the Fast Charging Plan on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_BACKUP,
            PARAMETERS_BACKUP_SWITCH,
            plan=BACKUP_FAST_CHARGING_PLAN,
            on=True,
        )

    async def turn_fast_charging_plan_off(self) -> None:
        """Turn the Fast Charging Plan off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_BACKUP,
            PARAMETERS_BACKUP_SWITCH,
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
            CMD_BACKUP,
            PARAMETERS_BACKUP_WINDOW,
            start=start_epoch,
            end=end_epoch,
        )

    async def turn_storm_guard_on(self) -> None:
        """Turn Storm Guard on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_BACKUP,
            PARAMETERS_BACKUP_SWITCH,
            plan=BACKUP_STORM_GUARD,
            on=True,
        )

    async def turn_storm_guard_off(self) -> None:
        """Turn Storm Guard off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_BACKUP,
            PARAMETERS_BACKUP_SWITCH,
            plan=BACKUP_STORM_GUARD,
            on=False,
        )

    async def set_tou_plan(
        self,
        periods: list[TouPeriod],
        *,
        enabled: bool,
        reserve_battery_percentage: int | None = None,
    ) -> None:
        """Set the time-of-use plan.

        Periods are whole hours on the device clock and may leave gaps; one
        that crosses midnight is sent as two. :attr:`active_tariff` lists when
        a period takes effect.

        :param periods: Up to 6 periods, each ending after it starts.
        :param enabled: True for time-of-use, False for the standard mode.
        :param reserve_battery_percentage: Battery percentage the plan keeps in
            reserve, 0-100, or None to keep the current one.
        :raises ValueError: If a period or the reserve is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        _validate_tou_periods(periods)
        parameters = PARAMETERS_TOU_PLAN
        if reserve_battery_percentage is None:
            parameters = {
                tag: spec for tag, spec in PARAMETERS_TOU_PLAN.items() if tag != "a5"
            }
        else:
            _validate_percentage(reserve_battery_percentage)

        await self._send_command(
            CMD_TOU_PLAN,
            parameters,
            enabled=enabled,
            percentage=reserve_battery_percentage,
            records=[
                {
                    "tariff": period.tariff.value,
                    "start_hour": period.start_hour,
                    "end_hour": period.end_hour,
                }
                for period in periods
            ],
        )

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

        :returns: Percentage battery health or default int value.
        """
        battery = self._tag("a5", A5_BATTERY)
        return DEFAULT_METADATA_INT if battery is None else battery.battery_health

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

        .. note::
           :collapsible: closed

           The AC port status is the first byte of the ``a7`` parameter,
           mirroring the ``04 <status> <watts LE>`` per-port shape used by the
           DC port (``b2``) and the USB ports; ``ac_power_out`` reads the watts
           from this same ``a7`` TLV. Confirmed on hardware: ``a7[1]`` latches
           ``01`` (OUTPUT) when AC is on and ``00`` when off, tracking the relay.
           (The ``a4`` parameter is constant at the previously-used offset and
           does NOT reflect the AC state.)

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
    def dc_input_port(self) -> PortStatus:
        """DC input (XT-60i) port status.

        The one DC input port, whatever is plugged into it: a solar array, the
        12 V car-socket adapter or the Alternator Charger.

        PortStatus.INPUT signifies a source is present, NOT_CONNECTED that the
        port is empty. Presence only; it does not imply current is flowing.

        .. note::
           A solar array counts as present only while its panels give a
           voltage, so it reads NOT_CONNECTED at night with the panels still
           attached. The 12 V car-socket adapter reads INPUT at 0 W.

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
        """DC Port Status.

        Confirmed on hardware: ``b2[1]`` latched ``01`` (OUTPUT) when the 12 V
        port was switched on and ``00`` (NOT_CONNECTED) when off.

        :returns: Status of the DC output port.
        """
        port = self._tag("b2", PORT_STATUS_POWER)
        return PortStatus.UNKNOWN if port is None else PortStatus(port.status)

    @property
    def dc_power_out(self) -> int:
        """DC Power Out (watts).

        Confirmed on hardware: ``b2`` [2:4] read 6 W with a 12 V load on the DC
        output, matching the ``04 <status> <watts LE>`` per-port shape.

        :returns: DC power out or default int value.
        """
        port = self._tag("b2", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

    @property
    def max_battery_percentage(self) -> int:
        """Maximum charge percentage.

        :returns: Battery charge percentage upper limit or default int value.
        """
        tou = self._tag("d9", PPS_M6_TOU)
        return DEFAULT_METADATA_INT if tou is None else tou.max_battery_percentage

    @property
    def min_battery_percentage(self) -> int:
        """Minimum charge percentage.

        :returns: Battery charge percentage lower limit or default int value.
        """
        tou = self._tag("d9", PPS_M6_TOU)
        return DEFAULT_METADATA_INT if tou is None else tou.min_battery_percentage

    @property
    def ac_input_port(self) -> PortStatus:
        """AC input (mains) status.

        PortStatus.INPUT signifies the mains lead is plugged in, NOT_CONNECTED
        that it is not. Presence only; it does not imply current is flowing.

        :returns: Status of the AC input.
        """
        ac = self._tag("a7", A7_AC)
        return (
            PortStatus.UNKNOWN
            if ac is None
            else PortStatus.from_input_only(ac.input_status)
        )

    @property
    def max_input_power(self) -> int:
        """Most charge-input power the unit can draw (W).

        :returns: Maximum input power in watts, or default int value if there
            is no data.
        """
        status = self._tag("a3", A3_STATUS)
        return DEFAULT_METADATA_INT if status is None else status.max_input_power

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
    def display_plan(self) -> DisplayPlan | None:
        """The display's clock screen and its day / night schedule.

        :returns: The display plan, or None without data.
        """
        plan = self._tag("da", DA_DISPLAY_PLAN)
        if plan is None:
            return None

        theme = plan.screensaver_and_theme & CLOCK_THEME_MASK
        return DisplayPlan(
            screensaver_enabled=bool(plan.screensaver_and_theme & SCREENSAVER_BIT),
            clock_theme=(
                ClockTheme(theme)
                if theme <= ClockTheme.CATALOG.value
                else ClockTheme.THEME_1
            ),
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

    @property
    def tou_enabled(self) -> bool | None:
        """Whether the time-of-use plan is switched on.

        :returns: True if on, False if off, or default bool value.
        """
        tou = self._tag("d9", PPS_M6_TOU)
        return DEFAULT_METADATA_BOOL if tou is None else bool(tou.tou_mode)

    @property
    def active_tariff(self) -> TariffType:
        """Tariff of the time-of-use period in force.

        .. note::
           A period is in force only while time-of-use is on, the device is
           bound to an Anker account and on WiFi, it has AC input, no
           Alternator Charger is attached, Battery-Only Power is off and the
           clock is inside one of :attr:`tou_periods`; otherwise this reads
           NONE. The plan may be written from any client.

        .. warning::
           During a PEAK or MID_PEAK period the device stops charging from AC
           while the battery is at or above the greater of
           :attr:`reserve_battery_percentage` and
           :attr:`min_battery_percentage` + 5 % (0.3 % higher while it is
           already charging). OFF_PEAK and NONE charge as usual, and the AC
           output is not affected.

        :returns: Active tariff, NONE, or UNKNOWN.
        """
        tou = self._tag("d9", PPS_M6_TOU)
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
        tou = self._tag("d9", PPS_M6_TOU)
        return DEFAULT_METADATA_INT if tou is None else tou.reserve_battery_percentage

    @property
    def tou_periods(self) -> list[TouPeriod]:
        """Periods of the time-of-use plan.

        :returns: The periods in the order stored, empty without data.
        """
        tou = self._tag("d9", PPS_M6_TOU)
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
        start = epoch_to_local(backup.fast_charging_plan_start)
        end = epoch_to_local(backup.fast_charging_plan_end)
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
        start = epoch_to_local(backup.backup_window_start)
        end = epoch_to_local(backup.backup_window_end)
        return (start, end) if start is not None else None

    def _backup(self) -> Container | None:
        """Parse the backup-plan tail of the time-of-use block.

        :returns: The parsed tail, or None without data or on firmware that
            doesn't send it.
        """
        tou = self._tag("d9", PPS_M6_TOU)
        return None if tou is None else tou.backup
