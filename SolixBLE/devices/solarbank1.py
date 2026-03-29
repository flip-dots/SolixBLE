"""Solarbank 1 power station model.

.. moduleauthor:: Simon Mariacher https://github.com/smariacher

"""

import struct

from ..const import (
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice

CMD_SB_SET_SCHEDULE = "405e"


class Solarbank1(SolixBLEDevice):
    """
    SolarBank 1 Power Station.

    Use this class to connect and monitor a Solarbank 1 power station.
    This model is also known as the A17C0.

    .. note::
        This model was added using data from anker-solix-api as well as logging the actual anker app.
        It seems to be working so far, altough not everything has been reverse engineered so far.


    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("a2", begin=1)

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a3", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a6", begin=1))])

    @property
    def software_version_controller(self) -> str:
        """Software version of the controller.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a7", begin=1))])

    @property
    def hardware_version(self) -> str:
        """Hardware version.

        :returns: Hardware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a8", begin=1))])

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("aa", begin=1, signed=True)

    @property
    def solar_power_in(self) -> float:
        """Total Solar Power In.

        :returns: Total solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ab", begin=1) / 10.0

    @property
    def output_power(self) -> int:
        """Output power.

        :returns: Total power out in watts or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_INT

        return self._parse_int("ac", begin=1)

    @property
    def charging_status(self) -> int:
        """Charging status.

        :returns: Charging status or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def current_schedule(self) -> str:
        """Parse the active daily schedule block(s).

        :returns: A human-readable string describing the current schedule or a message if no schedule is set.
        """
        if self._data is None or "ae" not in self._data:
            return "No Schedule Set"

        data = self._data["ae"]

        # Safely extract the raw bytes
        if isinstance(data, bytes):
            raw_bytes = data
        elif isinstance(data, dict):
            hex_str = data.get("hex", "")
            raw_bytes = bytes.fromhex(hex_str)
        else:
            return "Invalid data format"

        # A valid payload has a 1-byte header, plus N * 8-byte blocks
        if len(raw_bytes) < 9 or (len(raw_bytes) - 1) % 8 != 0:
            return f"Unknown structure: {raw_bytes.hex()}"

        # We can ignore the first byte (04 header) and loop through the rest
        periods = []
        for i in range(1, len(raw_bytes), 8):
            chunk = raw_bytes[i : i + 8]

            start_min = int.from_bytes(chunk[0:2], byteorder="little")
            end_min = int.from_bytes(chunk[2:4], byteorder="little")
            watts = int.from_bytes(chunk[4:6], byteorder="little")
            limit = int.from_bytes(chunk[6:8], byteorder="little")

            start_time = f"{start_min // 60:02d}:{start_min % 60:02d}"
            end_time = f"{end_min // 60:02d}:{end_min % 60:02d}"

            periods.append(f"[{start_time}-{end_time} @ {watts}W, Limit: {limit}%]")

        return " | ".join(periods)

    @property
    def battery_charge_power(self) -> float:
        """Battery charging power.

        :returns: Total battery power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b0", begin=1) / 100.0

    @property
    def pv_yield(self) -> float:
        """Solar power generated.

        :returns: Total solar power generated or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b1", begin=1) / 10000.0

    @property
    def charged_energy(self) -> float:
        """Probably aggregated energy charged in Wh?

        :returns: Charged energy or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b2", begin=1) / 10000.0

    @property
    def output_energy(self) -> float:
        """Output energy.

        :returns: Total energy output or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b3", begin=1) / 10000.0

    @property
    def inverter_brand(self) -> str:
        """Brand of the connected inverter.

        :returns: Inverter brand or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return self._parse_string("b7", begin=1)  # TODO: Check this later

    @property
    def inverter_model(self) -> str:
        """Model of the connected inverter.

        :returns: Inverter model or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return self._parse_string("b8", begin=1)  # TODO: Check this later

    @property
    def min_load(self) -> int:
        """Maybe minimum wattage the battery will output?

        :returns: Don't know yet or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return self._parse_int("b9", begin=1)  # TODO: Check this later

    async def set_schedule(self, schedules: list[dict]) -> None:
        """Set the daily charge/discharge schedule on the Solarbank 1.

        Sends a schedule write command (CMD 0x405e) to the device.
        The base class ``_send_command`` automatically appends the current
        session timestamp and handles AES-CBC encryption and framing.

        Each schedule entry is a ``dict`` with the following keys:

        =========  =======  =====================================================
        Key        Type     Description
        =========  =======  =====================================================
        ``start``  ``str``  Start time in ``"HH:MM"`` format, e.g. ``"00:00"``
        ``end``    ``str``  End time   in ``"HH:MM"`` format, e.g. ``"06:00"``
        ``power``  ``int``  Output wattage; use ``0`` for charge-only mode
        ``soc``    ``int``  Max battery SOC cap as a percentage (e.g. ``80``)
        =========  =======  =====================================================

        Pass an empty list to clear/delete all schedules.

        Examples::

            # Single schedule: charge-only midnight-06:00, cap at 80 % SOC
            await sb1.set_schedule([
                {"start": "00:00", "end": "06:00", "power": 0, "soc": 80}
            ])

            # Two back-to-back schedules
            await sb1.set_schedule([
                {"start": "00:00", "end": "06:00", "power":   0, "soc": 80},
                {"start": "06:00", "end": "14:30", "power": 240, "soc": 80},
            ])

            # Clear all schedules
            await sb1.set_schedule([])

        :param schedules: List of schedule dicts. The device-side upper limit
            is unknown but confirmed to be at least 10.
        :raises ValueError: If a time string is not in ``"HH:MM"`` format, or
            if ``power``/``soc`` values are out of range.
        :raises ConnectionError: If not connected/negotiated to the device.
        """

        for i, s in enumerate(schedules):
            if not (0 <= s["power"] <= 800):
                raise ValueError(
                    f"Schedule {i}: power must be 0–800 W, got {s['power']}"
                )
            if not (1 <= s["soc"] <= 100):
                raise ValueError(f"Schedule {i}: soc must be 1–100 %, got {s['soc']}")

        def _time_to_minutes(t: str) -> int:
            """Convert 'HH:MM' string to minutes since midnight."""
            try:
                h, m = t.split(":")
                return int(h) * 60 + int(m)
            except (ValueError, AttributeError):
                raise ValueError(f"Time '{t}' is not in HH:MM format")

        # ── Build plaintext TLV payload ────────────────────────────────────
        #
        # Format per field:  <ID 1B> <LENGTH 1B> <TYPE 1B> <DATA nB>
        # LENGTH counts the TYPE byte plus data bytes (i.e. len(DATA) + 1).
        #
        # 0xa1 — command marker: no data, type byte 0x21 only
        payload = bytes([0xA1, 0x01, 0x21])

        # 0xa2 — schedule count: type 0x01, 1-byte unsigned int
        payload += bytes([0xA2, 0x02, 0x01, len(schedules)])

        # 0xa3 — schedule blocks: type 0x04, then N × 8-byte entries
        #   Each entry: [start_min u16le][end_min u16le][power_W u16le][soc_% u16le]
        schedule_bytes = b""
        for s in schedules:
            schedule_bytes += struct.pack(
                "<HHHH",
                _time_to_minutes(s["start"]),
                _time_to_minutes(s["end"]),
                s["power"],
                s["soc"],
            )

        # LENGTH = 1 (type byte) + len(schedule_bytes)
        payload += bytes([0xA3, 1 + len(schedule_bytes), 0x04]) + schedule_bytes

        await self._send_command(bytes.fromhex(CMD_SB_SET_SCHEDULE), payload)
