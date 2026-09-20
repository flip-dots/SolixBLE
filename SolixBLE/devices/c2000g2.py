"""C2000(X) Gen 2 power station model.

.. moduleauthor:: kb1ibt

"""

from ..const import DEFAULT_METADATA_INT, DEFAULT_METADATA_STRING
from .c1000g2 import (
    C1000G2,
    CMD_AC_OUTPUT,
    CMD_SUBSCRIBE,
    PARAMETERS_SUBSCRIBE,
    _version,
)
from .c2000g2_summary import SUMMARY_MAPS

#: Realtime telemetry latch. Once armed the device pushes telemetry on its own.
CMD_REALTIME = "4057"

#: Routing byte the ``4057`` latch requires.
REALTIME_ROUTING = "21"

PARAMETERS_REALTIME_ON = {
    "a1": {
        "value": REALTIME_ROUTING,
    },
    "a2": {
        "type": 1,
        "value": 1,
    },
}

#: The AC group takes its charging power limit at a4 as a 16-bit little endian
#: integer.
PARAMETERS_AC_CHARGING_POWER = {
    "a1": {
        "value": "21",
    },
    "a4": {
        "type": 2,
        "value": lambda watts: watts.to_bytes(length=2, byteorder="little"),
    },
}

#: Range the AC charging-power limit accepts (W).
MIN_AC_CHARGING_POWER = 500
MAX_AC_CHARGING_POWER = 1800

#: ``subPackageConnectionStatus`` value meaning a pack is actually attached.
SUB_PACKAGE_CONNECTED = 1

#: Bytes of the ``c0`` block that follow its variable-length serial.
SUB_PACKAGE_TAIL_LENGTH = 15


