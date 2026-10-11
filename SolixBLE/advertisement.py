"""Anker manufacturer advertisement record.

Anker devices publish a fixed-shape record under BLE company identifier
``0xffff``: the device MAC, the model key (``product_type``), the sku, and on
newer firmware a ``capability`` byte whose ``0x04`` bit means the device
accepts the encrypted negotiation. All of it is readable before connecting.

.. moduleauthor:: kb1ibt
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from construct import (  # type: ignore[import-untyped]  # construct ships no types
    Bytes,
    ConstructError,
    Container,
    Error,
    Int8ub,
    Optional,
    PaddedString,
    Struct,
    Switch,
    this,
)

if TYPE_CHECKING:
    from bleak.backends.scanner import AdvertisementData

#: BLE company identifier the record is published under.
ANKER_COMPANY_ID = 0xFFFF

#: Capability bit: the device accepts the encrypted ``4xxx`` negotiation.
CAPABILITY_ENCRYPTED_ECDH = 0x04

#: ``version_code | mac(6) | bind_type | product_type(2) | sku(3-4) | capability(0-1)``.
ANKER_RECORD = Struct(
    "version_code" / Int8ub,
    "mac" / Bytes(6),
    "bind_type" / Int8ub,
    "product_type" / Bytes(2),
    "sku"
    / Switch(
        this.version_code,
        {1: PaddedString(3, "ascii"), 2: PaddedString(4, "ascii")},
        default=Error,
    ),
    "capability" / Optional(Int8ub),
)


def parse_advertisement(data: bytes) -> Container | None:
    """Decode an Anker ``0xffff`` manufacturer record, or None if malformed."""
    try:
        return ANKER_RECORD.parse(data)
    except ConstructError:
        return None


def record_from_advertisement(advertisement: AdvertisementData) -> Container | None:
    """Decode the Anker record of a scan result, if it carries one."""
    data = advertisement.manufacturer_data.get(ANKER_COMPANY_ID)
    return parse_advertisement(data) if data is not None else None


def capability_from_advertisement(advertisement: AdvertisementData) -> int | None:
    """Read the capability byte from a scan result, or None if absent."""
    record = record_from_advertisement(advertisement)
    return record.capability if record is not None else None
