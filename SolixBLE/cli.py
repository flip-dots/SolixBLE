"""Interactive console for Anker Solix and Prime BLE devices.

Install with ``pip install "SolixBLE[cli]"`` and run ``solixble`` (or
``python -m SolixBLE``). It scans, connects and drives devices with the
library's own vocabulary, records every frame in both directions as
cleartext, and ``console`` opens a Python prompt on the same event loop with
the devices in scope.

.. moduleauthor:: kb1ibt
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import codeop
import copy
import inspect
import json
import logging
import re
import rlcompleter
import sys
import traceback
import typing
from collections import deque
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TextIO

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from construct import (  # type: ignore[import-untyped]  # construct ships no types
    ConstructError,
    Container,
)
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

import SolixBLE

from .advertisement import ANKER_COMPANY_ID, record_from_advertisement
from .const import NEGOTIATION_PATTERN, SERVICE_2215, UUID_IDENTIFIERS
from .constructs import Packet, PacketCommand, PacketPattern, Parameters
from .device import SolixBLEDevice
from .factory import device_class_from_advertisement
from .protocols import EncryptedOuter, NegotiatedSession, Outer, PlainOuter
from .protocols.base import override
from .utilities import region, set_region

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from bleak import BleakClient
    from prompt_toolkit.document import Document

PROMPT = "solixble> "
#: Channel byte of the factory lane, refused unless the console allows it.
FACTORY_CHANNEL = 0x0C
#: A parameter value replaced by the live 4-byte timestamp when sent.
TIMESTAMP = "@ts"
CONNECT_USAGE = (
    "connect <n|mac|address> [class] [--no-advert] [--outer plain|encrypted]"
    " [--no-register] [--manual]"
)
#: Message type of the client registration ``--no-register`` withholds.
REGISTRATION_MSGTYPE = 0x027
#: The outer protocols ``connect --outer`` attempts, ignoring the advert.
OUTERS: dict[str, type[Outer]] = {"plain": PlainOuter, "encrypted": EncryptedOuter}
#: Loggers of the BLE stack, set by ``--bleak-log-level`` apart from the library's.
BLEAK_LOGGERS = ("bleak", "bleak_retry_connector")
#: Announcement fields shown in hex, as on the wire.
HEX_FIELDS = frozenset(
    {"base_method", "encrypt_method", "auth_method", "registration_status"},
)
#: Shown when a capture starts.
CAPTURE_NOTE = (
    "! the capture holds decrypted frames, the client token and device serials"
    " in clear: keep it out of version control and redact it before sharing"
)
DEFAULT_SCAN_SECONDS = 5.0
DEFAULT_FRAMES = 20
FRAME_HISTORY = 1000
#: Index of the model class in a tapped class's MRO: (tapped, FrameTap, model).
_MODEL_MRO_INDEX = 2

HELP_LINES = (
    "scan [secs] [raw]                    advertising Anker devices (default 5 s);",
    "                                     raw adds each one's advertisement bytes",
    "connect <n|mac|address> [class] [--no-advert] [--outer plain|encrypted]",
    "        [--no-register] [--manual]   connect a scanned device; the class",
    "                                     defaults to the factory's choice;",
    "                                     --no-advert connects as HaSolixBLE does",
    "                                     (no capability hint), --outer attempts",
    "                                     only that outer, ignoring the advert's",
    "                                     capability byte;",
    "                                     --no-register withholds 4027 and carries",
    "                                     on as if authorized;",
    "                                     --manual subscribes and sends nothing:",
    "                                     nego frames go as typed, a flagged one",
    "                                     under the outer's static key, and no",
    "                                     reply is answered",
    "devices | use <n> | disconnect [n]   the open links and the current one",
    "release [n] | reconnect [n]          drop the link (no auto-reconnect) so the",
    "                                     app can connect; retake it on the same",
    "                                     device, which keeps its last outer",
    "info                                 class, outer, path, announcement",
    "data [verbose]                       decoded telemetry tags",
    "props | constants                    public properties; CMD_* and PARAMETERS_*",
    "call <method> [args]                 a public method; enums by name: ['S10']",
    "send <cmd> <params> [kwargs]         _send_command (typed fe trailer added)",
    "packet <pattern> <cmd> <params> [kwargs]",
    "                                     _send_packet on any pattern, no trailer",
    "nego <cmd> <params> [kwargs]         a frame on 030001 under the live session",
    "    <params> = a dict as a device module writes it, JSON or Python literal,",
    "    e.g. {'a1': {'value': '21'}}, or a PARAMETERS_* name; a value of '@ts'",
    "    is the live timestamp; kwargs feed lambda values: {'seconds': 300}",
    "frames [n]                           last n frames, both directions (default 20)",
    "capture <file> | capture off         append the session to a file, dated:",
    "                                     frames, commands, output and log records",
    "token [id] | region [cc]             client token (4027 / 420a owner); region",
    "console                              Python prompt on this loop; exit() returns",
    "help | quit",
)


class CommandError(Exception):
    """A command that cannot run as typed."""


def new_frame(  # noqa: PLR0913  # one argument per frame field
    *,
    time: datetime,
    device: str,
    direction: str,
    pattern: bytes,
    cmd: bytes,
    cleartext: bytes | None,
    raw: bytes | None = None,
) -> Container:
    """Return one frame as sent or received, with its cleartext when available.

    :param time: When the frame was sent or received.
    :param device: The console's name for the device.
    :param direction: ``in`` or ``out``.
    :param pattern: The frame's pattern.
    :param cmd: The frame's command.
    :param cleartext: The decrypted payload, or None if it didn't decrypt.
    :param raw: The whole frame as on the wire, if known.
    """
    return Container(
        time=time,
        device=device,
        direction=direction,
        pattern=pattern,
        cmd=cmd,
        cleartext=cleartext,
        raw=raw,
    )


def frame_line(frame: Container) -> str:
    """Return a frame as one console line: time, [device], then the frame.

    :param frame: A frame from :func:`new_frame`.
    """
    clear = frame.cleartext.hex() if frame.cleartext is not None else "undecryptable"
    text = (
        f"{frame.time:%H:%M:%S.%f}"[:-3]
        + f" [{frame.device}] {frame.direction:<3} {frame.pattern.hex()}"
        + f" {frame.cmd.hex()} {clear}"
    )
    described = describe(frame.cleartext)
    return f"{text}  {described}" if described else text


def capture_line(frame: Container) -> str:
    """Return a frame as one dated capture-file line, raw bytes included.

    :param frame: A frame from :func:`new_frame`.
    """
    raw = f" raw={frame.raw.hex()}" if frame.raw is not None else ""
    return f"{frame.time:%Y-%m-%d} {frame_line(frame)}{raw}"


def describe(cleartext: bytes | None) -> str:
    """Render a payload as its status byte and tags, or nothing if it doesn't parse.

    :param cleartext: The decrypted payload.
    """
    if not cleartext:
        return ""
    try:
        parameters = Parameters.parse(cleartext)
    except (ConstructError, ValueError):
        return ""
    status = (
        [f"status={parameters.status:02x}"] if parameters.status is not None else []
    )
    tags = [f"{tag}={p.value_legacy.hex()}" for tag, p in parameters.items()]
    return " ".join(status + tags)


class FrameLog:
    """The frames of every tapped device, and an optional append-only capture.

    The capture holds the frames and, through :meth:`note`, the session
    around them: commands, their output and log records.
    """

    def __init__(self, size: int = FRAME_HISTORY) -> None:
        """Keep the last ``size`` frames.

        :param size: How many frames to keep in memory.
        """
        self.frames: deque[Container] = deque(maxlen=size)
        self.total = 0
        self._capture: TextIO | None = None
        self.capture_path: Path | None = None

    def capture(self, path: Path | None) -> None:
        """Append every later frame to ``path`` (never truncated), or stop.

        :param path: The capture file, or None to stop capturing.
        """
        if self._capture is not None:
            self._capture.close()
            self._capture = None
        self.capture_path = path
        if path is not None:
            self._capture = path.open("a", encoding="utf-8")

    def capture_to(self, name: str) -> None:
        """Append every later frame to the file ``name`` (``~`` expanded).

        :param name: The capture file's path as typed.
        """
        self.capture(Path(name).expanduser())

    def record(self, frame: Container) -> None:
        """Keep a frame and append it to the capture file, if one is open.

        :param frame: The frame to record, from :func:`new_frame`.
        """
        self.frames.append(frame)
        self.total += 1
        if self._capture is not None:
            self._capture.write(capture_line(frame) + "\n")
            self._capture.flush()

    def note(self, text: str) -> None:
        """Append console text to the capture file, if one is open, each line dated.

        :param text: A command, its output, or a log record.
        """
        if self._capture is None:
            return
        stamp = f"{datetime.now(UTC).astimezone():%Y-%m-%d %H:%M:%S.%f}"[:-3]
        for line in text.splitlines() or [""]:
            self._capture.write(f"{stamp} {line}\n")
        self._capture.flush()

    def since(self, total: int) -> list[Container]:
        """Return the frames recorded after the log held ``total`` frames.

        :param total: An earlier value of :attr:`total`.
        """
        count = min(self.total - total, len(self.frames))
        return list(self.frames)[len(self.frames) - count :] if count else []


class CaptureHandler(logging.Handler):
    """Writes log records, tracebacks included, to the capture file."""

    def __init__(self, frames: FrameLog) -> None:
        """Write to the capture of ``frames``.

        :param frames: The frame log whose capture file receives the records.
        """
        super().__init__()
        self._frames = frames
        self.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

    @override
    def emit(self, record: logging.LogRecord) -> None:
        """Note one formatted record in the capture."""
        self._frames.note(self.format(record))


class ManualSession(NegotiatedSession):
    """A session that answers no reply: only what is typed is sent.

    Frames seal under the outer with no keys installed, so a flagged one goes
    under the static GCM key on the encrypted outer. It never authorizes.
    """

    @property
    @override
    def authorized(self) -> bool:
        """Never: nothing negotiated here unlocks session commands."""
        return False

    @override
    async def on_plaintext(
        self,
        pattern: bytes,  # noqa: ARG002  # the library's signature
        cmd: bytes,  # noqa: ARG002  # the library's signature
        plaintext: bytes,  # noqa: ARG002  # the library's signature
    ) -> None:
        """Note the reply and leave it unanswered."""
        self._replied = True


class FrameTap(SolixBLEDevice):
    """Device mixin that records every frame it sends and receives as cleartext.

    Combined with a model class as ``type(name, (FrameTap, Model), {})``; the
    console sets :attr:`frames` before connecting.
    """

    frames: FrameLog
    #: Withhold ``x027`` and carry on as if authorized (``connect --no-register``).
    withhold_registration = False
    #: Keep the outer ``connect --outer`` chose: a refusal ends the connect.
    pin_outer = False
    #: Subscribe and send nothing until typed (``connect --manual``).
    manual = False
    #: Pattern and cmd of the packet being built, while ``_send_packet`` runs.
    _sending: tuple[bytes, bytes] | None = None

    @override
    async def _negotiate(self) -> bool:
        """Negotiate, or under ``--manual`` start a session that answers nothing."""
        if not self.manual:
            return await super()._negotiate()
        self._session = ManualSession(self._outer_class(), self)
        return True

    @override
    async def _auto_reconnect(self) -> None:
        """Reconnect after a drop, except under ``--manual``.

        A manual link never negotiates, so the library's task would reopen it
        every few seconds; ``reconnect`` retakes a dropped one instead.
        """
        if not self.manual:
            await super()._auto_reconnect()

    @override
    async def _post_authorize(self) -> None:
        """Send the model's post-authorize requests, except under ``--manual``."""
        if not self.manual:
            await super()._post_authorize()

    @override
    async def _post_connect(self) -> None:
        """Run the model's post-connect setup, except under ``--manual``."""
        if not self.manual:
            await super()._post_connect()

    @override
    async def _reopen_if_refused(
        self,
        max_attempts: int,
        run_callbacks: bool,  # noqa: FBT001  # the library's signature
    ) -> bool:
        """Reopen on the other outer as the library does, unless it is pinned."""
        if self.pin_outer:
            return False
        return await super()._reopen_if_refused(max_attempts, run_callbacks)

    @override
    def _encrypt_payload(self, payload: bytes) -> bytes:
        """Record the frame being sent, before it is written, then encrypt it.

        Recorded here rather than after the write, since a device can answer
        before the write returns.
        """
        if self._sending is not None:
            self._record("out", *self._sending, payload)
            if self.manual and not PacketCommand.parse(self._sending[1]).encrypted:
                return payload
        return super()._encrypt_payload(payload)

    @override
    async def _send_packet(
        self,
        pattern: str,
        cmd: str,
        parameters: dict[Any, Any],
        **kwargs: dict[Any, Any],
    ) -> None:
        """Send a packet, noting its pattern and cmd for the record."""
        if (
            self.withhold_registration
            and pattern == NEGOTIATION_PATTERN
            and PacketCommand.parse(bytes.fromhex(cmd)).msgtype == REGISTRATION_MSGTYPE
            and self._session is not None
            and self._session.path is not None
        ):
            self._session.path.authorized = True
            return
        self._sending = (bytes.fromhex(pattern), bytes.fromhex(cmd))
        try:
            await super()._send_packet(pattern, cmd, parameters, **kwargs)
        finally:
            self._sending = None

    @override
    async def _process_notification(
        self,
        client: BleakClient,
        handle: int,
        data: bytearray,
    ) -> None:
        """Record a received frame, then process it."""
        raw = bytes(data)
        try:
            packet = Packet.parse(raw)
        except (ConstructError, ValueError):
            self._record("in", b"", b"", None, raw)
        else:
            if not PacketCommand.parse(packet.cmd).fragmented:
                self._record_received(
                    packet.pattern,
                    packet.cmd,
                    packet.payload_bytes,
                    raw,
                )
        await super()._process_notification(client, handle, data)

    @override
    def _reassemble(self, packet: Packet) -> bytes | None:
        """Re-assemble a fragmented payload and record it once complete."""
        payload = super()._reassemble(packet)
        if payload is not None:
            self._record_received(packet.pattern, packet.cmd, payload, None)
        return payload

    def _record_received(
        self,
        pattern: bytes,
        cmd: bytes,
        payload: bytes,
        raw: bytes | None,
    ) -> None:
        """Record a received payload, decrypted under the session if flagged."""
        cleartext: bytes | None = payload
        if PacketCommand.parse(cmd).encrypted and self._session is not None:
            try:
                cleartext = self._session.decrypt(payload)
            except ValueError:
                cleartext = None
        self._record("in", pattern, cmd, cleartext, raw)

    def _record(
        self,
        direction: str,
        pattern: bytes,
        cmd: bytes,
        cleartext: bytes | None,
        raw: bytes | None = None,
    ) -> None:
        """Hand one frame to the frame log."""
        self.frames.record(
            new_frame(
                time=datetime.now(UTC).astimezone(),
                device=self.name,
                direction=direction,
                pattern=pattern,
                cmd=cmd,
                cleartext=cleartext,
                raw=raw,
            ),
        )


