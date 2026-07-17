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


def _is_protobuf_message(sub: bytes) -> bool:
    """True if ``sub`` parses cleanly as a protobuf message (so it is recursed into)."""
    pos = 0
    try:
        while pos < len(sub):
            tag, pos = read_varint(sub, pos)
            wire = tag & 7
            if wire == 0:
                _, pos = read_varint(sub, pos)
            elif wire == 2:
                length, pos = read_varint(sub, pos)
                pos += length
            elif wire == 5:
                pos += 4
            elif wire == 1:
                pos += 8
            else:
                return False
        return pos == len(sub)
    except (IndexError, ValueError):
        return False


def walk_protobuf(
    buf: bytes, prefix: str = "", out: dict[str, object] | None = None
) -> dict[str, object]:
    """Flatten a protobuf(-like) blob to a ``.field.subfield`` -> value map.

    Repeated tags keep wire order (occurrence index appended as ``#n``) and every field
    is addressed by its ``.path``, so byte offsets never matter -- a leaf value crossing
    a varint byte boundary grows in place without shifting anything after it.
    Length-delimited fields that themselves parse cleanly as a sub-message are recursed
    into; otherwise they are kept as an ASCII string (if fully printable) or hex.

    :param buf: The (decrypted, reassembled) protobuf payload.
    :param prefix: Path prefix used during recursion.
    :param out: Accumulator dict used during recursion.
    :returns: Mapping of ``.path`` to value (int, str or hex str).
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
        if wire == 0:
            out[path], pos = read_varint(buf, pos)
        elif wire == 2:
            length, pos = read_varint(buf, pos)
            sub = buf[pos : pos + length]
            pos += length
            if length and _is_protobuf_message(sub) and any(sub):
                walk_protobuf(sub, path, out)
            elif sub and all(32 <= b < 127 for b in sub):
                out[path] = sub.decode("ascii")
            else:
                out[path] = sub.hex()
        elif wire == 5:
            out[path] = int.from_bytes(buf[pos : pos + 4], "little")
            pos += 4
        elif wire == 1:
            out[path] = int.from_bytes(buf[pos : pos + 8], "little")
            pos += 8
        else:
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
