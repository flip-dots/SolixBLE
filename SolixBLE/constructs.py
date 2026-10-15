"""Data structures of packets.

This module contains the byte structures used for encoding and
decoding the packet format used by Anker devices.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import json
import operator
from functools import reduce
from typing import Any, Self

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    BitsInteger,
    BitStruct,
    Bytes,
    Checksum,
    Const,
    Container,
    ExprAdapter,
    ExprValidator,
    Flag,
    FlagsEnum,
    GreedyBytes,
    GreedyRange,
    Hex,
    HexDump,
    If,
    Int8ub,
    Int8ul,
    Int16ul,
    Int32ul,
    Nibble,
    Optional,
    Padding,
    RawCopy,
    Rebuild,
    Struct,
    this,
)

from SolixBLE.utilities import _to_bytes


def _get_val(obj: Any, key: str, default: Any=None) -> Any:
    """
    Return value from dictionary, container, objects, or None.

    :param obj: Object to extract value from.
    :param key: The key or property to extract from the object.
    :param default: Default to return if not found.
    :returns: Found value or default.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

Packet = ExprAdapter(

    # Structure of the packet
    Struct(

        # Bytes of packet excluding checksum
        "content" / RawCopy(
            Struct(

                # Header of the packet
                "header" / Hex(Const(bytes.fromhex("ff09"))),

                # Length of the entire packet
                "length" / Rebuild(Int16ul, lambda this: 10 + len(this.payload_bytes)),

                # Pattern of the packet (e.g negotiation type, telemetry type etc)
                "pattern" / Hex(Bytes(3)),

                # Command of the packet (e.g turn on, off, etc)
                "cmd" / Hex(Bytes(2)),

                # Payload bytes of the packet (may be encrypted or fragmented)
                "payload_bytes" / HexDump(Bytes(lambda this: this.length - 10)),
            ),
        ),

        # XOR checksum of the packet
        "checksum" / Hex(Checksum(
            Int8ul,
            lambda data: reduce(operator.xor, data, 0),
            this.content.data,
        )),
    ),

    # Encoders and decoders which allow for direct access
    # (e.g packet.cmd rather than packet.content.cmd)
    decoder=lambda p, _: p.content.value,
    encoder=lambda p, _: {
            "content": {
                "value": {
                    "header": _to_bytes(_get_val(p, "header", "ff09")),
                    "pattern": _to_bytes(_get_val(p, "pattern")),
                    "cmd": _to_bytes(_get_val(p, "cmd")),
                    "payload_bytes": _to_bytes(_get_val(p, "payload_bytes", b"")),
                },
            },
    },
)
"""
Anker device packet.

This class represents a packet of an Anker device. Packets are made up of a
header, size, pattern, cmd, payload, and a checksum.

Structure: <Header 2B> <Size 2B> <Pattern 3B> <CMD 2B> <Payload nB> <Checksum 1B>.

Usage:
    .. code-block:: python
       :linenos:

        packet = Packet.parse(packet_bytes)
        print(f"p: {packet.pattern}, c: {packet.cmd}, b: {packet.payload_bytes}")

        packet_bytes = Packet.build({
            "pattern": "030001",
            "cmd": "0000",
            "payload_bytes": "a101a20200a303010000",
        })

"""

#: Dispatch channel of negotiation requests, replies and the grant.
CHANNEL_NEGOTIATION = 0x01

#: Dispatch channel of session commands, replies and pushes.
CHANNEL_SESSION = 0x0F

#: Dispatch channel of app session pushes.
CHANNEL_APP = 0x11

#: Composer of a reply that echoes the request's pattern.
COMPOSER_REPLY = 0x00

#: Composer of a frame the device sends on its own.
COMPOSER_SEND = 0x01

PacketPattern = Struct(
    "family" / Int8ub,
    "composer" / Int8ub,
    "channel" / Int8ub,
)
"""
Pattern of an Anker packet: ``03 <composer> <channel>``.

The channel is the module's dispatch key (``0x01`` negotiation, ``0x0f`` /
``0x11`` session); the composer is ``01`` on frames the module sends on its
own and ``00`` on replies that echo the request.

Usage:
    .. code-block:: python
       :linenos:

        pattern = PacketPattern.parse(packet.pattern)
        print(f"composer: {pattern.composer}, channel: {pattern.channel}")

"""