#: One advertising device as last seen, as bleak pairs them.
ScanResult = tuple[BLEDevice, AdvertisementData]


def is_anker(advertisement: AdvertisementData) -> bool:
    """Whether a scan result carries the Anker record or an Anker service.

    :param advertisement: The scan result.
    """
    return ANKER_COMPANY_ID in advertisement.manufacturer_data or any(
        uuid in UUID_IDENTIFIERS for uuid in advertisement.service_uuids
    )


def split_args(text: str) -> list[str]:
    """Split a command line on spaces outside brackets and quotes.

    :param text: The command line.
    """
    words: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    for char in text:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char.isspace() and depth == 0:
            if current:
                words.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        words.append("".join(current))
    return words


def parse_literal(text: str) -> Any:  # noqa: ANN401  # any literal the user types
    """Return ``text`` as JSON, else as a Python literal.

    :param text: The typed value.
    :raises CommandError: If it is neither.
    """
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError) as error:
        msg = f"not a JSON or Python literal: {text!r}"
        raise CommandError(msg) from error


def model_class(device: SolixBLEDevice) -> type[SolixBLEDevice]:
    """Return the model class of a device, behind its frame tap if it has one.

    :param device: The device.
    """
    cls = type(device)
    if isinstance(device, FrameTap):
        model: type[SolixBLEDevice] = cls.__mro__[_MODEL_MRO_INDEX]
        return model
    return cls


