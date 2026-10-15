"""C1000(X) Gen 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Array,
    BitsInteger,
    BitStruct,
    Bytes,
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
)
from SolixBLE.constructs import WeekdayMask
from SolixBLE.device import SolixBLEDevice
from SolixBLE.states import LightStatus, PortStatus


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
CMD_SUBSCRIBE = "4100"

PARAMETERS_SUBSCRIBE = {
    "a1": {
        "value": "21",
    },
}

CMD_AC_OUTPUT = "4101"
CMD_DC_OUTPUT = "4102"

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

    #: The Gen 2 pushes telemetry on different command codes to the gen-1 models.
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("c421", "c900")

    async def _post_connect(self) -> None:
        """Subscribe to telemetry once connected.

        The Gen 2 streams no telemetry until it receives this command, so we send
        it after every (re)connection.
        """
        await self._send_command(
            cmd=CMD_SUBSCRIBE,
            parameters=PARAMETERS_SUBSCRIBE,
        )

    async def turn_ac_on(self) -> None:
        """Turn the AC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_AC_OUTPUT, parameters=PARAMETERS_ON)

    async def turn_ac_off(self) -> None:
        """Turn the AC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_AC_OUTPUT, parameters=PARAMETERS_OFF)

    async def turn_dc_on(self) -> None:
        """Turn the DC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_DC_OUTPUT, parameters=PARAMETERS_ON)

    async def turn_dc_off(self) -> None:
        """Turn the DC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_DC_OUTPUT, parameters=PARAMETERS_OFF)

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
        tou = self._tag("d9", D9_TOU)
        return DEFAULT_METADATA_INT if tou is None else tou.max_battery_percentage

    @property
    def min_battery_percentage(self) -> int:
        """Minimum charge percentage.

        :returns: Battery charge percentage lower limit or default int value.
        """
        tou = self._tag("d9", D9_TOU)
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
        tou = self._tag("d9", D9_TOU)
        return None if tou is None else tou.backup
