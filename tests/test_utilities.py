"""
Tests for the module utilities.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
"""

import time
from unittest import mock

import pytest

from SolixBLE.const import NEGOTIATION_AAD, NEGOTIATION_KEY, NEGOTIATION_NONCE
from SolixBLE.utilities import (
    _offset_seconds_west,
    cbc_decrypt,
    cbc_encrypt,
    ecdh_public_bytes,
    ecdh_shared_secret,
    gcm_decrypt,
    gcm_encrypt,
    generate_ecdh_key,
    get_posix_tz,
    region,
    set_region,
)

#: Length of a raw P-256 public point (X || Y) on the wire.
ECDH_POINT_LENGTH = 64

#: Length of a P-256 ECDH shared secret.
ECDH_SECRET_LENGTH = 32


@pytest.mark.parametrize(
    ("tz", "output"),
    [
        pytest.param(
            "Europe/London",
            "GMT0BST,M3.5.0/1,M10.5.0",
            id="london",
        ),
        pytest.param(
            "America/New_York",
            "EST5EDT,M3.2.0,M11.1.0",
            id="new_york",
        ),
        pytest.param(
            Exception,
            None,
            id="no_tz",
        ),
        pytest.param(
            "not_a_tz",
            None,
            id="invalid_tz",
        ),
    ],
)
def test_util_tz(
    tz: str | Exception,
    output: str | None,
) -> None:
    """
    Test the generation of POSIX timezone strings.

    :param tz: The time zone (e.g Europe/London) or error.
    :param output: Expected output of function.
    """
    with mock.patch("tzlocal.get_localzone_name", side_effect=[tz]):
        assert get_posix_tz() == output


@pytest.mark.parametrize(
    ("gmtoff", "output"),
    [
        pytest.param(
            -14400,
            "40380000",
            id="edt",
        ),
        pytest.param(
            32400,
            "7081ffff",
            id="jst",
        ),
        pytest.param(
            0,
            "00000000",
            id="utc",
        ),
    ],
)
def test_util_offset_seconds_west(gmtoff: int, output: str) -> None:
    """
    Test the local UTC offset is encoded as signed int32 LE seconds west.

    :param gmtoff: Offset east of UTC reported by the local time.
    :param output: Expected output of function as hex.
    """
    local_time = time.struct_time(
        (2026, 7, 1, 12, 0, 0, 2, 182, 1),
        {"tm_zone": "LOCAL", "tm_gmtoff": gmtoff},
    )
    with mock.patch("SolixBLE.utilities.time.localtime", return_value=local_time):
        assert _offset_seconds_west() == bytes.fromhex(output)


def test_util_ecdh_agreement() -> None:
    """Test two ECDH keys derive the same shared secret from each other's points."""
    key_a = generate_ecdh_key()
    key_b = generate_ecdh_key()
    public_a = ecdh_public_bytes(key_a)
    public_b = ecdh_public_bytes(key_b)
    assert len(public_a) == ECDH_POINT_LENGTH
    assert len(public_b) == ECDH_POINT_LENGTH
    secret = ecdh_shared_secret(key_a, public_b)
    assert secret == ecdh_shared_secret(key_b, public_a)
    assert len(secret) == ECDH_SECRET_LENGTH


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            b"",
            id="empty",
        ),
        pytest.param(
            bytes.fromhex("0011223344"),
            id="partial_block",
        ),
        pytest.param(
            bytes(range(16)),
            id="full_block",
        ),
    ],
)
def test_util_cbc_round_trip(payload: bytes) -> None:
    """
    Test AES-CBC decryption reverses encryption including the padding.

    :param payload: Plain-text bytes to encrypt.
    """
    key = bytes(range(16))
    iv = bytes(range(16, 32))
    assert cbc_decrypt(key, iv, cbc_encrypt(key, iv, payload)) == payload


@pytest.mark.parametrize(
    ("key", "nonce", "aad", "payload", "encrypted"),
    [
        pytest.param(
            NEGOTIATION_KEY,
            NEGOTIATION_NONCE,
            NEGOTIATION_AAD,
            "00a10101",
            "ab273ed3e27270c3f4d676ac7d69a00572793732",
            id="negotiation_key",
        ),
    ],
)
def test_util_gcm_known_frame(
    key: str,
    nonce: str,
    aad: str,
    payload: str,
    encrypted: str,
) -> None:
    """
    Test AES-GCM against a recorded frame on the static negotiation key.

    :param key: AES key as hex.
    :param nonce: Nonce as hex; GCM uses only its first 12 bytes.
    :param aad: Additional authenticated data as hex.
    :param payload: Plain-text bytes as hex.
    :param encrypted: Cipher-text and MAC as hex.
    """
    key_bytes = bytes.fromhex(key)
    nonce_bytes = bytes.fromhex(nonce)[:12]
    aad_bytes = bytes.fromhex(aad)
    assert gcm_decrypt(
        key_bytes,
        nonce_bytes,
        aad_bytes,
        bytes.fromhex(encrypted),
    ) == bytes.fromhex(payload)
    assert gcm_encrypt(
        key_bytes,
        nonce_bytes,
        aad_bytes,
        bytes.fromhex(payload),
    ) == bytes.fromhex(encrypted)


@pytest.mark.parametrize(
    ("key", "nonce", "aad", "payload"),
    [
        pytest.param(
            "3c9d1e07a4b25f68e0d1c3b7a9f24e15",
            "5e8a1f3c7b2d9e04a6c1f873",
            "d4e7a19c03b6f25e",
            "0102030405060708090a0b0c0d0e0f101112",
            id="random_key",
        ),
    ],
)
def test_util_gcm_round_trip(key: str, nonce: str, aad: str, payload: str) -> None:
    """
    Test AES-GCM decryption reverses encryption and the MAC is appended.

    :param key: AES key as hex.
    :param nonce: Nonce as hex.
    :param aad: Additional authenticated data as hex.
    :param payload: Plain-text bytes as hex.
    """
    key_bytes = bytes.fromhex(key)
    nonce_bytes = bytes.fromhex(nonce)
    aad_bytes = bytes.fromhex(aad)
    plain = bytes.fromhex(payload)
    encrypted = gcm_encrypt(key_bytes, nonce_bytes, aad_bytes, plain)
    assert len(encrypted) == len(plain) + 16
    assert gcm_decrypt(key_bytes, nonce_bytes, aad_bytes, encrypted) == plain


@pytest.mark.parametrize(
    ("configured", "host_locale", "output"),
    [
        pytest.param(
            "us",
            ("en_GB", "UTF-8"),
            "US",
            id="configured_wins",
        ),
        pytest.param(
            None,
            ("en_US", "UTF-8"),
            "US",
            id="host_locale",
        ),
        pytest.param(
            None,
            ("C", None),
            "GB",
            id="locale_without_territory",
        ),
        pytest.param(
            None,
            (None, None),
            "GB",
            id="no_locale",
        ),
        pytest.param(
            None,
            ValueError,
            "GB",
            id="unparsable_locale",
        ),
    ],
)
def test_util_region(
    configured: str | None,
    host_locale: tuple[str | None, str | None] | type[Exception],
    output: str,
) -> None:
    """
    Test the region is the configured one, else the host locale's, else GB.

    :param configured: Region passed to set_region, if any.
    :param host_locale: Result (or exception) of locale.getlocale().
    :param output: Expected region.
    """
    with mock.patch("SolixBLE.utilities.locale.getlocale", side_effect=[host_locale]):
        set_region(configured)
        try:
            assert region() == output
        finally:
            set_region(None)
