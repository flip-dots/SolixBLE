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
    F2000,
    F2600,
    F3800,
    Generic,
    MagGo3in1,
    PrimeCharger160w,
    PrimeCharger250w,
    PrimeChargingStation240w,
    PrimePowerBank20k,
    Solarbank2,
    Solarbank3,
)
from .prime_device import PrimeDevice
from .states import (
    AcLightMode,
    ChargingMode,
    ChargingStatus,
    ChargingStatusF3800,
    ClockFormat,
    DisplayTimeout,
    LightStatus,
    PortOverload,
    PortSchedule,
    PortStatus,
    PortTimer,
    TemperatureUnit,
)
from .utilities import discover_devices

__all__ = [
    "C300",
    "C300DC",
    "C800",
    "C1000",
    "C1000G2",
    "F2000",
    "F2600",
    "F3800",
    "AcLightMode",
    "ChargingMode",
    "ChargingStatus",
    "ChargingStatusF3800",
    "ClockFormat",
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
    "PrimeChargingStation240w",
    "PrimeDevice",
    "PrimePowerBank20k",
    "Solarbank2",
    "Solarbank3",
    "SolixBLEDevice",
    "TemperatureUnit",
    "capability_from_advertisement",
    "discover_devices",
]
