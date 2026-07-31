"""C300(X) DC power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from datetime import datetime, timedelta

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice
from ..states import (
    ChargingStatus,
    DisplayTimeout,
    LightStatus,
    PortOverload,
    PortStatus,
    TemperatureUnit,
)

CMD_DC_OUTPUT = "404b"
CMD_DISPLAY_ON_OFF = "4052"
CMD_LIGHT_MODE = "404f"
CMD_DISPLAY_TIMEOUT = "4046"
CMD_DISPLAY_MODE = "404c"

PAYLOAD_ON = "a10121a2020101"
PAYLOAD_OFF = "a10121a2020100"
PAYLOAD_LIGHT_MODE = "a10121a20201"
PAYLOAD_TIMEOUT_TIME = "a10121a20302"

class C300DC(SolixBLEDevice):
    """
    C300(X) DC Power Station.

    Use this class to connect and monitor a C300(X) DC power station.
    This model is also known as the A1728.

    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int("a2", begin=1)

    @property
    def dc_timer(self) -> datetime | None:
        """Timestamp of DC timer.

        :returns: Timestamp of when DC timer expires or None.
        """
        if (
            self.dc_timer_remaining != DEFAULT_METADATA_INT
            and self.dc_timer_remaining != 0
        ):
            return datetime.now() + timedelta(seconds=self.dc_timer_remaining)

    @property
    def hours_remaining(self) -> float:
        """Time remaining to full/empty.

        Note that any hours over 24 are overflowed to the
        days remaining. Use time_remaining if you want
        days to be included.

        :returns: Hours remaining or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return round(divmod(self.time_remaining, 24)[1], 1)

    @property
    def days_remaining(self) -> int:
        """Time remaining to full/empty.

        Note that any partial days are overflowed into
        the hours remaining. Use time_remaining if you want
        hours to be included.

        :returns: Days remaining or default int value.
        """
        if self._data is None:
            return DEFAULT_METADATA_INT

        return round(divmod(self.time_remaining, 24)[0])

    @property
    def time_remaining(self) -> float:
        """Time remaining to full/empty in hours.

        :returns: Hours remaining or default float value.
        """
        return (
            self._parse_int("a3", begin=1) / 10.0
            if self._data is not None
            else DEFAULT_METADATA_FLOAT
        )

    @property
    def timestamp_remaining(self) -> datetime | None:
        """Timestamp of when device will be full/empty.

        :returns: Timestamp of when will be full/empty or None.
        """
        if self._data is None:
            return None
        return datetime.now() + timedelta(hours=self.time_remaining)

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._parse_int("a4", begin=1)

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power.

        :returns: USB port C3 power or default int value.
        """
        return self._parse_int("a6", begin=1)

    @property
    def usb_c4_power(self) -> int:
        """USB C4 Power.

        :returns: USB port C4 power or default int value.
        """
        return self._parse_int("a7", begin=1)

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._parse_int("a8", begin=1)

    @property
    def usb_a2_power(self) -> int:
        """USB A2 Power.

        :returns: USB port A2 power or default int value.
        """
        return self._parse_int("a9", begin=1)

    @property
    def dc_power_out(self) -> int:
        """DC Power Out.

        :returns: DC power out or default int value.
        """
        return self._parse_int("aa", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int("ab", begin=1)

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total power in or default int value.
        """
        return self._parse_int("ac", begin=1)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def battery_capacity(self) -> int:
        """Current battery capacity in mAh.

        :returns: Current battery capacity or default int value.
        """
        return self._parse_int("af", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("b0", begin=1))])

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("b5", begin=1, signed=True)

    @property
    def charging_status(self) -> ChargingStatus:
        """Charging status of the device.

        :returns: Status of charging.
        """
        return ChargingStatus(self._parse_int("b6", begin=1))

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("b7", begin=1)

    @property
    def battery_health(self) -> int:
        """Battery health.

        :returns: Percentage battery health or default int value.
        """
        return self._parse_int("b8", begin=1)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("b9", begin=1))

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("ba", begin=1))

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("bb", begin=1))

    @property
    def usb_port_c4(self) -> PortStatus:
        """USB C4 Port Status.

        :returns: Status of the USB C4 port.
        """
        return PortStatus(self._parse_int("bc", begin=1))

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("bd", begin=1))

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB A2 Port Status.

        :returns: Status of the USB A2 port.
        """
        return PortStatus(self._parse_int("be", begin=1))

    @property
    def dc_port(self) -> PortStatus:
        """DC Port Status.

        :returns: Status of the DC port.
        """
        return PortStatus(self._parse_int("bf", begin=1))

    @property
    def device_overload(self) -> PortOverload:
        """Device overload status.

        :returns: Device overload status or default int value.
        """
        return PortOverload(self._parse_int("c1", begin=1))

    @property
    def serial_number(self) -> str:
        """Serial number.

        :returns: The serial number of the device.
        """
        return self._parse_string("c3", begin=1)

    @property
    def device_timeout(self) -> int:
        """Configured device timeout in minutes.

        :returns: Configured device timeout or default int value.
        """
        return self._parse_int("c4", begin=1)

    @property
    def display_timeout(self) -> int:
        """Configured display timeout in seconds.

        :returns: Configured display timeout or default int value.
        """
        return self._parse_int("c5", begin=1)

    @property
    def display_mode(self) -> LightStatus:
        """Configured display backlight brightness.

        :returns: Configured display backlight brightness.
        """
        return LightStatus(self._parse_int("c7", begin=1))

    @property
    def light(self) -> LightStatus:
        """Light Status.

        :returns: Status of the light bar.
        """
        return LightStatus(self._parse_int("c8", begin=1))

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Configured temperature unit (returned temperature is always in degrees C).

        :returns: Configured temperature unit or default int value.
        """
        return TemperatureUnit(self._parse_int("c9", begin=1))

    @property
    def is_display_on(self) -> bool:
        """Display on status.

        :returns: Status of the display.
        """
        return (
            bool(self._parse_int("ca", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    @property
    def light_timeout(self) -> int:
        """Configured light timeout in minutes.

        :returns: Configured light timeout or default int value.
        """
        return self._parse_int("cb", begin=1)

    @property
    def solar_port(self) -> PortStatus:
        """Solar Port Status.

        :returns: Status of the solar port.
        """
        return PortStatus.from_input_only(self._parse_int("cd", begin=1))

    @property
    def dc_12v_auto_on(self) -> bool:
        """Configured DC Port Auto On.

        :returns: Status of the DC auto on mode.
        """
        return (
            bool(self._parse_int("f7", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    async def turn_dc_on(self) -> None:
        """Turn the DC output on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_dc_off(self) -> None:
        """Turn the DC output off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DC_OUTPUT), payload=bytes.fromhex(PAYLOAD_OFF)
        )

    async def turn_display_on(self) -> None:
        """Turn the display on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_ON_OFF), payload=bytes.fromhex(PAYLOAD_ON)
        )

    async def turn_display_off(self) -> None:
        """Turn the display off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_DISPLAY_ON_OFF), payload=bytes.fromhex(PAYLOAD_OFF)
        )

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
            cmd=bytes.fromhex(CMD_LIGHT_MODE),
            payload=bytes.fromhex(PAYLOAD_LIGHT_MODE) + mode.value.to_bytes(),
        )

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
            cmd=bytes.fromhex(CMD_DISPLAY_TIMEOUT),
            payload=bytes.fromhex(PAYLOAD_TIMEOUT_TIME)
            + timeout.value.to_bytes(length=2, byteorder="little", signed=False),
        )

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
            cmd=bytes.fromhex(CMD_DISPLAY_MODE),
            payload=bytes.fromhex(PAYLOAD_LIGHT_MODE) + mode.value.to_bytes(),
        )
