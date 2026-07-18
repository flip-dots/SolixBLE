"""Tests for the nested-payload walkers (protobuf + length-value)."""

import pytest

from SolixBLE.parsing import read_varint, walk_lv, walk_protobuf


@pytest.mark.parametrize(
    "hexstr,pos,expected",
    [
        # 0x96 0x01 -> 150 (the canonical protobuf varint example)
        ("9601", 0, (150, 2)),
        ("00", 0, (0, 1)),
        ("7f", 0, (127, 1)),  # largest single-byte varint
        ("8001", 0, (128, 2)),  # smallest two-byte varint
        ("ff01", 0, (255, 2)),
        ("ffff03", 0, (65535, 3)),
        # read starting partway through a buffer
        ("aa9601", 1, (150, 3)),
    ],
)
def test_read_varint(hexstr: str, pos: int, expected: tuple[int, int]) -> None:
    assert read_varint(bytes.fromhex(hexstr), pos) == expected


@pytest.mark.parametrize(
    "hexstr,expected,note",
    [
        # field 1 = varint 150 (08 96 01); field 2 = "ABC" (12 03 414243)
        ("0896011203414243", {".1": 150, ".2": "ABC"}, "varint + printable string"),
        # field 1 = submessage{ field 1 = varint 150 }: the container records its byte
        # length AND its leaves are recursed -- dropping the container under-counts.
        ("0a03089601", {".1": 3, ".1.1": 150}, "submessage records container + leaf"),
        # repeated field 1 keeps wire order (second occurrence suffixed #1)
        ("08010802", {".1": 1, ".1#1": 2}, "repeated tag keeps order"),
        # field 1, wire type 5 (32-bit fixed), little-endian 0x12345678
        ("0d78563412", {".1": 0x12345678}, "wire 5 (32-bit fixed)"),
        # field 1, wire type 1 (64-bit fixed), little-endian 01..08
        (
            "090102030405060708",
            {".1": int.from_bytes(bytes(range(1, 9)), "little")},
            "wire 1 (64-bit fixed)",
        ),
        # field 2, non-printable length-delimited bytes -> kept as hex
        ("120200ff", {".2": "00ff"}, "non-printable bytes leaf -> hex"),
        # field 2, zero-length length-delimited -> empty (falls through to hex "")
        ("1200", {".2": ""}, "empty length-delimited leaf"),
        # field 2, all-zero sub is NOT recursed (any(sub) guard) -> kept as hex
        ("12020000", {".2": "0000"}, "all-zero sub kept as hex, not recursed"),
        # field 1 varint, then a wire-type-3 group marker for field 1 (0x0b): the group
        # is recorded as None and stops the walk -- the trailing 0802 is not parsed.
        ("08010b0802", {".1": 1, ".1#1": None}, "wire 3 group -> record None and stop"),
    ],
)
def test_walk_protobuf(hexstr: str, expected: dict, note: str) -> None:
    assert walk_protobuf(bytes.fromhex(hexstr)) == expected, note


def test_walk_protobuf_empty_buffer() -> None:
    assert walk_protobuf(b"") == {}


@pytest.mark.parametrize(
    "value_hex,first_field,first_nonzero,note",
    [
        # Real C2000 G2 `ce` value with no BP2000: a 16-byte zero combination-device ID,
        # then a 1-byte status (0x11), then zero padding. Passed without the 04 type byte.
        (
            "10000000000000000000000000000000000111"
            "000000000000000000000000000000000000000000000000",
            b"\x00" * 16,
            False,
            "empty combination id (no expansion unit)",
        ),
        # A non-zero 16-byte ID -> first field carries it verbatim.
        (
            (bytes([0x10]) + bytes(range(1, 17)) + bytes.fromhex("0111")).hex(),
            bytes(range(1, 17)),
            True,
            "populated combination id (expansion unit present)",
        ),
    ],
)
def test_walk_lv_first_field(
    value_hex: str,
    first_field: bytes,
    first_nonzero: bool,
    note: str,
) -> None:
    fields = walk_lv(bytes.fromhex(value_hex))
    assert fields[0] == first_field, note
    assert any(fields[0]) is first_nonzero


def test_walk_lv_reads_all_fields_and_trailing_padding() -> None:
    # <len><value> pairs to the end; trailing zero padding appears as zero-length fields.
    fields = walk_lv(bytes.fromhex("02aabb01cc0000"))
    assert fields == [b"\xaa\xbb", b"\xcc", b"", b""]


def test_walk_lv_empty_buffer() -> None:
    assert walk_lv(b"") == []
