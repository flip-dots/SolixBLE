"""Tests for the c490 device-summary decode on the C2000 Gen 2.

.. moduleauthor:: kb1ibt
"""

import logging
from unittest import mock

import pytest
from bleak import BleakClient

from SolixBLE import C2000G2
from SolixBLE.constructs import Packet
from SolixBLE.device import SolixBLEDevice
from SolixBLE.parsing import SummaryField, name_summary, walk_protobuf
from tests.const import MOCK_BLE_DEVICE

SCHEMA_0005 = "charging_pps_series_c_0005"
SCHEMA_0009 = "charging_pps_series_c_0009"
SCHEMA_0002 = "charging_pps_series_c_0002"

#: A minimal protobuf message: field 1 (varint) = 42.
PROTOBUF = "082a"

#: The c490 outer wrapper: ``a1`` (command echo) then ``a2`` (2-byte length, an
#: ``04`` type byte, and the protobuf blob), so ``a2``'s length counts the type
#: byte plus the blob bytes.
C490_PLAINTEXT = "a10131" + "a20300" + "04" + PROTOBUF

CELL_COUNT = 16
TEMP_COUNT = 4


def _varint(value: int) -> bytes:
    """Encode a protobuf varint."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number: int, value: int) -> bytes:
    """Encode a varint field."""
    return _varint(number << 3) + _varint(value)


def _bytes_field(number: int, payload: bytes) -> bytes:
    """Encode a length-delimited field."""
    return _varint((number << 3) | 2) + _varint(len(payload)) + payload


def _wrap(protobuf: bytes, schema: str) -> bytes:
    """Wrap a protobuf blob in the c490 outer TLV with the given schema name.

    ``a3`` is a typed parameter like ``a2``: its length counts the ``04`` type
    byte and the null-terminated schema name, matching what the device sends.
    """
    a2 = b"\xa2" + (len(protobuf) + 1).to_bytes(2, "little") + b"\x04" + protobuf
    a3 = b"\xa3" + bytes([len(schema) + 2]) + b"\x04" + schema.encode() + b"\x00"
    return bytes.fromhex("a10131") + a2 + a3


def _frame(device: C2000G2, plaintext: bytes) -> bytearray:
    """Build an encrypted c490 frame as the device sends it."""
    return bytearray(
        Packet.build(
            {
                "pattern": bytes.fromhex("03010f"),
                "cmd": bytes.fromhex("c490"),
                "payload_bytes": device._encrypt_payload(plaintext),
            },
        ),
    )


def _device() -> tuple[C2000G2, BleakClient]:
    """Build a C2000 G2 with a mock client so notifications are processed."""
    device = C2000G2(MOCK_BLE_DEVICE)
    client = mock.AsyncMock(spec=BleakClient)
    device._client = client
    return device, client


#: A ledger block (.19) with 1000 counts of AC charge and 200 of DC discharge,
#: and a rollup (.23) with a DC input voltage of 12.34 V.
LEDGER = _bytes_field(19, _field(3, 1000) + _field(8, 200))
ROLLUP = _bytes_field(23, _field(1, 95) + _field(6, 1234))


def test_c2000g2_declares_c490() -> None:
    """The C2000 G2 routes c490 as a protobuf telemetry frame."""
    assert "c490" in C2000G2._TELEMETRY_COMMANDS
    assert C2000G2._PROTOBUF_TELEMETRY_COMMANDS == ("c490",)


def test_protobuf_body_extracts_a2_blob() -> None:
    """The protobuf blob is sliced out of the outer ``a2`` field."""
    body = SolixBLEDevice._protobuf_body(bytes.fromhex(C490_PLAINTEXT))
    assert body.hex() == PROTOBUF


def test_protobuf_schema_extracts_a3() -> None:
    """The a3 schema name is read from the c490 frame."""
    assert (
        SolixBLEDevice._protobuf_schema(_wrap(b"\x08\x2a", SCHEMA_0005)) == SCHEMA_0005
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", [SCHEMA_0005, SCHEMA_0009])
async def test_known_schema_decodes_named_fields(schema: str) -> None:
    """A frame of a mapped schema decodes to named, scaled fields."""
    device, client = _device()
    await device._process_notification(
        client,
        0,
        _frame(device, _wrap(LEDGER + ROLLUP, schema)),
    )

    assert device.summary_schema == schema
    assert device.summary["ac_charge_energy_wh"] == 900.0
    assert device.summary["dc_discharge_energy_wh"] == 180.0
    assert device.summary["battery_soc"] == 95
    assert device.summary["dc_input_voltage"] == 12.34
    assert device.ac_charged_energy == 0.9
    assert device.dc_output_energy == 0.18
    assert device.dc_input_voltage == 12.34
    assert device.last_summary_update is not None


@pytest.mark.asyncio
async def test_summary_runs_state_callbacks() -> None:
    """A decoded summary notifies state-change subscribers."""
    device, client = _device()
    seen: list[bool] = []
    device.add_callback(lambda: seen.append(True))
    await device._process_notification(
        client,
        0,
        _frame(device, _wrap(ROLLUP, SCHEMA_0009)),
    )
    assert seen == [True]


@pytest.mark.asyncio
async def test_unknown_schema_keeps_raw_paths(caplog: pytest.LogCaptureFixture) -> None:
    """A frame of an unmapped schema is kept by path and warned about once."""
    device, client = _device()
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            await device._process_notification(
                client,
                0,
                _frame(device, _wrap(ROLLUP, SCHEMA_0002)),
            )

    assert device.summary_schema == SCHEMA_0002
    assert device.summary[".23.6"] == 1234
    assert device.dc_input_voltage is None
    assert sum("no field map" in r.message for r in caplog.records) == 1


def test_no_summary_leaves_optional_properties_none() -> None:
    """Until a post arrives every summary-backed property reads None."""
    device = C2000G2(MOCK_BLE_DEVICE)
    assert device.summary == {}
    assert device.summary_schema is None
    assert device.last_summary_update is None
    assert device.ac_charged_energy is None
    assert device.dc_charged_energy is None
    assert device.ac_output_energy is None
    assert device.dc_output_energy is None
    assert device.dc_input_voltage is None


def test_declared_arrays_decode_as_arrays() -> None:
    """A packed u16 array that looks like a sub-message decodes as an array."""
    # 16 cell voltages around 3.3 V: the bytes parse as a plausible message
    # (0x08 = field 1 varint) when not declared as an array.
    cells = b"".join(v.to_bytes(2, "little") for v in range(3336, 3336 + CELL_COUNT))
    temps = b"".join(v.to_bytes(2, "little") for v in (3009, 3001, 2993, 3005))
    pack = _bytes_field(14, _bytes_field(15, cells) + _bytes_field(16, temps))

    raw = walk_protobuf(pack, arrays={".14.15": "u16le", ".14.16": "u16le"})
    assert raw[".14.15"] == list(range(3336, 3336 + CELL_COUNT))
    assert raw[".14.16"] == [3009, 3001, 2993, 3005]

    named = name_summary(
        raw,
        {".14.15": SummaryField("cell_voltage", array="u16le")},
    )
    assert named["cell_voltage"] == list(range(3336, 3336 + CELL_COUNT))
    assert named[".14.16"] == [3009, 3001, 2993, 3005]


def test_name_summary_applies_factor_and_keeps_unmapped() -> None:
    """Mapped integers are scaled; unmapped paths keep their raw key."""
    named = name_summary(
        {".23.6": 1234, ".23.7": 2, ".99": "ff"},
        {
            ".23.6": SummaryField("dc_input_voltage", 0.01),
            ".23.7": SummaryField("working_status"),
        },
    )
    assert named == {"dc_input_voltage": 12.34, "working_status": 2, ".99": "ff"}
