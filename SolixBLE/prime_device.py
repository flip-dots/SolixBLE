"""Base Anker Prime device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Construct,
    Container,
    Int8ub,
)

from SolixBLE.const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.constructs import (
    PORT_FAULTS,
    PORT_READING,
    PORT_RECORD,
    SCHEDULE_TRIGGER,
    SCHEDULE_UNSET,
    TIMER_COMMAND,
    DecimalVersion,
)
from SolixBLE.device import SolixBLEDevice
from SolixBLE.protocols import EncryptedOuter, Outer
from SolixBLE.states import DisplayTimeout, PortSchedule, PortStatus, PortTimer
from SolixBLE.utilities import _parse_guarded, region

_LOGGER = logging.getLogger(__name__)

#: The pattern used in telemetry packets from Anker Prime and Solix devices
TELEMETRY_PATTERN = "03000f"

#: The UUID sent to the device during negotiation
UUID_STRING = "79ebed35-dc9c-4904-b40c-72c4e863aa10"

#: Command sent after connecting to start the telemetry stream. This must
#: be sent every ~10 seconds or no telemetry will be sent by the device.
CMD_SUB_AND_KEEP_ALIVE = 0x20B

PARAMETERS_KEEP_ALIVE = {
    "a1": {
        "value": "21",
    },
}

#: Command that requests the snapshot (``4a00``, fragmented as ``ca00``).
CMD_REQUEST_SNAPSHOT = 0x200

#: Seconds between keep-alives for a device that streams. One ``420b`` buys
#: ten ``4303`` pushes, and the cycle also fits the snapshot request, so 9 s
#: keeps it inside the firmware's 10-push count.
KEEP_ALIVE_INTERVAL = 9

#: Seconds between the snapshot request and the stream trigger, so their
#: replies don't collide.
SNAPSHOT_TO_STREAM_DELAY = 0.4

#: Port commands: on/off, daily schedule and countdown. Each takes the port's
#: wire index, which each model numbers its own way.
CMD_PORT_OUTPUT = 0x207
CMD_PORT_SCHEDULE = 0x208
CMD_PORT_TIMER = 0x209

#: Settings commands that carry a single byte.
CMD_DISPLAY_TIMEOUT = 0x203
CMD_DISPLAY_BRIGHTNESS = 0x204
CMD_CLOCK_FORMAT = 0x210

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
        "value": lambda seconds: TIMER_COMMAND.build(
            {"enabled": 1 if seconds else 0, "seconds": seconds},
        ),
    },
}

#: One ``4208`` sets one time of a port's daily schedule: ``a3`` picks the
#: time (1 on-time, 0 off-time) and ``a4`` carries it.
SCHEDULE_ON_TIME = 1
SCHEDULE_OFF_TIME = 0

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
        "value": lambda time: time,
    },
    "a4": {
        "type": 3,
        "value": lambda enabled, hour, minute, weekdays: SCHEDULE_TRIGGER.build(
            {
                "enabled": 1 if enabled else 0,
                "hour": hour,
                "minute": minute,
                "weekdays": weekdays,
            },
        ),
    },
}

PARAMETERS_SETTING = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": lambda setting: setting,
    },
}

#: Display timeouts a Prime device's ``4203`` setter and its snapshot's
#: timeout field both use, keyed by the wire code.
DISPLAY_TIMEOUTS = {
    0: DisplayTimeout.S0,
    1: DisplayTimeout.S30,
    2: DisplayTimeout.S60,
    3: DisplayTimeout.S300,
    4: DisplayTimeout.S1800,
}

#: The reverse of :data:`DISPLAY_TIMEOUTS`, for building a ``4203`` payload.
DISPLAY_TIMEOUT_CODES = {timeout: code for code, timeout in DISPLAY_TIMEOUTS.items()}


def _schedule_enabled(enabled: int) -> bool | None:
    """Return a schedule half's switch, or None if it has never been set.

    :param enabled: The half's :data:`~SolixBLE.constructs.SCHEDULE_TRIGGER`
        ``enabled`` byte.
    """
    if enabled == SCHEDULE_UNSET:
        return None
    return bool(enabled)


class PrimeDevice(SolixBLEDevice):
    """
    This is a base class based upon SolixBLEDevice which contains logic
    unique to Anker Prime devices that is designed to be overridden for
    specific implementations, e.g 160w, 250w, etc.

    Anker Prime devices negotiate with the encrypted outer protocol unless
    the device's advertisement says otherwise.
    """

    _OUTER_HINT: type[Outer] = EncryptedOuter

    #: A Prime's ``0300`` is telemetry only where :attr:`_TELEMETRY_COMMANDS`
    #: lists ``4300``; the A2345's is a stats push the module sends only to MQTT.
    _ALWAYS_TELEMETRY_MSGTYPES: frozenset[int] = frozenset()

    _UUID_STRING: str = UUID_STRING

    #: Seconds between keep-alives for a device that streams ``4303``, or None
    #: for one that needs no keep-alive.
    _KEEP_ALIVE_INTERVAL: int | None = None

    async def _post_authorize(self) -> None:
        """Start the session the way the app does once the client is authorized.

        ``4200`` asks for all device information; ``420a`` sets the region
        and the owner, which the device stores. The device treats a different
        owner as a new one, so the owner sent is this client's token.
        """
        await self._send_command(CMD_REQUEST_SNAPSHOT, {
            "a1": {
                "key": bytes.fromhex("a1"),
                "type": None,
                "value": bytes.fromhex("21"),
            },
        })
        await self._send_command("420a", {
            "a1": {
                "key": bytes.fromhex("a1"),
                "type": None,
                "value": bytes.fromhex("21"),
            }, "a2": {
                "key": bytes.fromhex("a2"),
                "type": 2,
                "value": region().encode(),
            }, "a3": {
                "key": bytes.fromhex("a3"),
                "type": 4,
                "value": self._client_token.encode(),
            },
        })

    async def _keep_alive(self) -> int | None:
        """Re-send the realtime trigger so the telemetry stream keeps flowing.

        .. note::
           :collapsible: closed

           One ``420b`` buys ten ``4303`` pushes about a second apart, so a
           device that streams must re-send it before the burst runs out.
           Only a device that sets :attr:`_KEEP_ALIVE_INTERVAL` sends it. A
           device with a snapshot (:attr:`_SNAPSHOT_COMMANDS` not empty) is
           first asked for a fresh one, a short pause ahead of the trigger.

        :returns: :attr:`_KEEP_ALIVE_INTERVAL`.
        """
        if self._KEEP_ALIVE_INTERVAL is None:
            return None
        if self._SNAPSHOT_COMMANDS:
            await self._send_command(CMD_REQUEST_SNAPSHOT, PARAMETERS_KEEP_ALIVE)
            await asyncio.sleep(SNAPSHOT_TO_STREAM_DELAY)
        await self._send_command(CMD_SUB_AND_KEEP_ALIVE, PARAMETERS_KEEP_ALIVE)
        return self._KEEP_ALIVE_INTERVAL

    async def _turn_port(self, port: int, *, on: bool) -> None:
        """Turn a switchable port on or off.

        :param port: The port's wire index.
        :param on: True to turn the port on, False to turn it off.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_PORT_OUTPUT,
            PARAMETERS_ON_OFF,
            port=port,
            on=on,
        )

    async def _set_port_timer(self, port: int, seconds: int) -> None:
        """Set a switchable port's countdown auto-off timer.

        :param port: The port's wire index.
        :param seconds: Seconds until shutdown, 0 to disarm the timer.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_PORT_TIMER,
            PARAMETERS_TIMER,
            port=port,
            seconds=seconds,
        )

    async def _send_schedule(self, port: int, schedule: PortSchedule) -> None:
        """Send both times of a port's daily schedule, on-time then off-time.

        :param port: The port's wire index.
        :param schedule: The schedule to store; a time whose switch is None
            is sent switched off.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_PORT_SCHEDULE,
            PARAMETERS_SCHEDULE,
            port=port,
            time=SCHEDULE_ON_TIME,
            enabled=schedule.on_time_enabled,
            hour=schedule.on_time_hour,
            minute=schedule.on_time_minute,
            weekdays=schedule.on_time_weekdays,
        )
        await self._send_command(
            CMD_PORT_SCHEDULE,
            PARAMETERS_SCHEDULE,
            port=port,
            time=SCHEDULE_OFF_TIME,
            enabled=schedule.off_time_enabled,
            hour=schedule.off_time_hour,
            minute=schedule.off_time_minute,
            weekdays=schedule.off_time_weekdays,
        )

    async def _send_setting(self, message: int, setting: int | bytes) -> None:
        """Send a settings command that carries a single byte.

        :param message: The settings command's message type.
        :param setting: The byte to send, as an integer or built by a construct.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(message, PARAMETERS_SETTING, setting=setting)

    def _snapshot_version(self, key: str) -> str:
        """Read a firmware version a snapshot tag packs as decimal digits.

        :param key: The snapshot tag (e.g ``"a2"``) to read.
        :returns: The version (e.g ``"2.1.1.6"``), or
            :data:`~SolixBLE.const.DEFAULT_METADATA_STRING` if no snapshot
            has carried it.
        """
        version = _parse_guarded(self._record(key), DecimalVersion)
        if version is None:
            return DEFAULT_METADATA_STRING
        return str(version)

    def _port_fault(self, flag: str) -> bool | None:
        """Read one flag of the snapshot's port fault bitmap.

        :param flag: Name of the flag in :data:`~SolixBLE.constructs.PORT_FAULTS`.
        :returns: The flag, or :data:`~SolixBLE.const.DEFAULT_METADATA_BOOL`
            if no snapshot has carried it.
        """
        faults = self._snapshot_struct("a3", PORT_FAULTS)
        if faults is None:
            return DEFAULT_METADATA_BOOL
        return bool(faults[flag])

    def _port_record(self, key: str) -> Container | None:
        """Parse a port's switch, schedule and timer from its snapshot record.

        :param key: Key of the port's record (e.g ``"aa"``, ``"ab"``, ...).
        :returns: The parsed :data:`~SolixBLE.constructs.PORT_RECORD`, or
            None if no snapshot has carried it.
        """
        return self._snapshot_struct(key, PORT_RECORD)

    def _port_schedule(self, key: str) -> PortSchedule | None:
        """Read a port's daily on/off-time schedule from its snapshot record.

        :param key: Key of the port's record (e.g ``"aa"``, ``"ab"``, ...).
        :returns: The schedule, or None if no snapshot has carried the record.
        """
        record = self._port_record(key)
        if record is None:
            return None
        on_time, off_time = record.on_time, record.off_time
        return PortSchedule(
            on_time_enabled=_schedule_enabled(on_time.enabled),
            on_time_hour=on_time.hour,
            on_time_minute=on_time.minute,
            on_time_weekdays=on_time.weekdays,
            off_time_enabled=_schedule_enabled(off_time.enabled),
            off_time_hour=off_time.hour,
            off_time_minute=off_time.minute,
            off_time_weekdays=off_time.weekdays,
        )

    def _port_timer(self, key: str) -> PortTimer | None:
        """Read a port's countdown auto-off timer from its snapshot record.

        :param key: Key of the port's record (e.g ``"aa"``, ``"ab"``, ...).
        :returns: The timer, or None if no snapshot has carried the record.
        """
        record = self._port_record(key)
        if record is None:
            return None
        return PortTimer(
            enabled=bool(record.timer.enabled),
            seconds=record.timer.seconds,
            remaining=record.timer.remaining,
        )

    def _stream_port(self, key: str) -> Container | None:
        """Return a port's realtime reading from the ``4303`` stream.

        :param key: The stream tag (e.g ``"a2"``) for the port.
        :returns: The parsed :data:`~SolixBLE.constructs.PORT_READING`, or
            None if the stream hasn't carried this tag yet or the record is
            too short to parse.
        """
        if self._data is None or key not in self._data:
            return None
        value = self._data[key].value or b""
        if len(value) < PORT_READING.sizeof():
            return None
        return PORT_READING.parse(value)

    def _port_status(self, key: str) -> PortStatus:
        """Return a port's status from the ``4303`` stream.

        :param key: The stream tag (e.g ``"a2"``) for the port.
        """
        reading = self._stream_port(key)
        if reading is None:
            return PortStatus.UNKNOWN
        return PortStatus(reading.status)

    def _port_reading(self, key: str, field: str, scale: float) -> float:
        """Return a scaled field of a port's reading from the ``4303`` stream.

        :param key: The stream tag (e.g ``"a2"``) for the port.
        :param field: The :data:`~SolixBLE.constructs.PORT_READING` field to
            read (``"voltage"``, ``"current"`` or ``"power"``).
        :param scale: Divide the raw field by this to get real units.
        """
        reading = self._stream_port(key)
        if reading is None:
            return DEFAULT_METADATA_FLOAT
        return float(getattr(reading, field)) / scale

    def _stream_or_snapshot(
        self, stream_key: str, snapshot_key: str, struct: Construct,
    ) -> Container | None:
        """Read a field from the latest stream frame, else from the snapshot.

        .. note::
           :collapsible: closed

           The ``4303`` stream arrives about every second while a ``420b``
           burst runs, the ``4a00`` snapshot only when requested. A field
           both carry reads from the stream while it has one, and from the
           snapshot otherwise. The two may use different tags for the same
           field (the A2345 stream's ``a8`` is the snapshot's ``bd``).

        :param stream_key: The field's tag in the stream.
        :param snapshot_key: The same field's tag in the snapshot.
        :param struct: The construct to parse the field with.
        :returns: The parsed value, or None if neither carries it in full.
        """
        value = self._tag(stream_key, struct)
        if value is not None:
            return value
        return self._snapshot_struct(snapshot_key, struct)

    def _snapshot_int(self, key: str, field: Construct = Int8ub) -> int:
        """Parse a snapshot tag as a plain integer.

        :param key: The snapshot tag (e.g ``"b0"``) to read.
        :param field: The integer construct to parse the tag's value with.
        :returns: The parsed value, or :data:`~SolixBLE.const.DEFAULT_METADATA_INT`
            if the tag is absent or its record is too short for ``field``.
        """
        record = self._record(key)
        if len(record) < field.sizeof():
            return DEFAULT_METADATA_INT
        return int(field.parse(record))
