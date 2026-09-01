"""SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

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
    F2000Legacy,
    Generic,
    MagGo3in1,
    PrimeCharger160w,
    PrimeCharger250w,
    PrimePowerBank20k,
    Solarbank2,
    Solarbank3,
)
from .prime_device import PrimeDevice
from .states import (
    ChargingStatus,
    ChargingStatusF3800,
    DisplayTimeout,
    LightStatus,
    PortOverload,
    PortStatus,
    TemperatureUnit,
)
from .utilities import discover_devices

__all__ = [
    "SolixBLEDevice",
    "PrimeDevice",
    "C300",
    "C300DC",
    "C800",
    "C1000",
    "C1000G2",
    "F2000",
    "F2000Legacy",
    "F2600",
    "F3800",
    "Solarbank2",
    "Solarbank3",
    "PrimeCharger160w",
    "PrimeCharger250w",
    "PrimePowerBank20k",
    "MagGo3in1",
    "Generic",
    "ChargingStatus",
    "ChargingStatusF3800",
    "DisplayTimeout",
    "LightStatus",
    "PortStatus",
    "TemperatureUnit",
    "PortOverload",
    "discover_devices",
]
