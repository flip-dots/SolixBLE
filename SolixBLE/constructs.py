"""Data structures of packets.

This module contains the byte structures used for encoding and
decoding the packet format used by Anker devices.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import json
import operator
from functools import reduce
from typing import Any, Self

from construct import (
    BitStruct,
    Bytes,
    Checksum,
    Const,
    Container,
    ExprAdapter,
    GreedyBytes,
    GreedyRange,
    Hex,
    HexDump,
    If,
    Int8ul,
    Int16ul,
    Nibble,
    Optional,
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

    def to_dict(self, types: bool | None = None) -> dict[str, str]:  # noqa: FBT001
        """Return possible representations of the parameter in dict form.

        :param: Parameter to be interpreted.
        :types: Display parameter with type information (T=y, F=n, N=both).
        :returns: Dictionary of encodings to decoded values.
        """
        representation: dict[str, str] = {}

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


class ParameterDict(dict):
    """Subclass to allow for direct action on the paramaters type."""

    def __init__(self, *args, prefix: bytes | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefix = prefix

    def diff(self, old: Self, types: bool | None = None) -> str:  # noqa: FBT001
        """
        Return changes from previous parameters to this in string representation.

        :param old: Previous entry to compare against.
        :param types: Display parameter with type information (T=y, F=n, N=both).
        """
        differences: dict[str, str] = {}

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

Parameters = ExprAdapter(
    Struct(

        # 0x00 optional prefix
        "prefix" / If(
            this._parsing or (this._building and this._.prefix is not None),
            Optional(Const(bytes.fromhex("00"))),
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
parameters and is sometimes prefixed with 00.

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
