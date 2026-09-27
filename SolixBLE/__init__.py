"""SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from .device import AnkerBLEDevice
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
    PrimePowerBank20k,
    Solarbank2,
    Solarbank3,
)
from .prime_device import PrimeBLEDevice
from .solix_device import SolixBLEDevice
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
    "C300",
    "C300DC",
    "C800",
    "C1000",
    "C1000G2",
    "F2000",
    "F2600",
    "F3800",
    "AnkerBLEDevice",
    "ChargingStatus",
    "ChargingStatusF3800",
    "DisplayTimeout",
    "Generic",
    "LightStatus",
    "MagGo3in1",
    "PortOverload",
    "PortStatus",
    "PrimeBLEDevice",
    "PrimeCharger160w",
    "PrimeCharger250w",
    "PrimePowerBank20k",
    "Solarbank2",
    "Solarbank3",
    "SolixBLEDevice",
    "TemperatureUnit",
    "discover_devices",
]
