"""Anker Prime Charging Station (240W) model.

.. moduleauthor:: kb1ibt
"""

from enum import Enum

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    BitsInteger,
    BitStruct,
    Int8ub,
    Struct,
)

from SolixBLE.const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.constructs import DISPLAY, FIRMWARE_UPDATE
from SolixBLE.device import UUID_STRING
from SolixBLE.prime_device import (
    CMD_CLOCK_FORMAT,
    CMD_DISPLAY_BRIGHTNESS,
    CMD_DISPLAY_TIMEOUT,
    CMD_REQUEST_SNAPSHOT,
    DISPLAY_TIMEOUT_CODES,
    DISPLAY_TIMEOUTS,
    KEEP_ALIVE_INTERVAL,
    PARAMETERS_KEEP_ALIVE,
    PrimeDevice,
)
from SolixBLE.protocols import Outer, PlainOuter
from SolixBLE.states import (
    ClockFormat,
    ClockTheme,
    DisplayTimeout,
    LightStatus,
    PortSchedule,
    PortStatus,
    PortTimer,
)

#: The wire index the port commands take for each switchable port. The two
#: USB A ports have no switch.
PORT_INDEX = {
    "ac_1": 0,
    "ac_2": 1,
    "usb_c1": 2,
    "usb_c2": 3,
    "usb_c3": 4,
    "usb_c4": 5,
}

CMD_DISPLAY = "4205"
CMD_CHARGING_MODE = "4206"
CMD_LIGHT_MODE = "4214"

#: The display settings byte (snapshot ``ad``): the brightness level in the
#: high nibble and the timeout code in the low nibble.
DISPLAY_SETTINGS = BitStruct(
    "brightness" / BitsInteger(4),
    "timeout" / BitsInteger(4),
)

#: Display brightness levels by the code ``ad`` reports and ``4204`` takes.
DISPLAY_MODES = {
    0: LightStatus.LOW,
    1: LightStatus.MEDIUM,
    2: LightStatus.HIGH,
}

#: The reverse of :data:`DISPLAY_MODES`, for building a ``4204`` payload.
DISPLAY_MODE_CODES = {mode: code for code, mode in DISPLAY_MODES.items()}

#: The charging mode (snapshot ``ae``, command ``4206``): the mode, then the
#: high power sub-mode from 0.
CHARGING_MODE = Struct(
    "mode" / Int8ub,
    "submode" / Int8ub,
)

PARAMETERS_CHARGING_MODE = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 2,
        "value": lambda mode, submode: CHARGING_MODE.build(
            {"mode": mode, "submode": submode},
        ),
    },
}

#: The themes the station's display offers.
BUILT_IN_THEMES = (ClockTheme.THEME_1, ClockTheme.THEME_2, ClockTheme.THEME_3)


class ChargingMode(Enum):
    """How the station shares its output between its ports."""

    #: The charging mode is unknown.
    UNKNOWN = -1

    #: The app's Smart Dynamic mode.
    SMART_DYNAMIC = 0

    #: The app's High-Power mode, with a sub-mode.
    HIGH_POWER = 1


class ChargingSubmode(Enum):
    """The sub-mode of the High-Power charging mode.

    These are the device-type allocation presets the app recommends under
    High-Power; the names are the app's (Mode 1-3).

    .. note::
       :collapsible: closed

       .. list-table::
          :header-rows: 1

          * - Sub-mode
            - USB C1
            - USB C2
            - USB C3
            - USB C4
          * - Mode 1
            - High Performance Laptop
            - Portable Office Laptop
            - Phone
            - Phone
          * - Mode 2
            - High Performance Laptop
            - Portable Office Laptop
            - Phone
            - Watches / Headphones
          * - Mode 3
            - Portable Office Laptop
            - Portable Office Laptop
            - Portable Office Laptop
            - Phone
    """

    #: The sub-mode is unknown.
    UNKNOWN = -1

    #: The app's Mode 1.
    MODE_1 = 0

    #: The app's Mode 2.
    MODE_2 = 1

    #: The app's Mode 3.
    MODE_3 = 2


class AcLightMode(Enum):
    """The mode of the indicator light on the AC outlets."""

    #: The light mode is unknown.
    UNKNOWN = -1

    #: The light is at its normal brightness.
    NORMAL = 0

    #: The light is dimmed.
    SLEEP = 1