def device_classes() -> dict[str, type[SolixBLEDevice]]:
    """Return the library's device classes by name."""
    exported = {name: getattr(SolixBLE, name) for name in SolixBLE.__all__}
    return {
        name: value
        for name, value in exported.items()
        if isinstance(value, type) and issubclass(value, SolixBLEDevice)
    }


def constants(device: SolixBLEDevice) -> dict[str, object]:
    """Return the ``CMD_*`` and ``PARAMETERS_*`` of a device's class modules.

    :param device: The device.
    """
    found: dict[str, object] = {}
    for cls in reversed(model_class(device).__mro__):
        module = sys.modules.get(cls.__module__)
        if module is None or not issubclass(cls, SolixBLEDevice):
            continue
        found |= {
            name: value
            for name, value in vars(module).items()
            if name.startswith(("CMD_", "PARAMETERS_"))
        }
    return found


def coerce_arguments(method: Callable[..., object], args: list[object]) -> list[object]:
    """Turn string arguments into enum members where the method takes an enum.

    :param method: The method to call.
    :param args: The arguments as typed.
    """
    try:
        hints = typing.get_type_hints(method)
    except (NameError, TypeError):
        hints = {}
    names = list(inspect.signature(method).parameters)
    coerced: list[object] = []
    for name, arg in zip(names, args, strict=False):
        hint = hints.get(name)
        if isinstance(hint, type) and issubclass(hint, Enum) and isinstance(arg, str):
            coerced.append(hint[arg])
        else:
            coerced.append(arg)
    return coerced + args[len(coerced) :]


