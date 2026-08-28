"""C300(X) power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import logging
from datetime import datetime, timedelta

from SolixBLE.constructs import ParameterDict, Parameters

from ..const import (
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
    TELEMETRY_PATTERN_A,
)
from ..device import SolixBLEDevice
from ..states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus

CMD_AC_OUTPUT = "404a"
CMD_DC_OUTPUT = "404b"
CMD_DISPLAY_ON_OFF = "4052"
CMD_LIGHT_MODE = "404f"
CMD_DISPLAY_TIMEOUT = "4046"
CMD_DISPLAY_MODE = "404c"
CMD_GET_STATUS = "4040"

CMD_RESPONSE_GET_STATUS = "c840"


PARAMETERS_ON = {
    "a1": {
        "value": "21",
    }, "a2": {
        "type": 1,
        "value": 1,
    },
}

PARAMETERS_OFF = {
    "a1": {
        "value": "21",
    }, "a2": {
        "type": 1,
        "value": 0,
    },
}

PARAMETERS_LIGHT_MODE = {
    "a1": {
        "value": "21",
    }, "a2": {
        "type": 1,
        "value": lambda mode: mode.value,
    },
}

PARAMETERS_TIMEOUT_TIME = {
    "a1": {
        "value": "21",
    }, "a2": {
        "type": 2,
        "value": lambda time: time.value.to_bytes(
            length=2,
            byteorder="little",
            signed=False,
        ),
    },
}

PARAMETERS_GET_STATUS = {
    "a1": {
        "value": "21",
    },
}


_LOGGER = logging.getLogger(__name__)


class C300(SolixBLEDevice):
    """
    C300(X) Power Station.

    Use this class to connect and monitor a C300(X) power station.
    This model is also known as the A1722.

    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    @property
    def ac_timer_remaining(self) -> int:
        """Time remaining on AC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int("a2", begin=1)

    @property
    def ac_timer(self) -> datetime | None:
        """Timestamp of AC timer.

        :returns: Timestamp of when AC timer expires or None.
        """
        if (
            self.ac_timer_remaining != DEFAULT_METADATA_INT
            and self.ac_timer_remaining != 0
        ):
            return datetime.now() + timedelta(seconds=self.ac_timer_remaining)

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int("a3", begin=1)

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
            self._parse_int("a4", begin=1) / 10.0
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
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: Total AC power out or default int value.
        """
        return self._parse_int("a6", begin=1)

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._parse_int("a7", begin=1)

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._parse_int("a8", begin=1)

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power.

        :returns: USB port C3 power or default int value.
        """
        return self._parse_int("a9", begin=1)

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._parse_int("aa", begin=1)

    @property
    def dc_power_out(self) -> int:
        """DC Power Out.

        :returns: DC power out or default int value.
        """
        return self._parse_int("ab", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int("ac", begin=1)

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total power in or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int("ae", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("b1", begin=1))])

    @property
    def ac_output(self) -> PortStatus:
        """AC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of the AC port.
        """
        return PortStatus(self._parse_int("b7", begin=1))

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("b9", begin=1, signed=True)

    @property
    def charging_status(self) -> ChargingStatus:
        """Charging status of the device.

        :returns: Status of charging.
        """
        return ChargingStatus(self._parse_int("ba", begin=1))

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("bb", begin=1)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("bd", begin=1))

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("be", begin=1))

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("bf", begin=1))

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("c0", begin=1))

    @property
    def dc_output(self) -> PortStatus:
        """DC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of the DC port.
        """
        return PortStatus(self._parse_int("c1", begin=1))

    @property
    def light(self) -> LightStatus:
        """Light Status.

        :returns: Status of the light bar.
        """
        return LightStatus(self._parse_int("cf", begin=1))

    @property
    def serial_number(self) -> str:
        """Serial number.

        :returns: The serial number of the device.
        """
        return self._parse_string("c5", begin=1)

    async def get_status_update(self) -> ParameterDict:
        """Request and retrieve a status update from the device.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: Dictionary containing telemetry parameters.
        """
        await self._send_command(cmd=CMD_GET_STATUS, parameters=PARAMETERS_GET_STATUS)
        payload = await self._listen_for_packet(
            bytes.fromhex(TELEMETRY_PATTERN_A), bytes.fromhex(CMD_RESPONSE_GET_STATUS),
        )
        if not payload:
            raise TimeoutError("Timed out waiting for payload!")

        parameters = Parameters.parse(payload)
        _LOGGER.debug(f"Parameters: {parameters}")
        return parameters

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

    async def turn_display_on(self) -> None:
        """Turn the display on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_DISPLAY_ON_OFF, parameters=PARAMETERS_ON)

    async def turn_display_off(self) -> None:
        """Turn the display off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_DISPLAY_ON_OFF, parameters=PARAMETERS_OFF)

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
            parameters=PARAMETERS_LIGHT_MODE,
            mode=mode,
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
            cmd=CMD_DISPLAY_TIMEOUT,
            parameters=PARAMETERS_TIMEOUT_TIME,
            time=timeout,
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
            cmd=CMD_DISPLAY_MODE,
            parameters=PARAMETERS_LIGHT_MODE,
            mode=mode,
        )
