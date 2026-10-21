"""SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from .advertisement import capability_from_advertisement
from .device import SolixBLEDevice
from .devices import (
    C300,
    C300DC,
    C800,
    C1000,
    C1000G2,
    C2000G2,
    F2000,
    F2600,
    F3800,
    Generic,
    MagGo3in1,
    PrimeCharger160w,
    PrimeCharger250w,
    PrimePowerBank20k,
    Solarbank2,
    Solarbank3,
)
from .factory import device_class_from_advertisement
from .prime_device import PrimeDevice
from .protocols import UnsupportedNegotiation
from .states import (
    ChargingStatus,
    ChargingStatusF3800,
    ClockFormat,
    ClockTheme,
    DisplayTimeout,
    LightStatus,
    PortOverload,
    PortSchedule,
    PortStatus,
    PortTimer,
    TariffType,
    TemperatureUnit,
    TouPeriod,
)
from .utilities import discover_devices, set_region

__all__ = [
    "C300",
    "C300DC",
    "C800",
    "C1000",
    "C1000G2",
    "C2000G2",
    "F2000",
    "F2600",
    "F3800",
    "ChargingStatus",
    "ChargingStatusF3800",
    "ClockFormat",
    "ClockTheme",
    "DisplayTimeout",
    "Generic",
    "LightStatus",
    "MagGo3in1",
    "PortOverload",
    "PortSchedule",
    "PortStatus",
    "PortTimer",
    "PrimeCharger160w",
    "PrimeCharger250w",
    "PrimeDevice",
    "PrimePowerBank20k",
    "Solarbank2",
    "Solarbank3",
    "SolixBLEDevice",
    "TariffType",
    "TemperatureUnit",
    "TouPeriod",
    "capability_from_advertisement",
    "device_class_from_advertisement",
    "discover_devices",
    "set_region",
    "UnsupportedNegotiation",
]