PacketCommand = ExprAdapter(
    BitStruct(
        "fragmented" / Flag,
        "encrypted" / Flag,
        "reserved" / BitsInteger(2),
        "msgtype" / BitsInteger(12),
    ),
    decoder=lambda obj, _: Container(
        fragmented=obj.fragmented,
        encrypted=obj.encrypted,
        msgtype=obj.msgtype,
        response=bool(obj.msgtype & 0x800),
    ),
    encoder=lambda obj, _: {"reserved": 0, **obj},
)
"""
Command of an Anker packet: link flags in the high nibble, a 12-bit message type.

``0x80`` marks a fragment (the payload's first byte is index << 4 | total) and
``0x40`` an encrypted/authorized link; a response is the request's message
type with ``0x800`` set.

Usage:
    .. code-block:: python
       :linenos:

        command = PacketCommand.parse(packet.cmd)
        print(f"msgtype: {command.msgtype:03x}, encrypted: {command.encrypted}")

        cmd_bytes = PacketCommand.build({
            "fragmented": False,
            "encrypted": True,
            "msgtype": 0x005,
        })

"""

FragmentedPayload = Struct(

    # Fragment information
    "frag" / BitStruct(
        "index" / Nibble,
        "total" / Nibble,
    ),

    # The content of the payload
    "data" / GreedyBytes,
)
"""
Payload section of an Anker packet that is fragmented.

The "frag" section represents the fragmentation information of the payload.
This information is not always present in non-fragmented packets.

The "data" section represents the content of the fragment and may be encrypted.
The fragments must be re-assembled before decryption can begin.

This structure is used for re-assembling fragmented payloads only.

Structure: <Index 4b> <Total 4b> <Data nB>.

Usage:

    .. code-block:: python
       :linenos:

        frag_payload = FragmentedPayload.parse(payload_bytes)
        print(f"{frag_p.frag.index}/{frag_p.frag.total}: {frag_p.data}")

"""


class ParameterContainer(Container):
    """Subclass to allow for direct action on the parameter type."""

    @property
    def value_legacy(self) -> bytes:
        """Return the type byte prepended to the value bytes for non-typed values."""
        type_byte = self.type.to_bytes(1) if self.get("type") is not None else b""
        val_bytes = self.get("value") or b""
        return type_byte + val_bytes

    def to_dict(self, types: bool | None = None) -> dict[str, str | int]:  # noqa: FBT001
        """Return possible representations of the parameter in dict form.

        :param: Parameter to be interpreted.
        :types: Display parameter with type information (T=y, F=n, N=both).
        :returns: Dictionary of encodings to decoded values.
        """
        representation: dict[str, str | int] = {}

        # Representation where no type info is encoded
        p_bytes = self.value_legacy

        # Representation where first byte encodes type information
        p_bytes_t = bytes(self.value)

        if types is not True:
            representation.update({
                "bytes": str(p_bytes),
                "hex": p_bytes.hex(),
                "int": int.from_bytes(p_bytes, byteorder="little", signed=True),
                "uint": int.from_bytes(p_bytes, byteorder="little", signed=False),
                "length": len(p_bytes),
            })

        if types is not False:
            representation.update({
                "type (t)": self.type,
                "bytes (t)": str(p_bytes_t),
                "hex (t)": p_bytes_t.hex(),
                "int (t)": int.from_bytes(p_bytes_t, byteorder="little", signed=True),
                "uint (t)": int.from_bytes(p_bytes_t, byteorder="little", signed=False),
                "length (t)": len(p_bytes_t),
             })

        return representation


Parameter = ExprAdapter(
    Struct(

        # The key of the parameter (e.g a1, a2, ...)
        "key" / Hex(Bytes(1)),

        # The length of the parameter excluding the key
        "length" / Rebuild(
            Int8ul,
            lambda p: (1 if p.get("type") is not None else 0) + len(p.get("value") or b""),
        ),

        # Optional type of the parameter
        "type" / If(
            lambda p: p.get("type") is not None if p._building else p.length > 1,
            Int8ul,
        ),

        # Optional content of the parameter
        "value" / If(
            lambda p: (p.length - (1 if p.type is not None else 0)) > 0,
            HexDump(Bytes(lambda p: p.length - (1 if p.type is not None else 0))),
        ),
    ),
    decoder=lambda obj, _: ParameterContainer(obj),
    encoder=lambda obj, _: obj,
)
"""
Individual parameter of a payload of an Anker packet.

Paramaters contain a key (e.g a1, a2, ...), the length, optional
type information, and an optional content.

Structure: <Key 1B> <Length 1B> <Type 1B> <Content nB>.

The length value is the length of the entire parameter excluding the key.

This structure is only used as a part of the Parameters type for creating,
modifying, encoding, and decoding payloads.
"""