def _connect_options(
    args: list[str],
) -> tuple[list[str], bool, type[Outer] | None, bool, bool]:
    """Split ``connect``'s arguments into positionals and its options.

    :returns: The positionals, ``--no-advert``, ``--outer``, ``--no-register``
        and ``--manual``.
    :raises CommandError: If ``--outer`` is not followed by plain or encrypted.
    """
    positional = []
    no_advert = False
    no_register = False
    manual = False
    outer: type[Outer] | None = None
    words = iter(args)
    for word in words:
        if word == "--no-advert":
            no_advert = True
        elif word == "--no-register":
            no_register = True
        elif word == "--manual":
            manual = True
        elif word == "--outer":
            name = next(words, "")
            if name not in OUTERS:
                raise CommandError(CONNECT_USAGE)
            outer = OUTERS[name]
        else:
            positional.append(word)
    return positional, no_advert, outer, no_register, manual


def _transport_without_class(advertisement: AdvertisementData) -> str:
    """Name the transport of a device the factory has no class for."""
    if SERVICE_2215 in advertisement.service_uuids:
        return "2215"
    return "legacy"


def _link_state(device: SolixBLEDevice) -> str:
    """Return how far a device's link has come: negotiated, connected or down."""
    if device.negotiated:
        return "negotiated"
    return "connected" if device.connected else "down"


def _render(name: str, value: object) -> str:
    """Render an announcement field.

    Bytes as ASCII when printable, else hex; method and status bytes in hex,
    as on the wire; counts and seconds in decimal.
    """
    if isinstance(value, bytes):
        text = value.decode("ascii", errors="replace")
        return text if text.isprintable() else value.hex()
    if name in HEX_FIELDS and isinstance(value, int):
        return f"0x{value:02x}"
    return str(value)


