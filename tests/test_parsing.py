"""Tests for the nested-payload walkers (protobuf + length-value)."""

from SolixBLE.parsing import read_varint, walk_lv, walk_protobuf


def test_read_varint_multibyte():
    # 0x96 0x01 -> 150 (the canonical protobuf varint example), next pos after both bytes
    assert read_varint(bytes.fromhex("9601"), 0) == (150, 2)
    assert read_varint(bytes.fromhex("00"), 0) == (0, 1)


def test_walk_protobuf_scalar_and_string():
    # field 1 = varint 150 (08 96 01); field 2 = "ABC" (12 03 414243)
    out = walk_protobuf(bytes.fromhex("0896011203414243"))
    assert out == {".1": 150, ".2": "ABC"}


def test_walk_protobuf_recurses_submessages():
    # field 1 = submessage{ field 1 = varint 150 }  ->  0a 03 08 96 01
    assert walk_protobuf(bytes.fromhex("0a03089601")) == {".1.1": 150}


def test_walk_protobuf_repeated_fields_keep_order():
    # field 1 = 1, field 1 = 2  ->  08 01 08 02
    assert walk_protobuf(bytes.fromhex("08010802")) == {".1": 1, ".1#1": 2}


def test_walk_lv_ce_empty_combination_block():
    # Real C2000 G2 `ce` value with no BP2000: type 04, then len16 + 16-byte zero ID,
    # then a 1-byte status (0x11), then zero padding. Pass without the 04 type byte.
    ce_value = bytes.fromhex(
        "0410000000000000000000000000000000000111"
        "000000000000000000000000000000000000000000000000",
    )
    fields = walk_lv(ce_value[1:])
    # first field is the 16-byte combination-device ID -- all zero == no unit combined
    assert fields[0] == b"\x00" * 16
    assert not any(fields[0])
    # the status byte that follows the empty ID
    assert fields[1] == b"\x11"


def test_walk_lv_reads_populated_first_field():
    # A non-zero 16-byte ID -> first field carries it verbatim
    ident = bytes(range(1, 17))
    fields = walk_lv(bytes([0x10]) + ident + bytes.fromhex("0111"))
    assert fields[0] == ident
    assert any(fields[0])
