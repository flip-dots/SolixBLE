"""Tests for the c490 protobuf device-summary path (C1000 G2 / C2000 G2).

The C2000 G2 (A1783) posts a protobuf device summary on command ``c490`` every
~9 min. It is delivered whole by the reassembler, decrypted, then walked into a
``.path`` field map exposed via :attr:`~SolixBLE.device.SolixBLEDevice.summary`
(see :mod:`SolixBLE.parsing`). The protobuf is wrapped in an outer ``a1``/``a2``
TLV, so it must be un-wrapped before walking. The frames below are real captures
(decrypted cleartext from the collector's journald log), re-encrypted with the
test secret to exercise the whole decrypt -> unwrap -> walk -> property path.
"""

import pytest

from SolixBLE import C1000G2, C2000G2
from SolixBLE.const import DEFAULT_METADATA_FLOAT, DEFAULT_METADATA_INT
from SolixBLE.device import SolixBLEDevice
from tests.const import MOCK_BLE_DEVICE

#: AES key/IV used to re-encrypt the captured cleartext (same secret the other
#: telemetry tests use); the decrypt round-trips it back to the cleartext below.
SECRET = "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b"

C490_CMD = b"\xc4\x90"

#: Real A1763 c490 frame, idle regime (flow-state 0, 95 % SoC), decrypted cleartext.
FRAME_IDLE = "a10131a25001040a0541313736331200320538b4094007722e0a200000040075411d61894900005201000000013c00000000000100000080000000100018cb1e20cf1628003000722c0a200000000000000000000000000000000000000000000000000000000000000000100018002000280030007a1b08820f1002189504208f04280330093800400048005000580060007a18080010001800200028003000380040004800500058006000920110080010001800200028003000380040009a011a08cefd0110900118d5ea0320aad00228c63a302438df0a409c42a2011608ee01100018e40220c101281330003800400048ee01aa01130800100018002000280030003800400048ee01b001da9702ba0119085f08001000180020002800302a3800409a1c48bb0950b202c20127080410011800200028003000380040004800500058006000680070007800800100880100900100a31c046368617267696e675f7070735f7365726965735f635f3030303500"  # noqa: E501

#: Real A1763 c490 frame, discharge regime (flow-state 1, 44 W out, 52.9 V).
FRAME_DISCHARGE = "a10131a25001040a0541313736331200320538b4094007722e0a200000000075001d61894800005201000000003c00000000000100000080000000100018cb1e20d01628003000722c0a200000000000000000000000000000000000000000000000000000000000000000100018002000280030007a1b08820f1002189104209104280830093800400048005000580060007a18080010001800200028003000380040004800500058006000920110080010001800200028003000380040009a011a08cefd0110900118d5ea0320aad00228d73a302438df0a40a442a2011608ee01100018e40220c101281330003800400048ee01aa01130800100018002000280030003800400048ee01b001eb9702ba0119085f0800102c180020002800302a380140910348bb0950b202c20127080410011800200028003000380040004800500058006000680070007800800100880100900100a31c046368617267696e675f7070735f7365726965735f635f3030303500"  # noqa: E501


async def _feed_c490(device: SolixBLEDevice, frame_hex: str) -> None:
    """Re-encrypt a captured cleartext frame and run it through the telemetry path."""
    device._shared_secret = bytes.fromhex(SECRET)
    encrypted = device._encrypt_payload(bytes.fromhex(frame_hex))
    await device._process_telemetry_packet(encrypted, cmd=C490_CMD)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,frame_hex,mapping",
    [
        pytest.param(
            C1000G2,
            FRAME_IDLE,
            {
                "c490_battery_soc": 95,
                "c490_output_power_total": 0,
                "c490_ac_output_power": 0,
                "c490_input_power_total": 0,
                "c490_dc_input_power": 0,
                "charge_presence": 42,
                "flow_state": 0,
                "battery_voltage": 53.3,
                "cumulative_discharge_energy": 8476,
            },
            id="c1000g2_c490_idle",
        ),
        pytest.param(
            C2000G2,
            FRAME_DISCHARGE,
            {
                "c490_battery_soc": 95,
                "c490_output_power_total": 44,
                "flow_state": 1,
                "battery_voltage": 52.9,
                "cumulative_discharge_energy": 8484,
            },
            id="c2000g2_c490_discharge",
        ),
    ],
)
async def test_c490_summary_properties(
    device_class: type[SolixBLEDevice],
    frame_hex: str,
    mapping: dict,
) -> None:
    """A real c490 frame decrypts, unwraps and walks into the summary properties."""
    device = device_class(MOCK_BLE_DEVICE)
    await _feed_c490(device, frame_hex)

    for prop, expected in mapping.items():
        assert getattr(device, prop) == expected, f"Mismatch for '{prop}'"


@pytest.mark.asyncio
async def test_c490_summary_is_faithful_field_map() -> None:
    """The walk records every field (containers included) and stops at the trailer.

    Recording message containers (not just their leaves) keeps the map faithful --
    an under-count is a wrong decode. The one wire-type-3 marker is the trailing
    ``a3`` string field past the protobuf, recorded as ``None`` and terminating the
    walk (see :func:`SolixBLE.parsing.walk_protobuf`).
    """
    device = C2000G2(MOCK_BLE_DEVICE)
    await _feed_c490(device, FRAME_IDLE)

    summary = device.summary
    assert summary[".1"] == "A1763"  # part number leaf
    assert isinstance(summary[".23"], int)  # the .23 rollup container is recorded
    assert summary[".23.1"] == 95  # ... and its leaf
    # the walk is bounded to a2's declared length, so it never runs into the trailing
    # a3 string field: no spurious .452 group marker, and every value is a real field.
    assert ".452" not in summary
    assert None not in summary.values()


@pytest.mark.parametrize(
    "payload_hex,expected_hex",
    [
        # a1 01 31 | a2 <len16=0004 -> type(04)+3-byte blob> 04 | 089601 -> just 089601
        ("a10131a2040004089601", "089601"),
        # an 8-byte blob: a2 length is 9 (04 type + 8) -> returns the 8 blob bytes
        ("a10131a2090004" + "08" * 8, "08" * 8),
        # a trailing a3 string field past a2 is bounded out, not appended to the blob
        ("a10131a2040004089601a31c0463686172", "089601"),
        # too short to carry the wrapper -> returned whole rather than mis-sliced
        ("a101", "a101"),
    ],
)
def test_protobuf_body_strips_wrapper(payload_hex: str, expected_hex: str) -> None:
    body = SolixBLEDevice._protobuf_body(bytes.fromhex(payload_hex))
    assert body == bytes.fromhex(expected_hex)


def test_summary_defaults_before_any_c490() -> None:
    """With no c490 frame yet, the summary is empty and its properties read defaults."""
    device = C2000G2(MOCK_BLE_DEVICE)

    assert device.summary == {}
    assert device.battery_voltage == DEFAULT_METADATA_FLOAT
    assert device.flow_state == DEFAULT_METADATA_INT
    assert device.c490_battery_soc == DEFAULT_METADATA_INT
    assert device.cumulative_discharge_energy == DEFAULT_METADATA_INT
