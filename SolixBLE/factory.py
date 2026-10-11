"""Choose the device class from a scan result.

The model comes from the advertised ``product_type``, else from the advertised
local name (the model's own name, or a Prime-style ``<part number>_<last four
MAC digits>``), else :class:`Generic`. Some firmware advertises the serial as
the name, so the product type is the key to trust.

.. moduleauthor:: kb1ibt
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .advertisement import record_from_advertisement
from .const import LEGACY_SERVICE, SERVICE_2215
from .devices import (
    C300DC,
    C800,
    C1000,
    C1000G2,
    F3800,
    Generic,
    PrimeCharger250w,
    Solarbank2,
)

if TYPE_CHECKING:
    from bleak.backends.scanner import AdvertisementData

    from .device import SolixBLEDevice

#: Services of transports no device class here speaks yet.
SERVICES_WITHOUT_CLASS = (LEGACY_SERVICE, SERVICE_2215)

#: Device class by the advertised ``product_type`` (hex).
MODELS_BY_PRODUCT_TYPE: dict[str, type[SolixBLEDevice]] = {
    "b402": PrimeCharger250w,
    "b118": C1000G2,  # A1763
    "b119": C1000G2,  # A1765, the same display-board build as the A1763
    "b106": F3800,  # A1790
    "b112": F3800,  # A1790P, the same command and telemetry map as the A1790
    "b103": C800,  # A1753 / A1754 / A1755 share one map
    "b006": Solarbank2,  # A17C1
}

#: Device class by the advertised local name.
MODELS_BY_NAME: dict[str, type[SolixBLEDevice]] = {
    "SOLIX C1000 Gen 2": C1000G2,
    "SOLIX C1000 Plus": C1000G2,
    "SOLIX C1000X Gen 2": C1000G2,
    "Anker SOLIX C1000": C1000,
    "Anker SOLIX C300 DC": C300DC,
    "Anker SOLIX F3800": F3800,
    "Anker SOLIX F3800 Plus": F3800,
    "Solarbank 2 E1600 Pro": Solarbank2,
}

#: Device class by the part number in a Prime-style local name.
MODELS_BY_PART_NUMBER: dict[str, type[SolixBLEDevice]] = {
    "A2345": PrimeCharger250w,
}

#: Prime-style local name: part number, then the last four MAC digits.
PRIME_NAME = re.compile(r"^(A[0-9A-Z]{4})_[0-9A-F]{4}$")


def device_class_from_advertisement(
    advertisement: AdvertisementData,
    name: str | None = None,
) -> type[SolixBLEDevice] | None:
    """Return the device class for a scan result.

    :param advertisement: The scan result.
    :param name: Local name to match if the scan result has none.
    :returns: The device class, or None for a device on a transport no class
        speaks yet (the legacy ``1780`` and the ``2215`` transports).
    """
    if any(uuid in advertisement.service_uuids for uuid in SERVICES_WITHOUT_CLASS):
        return None

    record = record_from_advertisement(advertisement)
    if record is not None and record.product_type.hex() in MODELS_BY_PRODUCT_TYPE:
        return MODELS_BY_PRODUCT_TYPE[record.product_type.hex()]

    local_name = advertisement.local_name or name or ""
    if local_name in MODELS_BY_NAME:
        return MODELS_BY_NAME[local_name]

    match = PRIME_NAME.match(local_name)
    if match is not None and match.group(1) in MODELS_BY_PART_NUMBER:
        return MODELS_BY_PART_NUMBER[match.group(1)]

    return Generic
