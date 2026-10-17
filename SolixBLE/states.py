"""Enums for SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from dataclasses import dataclass
from enum import Enum


class PortStatus(Enum):
    """The status of a port on the device."""

    #: The status of the port is unknown.
    UNKNOWN = -1

    #: The port is not connected / off.
    NOT_CONNECTED = 0

    #: The port is an output / on.
    OUTPUT = 1

    #: The port is an input / on.
    INPUT = 2

    @classmethod
    def from_input_only(cls, value: int) -> "PortStatus":
        """Build a status for a port that only supports being an input."""

        # If it would be an output (i.e 1) set it to input (i.e 2).
        if value == PortStatus.OUTPUT.value:
            value = PortStatus.INPUT.value

        return cls(value)


class ChargingStatus(Enum):
    """The status of charging/discharging on a device."""

    #: The status is unknown.
    UNKNOWN = -1

    #: The device is idle (Battery not charging or discharging).
    IDLE = 0

    #: The device is discharging.
    DISCHARGING = 1

    #: The device is charging.
    CHARGING = 2


class ChargingStatusF3800(Enum):
    """The charging type of an F3800."""

    #: The status is unknown.
    UNKNOWN = -1

    #: The device is idle.
    INACTIVE = 0

    #: The device is charging via solar.
    SOLAR = 1

    #: The device is charging via AC.
    AC = 2

    #: The device is charging via solar and AC.
    BOTH = 3


class LightStatus(Enum):
    """The status of the light on the device."""

    #: The status of the light is unknown.
    UNKNOWN = -1

    #: The light is off.
    OFF = 0

    #: The light is on low.
    LOW = 1

    #: The light is on medium.
    MEDIUM = 2

    #: The light is on high.
    HIGH = 3

    #: SOS mode. Not supported by all devices.
    SOS = 4


class LightMode(Enum):
    """The light mode of the device."""

    #: The light mode is unknown.
    UNKNOWN = -1

    #: Normal light mode.
    NORMAL = 0

    #: Mood light mode.
    MOOD = 1


class DisplayTimeout(Enum):
    """Display timeout on device in seconds. Only specific values are allowed."""

    #: The status of the display timeout is unknown.
    UNKNOWN = -1

    #: Never times out.
    S0 = 0

    #: 10 seconds.
    S10 = 10

    #: 20 seconds.
    S20 = 20

    #: 30 seconds.
    S30 = 30

    #: 60 seconds.
    S60 = 60

    #: 300 seconds (5m).
    S300 = 300

    #: 1800 seconds (30m).
    S1800 = 1800


class TemperatureUnit(Enum):
    """The status of the temperature unit of the device."""

    #: The display unit is unknown.
    UNKNOWN = -1

    #: Display unit Celsius.
    CELSIUS = 0

    #: Display unit is Fahrenheit.
    FAHRENHEIT = 1


class GridStatus(Enum):
    """The grid connection status."""

    #: The grid status is unknown.
    UNKNOWN = -1

    #: Grid is connected and OK.
    OK = 1

    #: Undocumented in API, but device operates as expected and
    #: outputs power to grid. Maybe a pure "dispense" state because
    #: SB2 can't draw power from the grid
    OK_AS_WELL_I_GUESS = 2

    #: Grid is connecting.
    CONNECTING = 3

    #: No grid connection.
    NO_GRID = 6


class SBUsageMode(Enum):
    """Usage mode of a Solarbank device."""

    #: The usage mode is unknown.
    UNKNOWN = -1

    #: Manual (schedule) mode.
    MANUAL = 1

    #: Smart meter mode.
    SMARTMETER = 2

    #: Smart plugs mode.
    SMARTPLUGS = 3

    #: Backup mode.
    BACKUP = 4

    #: Use time mode.
    USE_TIME = 5

    #: Smart mode.
    SMART = 7

    #: Time slot mode.
    TIME_SLOT = 8


class SBPowerCutoff(Enum):
    """Power cutoff threshold of a Solarbank device in %."""

    #: The cutoff threshold is unknown.
    UNKNOWN = -1

    #: 5 %.
    P5 = 5

    #: 10 %.
    P10 = 10


class PortOverload(Enum):
    """The overload status of a port."""

    #: Overload status is unknown.
    UNKNOWN = -1

    #: No overload event.
    NONE = 0

    #: USB C1 overload detected.
    USB_C1 = 8

    #: USB C2 overload detected.
    USB_C2 = 9

    #: USB C3 overload detected.
    USB_C3 = 10


class PortPriority(Enum):
    """The priority of a port in the Port Priority charging mode."""

    #: The priority is unknown.
    UNKNOWN = -1

    #: Not set, outside the Port Priority strategy.
    UNSET = 0

    #: Normal priority.
    NORMAL = 1

    #: Designated to take precedence.
    DESIGNATED = 2


class ClockFormat(Enum):
    """The format of the clock on the display of the device."""

    #: The clock format is unknown.
    UNKNOWN = -1

    #: 12 hour clock.
    HOUR_12 = 0

    #: 24 hour clock.
    HOUR_24 = 1


class ClockTheme(Enum):
    """The clock display theme of a Prime device, valued by its wire index."""

    #: The theme is unknown.
    UNKNOWN = -1

    #: Built-in theme, labelled Theme 1 in the app.
    THEME_1 = 0

    #: Built-in theme, labelled Theme 2 in the app.
    THEME_2 = 1

    #: Built-in theme, labelled Theme 3 in the app.
    THEME_3 = 2

    #: A theme from Anker's online catalog.
    CATALOG = 3

    #: An image uploaded in the app.
    CUSTOM = 5


@dataclass(frozen=True)
class PortSchedule:
    """A Prime port's daily schedule: an on-time and an off-time.

    Each time has its own switch, which is None when that time has never
    been set; its hour and minute then hold a stale default, so check the
    switch before the time. Weekdays run 0 (Monday) to 6 (Sunday), and no
    weekdays means the time fires once.
    """

    #: Whether the on-time is armed, or None if it has never been set.
    on_time_enabled: bool | None

    #: Hour the port turns on.
    on_time_hour: int

    #: Minute the port turns on.
    on_time_minute: int

    #: Weekdays the port turns on.
    on_time_weekdays: frozenset[int]

    #: Whether the off-time is armed, or None if it has never been set.
    off_time_enabled: bool | None

    #: Hour the port turns off.
    off_time_hour: int

    #: Minute the port turns off.
    off_time_minute: int

    #: Weekdays the port turns off.
    off_time_weekdays: frozenset[int]


@dataclass(frozen=True)
class PortTimer:
    """A Prime port's countdown auto-off timer.

    A disarmed timer keeps its last duration and remaining seconds.
    """

    #: Whether the countdown is armed.
    enabled: bool

    #: Countdown duration in seconds.
    seconds: int

    #: Seconds left on the countdown.
    remaining: int
