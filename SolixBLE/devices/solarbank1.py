"""Solarbank 1 power station model.

.. moduleauthor:: Simon Mariacher https://github.com/smariacher

"""

import struct
from dataclasses import dataclass

from ..const import (
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice
from ..states import ChargingStatus

CMD_SB_SET_SCHEDULE = "405e"

@dataclass
class ChargingSchedule:
    start_time: int
    """
    Start of schedule in minutes since midnight.
    """
    end_time: int
    """
    End of schedule in minutes since midnight.
    """
    output_wattage: int

    max_soc : int
    """
    Maximum SOC before Solarbank (presumably) goes into passthrough mode.
    """

    def __str__(self) -> str:
        """Convert the integer minutes back to HH:MM format for a nice display"""
        start_time_str = f"{self.start_time // 60:02d}:{self.start_time % 60:02d}"
        end_time_str = f"{self.end_time // 60:02d}:{self.end_time % 60:02d}"
        
        return (
            f"Charging Schedule:\n"
            f"   Time:    {start_time_str} - {end_time_str}\n"
            f"   Wattage: {self.output_wattage}W\n"
            f"   Max SOC: {self.max_soc}%"
        )

    def __post_init__(self):
        MIN_WATTAGE, MAX_WATTAGE = 0, 800 
        MIN_SOC, MAX_SOC = 0, 100
        
        if not (MIN_WATTAGE <= self.output_wattage <= MAX_WATTAGE):
            raise ValueError(
                f"Invalid output_wattage: {self.output_wattage}. "
                f"Must be between {MIN_WATTAGE} and {MAX_WATTAGE}."
            )
        
        if not (MIN_SOC <= self.max_soc <= MAX_SOC):
            raise ValueError(
                f"Invalid max_soc: {self.max_soc}. "
                f"Must be between {MIN_SOC} and {MAX_SOC}."
            )
        
        if not (self.end_time - self.start_time > 0):
            raise ValueError(
                f"Invalid time frame: Start: {self.start_time}, End: {self.end_time}. "
                f"Start time must be smaller than end time."
            )
        
        if not (self.start_time >= 0 and self.start_time <= 1440):
            raise ValueError(
                f"Invalid start time: {self.start_time}. "
                f"Start time cannot be less than 0 minutes or greater than 1440 minutes (24 hours)"
            )
        
        if not (self.end_time >= 0 and self.end_time <= 1440):
            raise ValueError(
                f"Invalid start time: {self.end_time}. "
                f"End time cannot be less than 0 minutes or greater than 1440 minutes (24 hours)"
            )

    @classmethod
    def from_time_strings(cls, start: str, end: str, output_wattage: int, max_soc: int) -> "ChargingSchedule":
        """Alternative constructor to create a schedule using HH:MM string formats."""
        return cls(
            start_time=cls.time_from_string(start),
            end_time=cls.time_from_string(end),
            output_wattage=output_wattage,
            max_soc=max_soc
        )

    @staticmethod
    def time_from_string(time: str) -> int:
        """
        Converts a string time in 24-hour HH:MM format to minutes since midnight.

        :param time: Time string in 24-hour HH:MM format.
        :returns: Minutes since midnight.
        """

        hours_str, minutes_str = time.split(":")
        hours = int(hours_str)
        minutes = int(minutes_str)
        
        if hours > 24:
            raise ValueError(f"Invalid hour value: {hours}. Hour must be between 0 and 24.")
        
        if minutes > 59:
            raise ValueError(f"Invalid minute value: {minutes}. Minute must be between 0 and 59.")
        
        if hours == 24 and minutes != 0:
            raise ValueError(f"Invalid time string: {time}. If hour is set to 24 then minutes may only be 0.")

        return hours * 60 + minutes


class Solarbank1(SolixBLEDevice):
    """
    SolarBank 1 Power Station.

    Use this class to connect and monitor a Solarbank 1 power station.
    This model is also known as the A17C0.

    .. note::
        This model was added using data from anker-solix-api as well as logging the actual anker app as described in the SolixBLE docs.
        It seems to be working so far, altough not everything has been reverse engineered so far.


    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    ChargingSchedule = ChargingSchedule # Added so the user only has to do one import

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
    def charging_status(self) -> ChargingStatus:
        """Retrieve the current charging status of the device.
        Parses the charging status from the device data. If device data is unavailable
        or does not contain charging status information, returns UNKNOWN.
        
        :returns: ChargingStatus enum member representing the current charging state
                  (e.g., CHARGING, DISCHARGING, IDLE, or UNKNOWN if status cannot be determined).
        """

        if self._data is None or "ad" not in self._data:
            return ChargingStatus.UNKNOWN

        value = self._parse_int("ad", begin=1)
        
        try:
            return ChargingStatus(value)
        except ValueError:
            return ChargingStatus.UNKNOWN

    @property
    def current_schedule(self) -> list[ChargingSchedule]:
        """Parse the active daily schedule block(s).

        :returns: A list of ChargingSchedule objects representing the current schedule,
                  or an empty list if no schedule is set.
        """
        if self._data is None or "ae" not in self._data:
            return []

        data = self._data["ae"]

        # Safely extract the raw bytes
        if isinstance(data, bytes):
            raw_bytes = data
        elif isinstance(data, dict):
            hex_str = data.get("hex", "")
            raw_bytes = bytes.fromhex(hex_str)
        else:
            return []

        # A valid payload has a 1-byte header, plus N * 8-byte blocks
        if len(raw_bytes) < 9 or (len(raw_bytes) - 1) % 8 != 0:
            return []

        schedules = []
        for i in range(1, len(raw_bytes), 8):
            chunk = raw_bytes[i : i + 8]

            start_min = int.from_bytes(chunk[0:2], byteorder="little")
            end_min = int.from_bytes(chunk[2:4], byteorder="little")
            watts = int.from_bytes(chunk[4:6], byteorder="little")
            limit = int.from_bytes(chunk[6:8], byteorder="little")

            schedules.append(
                ChargingSchedule(
                    start_time=start_min,
                    end_time=end_min,
                    output_wattage=watts,
                    max_soc=limit,
                )
            )

        return schedules

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

        return self._parse_string("b7", begin=1)

    @property
    def inverter_model(self) -> str:
        """Model of the connected inverter.

        :returns: Inverter model or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return self._parse_string("b8", begin=1)

    @property
    def min_load(self) -> int:
        """Maybe minimum wattage the battery will output?

        :returns: Don't know yet or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_INT

        return self._parse_int("b9", begin=1)  # TODO: Check this later

    async def set_schedule(self, schedules: list[ChargingSchedule]) -> None:
        """Set the daily charge/discharge schedule on the Solarbank 1.

        Sends a schedule write command (CMD 0x405e) to the device.
        The base class ``_send_command`` automatically appends the current
        session timestamp and handles AES-CBC encryption and framing.

        Pass an empty list to clear/delete all schedules.

        Examples::

            # Single schedule: charge-only midnight-06:00, cap at 80 % SOC
            await sb1.set_schedule([
                ChargingSchedule(start=0, end=360, output_wattage=0, max_soc=80)
            ])

            # Two back-to-back schedules
            await sb1.set_schedule([
                ChargingSchedule(start=0, end=360, output_wattage=0, max_soc=80),
                ChargingSchedule(start=360, end=870, output_wattage=240, max_soc=80),
            ])

            # Clear all schedules
            await sb1.set_schedule([])

        :param schedules: List of ChargingSchedule objects. The device-side upper limit
            is unknown but confirmed to be at least 10.
        :raises ConnectionError: If not connected/negotiated to the device.
        """

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
        for schedule in schedules:
            schedule_bytes += struct.pack(
                "<HHHH",
                schedule.start_time,
                schedule.end_time,
                schedule.output_wattage,
                schedule.max_soc,
            )

        # LENGTH = 1 (type byte) + len(schedule_bytes)
        payload += bytes([0xA3, 1 + len(schedule_bytes), 0x04]) + schedule_bytes

        await self._send_command(bytes.fromhex(CMD_SB_SET_SCHEDULE), payload)
