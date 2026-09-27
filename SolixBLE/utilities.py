"""Utilities for SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import importlib.resources as resources
import inspect
import logging
import time
from typing import Callable

import tzlocal
from bleak import BleakScanner, BLEDevice
from Crypto.Cipher import AES
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
    generate_private_key,
)
from cryptography.hazmat.primitives.padding import PKCS7

from .const import UUID_IDENTIFIER

_LOGGER = logging.getLogger(__name__)


async def discover_devices(
    scanner: BleakScanner | None = None, timeout: int = 5
) -> list[BLEDevice]:
    """Scan feature.

    Scans the BLE neighborhood for Solix BLE device(s) and returns
    a list of nearby devices based upon detection of a known UUID.

    :param scanner: Scanner to use. Defaults to new scanner.
    :param timeout: Time to scan for devices (default=5).
    """

    if scanner is None:
        scanner = BleakScanner

    devices = []

    def callback(device, advertising_data):
        _LOGGER.debug(
            f"Found generic BT device '{device}' with advertising data: '{advertising_data}'"
        )
        if UUID_IDENTIFIER in advertising_data.service_uuids and device not in devices:
            _LOGGER.debug(
                f"Found Anker device '{device}' with advertising data: '{advertising_data}'"
            )
            devices.append(device)

    async with BleakScanner(callback) as scanner:
        await asyncio.sleep(timeout)

    return devices

def _filter_kwargs(function: Callable, args: dict) -> dict:
    """
    Return only the keyword arguments which are valid for the function.

    :param function: Function to filter arguments for.
    :param args: Arguments to filter.
    :returns: Filtered arguments.
    """
    signature = inspect.signature(function)
    return {
        k: v for k, v in args.items()
        if k in signature.parameters and k != "self"
    }

def _to_bytes(data: bytes | str | int | Callable | None, **kwargs: dict) -> bytes:
    """Return input in byte form.

    Lambda functions are executed using keyword arguments.
    Keyword arguments are passed through to conversion functions.

    :param data: Data to convert to bytes.
    :returns: Byte form of input.
    :raises ValueError: If input type unsupported.
    """
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if type(data) is str:
        return bytes.fromhex(data)
    if type(data) is int:
        return int.to_bytes(data, **_filter_kwargs(int.to_bytes, kwargs))
    if isinstance(data, Callable):
        return _to_bytes(data(*[kwargs[x] for x in data.__code__.co_varnames]), **kwargs)
    raise ValueError(f"Unable to convert '{type(data)}' to bytes!")

def get_posix_tz() -> str | None:
    """Return the current time zone as a POSIX timezone string.

    Examples: `EST5EDT,M3.2.0,M11.1.0`, `GMT0BST,M3.5.0/1,M10.5.0`

    :returns: String of the systems timezone in POSIX format or None if unable.
    """

    try:
        local_zone = tzlocal.get_localzone_name()

        # The POSIX tz string is present on the last line of the tz db
        with resources.files("tzdata.zoneinfo").joinpath(local_zone).open("rb") as f:
            lines = f.readlines()
            return lines[-1].decode("ascii").strip()
    except Exception:
        _LOGGER.exception("Unable to determine system time zone!")

def _offset_seconds_west() -> bytes:
    """UTC offset of the local zone as a signed int32 LE, in seconds west of UTC.

    POSIX counts seconds west, so a zone east of UTC gives a negative value.

    :returns: The 4-byte little-endian signed offset.
    """
    gmtoff = time.localtime().tm_gmtoff
    seconds_west = -gmtoff if gmtoff is not None else 0
    return seconds_west.to_bytes(4, byteorder="little", signed=True)

def generate_ecdh_key() -> EllipticCurvePrivateKey:
    """Create a fresh P-256 private key for one ECDH negotiation.

    :returns: The private key.
    """
    return generate_private_key(SECP256R1())

def ecdh_public_bytes(private_key: EllipticCurvePrivateKey) -> bytes:
    """Return the public point of a key as the raw ``X || Y`` bytes.

    Anker devices exchange the uncompressed point without its ``04`` prefix.

    :param private_key: The ECDH private key.
    :returns: 64 bytes of public point.
    """
    return private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )[1:]

def ecdh_shared_secret(
    private_key: EllipticCurvePrivateKey, device_public_bytes: bytes
) -> bytes:
    """Derive the ECDH shared secret from the device's raw public point.

    :param private_key: The ECDH private key.
    :param device_public_bytes: The device's ``X || Y`` point without prefix.
    :returns: The 32-byte shared secret.
    """
    device_public_key = EllipticCurvePublicKey.from_encoded_point(
        SECP256R1(), b"\x04" + device_public_bytes
    )
    return private_key.exchange(ECDH(), device_public_key)

def cbc_encrypt(key: bytes, iv: bytes, payload: bytes) -> bytes:
    """AES-CBC encrypt a payload with PKCS7 padding.

    :param key: 16-byte AES key.
    :param iv: 16-byte initialisation vector.
    :param payload: Plain-text bytes.
    :returns: Cipher-text bytes.
    """
    padder = PKCS7(128).padder()
    padded = padder.update(payload) + padder.finalize()
    return AES.new(key, AES.MODE_CBC, iv=iv).encrypt(padded)

def cbc_decrypt(key: bytes, iv: bytes, payload: bytes) -> bytes:
    """AES-CBC decrypt a payload and strip its PKCS7 padding.

    :param key: 16-byte AES key.
    :param iv: 16-byte initialisation vector.
    :param payload: Cipher-text bytes.
    :returns: Plain-text bytes.
    """
    decrypted = AES.new(key, AES.MODE_CBC, iv=iv).decrypt(payload)
    unpadder = PKCS7(128).unpadder()
    return unpadder.update(decrypted) + unpadder.finalize()

def gcm_encrypt(key: bytes, nonce: bytes, aad: bytes, payload: bytes) -> bytes:
    """AES-GCM encrypt a payload, appending the 16-byte MAC.

    :param key: 16-byte AES key.
    :param nonce: 12-byte nonce.
    :param aad: Additional authenticated data.
    :param payload: Plain-text bytes.
    :returns: Cipher-text bytes followed by the MAC.
    """
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(aad)
    encrypted, mac = cipher.encrypt_and_digest(payload)
    return encrypted + mac

def gcm_decrypt(key: bytes, nonce: bytes, aad: bytes, payload: bytes) -> bytes:
    """AES-GCM decrypt a payload whose last 16 bytes are the MAC.

    If the MAC does not verify the payload is decrypted anyway and the failure
    is logged, so a corrupted frame is visible rather than silently dropped.

    :param key: 16-byte AES key.
    :param nonce: 12-byte nonce.
    :param aad: Additional authenticated data.
    :param payload: Cipher-text bytes followed by the MAC.
    :returns: Plain-text bytes.
    """
    mac = payload[-16:]
    encrypted = payload[:-16]
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        cipher.update(aad)
        return cipher.decrypt_and_verify(encrypted, mac)
    except ValueError:
        _LOGGER.exception(
            "Failed to validate authenticity of payload, decoding anyway..."
        )
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt(encrypted)
