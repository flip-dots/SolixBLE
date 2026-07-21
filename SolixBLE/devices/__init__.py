"""Anker Solix device models supported by the module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from .c300 import C300
from .c300dc import C300DC
from .c800 import C800
from .c1000 import C1000
from .c1000g2 import C1000G2
from .c2000g2 import C2000G2
from .f2000 import F2000
from .f2600 import F2600
from .f3800 import F3800
from .generic import Generic
from .maggo_3in1 import MagGo3in1
from .prime_charger_160w import PrimeCharger160w
from .prime_charger_250w import PrimeCharger250w
from .prime_power_bank_20k import PrimePowerBank20k
from .solarbank2 import Solarbank2
from .solarbank3 import Solarbank3

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
    "Generic",
    "MagGo3in1",
    "PrimeCharger160w",
    "PrimeCharger250w",
    "PrimePowerBank20k",
    "Solarbank2",
    "Solarbank3",
]
