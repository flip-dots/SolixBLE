"""C2000(X) Gen 2 power station model.

.. moduleauthor:: kb1ibt

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
from ..states import ChargingStatus, DisplayTimeout, LightStatus, PortStatus
from .c1000g2 import (
    C1000G2,
    CMD_AC_OUTPUT,
    CMD_DC_OUTPUT,
    CMD_SUBSCRIBE,
    PARAMETERS_SUBSCRIBE,
)
from .c2000g2_summary import SUMMARY_MAPS

#: System-parameters group: display switch, brightness, timeout and the SoC
#: limits are all fields of this one command, selected by payload tag.
CMD_SYSTEM = "4103"

#: Realtime telemetry latch. Once armed the device pushes telemetry on its own.
CMD_REALTIME = "4057"

#: Telemetry response drawn by the ``4100`` poll.
CMD_RESPONSE_GET_STATUS = "c900"

#: Routing byte the ``4057`` latch requires.
REALTIME_ROUTING = "21"

PARAMETERS_REALTIME_ON = {
    "a1": {
        "value": REALTIME_ROUTING,
    },
    "a2": {
        "type": 1,
        "value": 1,
    },
}

#: ``a3[0]`` value emitted while a firmware update is in progress. It is absent
#: from :class:`~SolixBLE.states.ChargingStatus`.
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

#: Highest accepted battery percentage for the charge cap / discharge floor.
MAX_PERCENTAGE = 100

#: Bounds on the AC and DC output auto-off timers.
MAX_TIMER_SECONDS = 86400
TIMER_STEP_SECONDS = 300

#: Range the AC charging-power limit accepts (W).
MIN_AC_CHARGING_POWER = 500
MAX_AC_CHARGING_POWER = 1800

#: ``subPackageConnectionStatus`` value meaning a pack is actually attached.
SUB_PACKAGE_CONNECTED = 1

#: Bytes of the ``c0`` block that follow its variable-length serial.
SUB_PACKAGE_TAIL_LENGTH = 15

#: Each setting of the system group is one payload tag: a2 the display switch,
#: a3 the brightness, a4 the timeout as a 16-bit little endian integer, aa and
#: ab the charge cap and discharge floor.
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

PARAMETERS_DISPLAY_TIMEOUT = {
    "a1": {
        "value": "21",
    },
    "a4": {
        "type": 2,
        "value": lambda seconds: seconds.to_bytes(length=2, byteorder="little"),
    },
}

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

#: The AC and DC groups take their auto-off timer at a3 as a 32-bit little
#: endian integer, and the AC group its charging power limit at a4 as a 16-bit
#: one.
PARAMETERS_TIMER = {
    "a1": {
        "value": "21",
    },
    "a3": {
        "type": 3,
        "value": lambda seconds: seconds.to_bytes(length=4, byteorder="little"),
    },
}

PARAMETERS_AC_CHARGING_POWER = {
    "a1": {
        "value": "21",
    },
    "a4": {
        "type": 2,
        "value": lambda watts: watts.to_bytes(length=2, byteorder="little"),
    },
}


def _validate_timer(seconds: int) -> None:
    """Range-check an output auto-off timer.

    :param seconds: Timer in seconds.
    :raises ValueError: If out of range or not a whole step.
    """
    if not 0 <= seconds <= MAX_TIMER_SECONDS or seconds % TIMER_STEP_SECONDS:
        msg = f"Timer must be 0-{MAX_TIMER_SECONDS} in steps of {TIMER_STEP_SECONDS}"
        raise ValueError(msg)


def _version(raw: bytes) -> str:
    """Format one of the ``f9`` version quads.

    :param raw: The four version bytes in wire order (little-endian).
    :returns: Dotted version string.
    """
    return ".".join(str(b) for b in reversed(raw))


class C2000G2(C1000G2):
    """
    C2000(X) Gen 2 Power Station.

    Use this class to connect, monitor and control a Gen 2 C2000(X) power
    station. This model is also known as the A1783.

    .. note::
       :collapsible: closed

       The C2000 G2 shares the C1000 G2's Gen 2 BLE stack (the ``c421``/``c900``
       telemetry framing and field map, the ``4100`` poll, and the ``4101``/
       ``4102`` AC and DC control), so the port and power properties come from
       :class:`~SolixBLE.devices.c1000g2.C1000G2`. It negotiates on the
       encrypted path, which its current firmware requires.

       On top of that it decodes the ``4103`` system group (display, timeouts
       and SoC limits), the ``a3``/``a6`` status and time-remaining fields, the
       ``f9`` version block, and the ``c0`` expansion-battery block for the
       BP2000.

       The device also posts a ``c490`` device summary about every nine
       minutes: a protobuf frame with its own field set (total input power, DC
       input voltage, the AC/DC energy ledgers and the per-pack BMS block),
       decoded into :attr:`summary` against the schema the frame names. It
       is gated twice, by the realtime latch this class arms on connect and by
       a schema map the device only holds after reaching the vendor cloud, and
       it cannot be requested. A unit kept off the network may never post one.
    """

    _DEFAULT_ENCRYPTED_NEGOTIATION: bool = True

    #: The Gen 2 telemetry set plus the ``c490`` device-summary post.
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("c421", "c900", "c490")

    #: ``c490`` is a protobuf blob, decoded into :attr:`summary`.
    _PROTOBUF_TELEMETRY_COMMANDS: tuple[str, ...] = ("c490",)

    _SUMMARY_MAPS = SUMMARY_MAPS

    async def _post_connect(self) -> None:
        """Subscribe to telemetry and arm the realtime latch once connected.

        The Gen 2 streams nothing until it receives the subscribe command, and
        pushes changes on its own only while the realtime latch is armed. The
        latch persists across sessions, and arming it again is harmless.
        """
        await self._send_command(cmd=CMD_SUBSCRIBE, parameters=PARAMETERS_SUBSCRIBE)
        await self._send_command(cmd=CMD_REALTIME, parameters=PARAMETERS_REALTIME_ON)

    ##############
    #   Status   #
    ##############

    @property
    def charging_status(self) -> ChargingStatus:
        """Whether the battery is charging, discharging or idle.

        .. note::
           :collapsible: closed

           This is the device's ``workStatus``, which applies a load threshold
           of roughly 11 W. :attr:`charge_discharge_status` trips on any flow at
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

    #####################
    # Firmware versions #
    #####################

    def _version_slot(self, index: int) -> str:
        """Read one of the seven 4-byte version quads out of ``f9``.

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

    #####################
    # Expansion battery #
    #####################

    @property
    def _sub_package(self) -> bytes | None:
        """Fixed-layout tail of the ``c0`` block, past the variable-length serial.

        :returns: The bytes from ``subPackageNumber`` onwards, or None if the
            tag is absent or too short to contain them.
        """
        if self._data is None or "c0" not in self._data:
            return None

        block = bytes(self._data["c0"].value or b"")
        if not block:
            return None

        fields = block[1 + block[0] :]
        return fields if len(fields) >= SUB_PACKAGE_TAIL_LENGTH else None

    @property
    def num_expansion(self) -> int:
        """Number of expansion batteries.

        .. note::
           :collapsible: closed

           The ``c0`` block is emitted whether or not a pack is connected; with
           none attached its fields are padded with sentinel values, so only the
           connection flag inside it says whether a pack is present. The C2000
           G2 has a single expansion slot.

        :returns: Number of expansion batteries or default int value.
        """
        fields = self._sub_package
        if fields is None:
            return DEFAULT_METADATA_INT

        return int(fields[12] == SUB_PACKAGE_CONNECTED)

    @property
    def serial_number_expansion(self) -> str:
        """Serial number of the expansion battery.

        :returns: Serial number, or default str value if no pack is attached.
        """
        if self._data is None or self.num_expansion < 1:
            return DEFAULT_METADATA_STRING

        block = bytes(self._data["c0"].value or b"")
        return block[1 : 1 + block[0]].decode("ascii")

    @property
    def temperature_expansion(self) -> int:
        """Temperature of the expansion battery (C).

        :returns: Temperature in degrees C, or default int value if no pack is
            attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_INT

        return int.from_bytes(fields[5:6], byteorder="little", signed=True)

    @property
    def battery_percentage_expansion(self) -> int:
        """Battery percentage of the expansion battery.

        :returns: Percentage charge, or default int value if no pack is attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_INT

        return fields[7]

    @property
    def battery_health_expansion(self) -> int:
        """Battery health of the expansion battery as a percentage.

        :returns: Percentage health, or default int value if no pack is attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_INT

        return fields[8]

    @property
    def software_version_expansion(self) -> str:
        """Software version of the expansion battery.

        :returns: Firmware version, or default str value if no pack is attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_STRING

        return _version(fields[1:5])

    ##################
    # Device summary #
    ##################

    def _summary_kwh(self, name: str) -> float | None:
        """Read an energy ledger from the summary as kWh.

        :param name: Summary field name holding watt-hours.
        :returns: Energy in kWh, or None until a summary has been received.
        """
        value = self._data_summary.get(name)
        return value / 1000.0 if isinstance(value, (int, float)) else None

    @property
    def ac_charged_energy(self) -> float | None:
        """Total energy charged through the AC input in kWh.

        Reported in the device summary, which the device posts about every
        nine minutes and only once it holds a schema map (see the class note).

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_charge_energy_wh")

    @property
    def dc_charged_energy(self) -> float | None:
        """Total energy charged through the DC input in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_charge_energy_wh")

    @property
    def ac_output_energy(self) -> float | None:
        """Total energy discharged through the AC output in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_discharge_energy_wh")

    @property
    def dc_output_energy(self) -> float | None:
        """Total energy discharged through the DC outputs in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_discharge_energy_wh")

    @property
    def dc_input_voltage(self) -> float | None:
        """Voltage at the DC (solar/car) input in volts.

        Reported in the device summary, so it is at most about nine minutes old.

        :returns: Voltage in V, or None until a summary has been received.
        """
        value = self._data_summary.get("dc_input_voltage")
        return float(value) if isinstance(value, (int, float)) else None

    ############
    # Commands #
    ############

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
        await self._send_command(
            cmd=CMD_SYSTEM,
            parameters=PARAMETERS_DISPLAY,
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
        """Set the status/mode of the LCD display.

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

    async def set_ac_charging_power(self, watts: int) -> None:
        """Set the AC charging power limit in watts.

        :param watts: AC charging power limit, 500-1800 W.
        :raises ValueError: If power value is out of valid range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if not MIN_AC_CHARGING_POWER <= watts <= MAX_AC_CHARGING_POWER:
            raise ValueError(
                f"AC charging power must be between {MIN_AC_CHARGING_POWER} "
                f"and {MAX_AC_CHARGING_POWER} W",
            )

        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_AC_CHARGING_POWER,
            watts=watts,
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
