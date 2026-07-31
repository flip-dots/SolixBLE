"""Anker MagGo 3-in-1 Wireless Charger model.

.. moduleauthor:: radzio <469111+radzio@users.noreply.github.com>

"""

from ..const import DEFAULT_METADATA_FLOAT
from ..prime_device import PrimeDevice
from ..states import PortStatus

#: Command sent after connecting to start the telemetry stream. Like the
#: C1000G2, this charger streams nothing until it receives this subscribe
#: command.
CMD_SUBSCRIBE = "4200"
SUBSCRIBE_PAYLOAD = "a10121"


class MagGo3in1(PrimeDevice):
    """
    Anker MagGo 3-in-1 Wireless Charger.

    Use this class to connect and monitor the 3-in-1 wireless charging station
    (phone MagSafe pad, Apple Watch puck and earbuds pad). This model is also
    known as the A25x7.

    .. note::
       :collapsible: closed

       Reverse-engineered from BLE captures. Like the C1000G2 it uses the same
       encryption and telemetry framing as the other Prime devices, but it
       streams nothing until it receives a subscribe command (``4200``);
       telemetry then arrives on command ``4300``.

       The three wireless pads live in TLV parameters ``a2``/``a3``/``a4``, each
       eight bytes with the ``04 <status> <2b> <2b> <power LE>`` per-port shape
       used by the Prime chargers. Per-pad power was confirmed on hardware (an
       Apple Watch charging at 2.85 W read ``a2[6:8]`` little-endian ``0x011d``
       = 285). The two intermediate fields per pad are present but their scaling
       was not confidently confirmed for the wireless pads, so only power and
       status are exposed. The report carries no dedicated total field (``a5``
       is a constant ``04ffff`` and ``a6``/``fe`` are zeros), so ``power_out``
       is computed as the sum of the three pads.
    """

    #: This charger only reports telemetry on command ``4300``.
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("4300",)

    async def _post_connect(self) -> None:
        """Subscribe to telemetry once connected.

        The charger streams no telemetry until it receives this command, so we
        send it after every (re)connection.
        """
        await self._send_command(
            cmd=bytes.fromhex(CMD_SUBSCRIBE),
            payload=bytes.fromhex(SUBSCRIBE_PAYLOAD),
        )

    @property
    def pad_1(self) -> PortStatus:
        """Wireless pad 1 status.

        :returns: Status of pad 1.
        """
        return PortStatus(self._parse_int("a2", begin=1, end=2))

    @property
    def pad_1_power(self) -> float:
        """Wireless pad 1 power (W).

        :returns: Power delivered by pad 1 or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT
        return self._parse_int("a2", begin=6, end=8) / 100.0

    @property
    def pad_2(self) -> PortStatus:
        """Wireless pad 2 status.

        :returns: Status of pad 2.
        """
        return PortStatus(self._parse_int("a3", begin=1, end=2))

    @property
    def pad_2_power(self) -> float:
        """Wireless pad 2 power (W).

        :returns: Power delivered by pad 2 or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT
        return self._parse_int("a3", begin=6, end=8) / 100.0

    @property
    def pad_3(self) -> PortStatus:
        """Wireless pad 3 status.

        :returns: Status of pad 3.
        """
        return PortStatus(self._parse_int("a4", begin=1, end=2))

    @property
    def pad_3_power(self) -> float:
        """Wireless pad 3 power (W).

        :returns: Power delivered by pad 3 or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT
        return self._parse_int("a4", begin=6, end=8) / 100.0

    @property
    def power_out(self) -> float:
        """Total Power Out (watts).

        The telemetry report has no dedicated total field, so this is computed
        as the sum of the three per-pad power values.

        :returns: Total power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT
        return round(self.pad_1_power + self.pad_2_power + self.pad_3_power, 2)
