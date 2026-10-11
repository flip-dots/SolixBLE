"""Tests for the Anker manufacturer advertisement record.

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE.advertisement import (
    ANKER_COMPANY_ID,
    capability_from_advertisement,
    parse_advertisement,
    record_from_advertisement,
)
from tests.helpers import make_advertisement


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        pytest.param(
            "01aa12deadb1b200b4014a544200",
            (1, "aa12deadb1b2", 0x00, "b401", "JTB", 0x00),
            id="a91b2",
        ),
        pytest.param(
            "01aa12deadb34500b402514a4204",
            (1, "aa12deadb345", 0x00, "b402", "QJB", 0x04),
            id="a2345",
        ),
        pytest.param(
            "01aa12deadc0de01b402514a4204",
            (1, "aa12deadc0de", 0x01, "b402", "QJB", 0x04),
            id="a2345_first_boot",
        ),
        pytest.param(
            "02aa12deadbeef00b11a444b4b4504",
            (2, "aa12deadbeef", 0x00, "b11a", "DKKE", 0x04),
            id="a1783",
        ),
        pytest.param(
            "02007f1d23a37000b118444b393604",
            (2, "007f1d23a370", 0x00, "b118", "DK96", 0x04),
            id="a1763",
        ),
        # SolixBLE #63, the MAC redacted there
        pytest.param(
            "01aabbccddeeff02b106373434",
            (1, "aabbccddeeff", 0x02, "b106", "744", None),
            id="f3800_shaped",
        ),
        # SolixBLE #2
        pytest.param(
            "01f49d8a8107d002b11254323704",
            (1, "f49d8a8107d0", 0x02, "b112", "T27", 0x04),
            id="f3800_plus",
        ),
        # SolixBLE #1: a capability byte that is present and clear
        pytest.param(
            "01f49d8aa1b3aa02b00647513800",
            (1, "f49d8aa1b3aa", 0x02, "b006", "GQ8", 0x00),
            id="solarbank2_e1600_pro",
        ),
        # HaSolixBLE #17
        pytest.param(
            "01f49d8a8a022602b103445a4204",
            (1, "f49d8a8a0226", 0x02, "b103", "DZB", 0x04),
            id="c800",
        ),
        # HaSolixBLE #48: the A1340 sends three NULs as its sku
        pytest.param(
            "01e8eeccc7011802010100000004",
            (1, "e8eeccc70118", 0x02, "0101", "", 0x04),
            id="a1340",
        ),
    ],
)
def test_parse_record(
    record: str,
    expected: tuple[int, str, int, str, str, int | None],
) -> None:
    """Decodes to (version_code, mac, bind_type, product_type, sku, capability)."""
    parsed = parse_advertisement(bytes.fromhex(record))
    assert parsed is not None
    assert (
        parsed.version_code,
        parsed.mac.hex(),
        parsed.bind_type,
        parsed.product_type.hex(),
        parsed.sku,
        parsed.capability,
    ) == expected


@pytest.mark.parametrize(
    "record",
    [
        pytest.param("01f49d8a", id="too_short"),
        pytest.param("03aa12deadb34500b402514a4204", id="unknown_version"),
        pytest.param("01aa12deadb34500b402ffffff04", id="sku_not_ascii"),
        # SolixBLE #55: the legacy 767 sends only its MAC, reversed
        pytest.param("1fa63fcceee8", id="legacy_bare_mac"),
    ],
)
def test_parse_malformed(record: str) -> None:
    """A truncated, unknown-version, non-ascii or bare-MAC record decodes to None."""
    assert parse_advertisement(bytes.fromhex(record)) is None


@pytest.mark.parametrize(
    ("manufacturer_data", "capability"),
    [
        pytest.param(
            {ANKER_COMPANY_ID: bytes.fromhex("01aa12deadb34500b402514a4204")},
            0x04,
            id="a2345",
        ),
        pytest.param(
            {ANKER_COMPANY_ID: bytes.fromhex("01aabbccddeeff02b106373434")},
            None,
            id="f3800_shaped",
        ),
        pytest.param({0x004C: bytes.fromhex("0215")}, None, id="no_anker_record"),
    ],
)
def test_capability_from_advertisement(
    manufacturer_data: dict[int, bytes],
    capability: int | None,
) -> None:
    """The capability byte is read from the ``0xffff`` record of a scan result."""
    advertisement = make_advertisement(manufacturer_data=manufacturer_data)
    assert capability_from_advertisement(advertisement) == capability


@pytest.mark.parametrize(
    ("manufacturer_data", "sku"),
    [
        pytest.param(
            {ANKER_COMPANY_ID: bytes.fromhex("02aa12deadbeef00b11a444b4b4504")},
            "DKKE",
            id="a1783",
        ),
        pytest.param({}, None, id="no_manufacturer_data"),
    ],
)
def test_record_from_advertisement(
    manufacturer_data: dict[int, bytes],
    sku: str | None,
) -> None:
    """A scan result yields its decoded record, or None without one."""
    advertisement = make_advertisement(manufacturer_data=manufacturer_data)
    record = record_from_advertisement(advertisement)
    assert (record.sku if record is not None else None) == sku
