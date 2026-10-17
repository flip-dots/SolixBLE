"""Walker for the protobuf device-summary some devices post.

.. moduleauthor:: kb1ibt

Most telemetry is flat TLV that :data:`SolixBLE.constructs.Parameters`
decodes directly. A device summary (e.g the C2000 Gen 2's ``c490``) instead
carries a protobuf message, whose fields are addressed by number rather than
offset, so :func:`walk_protobuf` flattens it to ``.field.subfield`` paths.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    ConstructError,
    GreedyBytes,
    GreedyRange,
    Int8ul,
    Int16ul,
    Int32ul,
    Int64ul,
    Prefixed,
    VarInt,
    ZigZag,
)

#: Protobuf wire types.
WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LENGTH_DELIMITED = 2
WIRE_FIXED32 = 5

#: A length-delimited value: a varint length, then that many bytes.
LENGTH_DELIMITED = Prefixed(VarInt, GreedyBytes)

#: Packed array kinds a field map can declare, by name.
ARRAYS = {
    "u8": GreedyRange(Int8ul),
    "u16le": GreedyRange(Int16ul),
}

#: Byte range of printable ASCII, kept as text when walking.
PRINTABLE_FIRST = 0x20
PRINTABLE_END = 0x7F


@dataclass(frozen=True)
class SummaryField:
    """How one walker ``.path`` of a device-summary post is named and scaled.

    :param name: The field name the value is published under.
    :param factor: Multiplier applied to an integer value.
    :param array: The packed array kind (a key of :data:`ARRAYS`), or None.
    :param signed: Whether the varint is zigzag-encoded (a protobuf ``sint``).
    """

    name: str
    factor: float = 1.0
    array: str | None = None
    signed: bool = False


def _is_protobuf_message(sub: bytes) -> bool:
    """Return whether ``sub`` parses cleanly, end to end, as a protobuf message.

    :param sub: The candidate sub-message bytes.
    :returns: True if every field parses and the bytes are consumed exactly.
    """
    stream = io.BytesIO(sub)
    try:
        while stream.tell() < len(sub):
            wire = VarInt.parse_stream(stream) & 7
            if wire == WIRE_VARINT:
                VarInt.parse_stream(stream)
            elif wire == WIRE_LENGTH_DELIMITED:
                LENGTH_DELIMITED.parse_stream(stream)
            elif wire == WIRE_FIXED32:
                Int32ul.parse_stream(stream)
            elif wire == WIRE_FIXED64:
                Int64ul.parse_stream(stream)
            else:
                return False
    except ConstructError:
        return False
    return stream.tell() == len(sub)


def name_summary(
    raw: dict[str, object],
    fields: dict[str, SummaryField] | None,
) -> dict[str, object]:
    """Rename and scale a walked summary using a schema's field map.

    Mapped paths appear under their field name with the factor applied to
    integer values; unmapped paths are kept under their ``.path``.

    :param raw: The walker output.
    :param fields: The field map for the frame's schema, or None if unknown.
    :returns: The named summary.
    """
    if not fields:
        return dict(raw)
    named: dict[str, object] = {}
    for path, value in raw.items():
        field = fields.get(path)
        if field is None:
            named[path] = value
        elif isinstance(value, int) and field.factor != 1.0:
            named[field.name] = round(value * field.factor, 6)
        else:
            named[field.name] = value
    return named


def walk_protobuf(
    buf: bytes,
    prefix: str = "",
    out: dict[str, object] | None = None,
    arrays: dict[str, str] | None = None,
    signed: set[str] | None = None,
) -> dict[str, object]:
    """Flatten a protobuf message to a ``.field.subfield`` -> value map.

    .. note::
       :collapsible: closed

       Repeated tags keep wire order, with the occurrence index appended as
       ``#n``, and every field is addressed by its ``.path``, so a value that
       grows past a byte boundary never shifts the fields after it. A
       length-delimited field that parses cleanly as a sub-message is
       recorded as its byte length and walked into; otherwise it is kept as
       text (if fully printable) or hex. A field of an unknown wire type is
       recorded as None and ends the walk.

       A packed array of integers can look like a sub-message, so paths known
       to be arrays are declared in ``arrays`` and decoded as such, and paths
       known to be zigzag-encoded are declared in ``signed``.

    :param buf: The protobuf payload.
    :param prefix: Path prefix used during recursion.
    :param out: Accumulator used during recursion.
    :param arrays: ``.path`` -> array kind (a key of :data:`ARRAYS`).
    :param signed: ``.path`` values whose varint is zigzag-encoded.
    :returns: Mapping of ``.path`` to value (int, list, str, hex str or None).
    """
    if out is None:
        out = {}
    stream = io.BytesIO(buf)
    seen: dict[int, int] = {}
    while stream.tell() < len(buf):
        try:
            key = VarInt.parse_stream(stream)
        except ConstructError:
            break
        number, wire = key >> 3, key & 7
        occurrence = seen.get(number, 0)
        seen[number] = occurrence + 1
        path = f"{prefix}.{number}" + (f"#{occurrence}" if occurrence else "")
        try:
            if wire == WIRE_VARINT:
                varint = ZigZag if signed and path in signed else VarInt
                out[path] = varint.parse_stream(stream)
            elif wire == WIRE_LENGTH_DELIMITED:
                sub = LENGTH_DELIMITED.parse_stream(stream)
                _walk_length_delimited(sub, path, out, arrays, signed)
            elif wire == WIRE_FIXED32:
                out[path] = Int32ul.parse_stream(stream)
            elif wire == WIRE_FIXED64:
                out[path] = Int64ul.parse_stream(stream)
            else:
                out[path] = None
                break
        except ConstructError:
            break
    return out


def _walk_length_delimited(
    sub: bytes,
    path: str,
    out: dict[str, object],
    arrays: dict[str, str] | None,
    signed: set[str] | None,
) -> None:
    """Record one length-delimited field: an array, a sub-message, text or hex.

    :param sub: The field's bytes.
    :param path: The field's ``.path``.
    :param out: Accumulator of the walk.
    :param arrays: ``.path`` -> array kind for fields that are packed arrays.
    :param signed: ``.path`` values whose varint is zigzag-encoded.
    """
    if arrays and path in arrays:
        out[path] = list(ARRAYS[arrays[path]].parse(sub))
    elif sub and any(sub) and _is_protobuf_message(sub):
        out[path] = len(sub)
        walk_protobuf(sub, path, out, arrays, signed)
    elif sub and all(PRINTABLE_FIRST <= b < PRINTABLE_END for b in sub):
        out[path] = sub.decode("ascii")
    else:
        out[path] = sub.hex()
