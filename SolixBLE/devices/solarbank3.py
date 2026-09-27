"""Solarbank 3 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..const import DEFAULT_METADATA_FLOAT, DEFAULT_METADATA_STRING
from ..solix_device import SolixBLEDevice


class Solarbank3(SolixBLEDevice):
    """
    SolarBank 3 Power Station.

    Use this class to connect and monitor a Solarbank 3 power station.
    This model is also known as the A17C5.

    .. note::
        This model was added using data from anker-solix-api. It has not been
        tested!

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
    def battery_percentage_aggregate(self) -> float:
        """Battery Percentage average across all batteries.

        :returns: Percentage charge of battery or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a5", begin=1) / 10.0

    @property
    def battery_health(self) -> float:
        """Battery health as a percentage.

        :returns: Percentage of battery health or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("a6", begin=1) / 10.0

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a7", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Total Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int("ab", begin=1)

    @property
    def pv_yield(self) -> int:
        """Solar power generated.

        :returns: Total solar power generated or default int value.
        """
        return self._parse_int("ac", begin=1)

    @property
    def house_demand(self) -> int:
        """House demand power.

        :returns: Power used by house or default int value.
        """
        return self._parse_int("b1", begin=1)

    @property
    def house_consumption(self) -> int:
        """House consumption power.

        Don't ask me how this differs from house demand, I have no idea.

        :returns: Power used by house or default int value.
        """
        return self._parse_int("b2", begin=1)

    @property
    def battery_power(self) -> int:
        """Battery power in and out.

        I don't know what direction is which.

        :returns: Power in/out of battery or default int value.
        """
        return self._parse_int("b6", begin=1, signed=True)

    @property
    def charged_energy(self) -> int:
        """Energy into battery?

        :returns: Energy into battery or default int value.
        """
        return self._parse_int("b7", begin=1)

    @property
    def discharged_energy(self) -> int:
        """Energy out of battery?

        :returns: Energy out of battery or default int value.
        """
        return self._parse_int("b8", begin=1)

    @property
    def grid_power(self) -> int:
        """Grid power in and out.

        I don't know what direction is which.

        :returns: Power in/out of grid or default int value.
        """
        return self._parse_int("bd", begin=1, signed=True)

    @property
    def grid_import_energy(self) -> int:
        """Grid import energy.

        :returns: Total energy imported from grid or default int value.
        """
        return self._parse_int("be", begin=1)

    @property
    def grid_export_energy(self) -> int:
        """Grid export energy.

        :returns: Total energy exported to grid or default int value.
        """
        return self._parse_int("bf", begin=1)

    @property
    def solar_pv_1_power_in(self) -> int:
        """Solar Power In for port 1.

        :returns: Solar power in or default int value.
        """
        return self._parse_int("c7", begin=1)

    @property
    def solar_pv_2_power_in(self) -> int:
        """Solar Power In for port 2.

        :returns: Solar power in or default int value.
        """
        return self._parse_int("c8", begin=1)

    @property
    def solar_pv_3_power_in(self) -> int:
        """Solar Power In for port 3.

        :returns: Solar power in or default int value.
        """
        return self._parse_int("c9", begin=1)

    @property
    def solar_pv_4_power_in(self) -> int:
        """Solar Power In for port 4.

        :returns: Solar power in or default int value.
        """
        return self._parse_int("ca", begin=1)

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("cc", begin=1, signed=True)

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int("d3", begin=1)

    @property
    def grid_to_home_power(self) -> int:
        """Grid to home power.

        :returns: Power from grid to home or default int value.
        """
        return self._parse_int("d5", begin=1)
