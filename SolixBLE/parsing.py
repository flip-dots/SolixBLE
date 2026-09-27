"""Walkers for nested self-delimiting telemetry payloads.

.. moduleauthor:: kb1ibt

Most telemetry fields are flat, fixed-layout TLV that
:meth:`SolixBLE.device.SolixBLEDevice._parse_payload` decodes directly. A few fields
instead carry a *nested* self-delimiting structure that fixed offsets cannot decode,
in one of two encodings (distinguished by the value's leading type byte):

* **protobuf** (type byte ``0x07``) -- e.g. the C2000 G2's ``c490`` device summary.
  Walked by :func:`walk_protobuf`.
* **length-value** (a ``<length><value>`` sequence, type byte ``0x04`` binary) -- e.g.
  the ``ce`` combination-battery block in the C2000 G2's ``c421`` telemetry. Walked by
  :func:`walk_lv`.

Both encodings self-delimit, so a value that grows past a byte boundary never shifts
the fields after it -- the whole point over a brittle fixed-offset map.
"""

from __future__ import annotations

from dataclasses import dataclass


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Read one LEB128 varint from ``buf`` at ``pos``.

    :param buf: Buffer to read from.
    :param pos: Index to start reading at.
    :returns: ``(value, next_pos)``.
    """
    result = shift = 0
    while True:
        byte = buf[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if not byte & 0x80:
            return result, pos
        shift += 7


#: Protobuf wire types.
_WIRE_VARINT = 0
_WIRE_FIXED64 = 1
_WIRE_LENGTH_DELIMITED = 2
_WIRE_FIXED32 = 5


def _is_protobuf_message(sub: bytes) -> bool:
    """Return whether ``sub`` parses cleanly as a protobuf message.

    :param sub: The candidate sub-message bytes.
    :returns: True if every field parses and the bytes are consumed exactly.
    """
    pos = 0
    try:
        while pos < len(sub):
            tag, pos = read_varint(sub, pos)
            wire = tag & 7
            if wire == _WIRE_VARINT:
                _, pos = read_varint(sub, pos)
            elif wire == _WIRE_LENGTH_DELIMITED:
                length, pos = read_varint(sub, pos)
                pos += length
            elif wire == _WIRE_FIXED32:
                pos += 4
            elif wire == _WIRE_FIXED64:
                pos += 8
            else:
                return False
        return pos == len(sub)
    except (IndexError, ValueError):
        return False


@dataclass(frozen=True)
class SummaryField:
    """How one walker ``.path`` of a device-summary post is named and scaled.

    :param name: The field name the value is published under.
    :param factor: Multiplier applied to an integer value.
    :param array: ``"u16le"`` when the field is a packed array of little-endian
        16-bit integers rather than a sub-message; None otherwise.
    """

    name: str
    factor: float = 1.0
    array: str | None = None


def _decode_array(sub: bytes, kind: str) -> list[int]:
    """Decode a packed array field.

    :param sub: The field's bytes.
    :param kind: The array kind, currently only ``"u16le"``.
    :returns: The decoded integers.
    :raises ValueError: If the kind is unknown.
    """
    if kind == "u16le":
        return [
            int.from_bytes(sub[i : i + 2], "little") for i in range(0, len(sub) - 1, 2)
        ]
    msg = f"Unknown array kind '{kind}'"
    raise ValueError(msg)


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
) -> dict[str, object]:
    """Flatten a protobuf(-like) blob to a ``.field.subfield`` -> value map.

    Repeated tags keep wire order (occurrence index appended as ``#n``) and every field
    is addressed by its ``.path``, so byte offsets never matter -- a leaf value crossing
    a varint byte boundary grows in place without shifting anything after it.
    Length-delimited fields that themselves parse cleanly as a sub-message are recorded
    as their byte length **and** recursed into (so the container and its leaves both
    appear); otherwise they are kept as an ASCII string (if fully printable) or hex. A
    wire-type 3/4 group marker is recorded as ``None`` and stops the walk. Every field
    is recorded -- silently dropping containers under-counts the message, which is a
    wrong decode.

    A packed array of integers can look like a sub-message, so paths known to be
    arrays are declared in ``arrays`` and decoded as such instead of recursed into.

    :param buf: The (decrypted, reassembled) protobuf payload.
    :param prefix: Path prefix used during recursion.
    :param out: Accumulator dict used during recursion.
    :param arrays: ``.path`` -> array kind for fields that are packed arrays.
    :returns: Mapping of ``.path`` to value (int, list, str, hex str or None).
    """
    if out is None:
        out = {}
    pos = 0
    seen: dict[int, int] = {}
    while pos < len(buf):
        try:
            tag, pos = read_varint(buf, pos)
        except IndexError:
            break
        fnum, wire = tag >> 3, tag & 7
        occ = seen.get(fnum, 0)
        seen[fnum] = occ + 1
        path = f"{prefix}.{fnum}" + (f"#{occ}" if occ else "")
        if wire == _WIRE_VARINT:
            out[path], pos = read_varint(buf, pos)
        elif wire == _WIRE_LENGTH_DELIMITED:
            length, pos = read_varint(buf, pos)
            sub = buf[pos : pos + length]
            pos += length
            if arrays and path in arrays:
                out[path] = _decode_array(sub, arrays[path])
            elif length and _is_protobuf_message(sub) and any(sub):
                out[path] = length  # container: record its length, then its fields
                walk_protobuf(sub, path, out, arrays)
            elif sub and all(32 <= b < 127 for b in sub):
                out[path] = sub.decode("ascii")
            else:
                out[path] = sub.hex()
        elif wire == _WIRE_FIXED32:
            out[path] = int.from_bytes(buf[pos : pos + 4], "little")
            pos += 4
        elif wire == _WIRE_FIXED64:
            out[path] = int.from_bytes(buf[pos : pos + 8], "little")
            pos += 8
        else:
            out[path] = None  # group marker (wire type 3/4): record and stop
            break
    return out


def walk_lv(buf: bytes) -> list[bytes]:
    """Walk a length-value blob into its fields.

    Each field is a single length byte followed by that many value bytes, repeated to
    the end of ``buf``. Used for nested ``bin`` fields such as the C2000 G2's ``ce``
    combination-battery block, whose first field is a fixed 16-byte device ID (all-zero
    when no unit is combined). Trailing zero padding therefore appears as trailing
    zero-length fields. Pass the value **without** its leading type byte.

    :param buf: The field value, with its ``0x04`` type byte already stripped.
    :returns: The fields in wire order.
    """
    fields: list[bytes] = []
    pos = 0
    while pos < len(buf):
        length = buf[pos]
        pos += 1
        fields.append(buf[pos : pos + length])
        pos += length
    return fields