class Console:
    """The console's commands and state, independent of the terminal."""

    COMMANDS: ClassVar[tuple[str, ...]] = (
        "help",
        "scan",
        "connect",
        "devices",
        "use",
        "disconnect",
        "release",
        "reconnect",
        "info",
        "data",
        "props",
        "constants",
        "call",
        "send",
        "packet",
        "nego",
        "frames",
        "capture",
        "token",
        "region",
        "quit",
    )

    def __init__(
        self,
        frames: FrameLog | None = None,
        *,
        scanner: type = BleakScanner,
        allow_factory_channel: bool = False,
        token: str | None = None,
        reply_wait: float = 2.0,
    ) -> None:
        """Start with no scan results and no devices.

        :param frames: Where frames are recorded.
        :param scanner: The scanner class (BleakScanner's interface).
        :param allow_factory_channel: Let ``packet`` send on channel ``0c``.
        :param token: Client token sent as ``4027`` / ``420a`` owner.
        :param reply_wait: Seconds to collect frames after a send.
        """
        self.frames = frames or FrameLog()
        self.results: list[ScanResult] = []
        self.devices: list[SolixBLEDevice] = []
        self.current: SolixBLEDevice | None = None
        self.token = token
        self.finished = False
        self._scanner = scanner
        self._allow_factory_channel = allow_factory_channel
        self._reply_wait = reply_wait

    async def run_line(self, line: str) -> list[str]:
        """Run one command line, note it and its output in the capture.

        Frame lines are left out of the note; the capture already holds the
        frames themselves.

        :param line: The command line.
        """
        if line.strip():
            self.frames.note(f"{PROMPT}{line.strip()}")
        mark = self.frames.total
        lines = await self._run(line)
        frame_lines = {frame_line(frame) for frame in self.frames.since(mark)}
        if not line.strip().startswith("frames"):
            for output in lines:
                if output not in frame_lines:
                    self.frames.note(output)
        return lines

    async def _run(self, line: str) -> list[str]:
        """Run one command line and return what it prints."""
        words = split_args(line.strip())
        if not words:
            return []
        if words[0] not in self.COMMANDS:
            return [f"! unknown command {words[0]!r}; help lists them"]
        handler = getattr(self, f"_cmd_{words[0]}")
        try:
            lines: list[str] = await handler(words[1:])
        except CommandError as error:
            return [f"! {error}"]
        except Exception as error:  # noqa: BLE001  # a failed command must not end the session
            return [f"! {type(error).__name__}: {error}"]
        return lines

    def namespace(self) -> dict[str, object]:
        """Return the names the Python console starts with."""
        return {
            "console": self,
            "devices": self.devices,
            "device": self.current,
            "frames": self.frames,
            "asyncio": asyncio,
            "SolixBLE": SolixBLE,
            "Packet": Packet,
            "Parameters": Parameters,
        }

    async def close(self) -> None:
        """Disconnect every device and stop capturing."""
        for device in self.devices:
            await device.disconnect()
        self.devices.clear()
        self.current = None
        self.frames.capture(None)

    def _device(self) -> SolixBLEDevice:
        """Return the current device.

        :raises CommandError: If no device is connected.
        """
        if self.current is None:
            msg = "no current device; connect or use one"
            raise CommandError(msg)
        return self.current

    async def _cmd_help(self, _args: list[str]) -> list[str]:
        return list(HELP_LINES)

    async def _cmd_quit(self, _args: list[str]) -> list[str]:
        self.finished = True
        return []

    async def _cmd_scan(self, args: list[str]) -> list[str]:
        raw = "raw" in args
        numbers = [arg for arg in args if arg != "raw"]
        seconds = float(numbers[0]) if numbers else DEFAULT_SCAN_SECONDS
        found: dict[str, ScanResult] = {}

        def detected(ble_device: BLEDevice, advertisement: AdvertisementData) -> None:
            if is_anker(advertisement):
                found[ble_device.address] = (ble_device, advertisement)

        async with self._scanner(detected):
            await asyncio.sleep(seconds)
        self.results = sorted(
            found.values(),
            key=lambda result: -result[1].rssi,
        )
        return self._scan_table() + (self._raw_lines() if raw else [])

    def _raw_lines(self) -> list[str]:
        """Return each scanned device's advertisement as raw bytes, by index.

        The Anker record is shown whether or not it parses, then any other
        manufacturer data, service data and the advertised services.
        """
        lines = []
        for index, (_, advertisement) in enumerate(self.results):
            record = advertisement.manufacturer_data.get(ANKER_COMPANY_ID)
            if record is not None:
                unparsed = (
                    " (unparsed)"
                    if record_from_advertisement(advertisement) is None
                    else ""
                )
                lines.append(f"{index}  ffff={record.hex()}{unparsed}")
            lines.extend(
                f"{index}  mfr {company:04x}={data.hex()}"
                for company, data in advertisement.manufacturer_data.items()
                if company != ANKER_COMPANY_ID
            )
            lines.extend(
                f"{index}  data {uuid}={data.hex()}"
                for uuid, data in advertisement.service_data.items()
            )
            if advertisement.service_uuids:
                lines.append(
                    f"{index}  services {' '.join(advertisement.service_uuids)}",
                )
        return lines

    def _scan_table(self) -> list[str]:
        """Return the last scan as a table."""
        rows = [("#", "address", "name", "mac", "type", "sku", "cap", "class", "rssi")]
        for index, (ble_device, advertisement) in enumerate(self.results):
            record = record_from_advertisement(advertisement)
            cls = device_class_from_advertisement(advertisement, ble_device.name)
            capability = record.capability if record is not None else None
            rows.append(
                (
                    str(index),
                    ble_device.address,
                    advertisement.local_name or ble_device.name or "",
                    record.mac.hex() if record is not None else "",
                    record.product_type.hex() if record is not None else "",
                    record.sku if record is not None else "",
                    f"{capability:02x}" if capability is not None else "",
                    cls.__name__
                    if cls is not None
                    else f"({_transport_without_class(advertisement)})",
                    str(advertisement.rssi),
                ),
            )
        widths = [
            max(len(row[column]) for row in rows) for column in range(len(rows[0]))
        ]
        return [
            "  ".join(
                cell.ljust(width) for cell, width in zip(row, widths, strict=True)
            ).rstrip()
            for row in rows
        ]

    def _find(self, key: str) -> ScanResult | None:
        """Return the scanned device a key names: an index, advert MAC or address."""
        if key.isdigit() and int(key) < len(self.results):
            return self.results[int(key)]
        mac = re.sub("[:-]", "", key).lower()
        for result in self.results:
            ble_device, advertisement = result
            record = record_from_advertisement(advertisement)
            if record is not None and record.mac.hex() == mac:
                return result
            if ble_device.address.lower() == key.lower():
                return result
        return None

    async def _cmd_connect(self, args: list[str]) -> list[str]:
        positional, no_advert, outer, no_register, manual = _connect_options(args)
        if not positional:
            raise CommandError(CONNECT_USAGE)
        result = self._find(positional[0])
        if result is None:
            await self._cmd_scan([])
            result = self._find(positional[0])
        if result is None:
            msg = f"{positional[0]} was not seen advertising"
            raise CommandError(msg)
        ble_device, advertisement = result
        slot = self._slot_for(ble_device.address)
        cls = self._class_for(result, positional[1] if len(positional) > 1 else None)
        # Named after the model, so the library's own log lines read as usual
        tapped = type(cls.__name__, (FrameTap, cls), {})
        device: FrameTap = tapped(
            ble_device,
            advertisement=None if no_advert else advertisement,
        )
        if outer is not None:
            device._outer_class = outer  # noqa: SLF001
            device.pin_outer = True
        device.withhold_registration = no_register
        device.manual = manual
        device.frames = self.frames
        if self.token is not None:
            device._client_token = self.token  # noqa: SLF001
        if not await device.connect():
            await device.disconnect()
            return [
                f"! could not connect to {ble_device.address}",
                *self._info(device),
            ]
        if slot is None:
            self.devices.append(device)
            slot = len(self.devices) - 1
        else:
            self.devices[slot] = device
        self.current = device
        return [f"[{slot}] connected", *self._info(device)]

    def _slot_for(self, address: str) -> int | None:
        """Return the index of a released device at ``address``, to connect into.

        :raises CommandError: If a device at ``address`` is still connected.
        """
        for index, device in enumerate(self.devices):
            if device.address == address:
                if device.connected:
                    msg = f"[{index}] is connected to {address}; release it first"
                    raise CommandError(msg)
                return index
        return None

    def _class_for(
        self,
        result: ScanResult,
        name: str | None,
    ) -> type[SolixBLEDevice]:
        """Return the class named, else the factory's choice for a scan result.

        :raises CommandError: If the name is unknown or the device needs one.
        """
        classes = device_classes()
        if name is not None:
            if name not in classes:
                msg = f"unknown class {name!r}; one of {', '.join(sorted(classes))}"
                raise CommandError(msg)
            return classes[name]
        ble_device, advertisement = result
        cls = device_class_from_advertisement(advertisement, ble_device.name)
        if cls is None:
            transport = _transport_without_class(advertisement)
            msg = f"no class speaks the {transport} transport yet; name one to try"
            raise CommandError(msg)
        return cls

    async def _cmd_devices(self, _args: list[str]) -> list[str]:
        return [
            f"{'*' if device is self.current else ' '}[{index}] {device.name} "
            f"{device.address} {model_class(device).__name__} {_link_state(device)}"
            for index, device in enumerate(self.devices)
        ]

    def _index(self, args: list[str]) -> int:
        """Return the device index in ``args``, else the current device's."""
        if args:
            index = int(args[0])
            if not 0 <= index < len(self.devices):
                msg = f"no device [{index}]"
                raise CommandError(msg)
            return index
        return self.devices.index(self._device())

    async def _cmd_use(self, args: list[str]) -> list[str]:
        self.current = self.devices[self._index(args)]
        return await self._cmd_devices([])

    async def _cmd_disconnect(self, args: list[str]) -> list[str]:
        device = self.devices.pop(self._index(args))
        await device.disconnect()
        if device is self.current:
            self.current = self.devices[-1] if self.devices else None
        return [f"disconnected {device.name}"]

    async def _cmd_release(self, args: list[str]) -> list[str]:
        index = self._index(args)
        device = self.devices[index]
        if not device.connected:
            return [f"[{index}] {device.name} is already down"]
        await device.disconnect()
        return [f"released [{index}] {device.name}; reconnect {index} retakes it"]

    async def _cmd_reconnect(self, args: list[str]) -> list[str]:
        index = self._index(args)
        device = self.devices[index]
        if not await device.connect():
            return [
                f"! could not reconnect [{index}] {device.name}",
                *self._info(device),
            ]
        return [f"[{index}] reconnected", *self._info(device)]

    async def _cmd_info(self, _args: list[str]) -> list[str]:
        return self._info(self._device())

    def _info(self, device: SolixBLEDevice) -> list[str]:
        """Return the class, link state, negotiation and announcement of a device."""
        session = device._session  # noqa: SLF001
        rows = [
            ("class", model_class(device).__name__),
            ("address", f"{device.address}  name {device.name}"),
            ("connected", f"{device.connected}  negotiated {device.negotiated}"),
        ]
        if session is not None:
            path = session.path.name if session.path is not None else "-"
            rows.append(("outer", f"{session.outer.name}  path {path}"))
        error = device._negotiation_error  # noqa: SLF001
        if error is not None:
            rows.append(("error", str(error)))
        announcement = device.announcement
        if announcement is not None:
            rows.extend(
                (name, _render(name, value))
                for name, value in announcement.items()
                if value is not None
            )
        width = max(len(label) for label, _ in rows)
        return [f"{label:<{width}} {value}" for label, value in rows]

    async def _cmd_data(self, args: list[str]) -> list[str]:
        data = self._device()._data  # noqa: SLF001
        if data is None:
            return ["(no telemetry yet)"]
        return data.to_str(verbose=args == ["verbose"]).splitlines()

    async def _cmd_props(self, _args: list[str]) -> list[str]:
        device = self._device()
        lines = []
        for name in sorted(dir(type(device))):
            if name.startswith("_") or not isinstance(
                getattr(type(device), name),
                property,
            ):
                continue
            try:
                value = getattr(device, name)
            except Exception as error:  # noqa: BLE001  # one failing property must not hide the rest
                value = f"<{type(error).__name__}: {error}>"
            lines.append(f"{name} = {value!r}")
        return lines

    async def _cmd_constants(self, _args: list[str]) -> list[str]:
        return [
            f"{name} = {value!r}" for name, value in constants(self._device()).items()
        ]

    async def _cmd_call(self, args: list[str]) -> list[str]:
        if not args:
            msg = "call <method> [args]"
            raise CommandError(msg)
        device = self._device()
        method = getattr(device, args[0], None) if not args[0].startswith("_") else None
        if not callable(method):
            msg = f"no public method {args[0]!r}"
            raise CommandError(msg)
        typed = parse_literal(args[1]) if len(args) > 1 else []
        arguments = typed if isinstance(typed, list) else [typed]
        mark = self.frames.total
        result = method(*coerce_arguments(method, arguments))
        if inspect.isawaitable(result):
            result = await result
        return [repr(result), *await self._replies(mark)]

    def _parameters(self, text: str) -> dict[str, dict[str, object]]:
        """Return the parameter dict typed, or the ``PARAMETERS_*`` constant named.

        :raises CommandError: If it is neither a dict nor a known constant.
        """
        known = constants(self._device()) if self.current is not None else {}
        if text.isidentifier() and text not in known:
            model = model_class(self._device()).__name__
            msg = f"{model} has no constant {text}; constants lists them"
            raise CommandError(msg)
        value = copy.deepcopy(known[text]) if text in known else parse_literal(text)
        if not isinstance(value, dict):
            msg = f"parameters must be a dict, not {type(value).__name__}"
            raise CommandError(msg)
        for item in value.values():
            if isinstance(item, dict) and item.get("value") == TIMESTAMP:
                item["value"] = lambda self: self._timestamp()
        return value

    def _kwargs(self, args: list[str]) -> dict[str, Any]:
        """Return the optional kwargs literal of a send command."""
        if not args:
            return {}
        value = parse_literal(args[0])
        if not isinstance(value, dict):
            msg = "kwargs must be a dict"
            raise CommandError(msg)
        return value

    async def _cmd_send(self, args: list[str]) -> list[str]:
        if len(args) < 2:  # noqa: PLR2004  # cmd and parameters
            msg = "send <cmd> <params> [kwargs]"
            raise CommandError(msg)
        device = self._device()
        mark = self.frames.total
        await device._send_command(  # noqa: SLF001
            args[0],
            self._parameters(args[1]),
            **self._kwargs(args[2:]),
        )
        return await self._replies(mark)

    async def _cmd_packet(self, args: list[str]) -> list[str]:
        if len(args) < 3:  # noqa: PLR2004  # pattern, cmd and parameters
            msg = "packet <pattern> <cmd> <params> [kwargs]"
            raise CommandError(msg)
        channel = PacketPattern.parse(bytes.fromhex(args[0])).channel
        if channel == FACTORY_CHANNEL and not self._allow_factory_channel:
            msg = "channel 0c (factory) is refused; start with --allow-factory-channel"
            raise CommandError(msg)
        return await self._send_raw(args[0], args[1], args[2], args[3:])

    async def _cmd_nego(self, args: list[str]) -> list[str]:
        if len(args) < 2:  # noqa: PLR2004  # cmd and parameters
            msg = "nego <cmd> <params> [kwargs]"
            raise CommandError(msg)
        return await self._send_raw(NEGOTIATION_PATTERN, args[0], args[1], args[2:])

    async def _send_raw(
        self,
        pattern: str,
        cmd: str,
        parameters: str,
        rest: list[str],
    ) -> list[str]:
        """Send a packet as typed and return the frames that follow it."""
        device = self._device()
        if not device.connected:
            index = self.devices.index(device)
            msg = f"[{index}] {device.name} is down; reconnect {index} retakes it"
            raise CommandError(msg)
        mark = self.frames.total
        await device._send_packet(  # noqa: SLF001
            pattern,
            cmd,
            self._parameters(parameters),
            **self._kwargs(rest),
        )
        return await self._replies(mark)

    async def _replies(self, mark: int) -> list[str]:
        """Wait for replies, then return the frames recorded since ``mark``."""
        await asyncio.sleep(self._reply_wait)
        return [frame_line(frame) for frame in self.frames.since(mark)]

    async def _cmd_frames(self, args: list[str]) -> list[str]:
        count = int(args[0]) if args else DEFAULT_FRAMES
        return [frame_line(frame) for frame in list(self.frames.frames)[-count:]]

    async def _cmd_capture(self, args: list[str]) -> list[str]:
        if not args:
            path = self.frames.capture_path
            return [f"capturing to {path}" if path is not None else "not capturing"]
        if args[0] == "off":
            self.frames.capture(None)
            return ["capture off"]
        await asyncio.to_thread(self.frames.capture_to, args[0])
        return [f"capturing to {self.frames.capture_path} (appending)", CAPTURE_NOTE]

    async def _cmd_token(self, args: list[str]) -> list[str]:
        if args:
            self.token = args[0]
            for device in self.devices:
                device._client_token = self.token  # noqa: SLF001
        return [f"token {self.token or '(the class UUID)'}"]

    async def _cmd_region(self, args: list[str]) -> list[str]:
        if args:
            set_region(args[0])
        return [f"region {region()}"]


