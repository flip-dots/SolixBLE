"""Anker Prime Charging Station (240W) model.

.. moduleauthor:: kb1ibt
"""

import asyncio

from ..const import (
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
    FALLBACK_TZ,
    NEGOTIATION_PATTERN,
)
from ..constructs import Parameters
from ..device import SolixBLEDevice
from ..states import (
    AcLightMode,
    ChargingMode,
    ClockFormat,
    DisplayTimeout,
    PortSchedule,
    PortStatus,
    PortTimer,
)
from ..utilities import get_posix_tz

#: Command that requests the 4a00 snapshot and command that starts the 4303
#: telemetry stream. The stream stops about ten seconds after each request,
#: so every keep-alive sends both again, with a pause between them so the two
#: replies do not collide.
CMD_REQUEST_SNAPSHOT = "4200"
CMD_SUB_AND_KEEP_ALIVE = "420b"
KEEP_ALIVE_INTERVAL = 9
SNAPSHOT_TO_STREAM_DELAY = 0.4

#: Confer commands the station expects once per connection before it answers
#: any session command: the client's timezone and the station's own serial
#: number as reported in negotiation stage 3.
CMD_CONFER_TIMEZONE = "4022"
CMD_CONFER_SERIAL = "4023"

#: Port commands. The device numbers its switchable ports 0 and 1 for the AC
#: outlets and 2 to 5 for USB C1 to C4; the two USB A ports only report.
CMD_PORT_OUTPUT = "4207"
CMD_PORT_SCHEDULE = "4208"
CMD_PORT_TIMER = "4209"

#: Display and charging mode commands, each writing one field of the snapshot.
CMD_DISPLAY_TIMEOUT = "4203"
CMD_DISPLAY_BRIGHTNESS = "4204"
CMD_DISPLAY = "4205"
CMD_CHARGING_MODE = "4206"
CMD_CLOCK_FORMAT = "4210"
CMD_AC_LIGHT_MODE = "4214"

PARAMETERS_REQUEST = {
    "a1": {
        "value": "21",
    },
}

PARAMETERS_ON_OFF = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda port: port,
    },
    "a3": {
        "type": 1,
        "value": lambda on: 1 if on else 0,
    },
}

#: The timer value is an enable byte followed by the seconds as a 32-bit
#: little endian integer. A duration of 0 disarms the timer.
PARAMETERS_TIMER = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda port: port,
    },
    "a3": {
        "type": 4,
        "value": lambda seconds: (
            bytes([1 if seconds else 0])
            + seconds.to_bytes(length=4, byteorder="little", signed=False)
        ),
    },
}

#: One command sets one trigger of a port's daily schedule: a3 selects the
#: trigger (1 = on-time, 0 = off-time) and a4 carries its enable byte, hour,
#: minute and weekday bitmask (bit 0 = Monday ... bit 6 = Sunday).
PARAMETERS_SCHEDULE = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda port: port,
    },
    "a3": {
        "type": 1,
        "value": lambda trigger: trigger,
    },
    "a4": {
        "type": 3,
        "value": lambda switch, hour, minute, weekdays: bytes(
            [switch, hour, minute, weekdays],
        ),
    },
}

#: The display byte packs the on/off state in bit 7 and the theme index in
#: the low nibble.
PARAMETERS_DISPLAY = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda display: display,
    },
}

PARAMETERS_DISPLAY_TIMEOUT = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda timeout: timeout,
    },
}

PARAMETERS_DISPLAY_BRIGHTNESS = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda brightness: brightness,
    },
}

PARAMETERS_CHARGING_MODE = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 3,
        "value": lambda mode, submode: bytes([mode, submode]),
    },
}

PARAMETERS_CLOCK_FORMAT = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda clock_format: clock_format,
    },
}

PARAMETERS_AC_LIGHT_MODE = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda light_mode: light_mode,
    },
}

