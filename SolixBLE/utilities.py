"""Utilities for SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import inspect
import locale
import logging
import re
import time
from collections.abc import Callable
from importlib import resources

import tzlocal
from bleak import BleakScanner, BLEDevice
from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Construct,
    Container,
    Int32sl,
    SizeofError,
    Struct,
)
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

from .advertisement import ANKER_COMPANY_ID
from .const import DEFAULT_REGION, UUID_IDENTIFIERS

_LOGGER = logging.getLogger(__name__)


async def discover_devices(
    scanner: type[BleakScanner] | None = None,
    timeout: int = 5,
) -> list[BLEDevice]:
    """Scan feature.

    Scans the BLE neighborhood for Solix BLE device(s) and returns a list of
    nearby devices that carry the Anker manufacturer record or advertise a
    known service UUID.

    :param scanner: Scanner class to use. Defaults to BleakScanner.
    :param timeout: Time to scan for devices (default=5).
    """

    if scanner is None:
        scanner = BleakScanner

    devices = []

    def callback(device, advertising_data):
        _LOGGER.debug(
            f"Found generic BT device '{device}' with advertising data: '{advertising_data}'",
        )
        # A passive scan can miss the services; the record is always there
        if (
            ANKER_COMPANY_ID in advertising_data.manufacturer_data
            or any(uuid in advertising_data.service_uuids for uuid in UUID_IDENTIFIERS)
        ) and device not in devices:
            _LOGGER.debug(
                f"Found Anker device '{device}' with advertising data: '{advertising_data}'",
            )
            devices.append(device)

    async with scanner(callback):
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
    return {k: v for k, v in args.items() if k in signature.parameters and k != "self"}


def _to_bytes(
    data: bytes | str | int | Callable[..., bytes | str | int | None] | None,
    **kwargs: object,
) -> bytes:
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
    if callable(data):
        return _to_bytes(
            data(*[kwargs[x] for x in data.__code__.co_varnames]),
            **kwargs,
        )
    raise ValueError(f"Unable to convert '{type(data)}' to bytes!")


def _construct_min_length(struct: Construct, value: bytes | None = None) -> int:
    """Return the fewest bytes ``struct`` needs to parse ``value`` safely.

    :data:`~construct.Construct.sizeof` raises when any part of a struct has
    no static size (a trailing :func:`~construct.Optional` field, a
    :func:`~construct.PascalString`, or an :func:`~construct.Array` counted
    by a sibling field). This walks the struct's named fields in order,
    summing each one's static size, and - given the real bytes already read
    so far - resolves a trailing dynamically-sized field (a length-prefixed
    string, or a field-counted array) by reading its declared length
    straight from ``value`` instead of hardcoding it. Any fixed fields after
    a resolved dynamic one are summed the same way, so a static tail
    following an array (e.g a backup-plan record after a TOU period array)
    is included automatically. Multiple independent dynamic fields in one
    struct (e.g two Pascal strings in sequence) resolve correctly too, since
    each is handled as its turn in the field order comes up.

    :param struct: The construct to measure.
    :param value: The real bytes being guarded, needed only to resolve a
        dynamically-sized field; omit to get just the static prefix length.
    :returns: The minimum byte length ``struct.parse(value)`` needs.
    """
    try:
        return int(struct.sizeof())
    except SizeofError:
        pass

    total = 0
    subcons = list(getattr(struct, "subcons", []))
    for index, subcon in enumerate(subcons):
        try:
            total += subcon.sizeof()
            continue
        except SizeofError:
            pass

        if value is None:
            break

        inner = getattr(subcon, "subcon", subcon)

        # A field-counted array (e.g Array(this.period_count, ...)): read the
        # count from the sibling field already summed into total above.
        count_path = getattr(inner, "count", None)
        if count_path is not None and hasattr(count_path, "__getfield__"):
            prefix = Struct(*subcons[:index]).parse(value[:total])
            count = prefix[count_path.__getfield__()]
            total += count * inner.subcon.sizeof()
            continue

        # A length-prefixed string (e.g PascalString(Int8ub, "ascii")): read
        # its declared length directly from value.
        length_field = getattr(getattr(inner, "subcon", None), "lengthfield", None)
        if length_field is not None:
            field_size = length_field.sizeof()
            declared = length_field.parse(value[total : total + field_size])
            total += field_size + declared
            continue

        break

    return total


def _parse_guarded(value: bytes, struct: Construct) -> Container | None:
    """Parse ``value`` with ``struct``, or None if it is too short.

    :param value: The raw bytes to parse.
    :param struct: The construct to parse them with.
    :returns: The parsed value, or None if ``value`` is shorter than
        :func:`_construct_min_length` requires.
    """
    if len(value) < _construct_min_length(struct, value):
        return None
    return struct.parse(value)


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
        return None


#: Region set by :func:`set_region`, None to follow the host locale.
_region: str | None = None


def set_region(code: str | None) -> None:
    """Set the region sent to devices that store one (e.g Prime chargers).

    :param code: Two-letter country code (e.g ``US``), or None to use the
        host locale's territory.
    """
    global _region  # noqa: PLW0603
    _region = code.upper() if code else None


def region() -> str:
    """Return the region: the one set, else the host locale's, else the default.

    :returns: Two-letter upper-case country code.
    """
    if _region is not None:
        return _region
    try:
        language = locale.getlocale()[0] or ""
    except ValueError:
        language = ""
    territory = language.partition("_")[2][:2]
    if re.fullmatch("[A-Za-z]{2}", territory):
        return territory.upper()
    return DEFAULT_REGION


def _offset_seconds_west() -> bytes:
    """UTC offset of the local zone as a signed int32 LE, in seconds west of UTC.

    POSIX counts seconds west, so a zone east of UTC gives a negative value.

    :returns: The 4-byte little-endian signed offset.
    """
    gmtoff = time.localtime().tm_gmtoff
    seconds_west = -gmtoff if gmtoff is not None else 0
    offset: bytes = Int32sl.build(seconds_west)
    return offset


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
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )[1:]


def ecdh_shared_secret(
    private_key: EllipticCurvePrivateKey,
    device_public_bytes: bytes,
) -> bytes:
    """Derive the ECDH shared secret from the device's raw public point.

    :param private_key: The ECDH private key.
    :param device_public_bytes: The device's ``X || Y`` point without prefix.
    :returns: The 32-byte shared secret.
    """
    device_public_key = EllipticCurvePublicKey.from_encoded_point(
        SECP256R1(),
        b"\x04" + device_public_bytes,
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
            "Failed to validate authenticity of payload, decoding anyway...",
        )
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt(encrypted)
