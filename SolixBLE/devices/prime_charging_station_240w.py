"""Anker Prime Charging Station (240W) model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..const import DEFAULT_METADATA_BOOL, DEFAULT_METADATA_FLOAT
from .prime_usb_charger import PrimeUsbCharger


class PrimeChargingStation240w(PrimeUsbCharger):
    """
    Anker Prime Charging Station (240W) model.

    Use this class to connect and monitor the 240w charging station. This model
    is also known as the A91B2. It shares the four USB-C and two USB-A ports of
    the 250W charger (decoded by the base class) and adds two switchable 120V AC
    outlets and a display.

    .. note::
        Modelled on the anker-solix-api ``A91B2`` map. The AC-outlet switch
        states are decoded here; AC-outlet power/voltage and the display state
        are not yet mapped (they are absent from the cloud map too) and await a
        live capture with an AC load.
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    async def _post_connect(self) -> None:
        """No post-connect subscribe yet -- the station's enable sequence is unknown.

        The 250W charger's registration (command 4027) is rejected by the station
        (it drops the link), and no subscribe alone starts its stream, so the base
        PrimeDevice._post_connect is not used here. The correct post-ECDH enable
        needs an Anker-app handshake capture; until then the station negotiates and
        stays connected but does not stream telemetry.
        """
        return

    @property
    def usb_total_power_out(self) -> float:
        """Total USB output power across the six USB ports (W).

        Excludes the AC outlets, whose power is not yet decoded.

        :returns: Sum of the six USB port powers or default float value.
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
    def ac_1_switch(self) -> bool:
        """AC outlet 1 on/off switch state.

        :returns: True when AC outlet 1 is switched on or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("aa", begin=1, end=2))

    @property
    def ac_2_switch(self) -> bool:
        """AC outlet 2 on/off switch state.

        :returns: True when AC outlet 2 is switched on or default bool value.
        """
        if self._data is None:
            return DEFAULT_METADATA_BOOL

        return bool(self._parse_int("ab", begin=1, end=2))
