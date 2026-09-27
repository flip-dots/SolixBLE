"""Generic power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..solix_device import SolixBLEDevice


class Generic(SolixBLEDevice):
    """
    Generic to be used for adding support for an unsupported device.

    Add support for a device like this:

    1. Copy this subclass to a new class with a name of the device.
    2. Initialise the new class inside example.py and connect to it.
    3. Change values (e.g turn things on and off) to cause changes in the device state.
    4. Observe which values change in the log and add properties to your subclass that parse them (see C300, C1000, etc for examples).
    5. Profit???
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 0