class ParameterDict(dict[str, ParameterContainer]):
    """Subclass to allow for direct action on the paramaters type."""

    def __init__(
        self,
        *args: Any,
        prefix: bytes | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialise with the usual dict arguments, plus the reply's status prefix."""
        super().__init__(*args, **kwargs)
        self.prefix = prefix

    @property
    def status(self) -> int | None:
        """Status byte of a reply, or None for a push."""
        return self.prefix[0] if self.prefix else None

    def diff(self, old: Self, types: bool | None = None) -> str:  # noqa: FBT001
        """
        Return changes from previous parameters to this in string representation.

        :param old: Previous entry to compare against.
        :param types: Display parameter with type information (T=y, F=n, N=both).
        """
        differences: dict[str, dict[str, str | int]] = {}

        changed = {k for k in old.keys() & self.keys() if old[k] != self[k]}
        added = self.keys() - old.keys()
        removed = old.keys() - self.keys()

        for k in sorted(changed | added | removed):

            # Parameter modified
            if k in changed:
                old_p = old[k].to_dict(types=types)
                new_p = self[k].to_dict(types=types)

                differences[k] = {
                    "state": "~",
                    **{f: f"{old_p[f]} -> {new_p[f]}" for f in old_p},
                }

            # Parameter added
            elif k in added:
                differences[k] = {
                    "state": "+",
                    **self[k].to_dict(types=types),
                }

            # Parameter removed
            elif k in removed:
                differences[k] = {
                    "state": "-",
                    **old[k].to_dict(types=types),
                }

        return json.dumps(differences, indent=4)

    def to_str(self, verbose: bool = False, types: bool | None = None) -> str:
        """
        Return string representation of potential parameter encodings.

        :param verbose: Return possible representations instead of plain bytes.
        :param types: Display parameter with type information (T=y, F=n, N=both).
        :returns: String representation of parameters.
        """
        if verbose:
            return json.dumps({k: p.to_dict(types) for k, p in self.items()}, indent=4)
        return str({k: v.value_legacy.hex() for k, v in self.items()})

    def __str__(self) -> str:
        """Return string representation of potential parameter encodings."""
        return self.to_str()

STATUS_LIMIT = 0xA1
"""TLV tags start at ``0xa1``; a lower first byte is a reply's status."""

Parameters = ExprAdapter(
    Struct(

        # Optional status byte (replies only)
        "prefix" / If(
            lambda this: this._parsing or this.prefix is not None,
            Optional(ExprValidator(Bytes(1), lambda obj, _: obj[0] < STATUS_LIMIT)),
        ),

        # List of parameters
        "parameters" / GreedyRange(Parameter),
    ),
    decoder=lambda obj, _: ParameterDict(
        {p.key.hex(): p for p in obj.parameters},
        prefix=obj.prefix,
    ),
    encoder=lambda ps, _: {
        "prefix": getattr(ps, "prefix", None),
        "parameters": list(ps.values()) if isinstance(ps, dict) else ps,
    },
)
"""
Decoded parameters of the payload of an Anker packet.

The payload of Anker packets is made up of a list of
parameters. The payload of a reply starts with a status byte;
pushes have none.

Structure: <Prefix 1B> <Parameter 1 nB> ... <Parameter n nB>.

This structure is used to encode, decode, modify, and generate payloads.

Usage:

    .. code-block:: python
       :linenos:

        parameters = Parameters.parse(reassembled_payload)
        parameters["a1"] = Parameter({
            "key": "a1",
            "type": 12,
            "value": "00ff",
        })

        plaintext_payload = Parameters.build(parameters)

"""

WeekdayMask = ExprAdapter(
    Int8ub,
    decoder=lambda obj, _: frozenset(bit for bit in range(7) if obj & (1 << bit)),
    encoder=lambda obj, _: sum(1 << bit for bit in obj),
)
"""
A device's weekday bitmask: bit 0 Monday through bit 6 Sunday, matching
Python's own :py:meth:`date.weekday` convention. Bit 7 is unused.

Usage:
    .. code-block:: python
       :linenos:

        days = WeekdayMask.parse(b"\\x24")  # frozenset({2, 5}), Wed and Sat
        mask = WeekdayMask.build(frozenset(range(7)))  # b"\\x7f", every day

"""

DecimalVersion = ExprAdapter(
    Int16ul,
    decoder=lambda obj, _: (
        f"{obj // 1000}.{obj // 100 % 10}.{obj // 10 % 10}.{obj % 10}"
    ),
    encoder=lambda obj, _: int(obj.replace(".", "")),
)
"""
A firmware version packed as a 16-bit integer whose last three decimal digits
are the version's last three parts and whose thousands are the first, always
four parts (``297`` is ``0.2.9.7``). Shared by the A2345 and the A91B2
snapshot's version tag.

Usage:
    .. code-block:: python
       :linenos:

        version = DecimalVersion.parse(b"\\x44\\x08")  # "2.1.1.6" (2116)

"""

PORT_FAULTS = FlagsEnum(
    Int16ul,
    over_temperature=0x01,
    usb_c1=0x02,
    usb_c2=0x04,
    usb_c3=0x08,
    usb_c4=0x10,
    usb_a_undervoltage=0x20,
)
"""
A Prime device's port fault bitmap, confirmed identical on the A2345 and
the A91B2: bit 0 an over-temperature guard, bits 1-4 USB-C 1-4, bit 5 the
USB-A rail. Devices without a given port simply never see its bit set.

Usage:
    .. code-block:: python
       :linenos:

        faults = PORT_FAULTS.parse(a3_value)
        if faults.over_temperature:
            ...

"""

FIRMWARE_UPDATE = Struct(
    "updating" / Flag,
    "progress" / Int8ub,
)
"""
A Prime device's firmware update state: set while an update is armed, which
holds back the ``4303`` stream, then the update's progress in percent. The
A2345 snapshot carries it at ``b2``, the A91B2 snapshot at ``af``.
"""

SCHEDULE_TRIGGER = Struct(
    "enabled" / Int8ub,
    "hour" / Int8ub,
    "minute" / Int8ub,
    "weekdays" / WeekdayMask,
)
"""
One half (on-time or off-time) of a Prime port's daily schedule.

``enabled`` is ``0``/``1``, or ``0xff`` when this half has never been set -
the hour and minute then hold a stale default (``12:00``), so gate on
``enabled`` rather than the time.
"""

#: :data:`SCHEDULE_TRIGGER`'s ``enabled`` byte for a half never set.
SCHEDULE_UNSET = 0xFF

DISPLAY = BitStruct(
    "on" / Flag,
    Padding(1),
    "theme" / BitsInteger(6),
)
"""
A Prime device's display byte (A2345 snapshot ``af[0]``, A91B2 ``ac``): the
clock display's on/off state in bit 7 and its theme index, from 0, in bits
0-5. The bit between is the A2345's holiday mode.
"""

TIMER_SETTING = Struct(
    "enabled" / Int8ub,
    "seconds" / Int32ul,
    "remaining" / Int32ul,
)
"""
A Prime port's countdown timer: whether it is armed, the duration set, and
the seconds remaining. A disarmed (``enabled`` ``0``) timer keeps whatever
``seconds``/``remaining`` it last held.
"""

TIMER_COMMAND = Struct(
    "enabled" / Int8ub,
    "seconds" / Int32ul,
)
"""
The countdown a ``4209`` sets: whether it is armed, then its seconds. A
duration of 0 disarms it.
"""

PORT_RECORD = Struct(
    "switch" / Flag,
    "on_time" / SCHEDULE_TRIGGER,
    "off_time" / SCHEDULE_TRIGGER,
    "timer" / TIMER_SETTING,
    "priority" / Optional(Int8ub),
)
"""
A Prime device's per-port snapshot record: on/off switch, the daily
on-time/off-time schedule, the countdown timer, and - on ports that support
the Port Priority charging mode - a trailing priority byte
(:class:`~SolixBLE.states.PortPriority`). 18 bytes without it (the A91B2's
AC and USB-C ports), 19 with it (the A2345's USB-C ports); ``priority``
parses as ``None`` when the record ends before that byte.

Usage:
    .. code-block:: python
       :linenos:

        record = PORT_RECORD.parse(record_bytes)
        if record.on_time.enabled == 1:
            print(f"Turns on at {record.on_time.hour}:{record.on_time.minute:02}")

"""

PORT_READING = Struct(
    "status" / Int8ub,
    "voltage" / Int16ul,
    "current" / Int16ul,
    "power" / Int16ul,
)
"""
A Prime device's per-port realtime reading (the ``4303`` stream): status,
then voltage (mV), current (mA) and power (centiwatts). Shared by the USB-C
and USB-A ports on both the A2345 and the A91B2.
"""
