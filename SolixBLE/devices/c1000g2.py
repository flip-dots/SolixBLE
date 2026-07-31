"""C1000(X) Gen 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..device import SolixBLEDevice
from ..states import PortStatus

#: Command sent after connecting to start the telemetry stream. Unlike the gen-1
#: models, the Gen 2 streams nothing until it receives this subscribe command.
CMD_SUBSCRIBE = "4100"
SUBSCRIBE_PAYLOAD = "a10121"

CMD_AC_OUTPUT = "4101"
CMD_DC_OUTPUT = "4102"

PAYLOAD_ON = "a10121a2020101"
PAYLOAD_OFF = "a10121a2020100"


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
            cmd=bytes.fromhex(CMD_SUBSCRIBE),
            payload=bytes.fromhex(SUBSCRIBE_PAYLOAD),
        )

    async def turn_ac_on(self) -> None:
        """Turn the AC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_OUTPUT), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_ac_off(self) -> None:
        """Turn the AC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_AC_OUTPUT), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def turn_dc_on(self) -> None:
        """Turn the DC (12 V) output on.

        Confirmed on real hardware: the 12 V port physically switched and the
        ``b2`` status byte latched on. The Gen 2 reuses the AC on/off payload on
        a different command code (``4102``).

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_dc_off(self) -> None:
        """Turn the DC (12 V) output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("a2", begin=3, end=20)

    @property
    def part_number(self) -> str:
        """Device part number.

        :returns: Device part number or default str value.
        """
        return self._parse_string("a2", begin=22, end=27)

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("a5", begin=1, end=2, signed=True)

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a5", begin=3, end=4)

    @property
    def battery_health(self) -> int:
        """Battery health.

        :returns: Percentage battery health or default int value.
        """
        return self._parse_int("a5", begin=4, end=5)

    @property
    def power_out(self) -> int:
        """Total Power Out (watts).

        :returns: Total power out or default int value.
        """
        return self._parse_int("a6", begin=1, end=3)

    @property
    def ac_power_in(self) -> int:
        """AC Power In (watts).

        :returns: Total AC power in or default int value.
        """
        return self._parse_int("a6", begin=3, end=5)

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
        return PortStatus(self._parse_int("a7", begin=1, end=2))

    @property
    def ac_power_out(self) -> int:
        """AC Power Out (watts).

        :returns: Total AC power out or default int value.
        """
        return self._parse_int("a7", begin=2, end=4)

    @property
    def solar_port(self) -> PortStatus:
        """Solar Port Status.

        :returns: Status of the solar port.
        """
        return PortStatus.from_input_only(self._parse_int("a8", begin=1, end=2))

    @property
    def solar_power_in(self) -> int:
        """Solar/DC Power In (watts).

        .. note:: Offset inferred, not yet confirmed on hardware (no solar/DC-in capture taken).

        :returns: Solar/DC power in or default int value.
        """
        return self._parse_int("a8", begin=2)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("aa", begin=1, end=2))

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._parse_int("aa", begin=2)

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("ab", begin=1, end=2))

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._parse_int("ab", begin=2)

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("ac", begin=1, end=2))

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power (watts).

        :returns: USB port C3 power or default int value.
        """
        return self._parse_int("ac", begin=2)

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("ae", begin=1, end=2))

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._parse_int("ae", begin=2)

    @property
    def dc_output(self) -> PortStatus:
        """DC Port Status.

        Confirmed on hardware: ``b2[1]`` latched ``01`` (OUTPUT) when the 12 V
        port was switched on and ``00`` (NOT_CONNECTED) when off.

        :returns: Status of the DC output port.
        """
        return PortStatus(self._parse_int("b2", begin=1, end=2))

    @property
    def dc_power_out(self) -> int:
        """DC Power Out (watts).

        Confirmed on hardware: ``b2`` [2:4] read 6 W with a 12 V load on the DC
        output, matching the ``04 <status> <watts LE>`` per-port shape.

        :returns: DC power out or default int value.
        """
        return self._parse_int("b2", begin=2)

    @property
    def max_battery_percentage(self) -> int:
        """Maximum charge percentage.

        :returns: Battery charge percentage upper limit or default int value.
        """
        return self._parse_int("d9", begin=4, end=5)

    @property
    def min_battery_percentage(self) -> int:
        """Minimum charge percentage.

        :returns: Battery charge percentage lower limit or default int value.
        """
        return self._parse_int("d9", begin=5, end=6)
