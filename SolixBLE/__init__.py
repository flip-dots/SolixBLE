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
    F3800,
    Generic,
    MagGo3in1,
    PrimeCharger160w,
    PrimeCharger250w,
    PrimePowerBank20k,
    Solarbank2,
    Solarbank2Prime,
    Solarbank3,
)
from .devices.solarbank2 import Solarbank2Common
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
    "Solarbank2Common",
    "PrimeDevice",
    "C300",
    "C300DC",
    "C800",
    "C1000",
    "C1000G2",
    "F2000",
    "F3800",
    "Solarbank2",
    "Solarbank2Prime",
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