#: Display timeouts the station supports, keyed by the code the snapshot
#: reports in the low nibble of ad.
DISPLAY_TIMEOUTS = {
    0: DisplayTimeout.S0,
    1: DisplayTimeout.S30,
    2: DisplayTimeout.S60,
    3: DisplayTimeout.S300,
    4: DisplayTimeout.S1800,
}

#: The 4203 command numbers the same timeouts differently: 30 seconds to 30
#: minutes are 0 to 3 and always on is 4.
DISPLAY_TIMEOUT_COMMAND_CODES = {
    DisplayTimeout.S30: 0,
    DisplayTimeout.S60: 1,
    DisplayTimeout.S300: 2,
    DisplayTimeout.S1800: 3,
    DisplayTimeout.S0: 4,
}

#: Bit 7 of the display byte is the on/off state.
DISPLAY_ON = 0x80


class PrimeChargingStation240w(SolixBLEDevice):
    """
    Anker Prime Charging Station (240W) model.

    Use this class to connect, monitor and control the 240W charging station.
    This model is also known as the A91B2. It has two AC outlets, four USB C
    ports and two USB A ports; every port but the USB A pair can be switched,
    timed and scheduled.

    .. note::
       :collapsible: closed

       The station advertises without the capability bit for the encrypted
       negotiation, so it negotiates in plain text and encrypts the session
       with AES-CBC like the Solix power stations. Once negotiated it expects
       a timezone confer (``4022``) and a bind to its own serial number
       (``4023``) before it answers the snapshot request (``4200``) or
       streams telemetry (``420b``). The ``4a00`` snapshot carries the six
       ports at ``a4``-``a9``, the AC outlet states with the per-port
       schedule and timer records, the display settings and the software
       version; the ``4303`` stream carries only the six ports, at
       ``a2``-``a7``, and stops about ten seconds after each request, so the
       keep-alive requests both again.
    """

    #: The stream carries the six ports at a2-a7 and nothing else.
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("4303",)

    #: The snapshot carries the AC outlet states and the per-port schedule
    #: and timer records at aa, ab (AC outlets) and b0-b3 (USB C1-C4), the
    #: display settings at ac, ad, ae, b4, b5 and the software version at a2.
    _SNAPSHOT_COMMANDS: tuple[str, ...] = ("4a00",)

    #: Serial number the device reports in negotiation stage 3.
    _serial_number: bytes | None = None

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """Keep the serial number the device reports in negotiation stage 3.

        :param cmd: The command code of the response.
        :param payload: The response payload.
        """
        if cmd.hex() == "0829":
            parameters = Parameters.parse(self._decrypt_payload(payload))
            if "a4" in parameters:
                self._serial_number = parameters["a4"].value_legacy
        await super()._process_negotiation(cmd, payload)

    async def _post_connect(self) -> None:
        """Confer the timezone and serial number, then request the snapshot and stream.

        The station answers no session command until it has been sent the
        client's timezone and its own serial number, so both go out on every
        (re)connection before the first snapshot and stream requests.
        """
        await self._send_packet(
            pattern=NEGOTIATION_PATTERN,
            cmd=CMD_CONFER_TIMEZONE,
            parameters={
                "a1": {"value": lambda self: self._timestamp()},
                "a3": {"value": lambda self: self._timezone_offset()},
                "a5": {"value": (get_posix_tz() or FALLBACK_TZ).encode()},
            },
        )
        await asyncio.sleep(SNAPSHOT_TO_STREAM_DELAY)
        await self._send_packet(
            pattern=NEGOTIATION_PATTERN,
            cmd=CMD_CONFER_SERIAL,
            parameters={
                "a1": {"value": lambda self: self._timestamp()},
                "a3": {"value": self._serial_number or b""},
            },
        )
        await asyncio.sleep(SNAPSHOT_TO_STREAM_DELAY)
        await self._request_stream()

    async def _request_stream(self) -> None:
        """Request a fresh snapshot, then start the telemetry stream."""
        await self._send_command(
            cmd=CMD_REQUEST_SNAPSHOT,
            parameters=PARAMETERS_REQUEST,
        )
        await asyncio.sleep(SNAPSHOT_TO_STREAM_DELAY)
        await self._send_command(
            cmd=CMD_SUB_AND_KEEP_ALIVE,
            parameters=PARAMETERS_REQUEST,
        )

    async def _keep_alive(self) -> int | None:
        await self._request_stream()
        return KEEP_ALIVE_INTERVAL

    def _port_status(self, key: str) -> PortStatus:
        """Read a port's status from the stream.

        :param key: Key of the port's parameter (e.g a2, a3, a4, ...).
        :returns: Status of the port.
        """
        return PortStatus(self._parse_int(key, begin=1, end=2))

    def _port_reading(self, key: str, begin: int, end: int, scale: float) -> float:
        """Read one of a port's scaled readings from the stream.

        :param key: Key of the port's parameter (e.g a2, a3, a4, ...).
        :param begin: Slice bytes from this index.
        :param end: Slice bytes to this index.
        :param scale: Divisor applied to the integer.
        :returns: The reading or default float value if no data.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int(key, begin=begin, end=end) / scale

    def _record_int(self, key: str, begin: int, end: int) -> int:
        """Read an integer from a snapshot record.

        :param key: Key of the record (e.g aa, ab, ac, ...).
        :param begin: Slice bytes from this index.
        :param end: Slice bytes to this index.
        :returns: The integer or default int value if the record is absent.
        """
        record = self._record(key)
        if len(record) < end:
            return DEFAULT_METADATA_INT

        return int.from_bytes(record[begin:end], byteorder="little")

    def _port_schedule(self, key: str) -> PortSchedule | None:
        """Decode a port's daily on/off schedule from its snapshot record.

        :param key: Key of the port's record (e.g aa, ab, b0, ...).
        :returns: Schedule of the port or None if no snapshot has been received.
        """
        return PortSchedule.from_record(self._record(key))

    def _port_timer(self, key: str) -> PortTimer | None:
        """Decode a port's auto-off timer from its snapshot record.

        :param key: Key of the port's record (e.g aa, ab, b0, ...).
        :returns: Timer of the port or None if no snapshot has been received.
        """
        return PortTimer.from_record(self._record(key))

    @property
    def serial_number(self) -> str:
        """Serial number of the device.

        :returns: Serial number or default str value if not yet negotiated.
        """
        if self._serial_number is None:
            return DEFAULT_METADATA_STRING

        return self._serial_number.decode("ascii")

    @property
    def software_version(self) -> str:
        """Software version of the device.

        The snapshot reports it as a 16-bit integer whose decimal digits are
        the four parts of the version (1124 is version 1.1.2.4).

        :returns: Version string or default str value if no snapshot has been received.
        """
        version = self._record_int("a2", begin=1, end=3)
        if version == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_STRING

        major, minor, patch, build = (
            version // 1000,
            version // 100 % 10,
            version // 10 % 10,
            version % 10,
        )
        return f"{major}.{minor}.{patch}.{build}"

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
        return self._port_reading("a2", begin=2, end=4, scale=1000.0)

    @property
    def usb_c1_current(self) -> float:
        """USB C1 Port current (A).

        :returns: Current of the USB C1 port or default float value.
        """
        return self._port_reading("a2", begin=4, end=6, scale=1000.0)

    @property
    def usb_c1_power(self) -> float:
        """USB C1 Port power (W).

        :returns: Power of the USB C1 port or default float value.
        """
        return self._port_reading("a2", begin=6, end=8, scale=100.0)

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
        return self._port_reading("a3", begin=2, end=4, scale=1000.0)

    @property
    def usb_c2_current(self) -> float:
        """USB C2 Port current (A).

        :returns: Current of the USB C2 port or default float value.
        """
        return self._port_reading("a3", begin=4, end=6, scale=1000.0)

    @property
    def usb_c2_power(self) -> float:
        """USB C2 Port power (W).

        :returns: Power of the USB C2 port or default float value.
        """
        return self._port_reading("a3", begin=6, end=8, scale=100.0)

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
        return self._port_reading("a4", begin=2, end=4, scale=1000.0)

    @property
    def usb_c3_current(self) -> float:
        """USB C3 Port current (A).

        :returns: Current of the USB C3 port or default float value.
        """
        return self._port_reading("a4", begin=4, end=6, scale=1000.0)

    @property
    def usb_c3_power(self) -> float:
        """USB C3 Port power (W).

        :returns: Power of the USB C3 port or default float value.
        """
        return self._port_reading("a4", begin=6, end=8, scale=100.0)

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
        return self._port_reading("a5", begin=2, end=4, scale=1000.0)

    @property
    def usb_c4_current(self) -> float:
        """USB C4 Port current (A).

        :returns: Current of the USB C4 port or default float value.
        """
        return self._port_reading("a5", begin=4, end=6, scale=1000.0)

    @property
    def usb_c4_power(self) -> float:
        """USB C4 Port power (W).

        :returns: Power of the USB C4 port or default float value.
        """
        return self._port_reading("a5", begin=6, end=8, scale=100.0)

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
        return self._port_reading("a6", begin=2, end=4, scale=1000.0)

    @property
    def usb_a1_current(self) -> float:
        """USB A1 Port current (A).

        :returns: Current of the USB A1 port or default float value.
        """
        return self._port_reading("a6", begin=4, end=6, scale=1000.0)

    @property
    def usb_a1_power(self) -> float:
        """USB A1 Port power (W).

        :returns: Power of the USB A1 port or default float value.
        """
        return self._port_reading("a6", begin=6, end=8, scale=100.0)

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
        return self._port_reading("a7", begin=2, end=4, scale=1000.0)

    @property
    def usb_a2_current(self) -> float:
        """USB A2 Port current (A).

        :returns: Current of the USB A2 port or default float value.
        """
        return self._port_reading("a7", begin=4, end=6, scale=1000.0)

    @property
    def usb_a2_power(self) -> float:
        """USB A2 Port power (W).

        :returns: Power of the USB A2 port or default float value.
        """
        return self._port_reading("a7", begin=6, end=8, scale=100.0)

    @property
    def ac_output_1(self) -> PortStatus:
        """AC outlet 1 status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of AC outlet 1 or unknown if no snapshot has been received.
        """
        return PortStatus(self._record_int("aa", begin=1, end=2))

    @property
    def ac_output_2(self) -> PortStatus:
        """AC outlet 2 status.

        PortStatus.NOT_CONNECTED signifies off.
        PortStatus.OUTPUT signifies on.

        :returns: Status of AC outlet 2 or unknown if no snapshot has been received.
        """
        return PortStatus(self._record_int("ab", begin=1, end=2))

    @property
    def ac_output_1_schedule(self) -> PortSchedule | None:
        """AC outlet 1 daily on/off schedule.

        :returns: Schedule of AC outlet 1 or None if no snapshot has been received.
        """
        return self._port_schedule("aa")

    @property
    def ac_output_1_timer(self) -> PortTimer | None:
        """AC outlet 1 auto-off timer.

        :returns: Timer of AC outlet 1 or None if no snapshot has been received.
        """
        return self._port_timer("aa")

    @property
    def ac_output_2_schedule(self) -> PortSchedule | None:
        """AC outlet 2 daily on/off schedule.

        :returns: Schedule of AC outlet 2 or None if no snapshot has been received.
        """
        return self._port_schedule("ab")

    @property
    def ac_output_2_timer(self) -> PortTimer | None:
        """AC outlet 2 auto-off timer.

        :returns: Timer of AC outlet 2 or None if no snapshot has been received.
        """
        return self._port_timer("ab")

    @property
    def usb_c1_schedule(self) -> PortSchedule | None:
        """USB C1 Port daily on/off schedule.

        :returns: Schedule of the USB C1 port or None if no snapshot has been received.
        """
        return self._port_schedule("b0")

    @property
    def usb_c1_timer(self) -> PortTimer | None:
        """USB C1 Port auto-off timer.

        :returns: Timer of the USB C1 port or None if no snapshot has been received.
        """
        return self._port_timer("b0")

    @property
    def usb_c2_schedule(self) -> PortSchedule | None:
        """USB C2 Port daily on/off schedule.

        :returns: Schedule of the USB C2 port or None if no snapshot has been received.
        """
        return self._port_schedule("b1")

    @property
    def usb_c2_timer(self) -> PortTimer | None:
        """USB C2 Port auto-off timer.

        :returns: Timer of the USB C2 port or None if no snapshot has been received.
        """
        return self._port_timer("b1")

    @property
    def usb_c3_schedule(self) -> PortSchedule | None:
        """USB C3 Port daily on/off schedule.

        :returns: Schedule of the USB C3 port or None if no snapshot has been received.
        """
        return self._port_schedule("b2")

    @property
    def usb_c3_timer(self) -> PortTimer | None:
        """USB C3 Port auto-off timer.

        :returns: Timer of the USB C3 port or None if no snapshot has been received.
        """
        return self._port_timer("b2")

    @property
    def usb_c4_schedule(self) -> PortSchedule | None:
        """USB C4 Port daily on/off schedule.

        :returns: Schedule of the USB C4 port or None if no snapshot has been received.
        """
        return self._port_schedule("b3")

    @property
    def usb_c4_timer(self) -> PortTimer | None:
        """USB C4 Port auto-off timer.

        :returns: Timer of the USB C4 port or None if no snapshot has been received.
        """
        return self._port_timer("b3")

    @property
    def is_display_on(self) -> bool:
        """Whether the clock display is on.

        :returns: True if the display is on, else False, also before any snapshot.
        """
        display = self._record_int("ac", begin=1, end=2)
        return display != DEFAULT_METADATA_INT and bool(display & DISPLAY_ON)

    @property
    def display_theme(self) -> int:
        """Theme of the clock display, numbered 1 to 3 as in the app.

        :returns: Theme number or default int value if no snapshot has been received.
        """
        display = self._record_int("ac", begin=1, end=2)
        if display == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_INT

        return (display & 0x0F) + 1

    @property
    def display_brightness(self) -> int:
        """Brightness level of the display.

        :returns: Brightness level or default int value before any snapshot.
        """
        setting = self._record_int("ad", begin=1, end=2)
        if setting == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_INT

        return setting >> 4

    @property
    def display_timeout(self) -> int:
        """Display timeout in seconds, where 0 is always on.

        :returns: Timeout in seconds or default int value before any snapshot.
        """
        setting = self._record_int("ad", begin=1, end=2)
        if setting == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_INT

        return DISPLAY_TIMEOUTS.get(setting & 0x0F, DisplayTimeout.UNKNOWN).value

    @property
    def charging_mode(self) -> ChargingMode:
        """Charging mode of the device.

        :returns: Charging mode or unknown if no snapshot has been received.
        """
        try:
            return ChargingMode(self._record_int("ae", begin=1, end=2))
        except ValueError:
            return ChargingMode.UNKNOWN

    @property
    def charging_submode(self) -> int:
        """Sub-mode of the high power charging mode, numbered 1 to 3 as in the app.

        :returns: Sub-mode number or default int value if no snapshot has been received.
        """
        submode = self._record_int("ae", begin=2, end=3)
        if submode == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_INT

        return submode + 1

    @property
    def clock_format(self) -> ClockFormat:
        """Format of the clock on the display.

        :returns: Clock format or unknown if no snapshot has been received.
        """
        try:
            return ClockFormat(self._record_int("b4", begin=1, end=2))
        except ValueError:
            return ClockFormat.UNKNOWN

    @property
    def ac_light_mode(self) -> AcLightMode:
        """Mode of the indicator light on the AC outlets.

        :returns: Light mode or unknown if no snapshot has been received.
        """
        try:
            return AcLightMode(self._record_int("b5", begin=1, end=2))
        except ValueError:
            return AcLightMode.UNKNOWN

    async def _turn_port(self, port: int, *, on: bool) -> None:
        """Turn a switchable port on or off.

        :param port: Port number as the device counts them.
        :param on: True to turn the port on, False to turn it off.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_PORT_OUTPUT,
            parameters=PARAMETERS_ON_OFF,
            port=port,
            on=on,
        )

    async def _set_port_timer(self, port: int, seconds: int) -> None:
        """Set the auto-off timer of a switchable port.

        :param port: Port number as the device counts them.
        :param seconds: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_PORT_TIMER,
            parameters=PARAMETERS_TIMER,
            port=port,
            seconds=seconds,
        )

    async def _send_schedule(self, port: int, schedule: PortSchedule) -> None:
        """Send both triggers of a port's daily schedule, on-time then off-time.

        :param port: Port number as the device counts them.
        :param schedule: The schedule to store on the device.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_PORT_SCHEDULE,
            parameters=PARAMETERS_SCHEDULE,
            port=port,
            trigger=1,
            switch=schedule.start_switch,
            hour=schedule.start_hour,
            minute=schedule.start_minute,
            weekdays=schedule.start_weekdays,
        )
        await self._send_command(
            cmd=CMD_PORT_SCHEDULE,
            parameters=PARAMETERS_SCHEDULE,
            port=port,
            trigger=0,
            switch=schedule.end_switch,
            hour=schedule.end_hour,
            minute=schedule.end_minute,
            weekdays=schedule.end_weekdays,
        )

    async def _set_display(self, *, on: bool, theme: int) -> None:
        """Set the clock display's on/off state and theme together.

        :param on: True to turn the display on, False to turn it off.
        :param theme: Theme number, 1 to 3.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_DISPLAY,
            parameters=PARAMETERS_DISPLAY,
            display=(DISPLAY_ON if on else 0) | ((theme - 1) & 0x0F),
        )

    def _known_theme(self) -> int:
        """Return the theme in the last snapshot, or the first theme if unknown."""
        theme = self.display_theme
        return theme if theme != DEFAULT_METADATA_INT else 1

    async def turn_ac_1_on(self) -> None:
        """Turn AC outlet 1 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=0, on=True)

    async def turn_ac_1_off(self) -> None:
        """Turn AC outlet 1 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=0, on=False)

    async def set_timer_ac_1(self, time: int) -> None:
        """Set auto off timer for AC outlet 1.

        :param time: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(port=0, seconds=time)

    async def set_schedule_ac_1(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for AC outlet 1.

        :param schedule: The on-time and off-time triggers to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(port=0, schedule=schedule)

    async def turn_ac_2_on(self) -> None:
        """Turn AC outlet 2 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=1, on=True)

    async def turn_ac_2_off(self) -> None:
        """Turn AC outlet 2 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=1, on=False)

    async def set_timer_ac_2(self, time: int) -> None:
        """Set auto off timer for AC outlet 2.

        :param time: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(port=1, seconds=time)

    async def set_schedule_ac_2(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for AC outlet 2.

        :param schedule: The on-time and off-time triggers to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(port=1, schedule=schedule)

    async def turn_usb_c1_on(self) -> None:
        """Turn USB port C1 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=2, on=True)

    async def turn_usb_c1_off(self) -> None:
        """Turn USB port C1 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=2, on=False)

    async def set_timer_usb_c1(self, time: int) -> None:
        """Set auto off timer for USB C1.

        :param time: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(port=2, seconds=time)

    async def set_schedule_usb_c1(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C1.

        :param schedule: The on-time and off-time triggers to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(port=2, schedule=schedule)

    async def turn_usb_c2_on(self) -> None:
        """Turn USB port C2 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=3, on=True)

    async def turn_usb_c2_off(self) -> None:
        """Turn USB port C2 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=3, on=False)

    async def set_timer_usb_c2(self, time: int) -> None:
        """Set auto off timer for USB C2.

        :param time: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(port=3, seconds=time)

    async def set_schedule_usb_c2(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C2.

        :param schedule: The on-time and off-time triggers to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(port=3, schedule=schedule)

    async def turn_usb_c3_on(self) -> None:
        """Turn USB port C3 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=4, on=True)

    async def turn_usb_c3_off(self) -> None:
        """Turn USB port C3 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=4, on=False)

    async def set_timer_usb_c3(self, time: int) -> None:
        """Set auto off timer for USB C3.

        :param time: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(port=4, seconds=time)

    async def set_schedule_usb_c3(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C3.

        :param schedule: The on-time and off-time triggers to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(port=4, schedule=schedule)

    async def turn_usb_c4_on(self) -> None:
        """Turn USB port C4 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=5, on=True)

    async def turn_usb_c4_off(self) -> None:
        """Turn USB port C4 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(port=5, on=False)

    async def set_timer_usb_c4(self, time: int) -> None:
        """Set auto off timer for USB C4.

        :param time: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(port=5, seconds=time)

    async def set_schedule_usb_c4(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C4.

        :param schedule: The on-time and off-time triggers to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(port=5, schedule=schedule)

    async def turn_display_on(self) -> None:
        """Turn the clock display on, keeping its theme.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_display(on=True, theme=self._known_theme())

    async def turn_display_off(self) -> None:
        """Turn the clock display off, keeping its theme.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_display(on=False, theme=self._known_theme())

    async def set_display_theme(self, theme: int) -> None:
        """Set the theme of the clock display, keeping its on/off state.

        :param theme: Theme number, 1 to 3.
        :raises ValueError: If the theme is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if theme not in (1, 2, 3):
            msg = f"Theme must be 1, 2 or 3, not {theme}"
            raise ValueError(msg)
        await self._set_display(on=self.is_display_on, theme=theme)

    async def set_display_brightness(self, brightness: int) -> None:
        """Set the brightness level of the display.

        :param brightness: Brightness level.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            cmd=CMD_DISPLAY_BRIGHTNESS,
            parameters=PARAMETERS_DISPLAY_BRIGHTNESS,
            brightness=brightness,
        )

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:  # noqa: ASYNC109
        """Set the display timeout.

        :param timeout: One of S0 (always on), S30, S60, S300 and S1800.
        :raises ValueError: If the timeout is not supported by the device.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if timeout not in DISPLAY_TIMEOUT_COMMAND_CODES:
            msg = f"Display timeout {timeout} is not supported by this device"
            raise ValueError(msg)
        await self._send_command(
            cmd=CMD_DISPLAY_TIMEOUT,
            parameters=PARAMETERS_DISPLAY_TIMEOUT,
            timeout=DISPLAY_TIMEOUT_COMMAND_CODES[timeout],
        )

    async def set_charging_mode(self, mode: ChargingMode, submode: int = 1) -> None:
        """Set the charging mode.

        :param mode: The charging mode.
        :param submode: Sub-mode of the high power mode, 1 to 3.
        :raises ValueError: If the mode is unknown or the sub-mode out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is ChargingMode.UNKNOWN or submode not in (1, 2, 3):
            msg = f"Cannot set charging mode {mode} with sub-mode {submode}"
            raise ValueError(msg)
        await self._send_command(
            cmd=CMD_CHARGING_MODE,
            parameters=PARAMETERS_CHARGING_MODE,
            mode=mode.value,
            submode=submode - 1,
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
        await self._send_command(
            cmd=CMD_CLOCK_FORMAT,
            parameters=PARAMETERS_CLOCK_FORMAT,
            clock_format=clock_format.value,
        )

    async def set_ac_light_mode(self, mode: AcLightMode) -> None:
        """Set the mode of the indicator light on the AC outlets.

        :param mode: The light mode.
        :raises ValueError: If the mode is unknown.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode is AcLightMode.UNKNOWN:
            msg = "Cannot set an unknown AC light mode"
            raise ValueError(msg)
        await self._send_command(
            cmd=CMD_AC_LIGHT_MODE,
            parameters=PARAMETERS_AC_LIGHT_MODE,
            light_mode=mode.value,
        )
