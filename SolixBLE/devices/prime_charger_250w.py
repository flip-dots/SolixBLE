"""Anker Prime Charger (250W) model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..const import DEFAULT_METADATA_BOOL, DEFAULT_METADATA_FLOAT
from .prime_usb_charger import PrimeUsbCharger


class PrimeCharger250w(PrimeUsbCharger):
    """
    Anker Prime Charger (250W) model.

    Use this class to connect and monitor the 250w charger.
    This model is also known as the A2345.

    Telemetry has been confirmed on real hardware and cross-checked against the
    Anker cloud values. The per-port voltage/current/power/status live in the
    base class; this model adds the total output power and per-port on/off
    switch states (fields ``aa``-``ae``).
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 198

    @property
    def total_power_out(self) -> float:
        """Total output power across all six ports (W).

        :returns: Sum of the per-port powers or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return round(
            self.usb_c1_power
            + self.usb_c2_power
            + self.usb_c3_power
            + self.usb_c4_power
            + self.usb_a1_power
            + self.usb_a2_power,
            2,
        )

    @property
    def usb_c1_switch(self) -> bool:
        """USB C1 port on/off switch state.

        :returns: True when the port is switched on or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("aa", begin=1, end=2))

    @property
    def usb_c2_switch(self) -> bool:
        """USB C2 port on/off switch state.

        :returns: True when the port is switched on or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("ab", begin=1, end=2))

    @property
    def usb_c3_switch(self) -> bool:
        """USB C3 port on/off switch state.

        :returns: True when the port is switched on or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("ac", begin=1, end=2))

    @property
    def usb_c4_switch(self) -> bool:
        """USB C4 port on/off switch state.

        :returns: True when the port is switched on or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("ad", begin=1, end=2))

    @property
    def usba_switch(self) -> bool:
        """USB-A ports on/off switch state (shared by both A ports).

        :returns: True when the USB-A ports are switched on or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("ae", begin=1, end=2))
