"""Tests for the Solarbank 3 A17C5 protocol and model mappings."""

import struct

import pytest
from bleak.backends.device import BLEDevice
from cryptography.hazmat.primitives.asymmetric import ec

from SolixBLE.devices.solarbank3 import Solarbank3
from SolixBLE.sb3_protocol import (
    SB3_DEFAULT_CLIENT_ID,
    SB3_INITIAL_AES_KEY,
    SB3_INITIAL_NONCE,
    aes_gcm_decrypt,
    aes_gcm_encrypt,
    build_max_load_plaintext,
    build_schedule_plaintext,
    build_security_auth_packet,
    encode_public_key,
    parse_packet,
)


def _float_tlv(value: float) -> bytes:
    """Build the typed float representation used by A17C5 telemetry."""
    return b"\x05" + struct.pack("<f", value)


def test_sb3_schedule_matches_captured_layout() -> None:
    """The 405e payload contains seven identical weekday slots."""
    payload = build_schedule_plaintext(350, fd_token=b"\x01\x02\x03\x04")

    assert len(payload) == 168
    assert payload[:7] == bytes.fromhex("a10121a2020101")
    assert payload[161:] == bytes.fromhex("fd050301020304")
    assert [payload[18 + 22 * day] for day in range(7)] == [0x5E] * 7


def test_sb3_max_load_uses_little_endian_watts() -> None:
    """The 4080 payload encodes the selected maximum load as a LE integer."""
    assert build_max_load_plaintext(350) == bytes.fromhex(
        "a10121a203025e01a303020000"
    )
    assert build_max_load_plaintext(1200) == bytes.fromhex(
        "a10121a20302b004a303020000"
    )


def test_sb3_4027_uses_session_gcm_and_client_identifier() -> None:
    """The security-authentication request must use the negotiated session."""
    key = bytes(range(16))
    nonce = bytes(range(12))
    packet = build_security_auth_packet(
        SB3_DEFAULT_CLIENT_ID, key, nonce, timestamp=1_700_000_000
    )
    _, command, encrypted = parse_packet(packet)

    assert command == bytes.fromhex("4027")
    assert aes_gcm_decrypt(key, nonce, encrypted).startswith(
        bytes.fromhex("a10400f15365a224")
    )


def test_sb3_telemetry_mappings_match_firmware_1071() -> None:
    """Firmware 1.0.7.1 uses typed floats and the corrected A17C5 fields."""
    device = Solarbank3.__new__(Solarbank3)
    device._data = {
        "a2": b"\x02SN",
        "a3": b"\x01\x5a",
        "a5": b"\x01\x19",
        "a6": b"\x01\x64",
        "ab": _float_tlv(689),
        "ac": _float_tlv(12.5),
        "ad": _float_tlv(327),
        "b1": _float_tlv(400),
        "b2": _float_tlv(390),
        "b9": b"\x02\x90\x01",
        "c7": _float_tlv(309),
        "c8": _float_tlv(23),
        "c9": _float_tlv(13),
        "ca": _float_tlv(40),
    }

    assert device.battery_percentage == 90
    assert device.battery_percentage_aggregate == 90
    assert device.temperature == 25
    assert device.power_out == 327
    assert device.schedule_power == 400
    assert device.solar_power_in == 689
    assert device.solar_pv_2_power_in == 327


class _FakeClient:
    """Capture writes made by the model during the protocol test."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []

    async def write_gatt_char(
        self, _characteristic: str, data: bytes, response: bool = False
    ) -> None:
        del response
        self.writes.append(data)


@pytest.mark.asyncio
async def test_sb3_authentication_sequence_reaches_session_ready() -> None:
    """The complete 4021/4022/4027 flow reaches the authenticated session."""
    device = Solarbank3(
        BLEDevice("00:11:22:33:44:55", "A17C5", None),
        anker_user_id="1" * 40,
    )
    device._client = _FakeClient()

    device_private_key = ec.generate_private_key(ec.SECP256R1())
    device_4821 = aes_gcm_encrypt(
        SB3_INITIAL_AES_KEY,
        SB3_INITIAL_NONCE,
        b"\x00\xa1\x40" + encode_public_key(device_private_key.public_key()),
    )
    await device._process_negotiation(bytes.fromhex("4821"), device_4821)

    assert parse_packet(device._client.writes[-1])[1] == bytes.fromhex("4022")
    session_key = device._shared_secret[:16]
    session_nonce = device._shared_secret[16:28]

    await device._process_negotiation(
        bytes.fromhex("4822"),
        aes_gcm_encrypt(session_key, session_nonce, b"\x04"),
    )
    assert parse_packet(device._client.writes[-1])[1] == bytes.fromhex("4027")

    await device._process_negotiation(
        bytes.fromhex("4827"),
        aes_gcm_encrypt(session_key, session_nonce, b"\x04"),
    )
    assert device._sb3_session_ready
    assert parse_packet(device._client.writes[-1])[1] == bytes.fromhex("4040")
