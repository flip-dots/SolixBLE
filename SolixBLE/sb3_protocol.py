"""Protocol helpers for the Solarbank 3 E2700 Pro (A17C5).

The Solarbank 3 uses the Prime packet framing, but its authentication flow is
different from the older Prime devices.  This module intentionally contains
only protocol primitives; device lifecycle and BLE I/O remain in the model
class.
"""

from __future__ import annotations

import secrets
import time
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .const import BASE_TIMESTAMP

SB3_ACCOUNT_ID_LENGTH = 40
SB3_DEFAULT_CLIENT_ID = "79ebed35-dc9c-4904-b40c-72c4e8363a10"
SB3_4822_SUCCESS_PLAINTEXT = b"\x04"
SB3_INITIAL_AES_KEY = bytes.fromhex("b8ff7422955d4eb6d554a2c470280559")
SB3_INITIAL_NONCE = bytes.fromhex("6ba3e3f2f3a60f2971ce5d1f")
SB3_AES_GCM_AAD = bytes.fromhex("3322110077665544bbaa9988ffeeddcc")
SB3_MAX_LOAD_VALUES = (350, 600, 800, 1200)
SB3_SCHEDULE_MODE_DISCHARGE = "discharge"
SB3_SCHEDULE_MODE_CHARGE = "charge"
SB3_SCHEDULE_MODES = (SB3_SCHEDULE_MODE_DISCHARGE, SB3_SCHEDULE_MODE_CHARGE)

SB3_SET_SCHEDULE_COMMAND = bytes.fromhex("405e")
SB3_SET_MAX_LOAD_COMMAND = bytes.fromhex("4080")

# These packets are stable across the captured A17C5 connections.  The
# account-bound authentication starts only after the dynamic ECDH exchange.
SB3_4001 = bytes.fromhex(
    "ff09220003000140010a824f0bbd508bb2178c3054ae2df691dab7ce7dd037c5e38b"
)
SB3_4003 = bytes.fromhex(
    "ff09290003000140030a824e0bbd508bb25db5286d496f964ade328b233f57fcf51eb1f2639d69c6f9"
)
SB3_4029 = bytes.fromhex(
    "ff094a0003000140290a824e0bbd508b9acc816cf1285604b0b741b6b202d4f3b4c28ad6630662ca07b3fef57148a0835a890e253dcdeaf36c2a4ca1d6229283bc963af531b711fd239a"
)
SB3_4005 = bytes.fromhex(
    "ff092f0003000140050a824e0bbd508bb25db5286d496f9670823925d138f20cc16133c3ead23c3a1da7e14615bdb8"
)


def xor_checksum(data: bytes) -> bytes:
    """Return the checksum used by the FF09 packet framing."""
    value = 0
    for byte in data:
        value ^= byte
    return bytes((value,))


def build_packet(pattern: bytes, command: bytes, payload: bytes) -> bytes:
    """Build an FF09 packet and append its checksum."""
    if len(pattern) != 3 or len(command) != 2:
        raise ValueError("pattern must be 3 bytes and command must be 2 bytes")
    length = 2 + 2 + len(pattern) + len(command) + len(payload) + 1
    packet = b"\xff\x09" + length.to_bytes(2, "little") + pattern + command + payload
    return packet + xor_checksum(packet)


def parse_packet(packet: bytes) -> tuple[bytes, bytes, bytes]:
    """Validate an FF09 packet and return pattern, command and payload."""
    if len(packet) < 10 or packet[:2] != b"\xff\x09":
        raise ValueError("invalid FF09 packet")
    if int.from_bytes(packet[2:4], "little") != len(packet):
        raise ValueError("packet length mismatch")
    if packet[-1:] != xor_checksum(packet[:-1]):
        raise ValueError("packet checksum mismatch")
    return packet[4:7], packet[7:9], packet[9:-1]


def aes_gcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    """Encrypt a Solarbank 3 payload with AES-GCM and the protocol AAD."""
    return AESGCM(key).encrypt(nonce, plaintext, SB3_AES_GCM_AAD)


def aes_gcm_decrypt(key: bytes, nonce: bytes, payload: bytes) -> bytes:
    """Authenticate and decrypt a Solarbank 3 payload."""
    try:
        return AESGCM(key).decrypt(nonce, payload, SB3_AES_GCM_AAD)
    except InvalidTag as error:
        raise ValueError("Solarbank 3 AES-GCM authentication failed") from error


def encode_public_key(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """Encode a P-256 public key as the captured X||Y representation."""
    numbers = public_key.public_numbers()
    return numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")


def decode_public_key(raw_key: bytes) -> ec.EllipticCurvePublicKey:
    """Decode and validate a 64-byte P-256 X||Y public key."""
    if len(raw_key) != 64:
        raise ValueError("Solarbank 3 public key must contain 64 bytes")
    return ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b"\x04" + raw_key
    )