class PrimeChargingStation240w(PrimeDevice):
    """
    Anker Prime Charging Station (240W) model.

    Use this class to connect, monitor and control the 240W charging station.
    This model is also known as the A91B2. It has two AC outlets, four USB C
    ports and two USB A ports; every port but the USB A pair can be switched,
    timed and scheduled.

    .. note::
       :collapsible: closed

       The station negotiates the way the app does: ECDH on the plain outer,
       which authorizes the link without a user registration. ECDH on the
       encrypted outer authorizes nothing and goes on to register the user,
       which this station answers by dropping the link.
    """

    #: The plain outer when no advertisement says otherwise; see the class note.
    _OUTER_HINT: type[Outer] = PlainOuter

    #: Write without response, as the app writes every packet to this station.
    _COMMAND_WRITE_RESPONSE = False

    #: The plain outer's client id, whose first 16 bytes also key the legacy
    #: confer; the station has been run with this one.
    _UUID_STRING: str = UUID_STRING

    #: The stream carries the six ports at a2-a7.
    _TELEMETRY_COMMANDS = ("4303",)

    #: The snapshot the device sends on request carries its settings.
    _SNAPSHOT_COMMANDS = ("4a00",)

    _KEEP_ALIVE_INTERVAL: int | None = KEEP_ALIVE_INTERVAL

    async def _post_authorize(self) -> None:
        """Request the snapshot once the client is authorized.

        The station takes ``420a`` as a display page switch, so unlike the
        other Prime devices it is sent no region and owner.
        """
        await self._send_command(
            cmd=CMD_REQUEST_SNAPSHOT,
            parameters=PARAMETERS_KEEP_ALIVE,
        )

    @property
    def serial_number(self) -> str:
        """Serial number of the device.

        :returns: Serial number or default str value if not yet negotiated.
        """
        announcement = self.announcement
        serial = announcement.serial if announcement is not None else None
        if not isinstance(serial, bytes):
            return DEFAULT_METADATA_STRING

        return serial.decode("ascii")

    @property
    def software_version(self) -> str:
        """Software version of the device.

        :returns: Version string or default str value if no snapshot has been
            received.
        """
        return self._snapshot_version("a2")

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return self._port_status("a2")

    @property
    def usb_c1_voltage(self) -> float:
        """USB C1 Port voltage (V).

        :returns: Voltage of the USB C1 port or default float value.
        """
        return self._port_reading("a2", "voltage", scale=1000.0)

    @property
    def usb_c1_current(self) -> float:
        """USB C1 Port current (A).

        :returns: Current of the USB C1 port or default float value.
        """
        return self._port_reading("a2", "current", scale=1000.0)

    @property
    def usb_c1_power(self) -> float:
        """USB C1 Port power (W).

        :returns: Power of the USB C1 port or default float value.
        """
        return self._port_reading("a2", "power", scale=100.0)

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return self._port_status("a3")

    @property
    def usb_c2_voltage(self) -> float:
        """USB C2 Port voltage (V).

        :returns: Voltage of the USB C2 port or default float value.
        """
        return self._port_reading("a3", "voltage", scale=1000.0)

    @property
    def usb_c2_current(self) -> float:
        """USB C2 Port current (A).

        :returns: Current of the USB C2 port or default float value.
        """
        return self._port_reading("a3", "current", scale=1000.0)

    @property
    def usb_c2_power(self) -> float:
        """USB C2 Port power (W).

        :returns: Power of the USB C2 port or default float value.
        """
        return self._port_reading("a3", "power", scale=100.0)

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return self._port_status("a4")

    @property
    def usb_c3_voltage(self) -> float:
        """USB C3 Port voltage (V).

        :returns: Voltage of the USB C3 port or default float value.
        """
        return self._port_reading("a4", "voltage", scale=1000.0)

    @property
    def usb_c3_current(self) -> float:
        """USB C3 Port current (A).

        :returns: Current of the USB C3 port or default float value.
        """
        return self._port_reading("a4", "current", scale=1000.0)

    @property
    def usb_c3_power(self) -> float:
        """USB C3 Port power (W).

        :returns: Power of the USB C3 port or default float value.
        """
        return self._port_reading("a4", "power", scale=100.0)

    @property
    def usb_port_c4(self) -> PortStatus:
        """USB C4 Port Status.

        :returns: Status of the USB C4 port.
        """
        return self._port_status("a5")

    @property
    def usb_c4_voltage(self) -> float:
        """USB C4 Port voltage (V).

        :returns: Voltage of the USB C4 port or default float value.
        """
        return self._port_reading("a5", "voltage", scale=1000.0)

    @property
    def usb_c4_current(self) -> float:
        """USB C4 Port current (A).

        :returns: Current of the USB C4 port or default float value.
        """
        return self._port_reading("a5", "current", scale=1000.0)

    @property
    def usb_c4_power(self) -> float:
        """USB C4 Port power (W).

        :returns: Power of the USB C4 port or default float value.
        """
        return self._port_reading("a5", "power", scale=100.0)

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return self._port_status("a6")

    @property
    def usb_a1_voltage(self) -> float:
        """USB A1 Port voltage (V).

        :returns: Voltage of the USB A1 port or default float value.
        """
        return self._port_reading("a6", "voltage", scale=1000.0)

    @property
    def usb_a1_current(self) -> float:
        """USB A1 Port current (A).

        :returns: Current of the USB A1 port or default float value.
        """
        return self._port_reading("a6", "current", scale=1000.0)

    @property
    def usb_a1_power(self) -> float:
        """USB A1 Port power (W).

        :returns: Power of the USB A1 port or default float value.
        """
        return self._port_reading("a6", "power", scale=100.0)

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB A2 Port Status.

        :returns: Status of the USB A2 port.
        """
        return self._port_status("a7")

    @property
    def usb_a2_voltage(self) -> float:
        """USB A2 Port voltage (V).

        :returns: Voltage of the USB A2 port or default float value.
        """
        return self._port_reading("a7", "voltage", scale=1000.0)

    @property
    def usb_a2_current(self) -> float:
        """USB A2 Port current (A).

        :returns: Current of the USB A2 port or default float value.
        """
        return self._port_reading("a7", "current", scale=1000.0)

    @property
    def usb_a2_power(self) -> float:
        """USB A2 Port power (W).

        :returns: Power of the USB A2 port or default float value.
        """
        return self._port_reading("a7", "power", scale=100.0)

    @property
    def ac_output_1(self) -> PortStatus:
        """AC outlet 1 status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of AC outlet 1 or unknown if no snapshot has been
            received.
        """
        record = self._port_record("aa")
        if record is None:
            return PortStatus.UNKNOWN

        return PortStatus(int(record.switch))

    @property
    def ac_output_2(self) -> PortStatus:
        """AC outlet 2 status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of AC outlet 2 or unknown if no snapshot has been
            received.
        """
        record = self._port_record("ab")
        if record is None:
            return PortStatus.UNKNOWN

        return PortStatus(int(record.switch))

    @property
    def ac_output_1_schedule(self) -> PortSchedule | None:
        """AC outlet 1 daily on/off schedule.

        :returns: Schedule of AC outlet 1 or None if no snapshot has been
            received.
        """
        return self._port_schedule("aa")

    @property
    def ac_output_1_timer(self) -> PortTimer | None:
        """AC outlet 1 auto-off timer.

        :returns: Timer of AC outlet 1 or None if no snapshot has been
            received.
        """
        return self._port_timer("aa")

    @property
    def ac_output_2_schedule(self) -> PortSchedule | None:
        """AC outlet 2 daily on/off schedule.

        :returns: Schedule of AC outlet 2 or None if no snapshot has been
            received.
        """
        return self._port_schedule("ab")

    @property
    def ac_output_2_timer(self) -> PortTimer | None:
        """AC outlet 2 auto-off timer.

        :returns: Timer of AC outlet 2 or None if no snapshot has been
            received.
        """
        return self._port_timer("ab")

    @property
    def usb_c1_schedule(self) -> PortSchedule | None:
        """USB C1 Port daily on/off schedule.

        :returns: Schedule of the USB C1 port or None if no snapshot has been
            received.
        """
        return self._port_schedule("b0")

    @property
    def usb_c1_timer(self) -> PortTimer | None:
        """USB C1 Port auto-off timer.

        :returns: Timer of the USB C1 port or None if no snapshot has been
            received.
        """
        return self._port_timer("b0")

    @property
    def usb_c2_schedule(self) -> PortSchedule | None:
        """USB C2 Port daily on/off schedule.

        :returns: Schedule of the USB C2 port or None if no snapshot has been
            received.
        """
        return self._port_schedule("b1")

    @property
    def usb_c2_timer(self) -> PortTimer | None:
        """USB C2 Port auto-off timer.

        :returns: Timer of the USB C2 port or None if no snapshot has been
            received.
        """
        return self._port_timer("b1")

    @property
    def usb_c3_schedule(self) -> PortSchedule | None:
        """USB C3 Port daily on/off schedule.

        :returns: Schedule of the USB C3 port or None if no snapshot has been
            received.
        """
        return self._port_schedule("b2")

    @property
    def usb_c3_timer(self) -> PortTimer | None:
        """USB C3 Port auto-off timer.

        :returns: Timer of the USB C3 port or None if no snapshot has been
            received.
        """
        return self._port_timer("b2")

    @property
    def usb_c4_schedule(self) -> PortSchedule | None:
        """USB C4 Port daily on/off schedule.

        :returns: Schedule of the USB C4 port or None if no snapshot has been
            received.
        """
        return self._port_schedule("b3")

    @property
    def usb_c4_timer(self) -> PortTimer | None:
        """USB C4 Port auto-off timer.

        :returns: Timer of the USB C4 port or None if no snapshot has been
            received.
        """
        return self._port_timer("b3")

    @property
    def clock_display_enabled(self) -> bool | None:
        """Whether the screen shows the clock after the screen timeout.

        .. note::
           This is the app's Clock Display switch.

        :returns: True if on, False if off, or default bool value before any
            snapshot.
        """
        display = self._snapshot_struct("ac", DISPLAY)
        if display is None:
            return DEFAULT_METADATA_BOOL

        return bool(display.on)

    @property
    def display_theme(self) -> ClockTheme:
        """Theme of the clock display.

        :returns: Theme or unknown if no snapshot has been received.
        """
        display = self._snapshot_struct("ac", DISPLAY)
        if display is None:
            return ClockTheme.UNKNOWN

        try:
            return ClockTheme(display.theme)
        except ValueError:
            return ClockTheme.UNKNOWN

    @property
    def display_mode(self) -> LightStatus:
        """Brightness of the display.

        :returns: Low, medium or high, or unknown if no snapshot has been
            received.
        """
        settings = self._snapshot_struct("ad", DISPLAY_SETTINGS)
        if settings is None:
            return LightStatus.UNKNOWN

        return DISPLAY_MODES.get(settings.brightness, LightStatus.UNKNOWN)

    @property
    def display_timeout(self) -> int:
        """Display timeout in seconds, where 0 is always on.

        :returns: Timeout in seconds or default int value before any snapshot.
        """
        settings = self._snapshot_struct("ad", DISPLAY_SETTINGS)
        if settings is None:
            return DEFAULT_METADATA_INT

        return DISPLAY_TIMEOUTS.get(settings.timeout, DisplayTimeout.UNKNOWN).value

    @property
    def charging_mode(self) -> ChargingMode:
        """How the station shares its output between its ports.

        :returns: Charging mode or unknown if no snapshot has been received.
        """
        charging_mode = self._snapshot_struct("ae", CHARGING_MODE)
        if charging_mode is None:
            return ChargingMode.UNKNOWN

        try:
            return ChargingMode(charging_mode.mode)
        except ValueError:
            return ChargingMode.UNKNOWN

    @property
    def charging_submode(self) -> ChargingSubmode | None:
        """Sub-mode of the High-Power charging mode.

        :returns: Sub-mode, or None unless the charging mode is High-Power.
        """
        charging_mode = self._snapshot_struct("ae", CHARGING_MODE)
        if charging_mode is None or charging_mode.mode != ChargingMode.HIGH_POWER.value:
            return None

        try:
            return ChargingSubmode(charging_mode.submode)
        except ValueError:
            return ChargingSubmode.UNKNOWN

    @property
    def firmware_updating(self) -> bool | None:
        """Whether a firmware update is under way.

        .. note::
           The port readings stop updating while it is.

        :returns: True if updating, False if not, or default bool value
            before any snapshot.
        """
        update = self._snapshot_struct("af", FIRMWARE_UPDATE)
        if update is None:
            return DEFAULT_METADATA_BOOL

        return bool(update.updating)

    @property
    def firmware_update_progress(self) -> int:
        """Progress of the firmware update in percent.

        :returns: Progress or default int value if no snapshot has been
            received.
        """
        update = self._snapshot_struct("af", FIRMWARE_UPDATE)
        if update is None:
            return DEFAULT_METADATA_INT

        return int(update.progress)

    @property
    def clock_format(self) -> ClockFormat:
        """Format of the clock on the display.

        :returns: Clock format or unknown if no snapshot has been received.
        """
        try:
            return ClockFormat(self._snapshot_int("b4"))
        except ValueError:
            return ClockFormat.UNKNOWN

    @property
    def light_mode(self) -> AcLightMode:
        """Mode of the indicator light on the AC outlets.

        .. note::
           This is the app's Base LED Indicator.

        :returns: Light mode or unknown if no snapshot has been received.
        """
        try:
            return AcLightMode(self._snapshot_int("b5"))
        except ValueError:
            return AcLightMode.UNKNOWN

    @property
    def over_temperature(self) -> bool | None:
        """Whether the station is holding its outputs back for heat.

        .. note::
           :collapsible: closed

           Set when the temperature sensor's average reaches 117 °C, and
           cleared once it is back at 75 °C.

        :returns: True if over temperature, False if not, or default bool
            value before any snapshot.
        """
        return self._port_fault("over_temperature")

    @property
    def usb_c1_fault(self) -> bool | None:
        """Whether USB C1 reports a port fault.

        .. note::
           :collapsible: closed

           The station sets a port's fault after two faulty readings in a row
           and clears it after five clean ones.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c1")

    @property
    def usb_c2_fault(self) -> bool | None:
        """Whether USB C2 reports a port fault.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c2")

    @property
    def usb_c3_fault(self) -> bool | None:
        """Whether USB C3 reports a port fault.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c3")

    @property
    def usb_c4_fault(self) -> bool | None:
        """Whether USB C4 reports a port fault.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c4")

    @property
    def usb_a_fault(self) -> bool | None:
        """Whether the USB A ports report a fault.

        .. note::
           :collapsible: closed

           Set when a USB A supply stays below 4.0 V.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_a_undervoltage")

    async def turn_ac_1_on(self) -> None:
        """Turn AC outlet 1 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["ac_1"], on=True)

    async def turn_ac_1_off(self) -> None:
        """Turn AC outlet 1 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["ac_1"], on=False)

    async def set_timer_ac_1(self, time: int) -> None:
        """Set auto off timer for AC outlet 1.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["ac_1"], time)

    async def set_schedule_ac_1(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for AC outlet 1.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["ac_1"], schedule)

    async def turn_ac_2_on(self) -> None:
        """Turn AC outlet 2 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["ac_2"], on=True)

    async def turn_ac_2_off(self) -> None:
        """Turn AC outlet 2 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["ac_2"], on=False)

    async def set_timer_ac_2(self, time: int) -> None:
        """Set auto off timer for AC outlet 2.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["ac_2"], time)

    async def set_schedule_ac_2(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for AC outlet 2.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["ac_2"], schedule)

    async def turn_usb_c1_on(self) -> None:
        """Turn USB port C1 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c1"], on=True)

    async def turn_usb_c1_off(self) -> None:
        """Turn USB port C1 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c1"], on=False)

    async def set_timer_usb_c1(self, time: int) -> None:
        """Set auto off timer for USB C1.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c1"], time)

    async def set_schedule_usb_c1(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C1.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c1"], schedule)

    async def turn_usb_c2_on(self) -> None:
        """Turn USB port C2 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c2"], on=True)

    async def turn_usb_c2_off(self) -> None:
        """Turn USB port C2 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c2"], on=False)

    async def set_timer_usb_c2(self, time: int) -> None:
        """Set auto off timer for USB C2.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c2"], time)

    async def set_schedule_usb_c2(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C2.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c2"], schedule)

    async def turn_usb_c3_on(self) -> None:
        """Turn USB port C3 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c3"], on=True)

    async def turn_usb_c3_off(self) -> None:
        """Turn USB port C3 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c3"], on=False)

    async def set_timer_usb_c3(self, time: int) -> None:
        """Set auto off timer for USB C3.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c3"], time)

    async def set_schedule_usb_c3(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C3.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c3"], schedule)

    async def turn_usb_c4_on(self) -> None:
        """Turn USB port C4 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c4"], on=True)

    async def turn_usb_c4_off(self) -> None:
        """Turn USB port C4 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c4"], on=False)

    async def set_timer_usb_c4(self, time: int) -> None:
        """Set auto off timer for USB C4.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c4"], time)

    async def set_schedule_usb_c4(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C4.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c4"], schedule)

    async def _send_display(self, *, clock_display: bool, theme: int) -> None:
        """Send the display byte: the clock display switch and the theme index.

        :param clock_display: True to show the clock after the screen timeout.
        :param theme: The theme's wire index.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_setting(
            CMD_DISPLAY,
            DISPLAY.build({"on": clock_display, "theme": theme}),
        )

    def _current_theme(self) -> int:
        """Return the theme index the snapshot reports, else Theme 1's."""
        display = self._snapshot_struct("ac", DISPLAY)
        return ClockTheme.THEME_1.value if display is None else int(display.theme)

    async def turn_clock_display_on(self) -> None:
        """Show the clock after the screen timeout, keeping the theme.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_display(clock_display=True, theme=self._current_theme())

    async def turn_clock_display_off(self) -> None:
        """Stop showing the clock after the screen timeout, keeping the theme.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_display(clock_display=False, theme=self._current_theme())

    async def set_display_theme(self, theme: ClockTheme) -> None:
        """Set the theme of the clock display and turn the clock display on.

        :param theme: Theme 1, 2 or 3, the station's only themes.
        :raises ValueError: If the theme isn't one of the three.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if theme not in BUILT_IN_THEMES:
            msg = f"Cannot set the {theme.name} clock theme"
            raise ValueError(msg)
        await self._send_display(clock_display=True, theme=theme.value)

    async def set_display_mode(self, mode: LightStatus) -> None:
        """Set the brightness of the display.

        :param mode: Low, medium or high.
        :raises ValueError: If the brightness is not supported by the device.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode not in DISPLAY_MODE_CODES:
            msg = f"Display mode {mode} is not supported by this device"
            raise ValueError(msg)
        await self._send_setting(CMD_DISPLAY_BRIGHTNESS, DISPLAY_MODE_CODES[mode])

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:  # noqa: ASYNC109  # shared device API
        """Set the display timeout.

        :param timeout: One of S0 (always on), S30, S60, S300 and S1800.
        :raises ValueError: If the timeout is not supported by the device.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if timeout not in DISPLAY_TIMEOUT_CODES:
            msg = f"Display timeout {timeout} is not supported by this device"
            raise ValueError(msg)
        await self._send_setting(CMD_DISPLAY_TIMEOUT, DISPLAY_TIMEOUT_CODES[timeout])

    async def set_charging_mode(
        self,
        mode: ChargingMode,
        submode: ChargingSubmode = ChargingSubmode.MODE_1,
    ) -> None:
        """Set how the station shares its output between its ports.

        :param mode: The charging mode.
        :param submode: The High-Power sub-mode; see :class:`ChargingSubmode`.
        :raises ValueError: If the mode or the sub-mode is unknown.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is ChargingMode.UNKNOWN or submode is ChargingSubmode.UNKNOWN:
            msg = f"Cannot set charging mode {mode} with sub-mode {submode}"
            raise ValueError(msg)
        await self._send_command(
            cmd=CMD_CHARGING_MODE,
            parameters=PARAMETERS_CHARGING_MODE,
            mode=mode.value,
            submode=submode.value,
        )

    async def set_clock_format(self, clock_format: ClockFormat) -> None:
        """Set the format of the clock on the display.

        :param clock_format: The clock format.
        :raises ValueError: If the format is unknown.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if clock_format is ClockFormat.UNKNOWN:
            msg = "Cannot set an unknown clock format"
            raise ValueError(msg)
        await self._send_setting(CMD_CLOCK_FORMAT, clock_format.value)

    async def set_light_mode(self, mode: AcLightMode) -> None:
        """Set the mode of the indicator light on the AC outlets.

        :param mode: The light mode.
        :raises ValueError: If the mode is unknown.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is AcLightMode.UNKNOWN:
            msg = "Cannot set an unknown AC light mode"
            raise ValueError(msg)
        await self._send_setting(CMD_LIGHT_MODE, mode.value)