class C2000G2(C1000G2):
    """
    C2000(X) Gen 2 Power Station.

    Use this class to connect, monitor and control a Gen 2 C2000(X) power
    station. This model is also known as the A1783.

    .. note::
       :collapsible: closed

       The C2000 G2 shares the C1000 G2's Gen 2 BLE stack (the ``c421``/``c900``
       telemetry framing and field map, the ``4100`` poll, and the ``4101``/
       ``4102``/``4103`` control groups), so everything but what is listed
       here comes from :class:`~SolixBLE.devices.c1000g2.C1000G2`. It
       negotiates on the encrypted path, which its current firmware requires.

       On top of that it arms the realtime latch on connect, limits the AC
       charging power to its own 500-1800 W range, and decodes the ``c0``
       expansion-battery block for the BP2000.

       The device also posts a ``c490`` device summary about every nine
       minutes: a protobuf frame with its own field set (total input power, DC
       input voltage, the AC/DC energy ledgers and the per-pack BMS block),
       decoded into :attr:`summary` against the schema the frame names. It
       is gated twice, by the realtime latch this class arms on connect and by
       a schema map the device only holds after reaching the vendor cloud, and
       it cannot be requested. A unit kept off the network may never post one.
    """

    _DEFAULT_ENCRYPTED_NEGOTIATION: bool = True

    #: The Gen 2 telemetry set plus the ``c490`` device-summary post.
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("c421", "c900", "c490")

    #: ``c490`` is a protobuf blob, decoded into :attr:`summary`.
    _PROTOBUF_TELEMETRY_COMMANDS: tuple[str, ...] = ("c490",)

    _SUMMARY_MAPS = SUMMARY_MAPS

    async def _post_connect(self) -> None:
        """Subscribe to telemetry and arm the realtime latch once connected.

        The Gen 2 streams nothing until it receives the subscribe command, and
        pushes changes on its own only while the realtime latch is armed. The
        latch persists across sessions, and arming it again is harmless.
        """
        await self._send_command(cmd=CMD_SUBSCRIBE, parameters=PARAMETERS_SUBSCRIBE)
        await self._send_command(cmd=CMD_REALTIME, parameters=PARAMETERS_REALTIME_ON)

    #####################
    # Expansion battery #
    #####################

    @property
    def _sub_package(self) -> bytes | None:
        """Fixed-layout tail of the ``c0`` block, past the variable-length serial.

        :returns: The bytes from ``subPackageNumber`` onwards, or None if the
            tag is absent or too short to contain them.
        """
        if self._data is None or "c0" not in self._data:
            return None

        block = bytes(self._data["c0"].value or b"")
        if not block:
            return None

        fields = block[1 + block[0] :]
        return fields if len(fields) >= SUB_PACKAGE_TAIL_LENGTH else None

    @property
    def num_expansion(self) -> int:
        """Number of expansion batteries.

        .. note::
           :collapsible: closed

           The ``c0`` block is emitted whether or not a pack is connected; with
           none attached its fields are padded with sentinel values, so only the
           connection flag inside it says whether a pack is present. The C2000
           G2 has a single expansion slot.

        :returns: Number of expansion batteries or default int value.
        """
        fields = self._sub_package
        if fields is None:
            return DEFAULT_METADATA_INT

        return int(fields[12] == SUB_PACKAGE_CONNECTED)

    @property
    def serial_number_expansion(self) -> str:
        """Serial number of the expansion battery.

        :returns: Serial number, or default str value if no pack is attached.
        """
        if self._data is None or self.num_expansion < 1:
            return DEFAULT_METADATA_STRING

        block = bytes(self._data["c0"].value or b"")
        return block[1 : 1 + block[0]].decode("ascii")

    @property
    def temperature_expansion(self) -> int:
        """Temperature of the expansion battery (C).

        :returns: Temperature in degrees C, or default int value if no pack is
            attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_INT

        return int.from_bytes(fields[5:6], byteorder="little", signed=True)

    @property
    def battery_percentage_expansion(self) -> int:
        """Battery percentage of the expansion battery.

        :returns: Percentage charge, or default int value if no pack is attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_INT

        return fields[7]

    @property
    def battery_health_expansion(self) -> int:
        """Battery health of the expansion battery as a percentage.

        :returns: Percentage health, or default int value if no pack is attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_INT

        return fields[8]

    @property
    def software_version_expansion(self) -> str:
        """Software version of the expansion battery.

        :returns: Firmware version, or default str value if no pack is attached.
        """
        fields = self._sub_package
        if fields is None or self.num_expansion < 1:
            return DEFAULT_METADATA_STRING

        return _version(fields[1:5])

    ##################
    # Device summary #
    ##################

    def _summary_kwh(self, name: str) -> float | None:
        """Read an energy ledger from the summary as kWh.

        :param name: Summary field name holding watt-hours.
        :returns: Energy in kWh, or None until a summary has been received.
        """
        value = self._data_summary.get(name)
        return value / 1000.0 if isinstance(value, (int, float)) else None

    @property
    def ac_charged_energy(self) -> float | None:
        """Total energy charged through the AC input in kWh.

        Reported in the device summary, which the device posts about every
        nine minutes and only once it holds a schema map (see the class note).

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_charge_energy_wh")

    @property
    def dc_charged_energy(self) -> float | None:
        """Total energy charged through the DC input in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_charge_energy_wh")

    @property
    def ac_output_energy(self) -> float | None:
        """Total energy discharged through the AC output in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_discharge_energy_wh")

    @property
    def dc_output_energy(self) -> float | None:
        """Total energy discharged through the DC outputs in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_discharge_energy_wh")

    @property
    def dc_input_voltage(self) -> float | None:
        """Voltage at the DC (solar/car) input in volts.

        Reported in the device summary, so it is at most about nine minutes old.

        :returns: Voltage in V, or None until a summary has been received.
        """
        value = self._data_summary.get("dc_input_voltage")
        return float(value) if isinstance(value, (int, float)) else None

    ############
    # Commands #
    ############

    async def set_ac_charging_power(self, watts: int) -> None:
        """Set the AC charging power limit in watts.

        :param watts: AC charging power limit, 500-1800 W.
        :raises ValueError: If power value is out of valid range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if not MIN_AC_CHARGING_POWER <= watts <= MAX_AC_CHARGING_POWER:
            msg = (
                f"AC charging power must be between {MIN_AC_CHARGING_POWER} "
                f"and {MAX_AC_CHARGING_POWER} W"
            )
            raise ValueError(msg)

        await self._send_command(
            cmd=CMD_AC_OUTPUT,
            parameters=PARAMETERS_AC_CHARGING_POWER,
            watts=watts,
        )