def build_public_key_packet(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """Build the dynamic ECDH public-key request (4021)."""
    plaintext = b"\xa1\x40" + encode_public_key(public_key)
    encrypted = aes_gcm_encrypt(SB3_INITIAL_AES_KEY, SB3_INITIAL_NONCE, plaintext)
    return build_packet(b"\x03\x00\x01", b"\x40\x21", encrypted)


def validate_account_id(account_id: str) -> str:
    """Validate the 40-character hexadecimal Anker account identifier."""
    value = account_id.strip().lower()
    if len(value) != SB3_ACCOUNT_ID_LENGTH or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise ValueError(
            "Solarbank 3 account ID must be exactly 40 hexadecimal characters"
        )
    return value


def validate_client_id(client_id: str) -> str:
    """Validate the identifier carried by the 4027 security request."""
    value = client_id.strip().lower()
    if len(value) == 40 and all(char in "0123456789abcdef" for char in value):
        return value
    try:
        return str(UUID(value))
    except ValueError as error:
        raise ValueError(
            "Solarbank 3 client ID must be a UUID or 40-char hex ID"
        ) from error


def _timestamp(timestamp: int | None) -> bytes:
    value = int(time.time()) if timestamp is None else timestamp
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("timestamp does not fit in four bytes")
    return value.to_bytes(4, "little")


def build_account_auth_packet(
    account_id: str,
    session_key: bytes,
    session_nonce: bytes,
    timestamp: int | None = None,
) -> bytes:
    """Build the session-encrypted 4022 account-authentication request."""
    account = validate_account_id(account_id).encode("ascii")
    plaintext = b"\xa1\x04" + _timestamp(timestamp) + b"\xa2\x28" + account
    return build_packet(
        b"\x03\x00\x01",
        b"\x40\x22",
        aes_gcm_encrypt(session_key, session_nonce, plaintext),
    )


def build_security_auth_packet(
    client_id: str,
    session_key: bytes,
    session_nonce: bytes,
    timestamp: int | None = None,
) -> bytes:
    """Build the session-encrypted 4027 security-authentication request."""
    client = validate_client_id(client_id).encode("ascii")
    plaintext = (
        b"\xa1\x04" + _timestamp(timestamp) + bytes((0xA2, len(client))) + client
    )
    return build_packet(
        b"\x03\x00\x01",
        b"\x40\x27",
        aes_gcm_encrypt(session_key, session_nonce, plaintext),
    )


def build_telemetry_request_plaintext(timestamp: int | None = None) -> bytes:
    """Build the replay-protected 4040 request body."""
    if timestamp is None:
        timestamp = int.from_bytes(bytes.fromhex(BASE_TIMESTAMP), "little")
    return b"\xa1\x01\x21\xfe\x05\x03" + _timestamp(timestamp)


def build_telemetry_request_packet(
    session_key: bytes, session_nonce: bytes, timestamp: int | None = None
) -> bytes:
    """Build an encrypted 4040 telemetry request."""
    return build_packet(
        b"\x03\x00\x0f",
        b"\x40\x40",
        aes_gcm_encrypt(
            session_key,
            session_nonce,
            build_telemetry_request_plaintext(timestamp),
        ),
    )


def build_firmware_request_packet(
    session_key: bytes, session_nonce: bytes, timestamp: int | None = None
) -> bytes:
    """Build the authenticated ``4030`` firmware-information request.

    A17C5 firmware pages use the same replay-protected request body as
    ``4040``.  The response is ``4830`` and contains a compact ASCII TLV list.
    """
    return build_packet(
        b"\x03\x00\x0f",
        b"\x40\x30",
        aes_gcm_encrypt(
            session_key,
            session_nonce,
            build_telemetry_request_plaintext(timestamp),
        ),
    )


def build_schedule_plaintext(
    power_w: int,
    *,
    start_minutes: int = 0,
    end_minutes: int = 1440,
    mode: str = SB3_SCHEDULE_MODE_DISCHARGE,
    fd_token: bytes | None = None,
) -> bytes:
    """Build the seven-day 405e schedule payload observed on firmware 1.0.7.1."""
    if not isinstance(power_w, int) or isinstance(power_w, bool):
        raise TypeError("power_w must be an integer")
    if not 0 <= power_w <= 1200 or power_w % 50:
        raise ValueError("power_w must be between 0 and 1200 W in 50 W steps")
    if not 0 <= start_minutes <= end_minutes <= 1440:
        raise ValueError("schedule times must be between 0 and 1440 minutes")
    if mode not in SB3_SCHEDULE_MODES:
        raise ValueError("mode must be 'discharge' or 'charge'")
    if fd_token is None:
        fd_token = secrets.token_bytes(4)
    if len(fd_token) != 4:
        raise ValueError("fd_token must contain exactly four bytes")

    slot = (
        start_minutes.to_bytes(2, "little")
        + end_minutes.to_bytes(2, "little")
        + power_w.to_bytes(2, "little")
        + bytes((0x50, 0x01 if mode == SB3_SCHEDULE_MODE_CHARGE else 0x00))
    )
    schedule = bytearray(b"\xa1\x01\x21\xa2\x02\x01\x01")
    for day in range(7):
        base = 0xA3 + 4 * day
        schedule.extend(bytes((base,)) + b"\x02\x01\x01")
        schedule.extend(bytes((base + 1,)) + b"\x09\x04" + slot)
        schedule.extend(bytes((base + 2,)) + b"\x02\x01\x00")
        schedule.extend(bytes((base + 3,)) + b"\x01\x04")
    schedule.extend(b"\xfd\x05\x03" + fd_token)
    if len(schedule) != 168:
        raise AssertionError("unexpected Solarbank 3 schedule length")
    return bytes(schedule)


def build_max_load_plaintext(max_load_w: int) -> bytes:
    """Build the 4080 maximum-load payload observed on firmware 1.0.7.1."""
    if not isinstance(max_load_w, int) or isinstance(max_load_w, bool):
        raise TypeError("max_load_w must be an integer")
    if max_load_w not in SB3_MAX_LOAD_VALUES:
        raise ValueError("max_load_w must be one of 350, 600, 800 or 1200 W")
    return (
        b"\xa1\x01\x21\xa2\x03\x02"
        + max_load_w.to_bytes(2, "little")
        + b"\xa3\x03\x02\x00\x00"
    )
