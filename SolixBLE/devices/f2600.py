"""F2600 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
.. moduleauthor:: github.com/unex

"""

import logging
from datetime import datetime, timedelta

from SolixBLE.constructs import ParameterDict, Parameters

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_INT,
    TELEMETRY_PATTERN_A,
)
from ..states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus
from . import F2000

CMD_AC_TIMER = "4042"
CMD_DC_TIMER = "4043"
CMD_AC_CHARGING_POWER = "4044"
CMD_DISPLAY_TIMEOUT = "4046"
CMD_DISPLAY_ON_OFF = "4052"
CMD_AC_OUTPUT = "404a"
CMD_DC_OUTPUT = "404b"
CMD_DISPLAY_MODE = "404c"
CMD_POWER_SAVING_MODE = "404e"
CMD_LIGHT_MODE = "404f"
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

PARAMETERS_CHARGE_POWER = {
    "a1": {
        "value": "21",
    }, "a2": {
        "type": 2,
        "value": lambda watts: watts.to_bytes(
            length=2,
            byteorder="little",
            signed=False,
        ),
    },
}

PARAMETERS_TIMER = {
    "a1": {
        "value": "21",
    }, "a2": {
        "type": 2,
        "value": lambda seconds: seconds.to_bytes(
            length=4,
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


class F2600(F2000):
    """
    F2600 Power Station.

    Use this class to connect and monitor a F2600 power station.
    This model is also known as the A1781.
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    @property
    def charging_status(self) -> ChargingStatus:
        """Charging status of the device.

        .. note::
           :collapsible: closed

            - ``IDLE`` (0): no external source connected; this includes
              pure battery-only discharge — the device does *not* emit
              ``DISCHARGING`` in that state.
            - ``DISCHARGING`` (1): a solar source is present but insufficient
              to cover the load; battery is also contributing.
            - ``CHARGING`` (2): AC wall is connected and charging the battery.

        :returns: Status of charging.
        """
        return ChargingStatus(self._parse_int("bc", begin=1))

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
    def light(self) -> LightStatus:
        """Light Status.

        :returns: Status of the light bar.
        """
        return LightStatus(self._parse_int("cf", begin=1))

    @property
    def ac_output(self) -> PortStatus:
        """AC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of the AC port.
        """
        return PortStatus(self._parse_int("bb", begin=1))

    @property
    def dc_output(self) -> PortStatus:
        """DC Port Status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        .. note::
           :collapsible: closed

           Based on observed F2600 telemetry, key ``cb`` tracks DC output state.

        :returns: Status of the DC port.
        """
        return PortStatus(self._parse_int("cb", begin=1))

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("c6", begin=1))

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("c7", begin=1))

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("c8", begin=1))

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("c9", begin=1))

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB A2 Port Status.

        :returns: Status of the USB A2 port.
        """
        return PortStatus(self._parse_int("ca", begin=1))

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: AC socket output power in watts or default int value.
        """
        return self._parse_int("a6", begin=1)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total output power (AC + USB + DC) in watts or default int value.
        """
        return self._parse_int("b0", begin=1)

    @property
    def solar_port(self) -> PortStatus:
        """Solar/DC input port status.

        .. note::
           The port remains INPUT after the Anderson connector loses power
           until AC wall charging takes over, at which point it clears to
           NOT_CONNECTED.

        :returns: Status of the solar/DC input port.
        """
        return (
            PortStatus.INPUT
            if self._parse_int("bf", begin=1) == 1
            else PortStatus.NOT_CONNECTED
        )

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total input power in watts or default int value.
        """
        return self._parse_int("af", begin=1)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        .. note::
           :collapsible: closed

           On the F2600 key ``a5`` tracks total AC wall input and key ``af``
           tracks the combined total of all inputs.

        :returns: Total AC wall input power in watts or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def ac_charging_power(self) -> int:
        """Configured AC charging power limit in watts.

        :returns: AC charging power limit or default int value.
        """
        if self._data is None or "d1" not in self._data:
            return DEFAULT_METADATA_INT
        return self._parse_int("d1", begin=1)

    @property
    def display_timeout(self) -> int:
        """Display timeout limit in seconds.

        :returns: Display timeout in seconds or default int value.
        """
        if self._data is None or "d3" not in self._data:
            return DEFAULT_METADATA_INT
        return self._parse_int("d3", begin=1)

    @property
    def power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        return (
            bool(self._parse_int("db", begin=1))
            if self._data is not None and "db" in self._data
            else DEFAULT_METADATA_BOOL
        )

    @property
    def is_display_on(self) -> bool | None:
        """Whether the LCD display is on.

        :returns: True if on, False if off, or default bool value.
        """
        return (
            bool(self._parse_int("de", begin=1))
            if self._data is not None and "de" in self._data
            else DEFAULT_METADATA_BOOL
        )

    @property
    def display_mode(self) -> LightStatus:
        """Configured display brightness level.

        :returns: Display brightness as LightStatus (LOW/MEDIUM/HIGH) or UNKNOWN.
        """
        if self._data is None or "d9" not in self._data:
            return LightStatus.UNKNOWN
        return LightStatus(self._parse_int("d9", begin=1))

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

    async def set_ac_timer(self, seconds: int) -> None:
        """Set the AC auto-off timer.

        :param seconds: Seconds until AC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_AC_TIMER,
            parameters=PARAMETERS_TIMER,
            seconds=seconds,
        )

    async def set_dc_timer(self, seconds: int) -> None:
        """Set the DC auto-off timer.

        :param seconds: Seconds until DC output shuts off. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_DC_TIMER,
            parameters=PARAMETERS_TIMER,
            seconds=seconds,
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
            cmd=CMD_LIGHT_MODE,
            parameters=PARAMETERS_LIGHT_MODE,
            mode=mode,
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

    async def turn_power_saving_mode_on(self) -> None:
        """Turn the power saving mode on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_POWER_SAVING_MODE, parameters=PARAMETERS_ON)

    async def turn_power_saving_mode_off(self) -> None:
        """Turn the power saving mode off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(cmd=CMD_POWER_SAVING_MODE, parameters=PARAMETERS_OFF)

    async def set_ac_charging_power(self, watts: int) -> None:
        """Set the AC charging power limit in watts.

        :param watts: AC charging power limit in watts.
        :raises ValueError: If power value is out of valid range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        # Below 100 W the device charges at full power instead, and 1440 W is
        # the highest the app allows.
        if watts < 100 or watts > 1440:
            raise ValueError("AC charging power must be between 100 and 1440 W")

        await self._send_command(
            cmd=CMD_AC_CHARGING_POWER,
            parameters=PARAMETERS_CHARGE_POWER,
            watts=watts,
        )

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
        await self._process_telemetry(
            parameters,
        )  # update the internal parameters as well
        return parameters
