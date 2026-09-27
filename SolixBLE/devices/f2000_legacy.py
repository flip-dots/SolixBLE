"""F2000 (pre-P) / 767 PowerHouse power station model.

Note this module supports older Anker SOLIX 767 / F2000, model number A1780.
This model was a different control scheme from the revised F2000P, model number A1780P, introduced in roughly 2024.

.. moduleauthor:: Chuck Claunch <cclaunch@gmail.com>

Thanks to Silverstone-ui and his github.com/Silverstone-ui/SolixBLEF2000 repo for discovery of the
extended packet.
"""

import logging
import time
from datetime import datetime, timedelta
from enum import IntEnum

from bleak import BleakClient
from construct import (
    Bytes,
    Checksum,
    ExprAdapter,
    Hex,
    HexDump,
    Int8ul,
    Int16ub,
    Int16ul,
    RawCopy,
    Rebuild,
    Struct,
    this,
)
from construct import Enum as CEnum

from SolixBLE.const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.constructs import ParameterContainer, Parameters, _get_val
from SolixBLE.device import SolixBLEDevice
from SolixBLE.states import (
    ChargingStatus,
    DisplayTimeout,
    LightStatus,
    PortStatus,
    TemperatureUnit,
)
from SolixBLE.utilities import _to_bytes

_LOGGER = logging.getLogger(__name__)


CMD_GET_STATUS = "0101"
CMD_AC_TIMER = "0202"
CMD_DC_TIMER = "0203"
CMD_AC_CHARGING_POWER = "0280"
CMD_DISPLAY_TIMEOUT = "0282"
CMD_AC_OUTPUT = "0286"
CMD_DC_OUTPUT = "0287"
CMD_DISPLAY_MODE = "0288"
CMD_POWER_SAVING_MODE = "028a"
CMD_LIGHT_MODE = "028b"

PARAMETERS_INT = {
    "value": lambda value, length: value.to_bytes(
        length=length,
        byteorder="little",
        signed=False,
    ),
}

KEY_NORM = "a1"
KEY_EXT = "a2"


class PacketLegacyHeader(IntEnum):
    """Packet header in legacy Solix format. Depends on data direction."""

    RECEIVE = 0x09ff
    TRANSMIT = 0x08ee

PacketLegacy = ExprAdapter(

    # Structure of the packet
    Struct(

        # Bytes of packet excluding checksum
        "content" / RawCopy(
            Struct(

                # Header of the packet
                "header" / CEnum(Int16ub, PacketLegacyHeader),

                # Pattern of the packet (e.g 000000, 000001)
                "pattern" / Hex(Bytes(3)),

                # Command of the packet (e.g turn on, off, etc)
                "cmd" / Hex(Bytes(2)),

                # Length of the entire packet
                "length" / Rebuild(Int16ul, lambda this: 10 + len(this.payload_bytes)),

                # Payload bytes of the packet (may be encrypted or fragmented)
                "payload_bytes" / HexDump(Bytes(lambda this: this.length - 10)),
            ),
        ),

        # Sum checksum of the packet
        "checksum" / Hex(Checksum(
            Int8ul,
            lambda data: sum(data) & 0xFF,
            this.content.data,
        )),
    ),

    # Encoders and decoders which allow for direct access
    # (e.g packet.cmd rather than packet.content.cmd)
    decoder=lambda p, _: p.content.value,
    encoder=lambda p, _: {
            "content": {
                "value": {
                    "header": _get_val(p, "header", PacketLegacyHeader.TRANSMIT),
                    "pattern": _to_bytes(_get_val(p, "pattern")),
                    "cmd": _to_bytes(_get_val(p, "cmd")),
                    "payload_bytes": _to_bytes(_get_val(p, "payload_bytes", b"")),
                },
            },
    },
)
"""
Legacy Anker device packet.

This class represents a packet of a Legacy Anker device known to be used in
early variants of the F2000. Packets are made up of a header, pattern, cmd,
size, payload, and a checksum.

Structure: <Header 2B> <Pattern 3B> <CMD 2B> <Size 2B> <Payload nB> <Checksum 1B>.

Usage:
    .. code-block:: python
       :linenos:

        packet = Packet.parse(packet_bytes)
        print(f"p: {packet.pattern}, c: {packet.cmd}, b: {packet.payload_bytes}")

        packet_bytes = Packet.build({
            "pattern": "000000",
            "cmd": "0000",
            "payload_bytes": "",
        })

"""


