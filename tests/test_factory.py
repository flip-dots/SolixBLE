"""Tests for choosing the device class from a scan result.

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE import (
    C300DC,
    C800,
    C1000,
    C1000G2,
    F3800,
    Generic,
    PrimeCharger250w,
    Solarbank2,
    SolixBLEDevice,
)
from SolixBLE.advertisement import ANKER_COMPANY_ID
from SolixBLE.const import LEGACY_SERVICE, SERVICE_2215, UUID_IDENTIFIER
from SolixBLE.factory import device_class_from_advertisement
from tests.helpers import make_advertisement


@pytest.mark.parametrize(
    ("record", "local_name", "expected"),
    [
        pytest.param("01aa12deadb34500b402514a4204", None, PrimeCharger250w, id="b402"),
        pytest.param("02007f1d23a37000b118444b393604", None, C1000G2, id="b118"),
        # The A1763 record with the A1765's product type (firmware model table)
        pytest.param("02007f1d23a37000b119444b393604", None, C1000G2, id="b119"),
        pytest.param("01aabbccddeeff02b106373434", None, F3800, id="b106"),
        pytest.param("01f49d8a8107d002b11254323704", None, F3800, id="b112"),
        pytest.param("01f49d8a8a022602b103445a4204", None, C800, id="b103"),
        pytest.param("01f49d8aa1b3aa02b00647513800", None, Solarbank2, id="b006"),
        pytest.param(
            "01aa12deadb1b200b4014a544200",
            "A2345_B345",
            PrimeCharger250w,
            id="unknown_type_prime_name",
        ),
        pytest.param(
            "02aa12deadbeef00b11a444b4b4504",
            "SOLIX C2000 Gen 2",
            Generic,
            id="unknown_type_unknown_name",
        ),
        pytest.param(None, "SOLIX C1000 Gen 2", C1000G2, id="name_c1000_gen_2"),
        pytest.param(None, "SOLIX C1000X Gen 2", C1000G2, id="name_c1000x_gen_2"),
        pytest.param(None, "Anker SOLIX C1000", C1000, id="name_c1000"),
        pytest.param(None, "Anker SOLIX C300 DC", C300DC, id="name_c300dc"),
        pytest.param(None, "Anker SOLIX F3800 Plus", F3800, id="name_f3800_plus"),
        pytest.param(None, "A1763_A370", Generic, id="no_part_number_entry"),
        pytest.param(None, "AFYDKPN0F49300504", Generic, id="serial_as_name"),
        pytest.param(None, None, Generic, id="nothing"),
    ],
)
def test_model_from_advertisement(
    record: str | None,
    local_name: str | None,
    expected: type[SolixBLEDevice],
) -> None:
    """The product type picks the model, then the name, else Generic."""
    advertisement = make_advertisement(
        manufacturer_data={ANKER_COMPANY_ID: bytes.fromhex(record)} if record else None,
        service_uuids=[UUID_IDENTIFIER],
        local_name=local_name,
    )
    assert device_class_from_advertisement(advertisement) is expected


def test_name_argument_used_without_a_local_name() -> None:
    """A name passed in is matched when the scan result carries none."""
    advertisement = make_advertisement(service_uuids=[UUID_IDENTIFIER])
    assert (
        device_class_from_advertisement(advertisement, name="A2345_B345")
        is PrimeCharger250w
    )


@pytest.mark.parametrize(
    ("service", "record"),
    [
        pytest.param(LEGACY_SERVICE, "1fa63fcceee8", id="legacy_1780"),
        pytest.param(SERVICE_2215, "01e8eeccc7011802010100000004", id="a1340_2215"),
    ],
)
def test_transport_without_class_has_no_class(service: str, record: str) -> None:
    """A device on a transport no class speaks yet gets no device class."""
    advertisement = make_advertisement(
        manufacturer_data={ANKER_COMPANY_ID: bytes.fromhex(record)},
        service_uuids=[service],
    )
    assert device_class_from_advertisement(advertisement) is None