class PythonConsole:
    """A Python prompt that runs each statement on the running event loop."""

    def __init__(self, namespace: dict[str, object]) -> None:
        """Start with an empty input buffer.

        :param namespace: The names the statements run with.
        """
        self.namespace = namespace
        self._buffer: list[str] = []
        self._compiler = codeop.CommandCompiler()
        self._compiler.compiler.flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT

    @property
    def prompt(self) -> str:
        """The prompt for the next line."""
        return "... " if self._buffer else ">>> "

    async def push(self, line: str) -> None:
        """Add a line; run the statement once it is complete.

        Expression results are printed, as in the standard interpreter;
        ``await`` works at the top level.

        :param line: One line of input.
        """
        self._buffer.append(line)
        source = "\n".join(self._buffer)
        try:
            code = self._compiler(source, "<console>", "single")
        except (OverflowError, SyntaxError, ValueError):
            self._buffer.clear()
            traceback.print_exc(limit=0)
            return
        if code is None:
            return
        self._buffer.clear()
        try:
            result = eval(code, self.namespace)  # noqa: S307  # running what the user types is the point
            if code.co_flags & inspect.CO_COROUTINE:
                await result
        except Exception:  # noqa: BLE001  # print it and keep the prompt
            traceback.print_exc()

    def reset(self) -> None:
        """Drop a partly typed statement."""
        self._buffer.clear()


