"""Anker Prime Power Bank 20k (220w) model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..const import DEFAULT_METADATA_FLOAT
from ..prime_device import PrimeDevice
from ..states import PortStatus


class PrimePowerBank20k(PrimeDevice):
    """
    Anker Prime Power Bank 20k (220w) model.

    Use this class to connect and monitor the 220w power bank.
    This model is also known as the A110B.
    """

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a2", begin=1, end=2)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int("a6", begin=2, end=4) / 10.0

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("af", begin=1, signed=True)

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("a8", begin=1, end=2))

    @property
    def usb_c1_voltage(self) -> float:
        """USB C1 Port voltage (V).

        :returns: Voltage of the USB C1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a8", begin=2, end=4) / 10.0

    @property
    def usb_c1_current(self) -> float:
        """USB C1 Port current (A).

        :returns: Current of the USB C1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a8", begin=4, end=6) / 10.0

    @property
    def usb_c1_power(self) -> float:
        """USB C1 Port power (W).

         .. important::

            There appears to be a firmware bug in the power bank which
            causes the value of USB C1 power to latch to whatever its 
            last value was when unplugged, this does not happen with
            USB C2 power for some reason. This has been observed on 
            version v1.6.0.5.

        :returns: Power of the USB C1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a8", begin=6, end=8) / 10.0

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("a9", begin=1, end=2))

    @property
    def usb_c2_voltage(self) -> float:
        """USB C2 Port voltage (V).

        :returns: Voltage of the USB C2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a9", begin=2, end=4) / 10.0

    @property
    def usb_c2_current(self) -> float:
        """USB C2 Port current (A).

        :returns: Current of the USB C2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a9", begin=4, end=6) / 10.0
    
    @property
    def usb_c2_power(self) -> float:
        """USB C2 Port power (W).

        :returns: Power of the USB C2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a9", begin=6, end=8) / 10.0
    
    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("ac", begin=1, end=2))

    @property
    def usb_a1_voltage(self) -> float:
        """USB A1 Port voltage (V).

        :returns: Voltage of the USB A1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ac", begin=2, end=4) / 10.0

    @property
    def usb_a1_current(self) -> float:
        """USB A1 Port current (A).

        :returns: Current of the USB A1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ac", begin=4, end=6) / 10.0
    
    @property
    def usb_a1_power(self) -> float:
        """USB A1 Port power (W).

        :returns: Power of the USB A1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ac", begin=6, end=8) / 10.0