class F2000Legacy(SolixBLEDevice):
    """
    F2000 (non-P) Power Station.

    Use this class to connect and monitor a F2000(non-P, pre-2024) power station.
    This model is also known as the A1780 or the 767 PowerHouse.

    """

    # These are specific to the older firmware
    UUID_TELEMETRY = "00008888-0000-1000-8000-00805f9b34fb"
    UUID_COMMAND = "00007777-0000-1000-8000-00805f9b34fb"

    async def _keep_alive(self) -> int | None:
        """On connection send a full status update request."""
        await self.get_status_update()
        return None

    async def _process_telemetry_legacy(self, data: bytes, key: str) -> None:
        """Process telemetry data from the device.

        This is modified to work with legacy variants which do not use
        the same a1, a2, ... data structure.

        :param data: Payload bytes.
        :param key: The identity of this data (a1 for standard or a2 for extended).
        """
        self._last_data_timestamp = time.time()

        new_p = ParameterContainer(key=key, type=None, value=data)

        changed = (self._data is None or self._data.get(key) is None or
        self._data[key] != new_p)

        if self._data is None:
            self._data = Parameters.parse(b"")

        if changed:
            self._data[key] = new_p
            _LOGGER.debug("State change detected!")
            _LOGGER.debug(self)
            self._run_state_changed_callbacks()

    async def _process_notification(
        self, client: BleakClient, handle: int, data: bytearray,
    ) -> None:
        """Process a notification from the device."""

        try:

            _LOGGER.debug(f"The client the notification is from: {client}")

            if self._client is not client:
                _LOGGER.debug("Ignoring notification from old client")
                return None

            # Log reception of packet
            _LOGGER.debug(
                f"Received notification from '{self.name}'. length: {len(data)}, packet: '{data.hex()}'"
            )
            self._last_packet_timestamp = time.time()

            # Parse packet
            packet = PacketLegacy.parse(data)
            _LOGGER.debug(f"Packet: {packet}")
            pattern = packet.pattern
            cmd = packet.cmd
            payload = packet.payload_bytes

            # If the packet has a future registered then we just trigger that
            # future instead of processing it here
            if pattern + cmd in self._packet_futures:
                _LOGGER.debug(
                    "Packet has future(s) registered. Triggering future(s) and ignoring packet..."
                )
                for future in self._packet_futures[pattern + cmd]:

                    # Decrypt payload
                    payload = self._decrypt_payload(payload)
                    future.set_result(payload)
                return None

            # Match against common message types
            match cmd.hex():

                # Normal telemetry messages
                case "0149":
                    _LOGGER.debug("Received normal telemetry message!")
                    return await self._process_telemetry_legacy(data, KEY_NORM)

                # Extended telemetry messages
                case "0101":
                    _LOGGER.debug("Received extended telemetry message!")
                    return await self._process_telemetry_legacy(data, KEY_EXT)

                case _:
                    _LOGGER.warning(
                        f"Unexpected message '{cmd.hex()}' sent by device! {packet}",
                    )

        except Exception:
            _LOGGER.exception(f"Failed to process packet from {self.name}!")

            return None

    async def _send_packet(self, pattern: str, cmd: str, parameters: dict, **kwargs: dict) -> None:
        """
        Build and send packet to device.

        Parameter values may use lambda functions which will be executed at
        this point, where variables may be passed in as keyword arguments.
        """
        _LOGGER.debug(f"Building payload with parameters: {parameters}")
        payload = _to_bytes(data=parameters["value"], **kwargs | { "self": self })
        _LOGGER.debug(f"Payload bytes: {payload.hex()}")

        _LOGGER.debug(f"Building packet with pattern: {pattern} and cmd: {cmd}...")
        packet = PacketLegacy.build({
            "pattern": bytes.fromhex(pattern),
            "cmd": bytes.fromhex(cmd),
            "payload_bytes": payload,
        })
        _LOGGER.debug(f"Built packet: {packet.hex()}")
        _LOGGER.debug("Sending packet...")
        await self._client.write_gatt_char(self.UUID_COMMAND, packet)
        _LOGGER.debug("Packet sent!")

    async def _send_command(self, cmd: str, parameters: dict, **kwargs: dict) -> None:
        """Send a command to the device.

        Parameter values may use lambda functions which will be executed at
        this point, where variables may be passed in as keyword arguments.

        :param cmd: 2 bytes containing command type.
        :param parameters: Parameter dictionary to send.
        :raises ConnectionError: If not connected/negotiated to device.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        await self._send_packet(
            pattern="000000",
            cmd=cmd,
            parameters=parameters,
            **kwargs,
        )

    def _parse_int(
            self,
            key: str,
            begin: int | None = None,
            end: int | None = None,
            signed: bool = False,  # noqa: FBT001, FBT002
        ) -> int:
            if self._data is None or self._data.get(key) is None:
                return DEFAULT_METADATA_INT
            return super()._parse_int(key, begin, end, signed)

    @property
    def negotiated(self) -> bool:
        """Not applicable to this device type."""
        return self.connected

    @property
    def available(self) -> bool:
        """Connected to device and data is available.

        :returns: True/False if the device is connected and sending telemetry.
        """
        return self.negotiated and self._data is not None

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int(KEY_NORM, begin=41, end=43)

    @property
    def light(self) -> LightStatus:
        """Light Status.

        :returns: Status of the light bar.
        """
        return LightStatus(self._parse_int(KEY_EXT, begin=117, end=118))

    @property
    def hours_remaining(self) -> float:
        """Time remaining to full/empty.

        Note that any hours over 24 are overflowed to the
        days remaining. Use time_remaining if you want
        days to be included.

        :returns: Hours remaining or default float value.
        """
        return self._parse_int(KEY_NORM, begin=17, end=18) / 10.0

    @property
    def days_remaining(self) -> int:
        """Time remaining to full/empty.

        Note that any partial days are overflowed into
        the hours remaining. Use time_remaining if you want
        hours to be included.

        :returns: Days remaining or default int value.
        """
        return self._parse_int(KEY_NORM, begin=18, end=19)

    @property
    def time_remaining(self) -> float:
        """Time remaining to full/empty in hours.

        :returns: Hours remaining or default float value.
        """
        return (
            (self.days_remaining * 24) + self.hours_remaining
            if self._data is not None and self._data.get(KEY_NORM) is not None
            else DEFAULT_METADATA_FLOAT
        )

    @property
    def timestamp_remaining(self) -> datetime | None:
        """Timestamp of when device will be full/empty.

        :returns: Timestamp of when will be full/empty or None.
        """
        if self._data is None:
            return None
        return datetime.now() + timedelta(hours=self.time_remaining)  # noqa: DTZ005

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int(KEY_NORM, begin=70, end=71)

    @property
    def battery_percentage_expansion(self) -> int:
        """Battery Percentage of the expansion battery.

        :returns: Expansion battery percentage or 0 if not present or default int value.
        """
        return self._parse_int(KEY_NORM, begin=71, end=72)

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int(KEY_NORM, begin=66, end=67, signed=True)

    @property
    def temperature_expansion(self) -> int:
        """Temperature of the expansion battery if present (C).

        :returns: Expansion temp in degrees C or 0 if not present or default int value.
        """
        return self._parse_int(KEY_NORM, begin=67, end=68, signed=True)

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Configured temperature unit (returned temperature is always in degrees C).

        :returns: Configured temperature unit or default int value.
        """
        return TemperatureUnit(self._parse_int(KEY_EXT, begin=119, end=120))

    @property
    def battery_health(self) -> int:
        """Battery health as a percentage.

        :returns: Percentage of battery health or default int value.
        """
        return self._parse_int(KEY_NORM, begin=72, end=73)

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total power in or default int value.
        """
        return self._parse_int(KEY_NORM, begin=39, end=41)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int(KEY_NORM, begin=19, end=21)

    @property
    def ac_charging_power(self) -> int:
        """Configured AC charging power limit in watts.

        :returns: AC charging power limit or default int value.
        """
        return self._parse_int(KEY_EXT, begin=101, end=103)

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: AC socket output power in watts or default int value.
        """
        return self._parse_int(KEY_NORM, begin=21, end=23)

    @property
    def ac_output(self) -> PortStatus:
        """AC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of the AC port.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=63, end=64))

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int(KEY_NORM, begin=37, end=39)

    @property
    def dc_power_out(self) -> int:
        """DC Power Out.

        :returns: DC power out or default int value.
        """
        return (self.dc_1_power_out + self.dc_2_power_out
        if self._data is not None and self._data.get(KEY_NORM) is not None
        else DEFAULT_METADATA_INT)

    @property
    def dc_1_power_out(self) -> int:
        """DC Power out for port 1.

        :returns: DC power out for port 1 or default int value.
        """
        return self._parse_int(KEY_NORM, begin=33, end=35)

    @property
    def dc_2_power_out(self) -> int:
        """DC Power out for port 2.

        :returns: DC power out for port 2 or default int value.
        """
        return self._parse_int(KEY_NORM, begin=35, end=37)

    @property
    def dc_output(self) -> PortStatus:
        """DC Power out for port 1.

        :returns: DC power out for port 1 or default int value.
        """
        if (self.dc_output_1 is PortStatus.OUTPUT or
            self.dc_output_2 is PortStatus.OUTPUT):
            return PortStatus.OUTPUT
        if (self.dc_output_1 is PortStatus.NOT_CONNECTED or
            self.dc_output_2 is PortStatus.NOT_CONNECTED):
            return PortStatus.NOT_CONNECTED

        return PortStatus.UNKNOWN

    @property
    def dc_output_1(self) -> PortStatus:
        """DC Power out for port 1.

        :returns: DC power out for port 1 or default port value.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=80, end=81))

    @property
    def dc_output_2(self) -> PortStatus:
        """DC Power out for port 2.

        :returns: DC power out for port 2 or default port value.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=81, end=82))

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int(KEY_NORM, begin=13, end=15)

    @property
    def dc_timer(self) -> datetime | None:
        """Timestamp of DC timer.

        :returns: Timestamp of when DC timer expires or None.
        """
        if (
            self.dc_timer_remaining not in (DEFAULT_METADATA_INT, 0)
        ):
            return datetime.now() + timedelta(seconds=self.dc_timer_remaining)  # noqa: DTZ005
        return None

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._parse_int(KEY_NORM, begin=23, end=25)

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._parse_int(KEY_NORM, begin=25, end=27)

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power.

        :returns: USB port C3 power or default int value.
        """
        return self._parse_int(KEY_NORM, begin=27, end=29)

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._parse_int(KEY_NORM, begin=29, end=31)

    @property
    def usb_a2_power(self) -> int:
        """USB A2 Power.

        :returns: USB port A2 power or default int value.
        """
        return self._parse_int(KEY_NORM, begin=31, end=33)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=75, end=76))

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=76, end=77))

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=77, end=78))

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=78, end=79))

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB A2 Port Status.

        :returns: Status of the USB A2 port.
        """
        return PortStatus(self._parse_int(KEY_NORM, begin=79, end=80))

    @property
    def charging_status(self) -> ChargingStatus:
        """Charging status of the device.

        :returns: Status of charging.
        """
        return ChargingStatus(self._parse_int(KEY_NORM, begin=68, end=69))

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None or self._data.get(KEY_NORM) is None:
            return DEFAULT_METADATA_STRING

        return ".".join(str(self._data[KEY_NORM].value_legacy[47]))

    @property
    def serial_number(self) -> str:
        """Serial number.

        :returns: The serial number of the device.
        """
        if self._data is None or self._data.get(KEY_NORM) is None:
            return DEFAULT_METADATA_STRING

        return self._parse_string(KEY_NORM, begin=85, end=101)

    @property
    def power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        return (
            bool(self._parse_int(KEY_EXT, begin=117, end=118))
            if self._data is not None and KEY_EXT in self._data
            else DEFAULT_METADATA_BOOL
        )

    @property
    def display_timeout(self) -> int:
        """Display timeout limit in seconds.

        :returns: Display timeout in seconds or default int value.
        """
        return self._parse_int(KEY_EXT, begin=105, end=107)

    @property
    def display_mode(self) -> LightStatus:
        """Configured display brightness level.

        :returns: Display brightness as LightStatus (LOW/MEDIUM/HIGH) or UNKNOWN.
        """
        if self._data is None or KEY_EXT not in self._data:
            return LightStatus.UNKNOWN
        return LightStatus(self._parse_int(KEY_EXT, begin=115, end=116))

    async def get_status_update(self) -> None:
        """Request a status update from the device.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_GET_STATUS, parameters={"value": b""})

    async def set_ac_timer(self, seconds: int) -> None:
        """Set the AC auto-off timer.

        :param seconds: Seconds until AC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_AC_TIMER,
            parameters=PARAMETERS_INT,
            value=seconds,
            length=4,
        )

    async def set_dc_timer(self, seconds: int) -> None:
        """Set the DC auto-off timer.

        :param seconds: Seconds until DC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_DC_TIMER,
            parameters=PARAMETERS_INT,
            value=seconds,
            length=4,
        )

    async def set_ac_charging_power(self, watts: int) -> None:
        """Set the AC charging power limit in watts.

        :param watts: AC charging power limit in watts.
        :raises ValueError: If power value is out of valid range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if watts < 200 or watts > 1440:
            raise ValueError("AC charging power must be between 100 and 1440 W")

        await self._send_command(
            cmd=CMD_AC_CHARGING_POWER,
            parameters=PARAMETERS_INT,
            value=watts,
            length=2,
        )
        await self.get_status_update()

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:
        """Set the status/mode of the LCD display.

        :param mode: Mode/timeout to set display to (30s, 5m, 30m, etc).
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """

        if timeout is DisplayTimeout.UNKNOWN:
            raise ValueError("You cannot set the display timeout to unknown")
        await self._send_command(
            cmd=CMD_DISPLAY_TIMEOUT,
            parameters=PARAMETERS_INT,
            value=timeout.value,
            length=2,
        )
        await self.get_status_update()

    async def turn_ac_on(self) -> None:
        """Turn the AC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_AC_OUTPUT, parameters=PARAMETERS_INT, value=1, length=1)

    async def turn_ac_off(self) -> None:
        """Turn the AC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_AC_OUTPUT, parameters=PARAMETERS_INT, value=0, length=1)

    async def turn_dc_on(self) -> None:
        """Turn the DC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_DC_OUTPUT, parameters=PARAMETERS_INT, value=1, length=1)

    async def turn_dc_off(self) -> None:
        """Turn the DC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_DC_OUTPUT, parameters=PARAMETERS_INT, value=0, length=1)

    async def set_display_mode(self, mode: LightStatus) -> None:
        """Set the status/mode of the LCD display.

        :param mode: Mode/status to set display to (off/low/med/high).
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the display brightness status to unknown")
        if mode is LightStatus.SOS:
            raise ValueError("You cannot set the display brightness status to SOS")
        await self._send_command(
            cmd=CMD_DISPLAY_MODE,
            parameters=PARAMETERS_INT,
            value=mode.value,
            length=1,
        )
        await self.get_status_update()

    async def turn_power_saving_mode_on(self) -> None:
        """Turn the power saving mode on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_POWER_SAVING_MODE, parameters=PARAMETERS_INT, value=1, length=1)
        await self.get_status_update()

    async def turn_power_saving_mode_off(self) -> None:
        """Turn the power saving mode off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_POWER_SAVING_MODE, parameters=PARAMETERS_INT, value=0, length=1)
        await self.get_status_update()

    async def set_light_mode(self, mode: LightStatus) -> None:
        """Set the light mode of the LED bar.

        :param mode: Mode to set light bar to.
        :raises ValueError: If requested mode is invalid.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the light status to unknown")
        await self._send_command(
            cmd=CMD_LIGHT_MODE,
            parameters=PARAMETERS_INT,
            value=mode.value,
            length=1,
        )
        await self.get_status_update()