class CommandCompleter(Completer):
    """Completes command names, scan entries, classes, methods and constants."""

    def __init__(self, console: Console) -> None:
        """Complete from the console's state.

        :param console: The console whose state is completed.
        """
        self._console = console

    @override
    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,  # noqa: ARG002  # the base's signature
    ) -> Iterator[Completion]:
        """Yield the completions for the word before the cursor."""
        words = document.text_before_cursor.split(" ")
        word = words[-1]
        for candidate in self._candidates(words[:-1]):
            if candidate.startswith(word):
                yield Completion(candidate, start_position=-len(word))

    def _candidates(self, previous: list[str]) -> Iterable[str]:
        """Return what may follow the words already typed."""
        if not previous:
            return (*Console.COMMANDS, "console")
        sources: dict[tuple[str, int], Callable[[], Iterable[str]]] = {
            ("connect", 1): self._scan_indices,
            ("connect", 2): lambda: sorted(device_classes()),
            ("use", 1): self._device_indices,
            ("disconnect", 1): self._device_indices,
            ("release", 1): self._device_indices,
            ("reconnect", 1): self._device_indices,
            ("call", 1): self._methods,
            ("send", 2): self._parameter_names,
            ("nego", 2): self._parameter_names,
            ("packet", 3): self._parameter_names,
        }
        source = sources.get((previous[0], len(previous)))
        return source() if source is not None else []

    def _scan_indices(self) -> list[str]:
        """Return the indices of the last scan."""
        return [str(index) for index in range(len(self._console.results))]

    def _device_indices(self) -> list[str]:
        """Return the indices of the open links."""
        return [str(index) for index in range(len(self._console.devices))]

    def _methods(self) -> list[str]:
        """Return the public methods of the current device."""
        device = self._console.current
        if device is None:
            return []
        return [
            name
            for name in dir(device)
            if not name.startswith("_") and callable(getattr(device, name))
        ]

    def _parameter_names(self) -> list[str]:
        """Return the ``PARAMETERS_*`` names of the current device's modules."""
        device = self._console.current
        if device is None:
            return []
        return [name for name in constants(device) if name.startswith("PARAMETERS_")]


