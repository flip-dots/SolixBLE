"""Solarbank 2 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from enum import Enum

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_STRING,
)
from ..solix_device import SolixBLEDevice
from ..states import GridStatus, LightMode, SBPowerCutoff, SBUsageMode, TemperatureUnit


class MaxLoadSB2(Enum):
    """
    Maximum output power of the Solarbank 2 in watts.
    
    Only specific values are allowed.
    """

    #: The maximum load is unknown.
    UNKNOWN = -1

    #: 350 watts.
    W350 = 350

    #: 600 watts.
    W600 = 600

    #: 800 watts.
    W800 = 800

    #: 1000 watts.
    W1000 = 1000


class Solarbank2(SolixBLEDevice):
    """
    SolarBank 2 Power Station.

    Use this class to connect and monitor a Solarbank 2 power station.
    This model is also known as the A17C1.

    .. note::
        It should be possible to add more sensors. I think devices with lots of
        telemetry values split them up into multiple messages but I have not
        played around with this yet. That and I am being a bit conservative with
        these initial implementations, if you want more sensors and are willing
        to help with testing feel free to raise a GitHub issue.

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
    def software_version_expansion(self) -> str:
        """Software version of any expansion batteries.

        If there is no expansion battery then it will be "0".

        :returns: Firmware version or default str value.
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
    def ac_power_out(self) -> float:
        """AC Power Out.

        :returns: Total AC power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ac", begin=1) / 10.0

    @property
    def battery_percentage_aggregate(self) -> int:
        """Battery Percentage average across all batteries.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("ad", begin=1)

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
        """Solar energy generated in kWh.

        :returns: Total solar energy generated or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b1", begin=1) / 10000.0

    @property
    def charged_energy(self) -> float:
        """Total accumulated energy that passed through the battery in kWh

        :returns: The amount of energy or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        # The / 100 000 is correct despite all other divisors being 10 000.
        # This is the "Storage" stats field in the Anker app
        return self._parse_int("b2", begin=1) / 100000.0

    @property
    def output_energy(self) -> float:
        """Output energy in kWh.

        :returns: Total energy output or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b3", begin=1) / 10000.0

    @property
    def battery_discharge_power(self) -> float:
        """Battery discharging power.

        :returns: Total battery power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b7", begin=1) / 100.0

    @property
    def grid_to_home_power(self) -> float:
        """Grid to home power.

        :returns: Power from grid to home or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bc", begin=1) / 10.0

    @property
    def pv_to_grid_power(self) -> float:
        """PV to grid power.

        :returns: Power from PV to grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bd", begin=1) / 10.0

    @property
    def grid_import_energy(self) -> float:
        """Grid import energy.

        :returns: Total energy imported from grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("be", begin=1) / 10000.0

    @property
    def grid_export_energy(self) -> float:
        """Grid export energy.

        :returns: Total energy exported to grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bf", begin=1) / 10000.0

    @property
    def house_demand(self) -> float:
        """House demand power.

        :returns: Power used by house or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c4", begin=1) / 10.0

    @property
    def ac_power_out_sockets(self) -> float:
        """AC Power Out to sockets.

        :returns: AC power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c8", begin=1) / 10.0

    @property
    def consumed_energy(self) -> float:
        """Consumed energy by house.

        :returns: Total energy consumed by house or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c9", begin=1) / 10000.0

    @property
    def solar_pv_1_power_in(self) -> float:
        """Solar Power In for port 1.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ca", begin=1) / 10.0

    @property
    def solar_pv_2_power_in(self) -> float:
        """Solar Power In for port 2.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cb", begin=1) / 10.0

    @property
    def solar_pv_3_power_in(self) -> float:
        """Solar Power In for port 3.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cc", begin=1) / 10.0

    @property
    def solar_pv_4_power_in(self) -> float:
        """Solar Power In for port 4.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cd", begin=1) / 10.0

    @property
    def power_out(self) -> float:
        """Total Power Out.

        :returns: Total power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("d3", begin=1) / 10.0

    @property
    def error_code(self) -> int:
        """Device error code.

        :returns: Error code or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Temperature unit setting.

        :returns: Temperature unit (Celsius or Fahrenheit).
        """
        return TemperatureUnit(self._parse_int("a9", begin=1))

    @property
    def output_cutoff_data(self) -> SBPowerCutoff:
        """
        Output cutoff threshold in %.

        Minimum battery SOC to maintain.

        :returns: Output cutoff battery SOC threshold.
        """
        return SBPowerCutoff(self._parse_int("b4", begin=1))

    @property
    def lowpower_input_data(self) -> int:
        """Low power input data.

        :returns: Low power input data or default int value.
        """
        return self._parse_int("b5", begin=1)

    @property
    def input_cutoff_data(self) -> SBPowerCutoff:
        """Input cutoff threshold in %.

        :returns: Input cutoff battery SOC threshold.
        """
        return SBPowerCutoff(self._parse_int("b6", begin=1))

    @property
    def max_load(self) -> MaxLoadSB2:
        """
        Maximum output power in watts.
        
        Maximum legal value depends on country of operation.

        :returns: Maximum load as a MaxLoadSB2 enum value.
        """
        return MaxLoadSB2(self._parse_int("c2", begin=1))

    @property
    def usage_mode(self) -> SBUsageMode:
        """Usage mode.

        :returns: Usage mode as a SBUsageMode enum value.
        """
        return SBUsageMode(self._parse_int("c6", begin=1))

    @property
    def home_load_preset(self) -> int:
        """Home load preset in watts.

        :returns: Home load preset in watts or default int value.
        """
        return self._parse_int("c7", begin=1)

    @property
    def light_mode(self) -> LightMode:
        """Light mode. Normal or Mood.

        :returns: Light mode.
        """
        return LightMode(self._parse_int("d2", begin=1))

    @property
    def grid_status(self) -> GridStatus:
        """Grid connection status.

        :returns: Grid status.
        """
        return GridStatus(self._parse_int("e0", begin=1))

    @property
    def light_on(self) -> bool | None:
        """Whether the light is switched on.
        Original value is inverted because it is called "light_off_switch"

        :returns: True if light is on, False if off.
        """
        return (
            not bool(self._parse_int("e1", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    @property
    def battery_heating(self) -> bool | None:
        """Whether the battery is currently heating.

        :returns: True if heating, False if not heating.
        """
        return (
            bool(self._parse_int("e8", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

