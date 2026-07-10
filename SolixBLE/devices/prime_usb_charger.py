"""Shared base for Anker Prime USB chargers (A2345 250W, A91B2 240W station).

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..const import DEFAULT_METADATA_FLOAT, DEFAULT_METADATA_STRING
from ..prime_device import PrimeDevice
from ..states import PortStatus


class PrimeUsbCharger(PrimeDevice):
    """Base for Prime chargers that stream per-USB-port telemetry on ``ca00``.

    The four USB-C and two USB-A ports live in parameters ``a4`` (C1) through
    ``a9`` (A2), each a ``04 <status> <u16 mV LE> <u16 mA LE> <u16 cW LE>`` block.
    Subclasses add their model-specific fields (USB switches on the 250W charger,
    AC-outlet switches on the 240W station).
    """

    #: Prime chargers stream telemetry on command ``ca00`` (msgtype ``0a00``).
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("ca00",)

    @property
    def serial_number(self) -> str:
        """Device serial number.

        Read from the negotiation handshake; the telemetry frame does not carry
        the serial number.

        :returns: Device serial number or default str value.
        """
        value = (getattr(self, "_device_info", None) or {}).get("a4", b"")
        return value.decode("ascii", "ignore") if value else DEFAULT_METADATA_STRING

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(self._parse_int("a4", begin=1, end=2))

    @property
    def usb_c1_voltage(self) -> float:
        """USB C1 Port voltage (V).

        :returns: Voltage of the USB C1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a4", begin=2, end=4) / 1000.0

    @property
    def usb_c1_current(self) -> float:
        """USB C1 Port current (A).

        :returns: Current of the USB C1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a4", begin=4, end=6) / 1000.0

    @property
    def usb_c1_power(self) -> float:
        """USB C1 Port power (W).

        :returns: Power of the USB C1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a4", begin=6, end=8) / 100.0

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(self._parse_int("a5", begin=1, end=2))

    @property
    def usb_c2_voltage(self) -> float:
        """USB C2 Port voltage (V).

        :returns: Voltage of the USB C2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a5", begin=2, end=4) / 1000.0

    @property
    def usb_c2_current(self) -> float:
        """USB C2 Port current (A).

        :returns: Current of the USB C2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a5", begin=4, end=6) / 1000.0

    @property
    def usb_c2_power(self) -> float:
        """USB C2 Port power (W).

        :returns: Power of the USB C2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a5", begin=6, end=8) / 100.0

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(self._parse_int("a6", begin=1, end=2))

    @property
    def usb_c3_voltage(self) -> float:
        """USB C3 Port voltage (V).

        :returns: Voltage of the USB C3 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a6", begin=2, end=4) / 1000.0

    @property
    def usb_c3_current(self) -> float:
        """USB C3 Port current (A).

        :returns: Current of the USB C3 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a6", begin=4, end=6) / 1000.0

    @property
    def usb_c3_power(self) -> float:
        """USB C3 Port power (W).

        :returns: Power of the USB C3 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a6", begin=6, end=8) / 100.0

    @property
    def usb_port_c4(self) -> PortStatus:
        """USB C4 Port Status.

        :returns: Status of the USB C4 port.
        """
        return PortStatus(self._parse_int("a7", begin=1, end=2))

    @property
    def usb_c4_voltage(self) -> float:
        """USB C4 Port voltage (V).

        :returns: Voltage of the USB C4 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a7", begin=2, end=4) / 1000.0

    @property
    def usb_c4_current(self) -> float:
        """USB C4 Port current (A).

        :returns: Current of the USB C4 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a7", begin=4, end=6) / 1000.0

    @property
    def usb_c4_power(self) -> float:
        """USB C4 Port power (W).

        :returns: Power of the USB C4 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a7", begin=6, end=8) / 100.0

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(self._parse_int("a8", begin=1, end=2))

    @property
    def usb_a1_voltage(self) -> float:
        """USB A1 Port voltage (V).

        :returns: Voltage of the USB A1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a8", begin=2, end=4) / 1000.0

    @property
    def usb_a1_current(self) -> float:
        """USB A1 Port current (A).

        :returns: Current of the USB A1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a8", begin=4, end=6) / 1000.0

    @property
    def usb_a1_power(self) -> float:
        """USB A1 Port power (W).

        :returns: Power of the USB A1 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a8", begin=6, end=8) / 100.0

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB A2 Port Status.

        :returns: Status of the USB A2 port.
        """
        return PortStatus(self._parse_int("a9", begin=1, end=2))

    @property
    def usb_a2_voltage(self) -> float:
        """USB A2 Port voltage (V).

        :returns: Voltage of the USB A2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a9", begin=2, end=4) / 1000.0

    @property
    def usb_a2_current(self) -> float:
        """USB A2 Port current (A).

        :returns: Current of the USB A2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a9", begin=4, end=6) / 1000.0

    @property
    def usb_a2_power(self) -> float:
        """USB A2 Port power (W).

        :returns: Power of the USB A2 port or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a9", begin=6, end=8) / 100.0