class PythonCompleter(Completer):
    """Completes names and attributes from the Python console's namespace."""

    def __init__(self, namespace: dict[str, object]) -> None:
        """Complete from ``namespace``.

        :param namespace: The console's names.
        """
        self._completer = rlcompleter.Completer(namespace)

    @override
    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,  # noqa: ARG002  # the base's signature
    ) -> Iterator[Completion]:
        """Yield rlcompleter's matches for the expression before the cursor."""
        word = re.split(r"[\s()\[\]{},=+\-*/:]", document.text_before_cursor)[-1]
        if not word:
            return
        state = 0
        while (match := self._completer.complete(word, state)) is not None:
            yield Completion(match, start_position=-len(word))
            state += 1


async def python_prompt(console: Console, history: Path) -> None:
    """Run the Python console until ``exit()``, ``quit()`` or end of input.

    :param console: The console whose devices are in scope.
    :param history: The Python prompt's history file.
    """
    python = PythonConsole(console.namespace())
    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=PythonCompleter(python.namespace),
        complete_while_typing=False,
    )
    sys.stdout.write("Python on the console loop: console, devices, device, frames.\n")
    while True:
        try:
            line = await session.prompt_async(python.prompt)
        except KeyboardInterrupt:
            python.reset()
            continue
        except EOFError:
            return
        console.frames.note(f"{python.prompt}{line}")
        if python.prompt == ">>> " and line.strip() in ("exit()", "quit()"):
            return
        await python.push(line)


def configure_logging(log_level: str, bleak_log_level: str) -> None:
    """Set the library's log level and, apart from it, the BLE stack's.

    :param log_level: Level of SolixBLE's records.
    :param bleak_log_level: Level of bleak's and bleak-retry-connector's records.
    """
    logging.getLogger("SolixBLE").setLevel(log_level.upper())
    for name in BLEAK_LOGGERS:
        logging.getLogger(name).setLevel(bleak_log_level.upper())


async def interactive(
    console: Console,
    history: Path,
    log_level: str,
    bleak_log_level: str,
) -> None:
    """Run the command prompt until ``quit`` or end of input.

    Packages other than the library and the BLE stack log warnings and up.

    :param console: The console to drive.
    :param history: The command history file.
    :param log_level: Level of SolixBLE's records.
    :param bleak_log_level: Level of bleak's and bleak-retry-connector's records.
    """
    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=CommandCompleter(console),
        complete_while_typing=True,
    )
    with patch_stdout():
        logging.basicConfig(level=logging.WARNING)
        configure_logging(log_level, bleak_log_level)
        logging.getLogger().addHandler(CaptureHandler(console.frames))
        sys.stdout.write("solixble: help lists the commands.\n")
        try:
            while not console.finished:
                try:
                    line = await session.prompt_async(PROMPT)
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break
                if line.strip() == "console":
                    await python_prompt(console, Path(f"{history}.console"))
                    continue
                for output in await console.run_line(line):
                    sys.stdout.write(output + "\n")
        finally:
            await console.close()


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and run the console.

    :param argv: Arguments, without the program name.
    """
    parser = argparse.ArgumentParser(
        prog="solixble",
        description="Interactive console for Anker BLE devices",
    )
    parser.add_argument("--capture", type=Path, help="append the session to this file")
    parser.add_argument("--token", help="client token sent as the 4027 / 420a owner")
    parser.add_argument("--region", help="two-letter region for Prime devices")
    parser.add_argument(
        "--allow-factory-channel",
        action="store_true",
        help="let packet send on channel 0c (the factory lane)",
    )
    parser.add_argument(
        "--reply-wait",
        type=float,
        default=2.0,
        help="seconds to show frames after a send",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path.home() / ".solixble_history",
    )
    parser.add_argument("--log-level", default="warning", help="SolixBLE's log level")
    parser.add_argument(
        "--bleak-log-level",
        default="warning",
        help="bleak's and bleak-retry-connector's log level",
    )
    args = parser.parse_args(argv)
    if args.region:
        set_region(args.region)
    frames = FrameLog()
    if args.capture:
        frames.capture(args.capture)
        sys.stdout.write(f"capturing to {args.capture} (appending)\n{CAPTURE_NOTE}\n")
    console = Console(
        frames,
        allow_factory_channel=args.allow_factory_channel,
        token=args.token,
        reply_wait=args.reply_wait,
    )
    asyncio.run(
        interactive(console, args.history, args.log_level, args.bleak_log_level),
    )
