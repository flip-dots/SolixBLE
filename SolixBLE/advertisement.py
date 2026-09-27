"""Parsing of the Anker manufacturer advertisement record.

Anker devices place a fixed-shape record under BLE company identifier
``0xffff`` in their advertisements. It carries the real MAC, the model
(``product_type`` and ``sku``), and a ``capability`` byte that declares which
negotiation path the device accepts, all readable before a connection is made.

.. moduleauthor:: kb1ibt

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bleak.backends.scanner import AdvertisementData

#: BLE company identifier the record is published under (a reserved/test id).
ANKER_COMPANY_ID = 0xFFFF

#: Capability bit meaning the device accepts the encrypted ``4xxx`` negotiation
#: under the static key. Devices that set it also accept the cleartext path;
#: newer firmware may accept only the encrypted one.
CAPABILITY_ENCRYPTED_ECDH = 0x04

#: Byte offsets within the record. ``capability`` has no fixed offset -- it is
#: the byte after the sku when present, and absent on some models -- so it is
#: derived from the sku length rather than listed here.
_MAC = slice(1, 7)
_BIND_TYPE = 7
_PRODUCT_TYPE = slice(8, 10)
_SKU_START = 10

#: Length of the ascii sku, keyed by ``version_code``. The record is otherwise
#: fixed up to the sku, and the capability byte (if any) follows the sku.
_SKU_LENGTH = {1: 3, 2: 4}

#: Shortest valid record: everything up to the sku, plus the shortest sku.
_MIN_LENGTH = _SKU_START + min(_SKU_LENGTH.values())


@dataclass(frozen=True)
class AnkerAdvertisement:
    """Decoded Anker manufacturer record.

    :param version_code: Record layout version (selects the sku length).
    :param mac: Device MAC as lowercase hex without separators.
    :param bind_type: Provisioning-state byte (dynamic per device).
    :param product_type: Two-byte model key as lowercase hex.
    :param sku: Ascii sku, a substring of the device serial.
    :param capability: Capability mask, or None when the record omits it.
    """

    version_code: int
    mac: str
    bind_type: int
    product_type: str
    sku: str
    capability: int | None


def parse_manufacturer_record(data: bytes) -> AnkerAdvertisement | None:
    """Decode an Anker ``0xffff`` manufacturer record.

    The layout is ``version_code(1) | mac(6) | bind_type(1) | product_type(2) |
    sku(3-4 ascii) | capability(1, optional)``. The sku length follows the
    version code, and the capability byte is present only on some models, so it
    must be read relative to the sku rather than at a fixed offset.

    :param data: Raw manufacturer-data bytes for company id ``0xffff``.
    :returns: The decoded record, or None if it is too short or malformed.
    """
    if len(data) < _MIN_LENGTH:
        return None

    version_code = data[0]
    sku_length = _SKU_LENGTH.get(version_code)
    if sku_length is None:
        return None

    sku_end = _SKU_START + sku_length
    if len(data) < sku_end:
        return None

    try:
        sku = data[_SKU_START:sku_end].decode("ascii")
    except UnicodeDecodeError:
        return None

    capability = data[sku_end] if len(data) > sku_end else None

    return AnkerAdvertisement(
        version_code=version_code,
        mac=data[_MAC].hex(),
        bind_type=data[_BIND_TYPE],
        product_type=data[_PRODUCT_TYPE].hex(),
        sku=sku,
        capability=capability,
    )


def capability_from_advertisement(advertisement: AdvertisementData) -> int | None:
    """Read the capability byte from an advertisement, if it carries one.

    :param advertisement: Advertisement data from a bleak scan callback.
    :returns: The capability mask, or None if there is no Anker record or the
        record omits the byte.
    """
    record = advertisement.manufacturer_data.get(ANKER_COMPANY_ID)
    if record is None:
        return None

    parsed = parse_manufacturer_record(record)
    return parsed.capability if parsed is not None else None
