"""C1000(X) Gen 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from datetime import datetime, timedelta

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
    TELEMETRY_PATTERN_A,
)
from ..constructs import ParameterDict, Parameters
from ..device import SolixBLEDevice
from ..states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus

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

#: The AC and DC groups take their auto-off timer at a3 as a 32-bit little
#: endian integer.
PARAMETERS_TIMER = {
    "a1": {
        "value": "21",
    }, "a3": {
        "type": 3,
        "value": lambda seconds: seconds.to_bytes(
            length=4,
            byteorder="little",
        ),
    },
}

#: System-parameters group: the display switch, brightness and timeout and
#: the SoC limits are all fields of this one command, selected by payload tag.
CMD_SYSTEM = "4103"

PARAMETERS_DISPLAY = {
    "a1": {
        "value": "21",
    }, "a2": {
        "type": 1,
        "value": lambda on: 1 if on else 0,
    },
}

PARAMETERS_DISPLAY_MODE = {
    "a1": {
        "value": "21",
    }, "a3": {
        "type": 1,
        "value": lambda mode: mode,
    },
}

#: The display timeout is a 16-bit little endian integer of seconds.
PARAMETERS_DISPLAY_TIMEOUT = {
    "a1": {
        "value": "21",
    }, "a4": {
        "type": 2,
        "value": lambda seconds: seconds.to_bytes(
            length=2,
            byteorder="little",
        ),
    },
}

PARAMETERS_MAX_BATTERY = {
    "a1": {
        "value": "21",
    }, "aa": {
        "type": 1,
        "value": lambda percentage: percentage,
    },
}

PARAMETERS_MIN_BATTERY = {
    "a1": {
        "value": "21",
    }, "ab": {
        "type": 1,
        "value": lambda percentage: percentage,
    },
}

#: Telemetry response drawn by the subscribe command when it is used as a poll.
CMD_RESPONSE_GET_STATUS = "c900"

#: Value of the first status byte while a firmware update is in progress. It
#: is absent from ChargingStatus.
WORK_STATUS_UPDATING = 5

#: Display timeouts the device accepts.
DISPLAY_TIMEOUTS = (
    DisplayTimeout.S10,
    DisplayTimeout.S20,
    DisplayTimeout.S30,
    DisplayTimeout.S60,
    DisplayTimeout.S300,
    DisplayTimeout.S1800,
)

#: Highest accepted battery percentage for the charge cap and discharge floor.
MAX_PERCENTAGE = 100

#: Bounds on the AC and DC output auto-off timers.
MAX_TIMER_SECONDS = 86400
TIMER_STEP_SECONDS = 300


def _validate_timer(seconds: int) -> None:
    """Range-check an output auto-off timer.

    :param seconds: Timer in seconds.
    :raises ValueError: If out of range or not a whole step.
    """
    if not 0 <= seconds <= MAX_TIMER_SECONDS or seconds % TIMER_STEP_SECONDS:
        raise ValueError(
            f"Timer must be 0-{MAX_TIMER_SECONDS} in steps of {TIMER_STEP_SECONDS}"
        )


def _version(raw: bytes) -> str:
    """Format one of the four-byte version quads of the version block.

    :param raw: The four version bytes in wire order (little-endian).
    :returns: Dotted version string.
    """
    return ".".join(str(b) for b in reversed(raw))

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

    .. note::
       :collapsible: closed

       The status, timer, display, SoC limit and version fields, and the
       commands that set them, are shared with the C2000 G2 (A1783), which
       runs the same platform: they were confirmed on that unit and are read
       from the same telemetry tags here, but have not yet been confirmed on a
       C1000 G2.
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
    def dc_input_port(self) -> PortStatus:
        """DC input (XT-60i) port status.

        The shared DC input port, whatever is plugged into it: a solar array, the
        12V cigarette-socket car adapter, and the Anker SOLIX Alternator Charger
        all connect here. (Battery-to-battery vehicle charging and RV expansion
        use the separate expansion connector, not this port.)

        PortStatus.INPUT signifies a source is present, NOT_CONNECTED that the
        port is empty. Presence only; it does not imply current is flowing.

        :returns: Status of the DC input port.
        """
        return PortStatus.from_input_only(self._parse_int("a8", begin=1, end=2))

    @property
    def solar_port(self) -> PortStatus:
        """Alias of :attr:`dc_input_port` (the XT-60i port).

        Kept because the port takes more than a solar array -- the 12V car
        adapter and the alternator charger connect here too; :attr:`dc_input_port`
        is the accurate name.

        :returns: Status of the DC input port.
        """
        return self.dc_input_port

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

    @property
    def charging_status(self) -> ChargingStatus:
        """Whether the battery is charging, discharging or idle.

        .. note::
           :collapsible: closed

           This is the device's work status, which applies a load threshold of
           roughly 11 W. :attr:`charge_discharge_status` trips on any flow at
           all, so the two disagree at low load. A firmware update puts this
           field in a state outside the enum; see :attr:`firmware_updating`.

        :returns: Charging status, or UNKNOWN if there is no data.
        """
        if self._data is None:
            return ChargingStatus.UNKNOWN

        try:
            return ChargingStatus(self._parse_int("a3", begin=1, end=2))
        except ValueError:
            return ChargingStatus.UNKNOWN

    @property
    def charge_discharge_status(self) -> ChargingStatus:
        """Whether current is flowing into or out of the battery.

        Unlike :attr:`charging_status` this trips on any flow rather than a
        load threshold.

        :returns: Charging status, or UNKNOWN if there is no data.
        """
        if self._data is None:
            return ChargingStatus.UNKNOWN

        try:
            return ChargingStatus(self._parse_int("a5", begin=2, end=3))
        except ValueError:
            return ChargingStatus.UNKNOWN

    @property
    def firmware_updating(self) -> bool | None:
        """Whether a firmware update is in progress.

        :returns: True while updating, else False, or default bool value if
            there is no data.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return self._parse_int("a3", begin=1, end=2) == WORK_STATUS_UPDATING

    @property
    def time_remaining(self) -> float:
        """Time remaining to full or empty, in hours.

        The field counts down to empty while discharging and to full while
        charging.

        :returns: Hours remaining, or default float value if there is no data.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a6", begin=7, end=9) / 10.0

    @property
    def hours_remaining(self) -> float:
        """Time remaining to full/empty, with whole days overflowed out.

        :returns: Hours remaining, or default float value if there is no data.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return round(divmod(self.time_remaining, 24)[1], 1)

    @property
    def days_remaining(self) -> int:
        """Time remaining to full/empty, whole days only.

        :returns: Days remaining, or default int value if there is no data.
        """
        if self._data is None:
            return DEFAULT_METADATA_INT

        return int(divmod(self.time_remaining, 24)[0])

    @property
    def ac_frequency(self) -> int:
        """AC mains frequency (Hz).

        :returns: Frequency in Hz, or default int value if there is no data.
        """
        return self._parse_int("a4", begin=7, end=8)

    @property
    def ac_charging_power(self) -> int:
        """Configured AC charging power limit in watts.

        :returns: AC charging power limit or default int value.
        """
        return self._parse_int("a4", begin=5, end=7)

    @property
    def max_input_power(self) -> int:
        """Maximum charge-input power the unit can draw (W).

        :returns: Maximum input power in watts, or default int value if there
            is no data.
        """
        return self._parse_int("a3", begin=5, end=7)

    @property
    def ac_input_port(self) -> PortStatus:
        """AC input (mains) status.

        PortStatus.INPUT signifies the mains lead is present, NOT_CONNECTED that
        it is absent. Presence only; it does not imply current is flowing.

        :returns: Status of the AC input.
        """
        return PortStatus.from_input_only(self._parse_int("a7", begin=4, end=5))

    @property
    def ac_timer_remaining(self) -> int:
        """Time remaining on AC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int("a4", begin=1, end=5)

    @property
    def ac_timer(self) -> datetime | None:
        """Timestamp of AC timer.

        :returns: Timestamp of when AC timer expires or None.
        """
        if self.ac_timer_remaining not in (DEFAULT_METADATA_INT, 0):
            return datetime.now() + timedelta(seconds=self.ac_timer_remaining)
        return None

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int("a4", begin=9, end=13)

    @property
    def dc_timer(self) -> datetime | None:
        """Timestamp of DC timer.

        :returns: Timestamp of when DC timer expires or None.
        """
        if self.dc_timer_remaining not in (DEFAULT_METADATA_INT, 0):
            return datetime.now() + timedelta(seconds=self.dc_timer_remaining)
        return None

    @property
    def power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled on the AC output.

        .. note::
           Enabled, the AC output switches itself off below 14 W.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("a4", begin=8, end=9))

    @property
    def dc_power_saving_mode_enabled(self) -> bool | None:
        """Whether power saving mode is enabled on the 12 V DC output.

        .. note::
           Enabled, the DC output switches itself off below 3 W.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("a4", begin=13, end=14))

    @property
    def device_timeout(self) -> int:
        """Configured device timeout in minutes.

        :returns: Configured device timeout (0 for never) or default int value.
        """
        return self._parse_int("a4", begin=14, end=16)

    @property
    def ac_fast_charge_enabled(self) -> bool | None:
        """Whether ultrafast AC charging is enabled.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("a4", begin=21, end=22))

    @property
    def port_memory_enabled(self) -> bool | None:
        """Whether output ports return to their previous state after a restart.

        :returns: True if enabled, False if disabled, or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("a4", begin=23, end=24))

    @property
    def is_display_on(self) -> bool | None:
        """Whether the LCD display is on.

        :returns: True if on, False if off, or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("a4", begin=22, end=23))

    @property
    def display_mode(self) -> LightStatus:
        """Configured display brightness level.

        :returns: Display brightness as LightStatus (LOW/MEDIUM/HIGH) or UNKNOWN.
        """
        if self._data is None:
            return LightStatus.UNKNOWN

        try:
            return LightStatus(self._parse_int("a4", begin=18, end=19))
        except ValueError:
            return LightStatus.UNKNOWN

    @property
    def display_timeout(self) -> int:
        """Display timeout limit in seconds.

        :returns: Display timeout in seconds or default int value.
        """
        return self._parse_int("a4", begin=16, end=18)

    def _version_slot(self, index: int) -> str:
        """Read one of the seven 4-byte version quads out of the version block.

        :param index: Slot index, 0-6.
        :returns: Dotted version string, or default str value if there is no
            data or the block is short.
        """
        if self._data is None or "f9" not in self._data:
            return DEFAULT_METADATA_STRING

        block = bytes(self._data["f9"].value or b"")
        begin = index * 4
        if len(block) < begin + 4:
            return DEFAULT_METADATA_STRING

        return _version(block[begin : begin + 4])

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        return self._version_slot(0)

    @property
    def software_version_controller(self) -> str:
        """Software version of the controller.

        :returns: Firmware version or default str value.
        """
        return self._version_slot(1)

    @property
    def software_version_inverter(self) -> str:
        """Software version of the inverter.

        .. note::
           Reads zero whenever the inverter is not energised, so a zero here
           means idle rather than absent.

        :returns: Firmware version or default str value.
        """
        return self._version_slot(3)

    @property
    def software_version_bms(self) -> str:
        """Software version of the battery management system.

        :returns: Firmware version or default str value.
        """
        return self._version_slot(4)

    @property
    def software_version_module(self) -> str:
        """Software version of the wireless module.

        :returns: Firmware version or default str value.
        """
        return self._version_slot(6)

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
        await self._send_command(cmd=CMD_SYSTEM, parameters=PARAMETERS_DISPLAY, on=False)

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
        if mode is LightStatus.UNKNOWN:
            raise ValueError("You cannot set the display brightness status to unknown")
        if mode is LightStatus.SOS:
            raise ValueError("You cannot set the display brightness status to SOS")
        if mode is LightStatus.OFF:
            await self.turn_display_off()
            return

        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_DISPLAY_MODE,
            mode=mode.value,
        )

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:
        """Set the display timeout.

        :param timeout: Timeout to set display to (10s, 20s, 30s, 1m, 5m or 30m).
        :raises ValueError: If requested timeout is invalid for this device.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if timeout not in DISPLAY_TIMEOUTS:
            raise ValueError(f"Display timeout must be one of {DISPLAY_TIMEOUTS}")

        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_DISPLAY_TIMEOUT,
            seconds=timeout.value,
        )

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
        if not 0 <= percentage <= MAX_PERCENTAGE:
            raise ValueError(f"Percentage must be 0-{MAX_PERCENTAGE}")

        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_MAX_BATTERY,
            percentage=percentage,
        )

    async def set_min_battery_percentage(self, percentage: int) -> None:
        """Set the discharge floor, below which the device stops discharging.

        .. warning::
           The firmware accepts any percentage, not only the 1-20 the app
           offers.

        :param percentage: Discharge floor, 0-100.
        :raises ValueError: If the percentage is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if not 0 <= percentage <= MAX_PERCENTAGE:
            raise ValueError(f"Percentage must be 0-{MAX_PERCENTAGE}")

        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_MIN_BATTERY,
            percentage=percentage,
        )

    async def set_ac_timer(self, seconds: int) -> None:
        """Set the AC auto-off timer.

        :param seconds: Seconds until AC output shuts off, 0-86400 in steps of
            300. Pass 0 to cancel.
        :raises ValueError: If the value is out of range or not a whole step.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        _validate_timer(seconds)
        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_TIMER,
            seconds=seconds,
        )

    async def set_dc_timer(self, seconds: int) -> None:
        """Set the DC auto-off timer.

        :param seconds: Seconds until DC output shuts off, 0-86400 in steps of
            300. Pass 0 to cancel.
        :raises ValueError: If the value is out of range or not a whole step.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        _validate_timer(seconds)
        await self._send_command(
            cmd=CMD_DC_OUTPUT,
            parameters=PARAMETERS_TIMER,
            seconds=seconds,
        )

    async def get_status_update(self) -> ParameterDict:
        """Request and retrieve a status update from the device.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: Dictionary containing telemetry parameters.
        """
        await self._send_command(cmd=CMD_SUBSCRIBE, parameters=PARAMETERS_SUBSCRIBE)
        payload = await self._listen_for_packet(
            bytes.fromhex(TELEMETRY_PATTERN_A),
            bytes.fromhex(CMD_RESPONSE_GET_STATUS),
        )
        if not payload:
            raise TimeoutError("Timed out waiting for payload!")

        parameters = Parameters.parse(payload)
        await self._process_telemetry(parameters)
        return parameters
