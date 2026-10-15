"""C1000(X) Gen 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Array,
    Bytes,
    ExprAdapter,
    Flag,
    Int8sb,
    Int8ub,
    Int16ul,
    Int32ul,
    Optional,
    PascalString,
    Struct,
    this,
)

from SolixBLE.const import DEFAULT_METADATA_INT, DEFAULT_METADATA_STRING
from SolixBLE.device import SolixBLEDevice
from SolixBLE.states import PortStatus

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
    def solar_port(self) -> PortStatus:
        """Solar Port Status.

        :returns: Status of the solar port.
        """
        port = self._tag("a8", PORT_STATUS_POWER)
        return (
            PortStatus.UNKNOWN
            if port is None
            else PortStatus.from_input_only(port.status)
        )

    @property
    def solar_power_in(self) -> int:
        """Solar/DC Power In (watts).

        :returns: Solar/DC power in or default int value.
        """
        port = self._tag("a8", PORT_STATUS_POWER)
        return DEFAULT_METADATA_INT if port is None else port.power

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
