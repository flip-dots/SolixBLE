"""F2000(P) / 767 PowerHouse power station model.

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
from ..states import LightStatus

CMD_DISPLAY_ON_OFF = "4052"
CMD_AC_OUTPUT = "404a"
CMD_DC_OUTPUT = "404b"
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

PARAMETERS_GET_STATUS = {
    "a1": {
        "value": "21",
    },
}

_LOGGER = logging.getLogger(__name__)


class F2000(SolixBLEDevice):
    """
    F2000(P) Power Station.

    Use this class to connect and monitor a F2000(P) power station.
    This model is also known as the A1780 or the 767 PowerHouse.

    .. note::
        This model was added using data from anker-solix-api. The commands
        below have been confirmed on real units (see issue #29), but not all
        of the telemetry has been tested.

    .. note::
        It should be possible to add more sensors. I think devices with lots of
        telemetry values split them up into multiple messages but I have not
        played around with this yet. That and I am being a bit conservative with
        these initial implementations, if you want more sensors and are willing
        to help with testing feel free to raise a GitHub issue.

    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

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
    def ac_to_battery(self) -> int:
        """AC Power that is going to the battery.

        :returns: Total AC power to battery or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def ac_power_out_sockets(self) -> int:
        """AC Power Out to sockets.

        :returns: AC power out or default int value.
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
    def usb_a2_power(self) -> int:
        """USB A2 Power.

        :returns: USB port A2 power or default int value.
        """
        return self._parse_int("ab", begin=1)

    @property
    def dc_1_power_out(self) -> int:
        """DC Power out for port 1.

        :returns: DC power out for port 1 or default int value.
        """
        return self._parse_int("ac", begin=1)

    @property
    def dc_2_power_out(self) -> int:
        """DC Power out for port 2.

        :returns: DC power out for port 2 or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int("ae", begin=1)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int("af", begin=1)

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: Total AC power out or default int value.
        """
        return self._parse_int("b0", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("b3", begin=1))])

    @property
    def software_version_expansion(self) -> str:
        """Software version of any expansion batteries.

        If there is no expansion battery then it will be "0".

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("b9", begin=1))])

    @property
    def software_version_controller(self) -> str:
        """Software version of the controller.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("ba", begin=1))])

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("bd", begin=1, signed=True)

    @property
    def temperature_expansion(self) -> int:
        """Temperature of the expansion battery if present (C).

        :returns: Temperature of expansion battery in degrees C or 0 if not present or default int value.
        """
        return self._parse_int("be", begin=1, signed=True)

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("c1", begin=1)

    @property
    def battery_percentage_expansion(self) -> int:
        """Battery Percentage of the expansion battery.

        :returns: Percentage charge of expansion battery or 0 if not present or default int value.
        """
        return self._parse_int("c2", begin=1)

    @property
    def battery_health(self) -> int:
        """Battery health as a percentage.

        :returns: Percentage of battery health or default int value.
        """
        return self._parse_int("c3", begin=1)

    @property
    def battery_health_expansion(self) -> int:
        """Battery health as a percentage for expansion battery.

        :returns: Percentage of expansion battery health or 0 if not present or default int value.
        """
        return self._parse_int("c4", begin=1)

    @property
    def num_expansion(self) -> int:
        """Number of expansion batteries.

        :returns: Number of expansion batteries or default int value.
        """
        return self._parse_int("c5", begin=1)

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("d0", begin=1)

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
