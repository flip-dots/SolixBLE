"""Anker Prime Charger (250W) model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from collections.abc import Collection
from dataclasses import asdict, dataclass
from enum import Enum

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
    FlagsEnum,
    Int8ub,
    Int32ul,
    Padding,
    Struct,
)

from SolixBLE.const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.constructs import (
    DEVICE_IDENTITIES,
    DISPLAY,
    FIRMWARE_UPDATE,
    IDENTITY_NONE,
    USB_PD_IDENTITIES,
    WeekdayMask,
)
from SolixBLE.prime_device import (
    CMD_CLOCK_FORMAT,
    CMD_DISPLAY_BRIGHTNESS,
    CMD_DISPLAY_TIMEOUT,
    DISPLAY_TIMEOUT_CODES,
    DISPLAY_TIMEOUTS,
    KEEP_ALIVE_INTERVAL,
    PrimeDevice,
)
from SolixBLE.states import (
    ClockFormat,
    ClockTheme,
    DisplayTimeout,
    PortPriority,
    PortSchedule,
    PortStatus,
    PortTimer,
)
from SolixBLE.usb_pd_identity import device_name, vendor_name

#: The wire index the port commands take for each port: USB C1-C4 are 0-3,
#: and 4 switches both USB A outlets together.
PORT_INDEX = {
    "usb_c1": 0,
    "usb_c2": 1,
    "usb_c3": 2,
    "usb_c4": 3,
    "usb_a1_a2": 4,
}

#: A USB-PD vendor ID that means no device (``{0xfffa, 0xfffb}``), or one that
#: answered without device identity (``{0, 0}``).
PD_VID_NONE = (0xFFFA, 0x0000)

CMD_DISPLAY = 0x205
CMD_CHARGING_MODE = 0x206
CMD_PRIORITY_PORTS = 0x20C
CMD_KNOB_DIRECTION = 0x20E
CMD_SCREENSAVER_WINDOW = 0x213
CMD_COMPATIBILITY_MODE = 0x214
CMD_DEVICE_IDENTIFICATION = 0x223

#: The screensaver window (snapshot ``b9``, command ``4213``): the hour and
#: minute it opens and closes, then the days it applies.
SCREENSAVER_WINDOW = Struct(
    "start_hour" / Int8ub,
    "start_minute" / Int8ub,
    "end_hour" / Int8ub,
    "end_minute" / Int8ub,
    "weekdays" / WeekdayMask,
)

PARAMETERS_SCREENSAVER_WINDOW = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 4,
        "value": lambda window: SCREENSAVER_WINDOW.build(asdict(window)),
    },
}

#: The USB-PD revision check (snapshot ``b7``): its second byte is 6 once every
#: port's PD controller reports a revision with device identity, 2 when one
#: doesn't, and 0 on firmware that predates the check. Only at 6 does the
#: screen show an identified device's name.
PD_REVISION_GATE = Struct(
    Padding(1),
    "revision" / Int8ub,
)
PD_REVISION_SUPPORTED = 6
PD_REVISION_UNSUPPORTED = 2

#: The clock display (snapshot ``af``): the display byte, then the catalog ID
#: of the last catalog theme chosen.
DISPLAY_THEME = Struct(
    "display" / DISPLAY,
    "catalog_id" / Int32ul,
)

#: The themes :meth:`PrimeCharger250w.set_display_theme` can set.
BUILT_IN_THEMES = (ClockTheme.THEME_1, ClockTheme.THEME_2, ClockTheme.THEME_3)

#: Highest display brightness, in percent.
MAX_DISPLAY_BRIGHTNESS = 100

#: Ports the Port Priority mode can designate (USB C1-C4), and how many
#: at once.
PRIORITY_PORTS = (1, 2, 3, 4)
MAX_PRIORITY_PORTS = 2

#: The ``420c`` payload: one bit per designated USB C port.
PRIORITY_PORTS_MASK = FlagsEnum(
    Int8ub,
    usb_c1=0x01,
    usb_c2=0x02,
    usb_c3=0x04,
    usb_c4=0x08,
)

#: Bounds of the screensaver window's times and days (0 Monday to 6 Sunday).
LAST_HOUR = 23
LAST_MINUTE = 59
WEEKDAYS = frozenset(range(7))


class ChargingMode(Enum):
    """How the charger shares its output between its ports."""

    #: The charging mode is unknown.
    UNKNOWN = -1

    #: Power follows the devices the charger identifies on its ports.
    AI_POWER = 1

    #: Up to two designated USB C ports take precedence.
    PORT_PRIORITY = 2

    #: Two laptops are found and served first.
    DUAL_LAPTOP = 3

    #: Every port runs at a reduced current.
    LOW_CURRENT = 4

    #: Per-port power limits set in the app.
    CUSTOM = 5


class CatalogTheme(Enum):
    """A clock theme from Anker's online catalog, valued by its catalog ID."""

    #: A catalog theme this library doesn't list.
    UNKNOWN = -1

    #: The app's Celestial (Futuristic).
    CELESTIAL = 948897111

    #: The app's Robotic (Futuristic).
    ROBOTIC = 236632206

    #: The app's Lunar (Cosmic).
    LUNAR = 938963984

    #: The app's Galactic (Cosmic).
    GALACTIC = 819158638

    #: The app's Meteorite (Cosmic).
    METEORITE = 95294588

    #: The app's Floral Waltz (Artistic).
    FLORAL_WALTZ = 130254227

    #: The app's Impressionist Bloom (Artistic).
    IMPRESSIONIST_BLOOM = 347235639

    #: The app's Sweet Treats (Lively).
    SWEET_TREATS = 172033515

    #: The app's Rhythmic Hue (Lively).
    RHYTHMIC_HUE = 496957652


class KnobDirection(Enum):
    """The turning direction of the charger's knob."""

    #: The direction is unknown.
    UNKNOWN = -1

    #: Forward.
    FORWARD = 0

    #: Backward.
    BACKWARD = 1


@dataclass(frozen=True)
class ScreensaverWindow:
    """The hours the screensaver shows; outside them the screen goes dark.

    :param start_hour: Hour the window opens, 0-23.
    :param start_minute: Minute the window opens, 0-59.
    :param end_hour: Hour the window closes, 0-23.
    :param end_minute: Minute the window closes, 0-59.
    :param weekdays: Days the window applies, 0 Monday to 6 Sunday.
    """

    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    weekdays: frozenset[int]


class PrimeCharger250w(PrimeDevice):
    """
    Anker Prime Charger (250W) model.

    Use this class to connect and monitor the 250w charger.
    This model is also known as the A2345.
    """

    #: Write without response, as the app writes every packet to this charger.
    _COMMAND_WRITE_RESPONSE = False

    #: The stream carries the six ports at a2-a7.
    _TELEMETRY_COMMANDS = (0x303,)

    #: The snapshot the device sends on request carries its settings.
    _SNAPSHOT_COMMANDS = (0xA00,)

    _KEEP_ALIVE_INTERVAL: int | None = KEEP_ALIVE_INTERVAL

    @property
    def serial_number(self) -> str:
        """Serial number of the device.

        :returns: Serial number or default str value if not yet negotiated.
        """
        announcement = self.announcement
        serial = announcement.serial if announcement is not None else None
        if not isinstance(serial, bytes):
            return DEFAULT_METADATA_STRING

        return serial.decode("ascii")

    @property
    def software_version(self) -> str:
        """Software version of the device.

        :returns: Version string or default str value if no snapshot has been
            received.
        """
        return self._snapshot_version("a2")

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return self._port_status("a2")

    @property
    def usb_c1_voltage(self) -> float:
        """USB C1 Port voltage (V).

        :returns: Voltage of the USB C1 port or default float value.
        """
        return self._port_reading("a2", "voltage", scale=1000.0)

    @property
    def usb_c1_current(self) -> float:
        """USB C1 Port current (A).

        :returns: Current of the USB C1 port or default float value.
        """
        return self._port_reading("a2", "current", scale=1000.0)

    @property
    def usb_c1_power(self) -> float:
        """USB C1 Port power (W).

        :returns: Power of the USB C1 port or default float value.
        """
        return self._port_reading("a2", "power", scale=100.0)

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return self._port_status("a3")

    @property
    def usb_c2_voltage(self) -> float:
        """USB C2 Port voltage (V).

        :returns: Voltage of the USB C2 port or default float value.
        """
        return self._port_reading("a3", "voltage", scale=1000.0)

    @property
    def usb_c2_current(self) -> float:
        """USB C2 Port current (A).

        :returns: Current of the USB C2 port or default float value.
        """
        return self._port_reading("a3", "current", scale=1000.0)

    @property
    def usb_c2_power(self) -> float:
        """USB C2 Port power (W).

        :returns: Power of the USB C2 port or default float value.
        """
        return self._port_reading("a3", "power", scale=100.0)

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return self._port_status("a4")

    @property
    def usb_c3_voltage(self) -> float:
        """USB C3 Port voltage (V).

        :returns: Voltage of the USB C3 port or default float value.
        """
        return self._port_reading("a4", "voltage", scale=1000.0)

    @property
    def usb_c3_current(self) -> float:
        """USB C3 Port current (A).

        :returns: Current of the USB C3 port or default float value.
        """
        return self._port_reading("a4", "current", scale=1000.0)

    @property
    def usb_c3_power(self) -> float:
        """USB C3 Port power (W).

        :returns: Power of the USB C3 port or default float value.
        """
        return self._port_reading("a4", "power", scale=100.0)

    @property
    def usb_port_c4(self) -> PortStatus:
        """USB C4 Port Status.

        :returns: Status of the USB C4 port.
        """
        return self._port_status("a5")

    @property
    def usb_c4_voltage(self) -> float:
        """USB C4 Port voltage (V).

        :returns: Voltage of the USB C4 port or default float value.
        """
        return self._port_reading("a5", "voltage", scale=1000.0)

    @property
    def usb_c4_current(self) -> float:
        """USB C4 Port current (A).

        :returns: Current of the USB C4 port or default float value.
        """
        return self._port_reading("a5", "current", scale=1000.0)

    @property
    def usb_c4_power(self) -> float:
        """USB C4 Port power (W).

        :returns: Power of the USB C4 port or default float value.
        """
        return self._port_reading("a5", "power", scale=100.0)

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return self._port_status("a6")

    @property
    def usb_a1_voltage(self) -> float:
        """USB A1 Port voltage (V).

        :returns: Voltage of the USB A1 port or default float value.
        """
        return self._port_reading("a6", "voltage", scale=1000.0)

    @property
    def usb_a1_current(self) -> float:
        """USB A1 Port current (A).

        :returns: Current of the USB A1 port or default float value.
        """
        return self._port_reading("a6", "current", scale=1000.0)

    @property
    def usb_a1_power(self) -> float:
        """USB A1 Port power (W).

        :returns: Power of the USB A1 port or default float value.
        """
        return self._port_reading("a6", "power", scale=100.0)

    @property
    def usb_port_a2(self) -> PortStatus:
        """USB A2 Port Status.

        :returns: Status of the USB A2 port.
        """
        return self._port_status("a7")

    @property
    def usb_a2_voltage(self) -> float:
        """USB A2 Port voltage (V).

        :returns: Voltage of the USB A2 port or default float value.
        """
        return self._port_reading("a7", "voltage", scale=1000.0)

    @property
    def usb_a2_current(self) -> float:
        """USB A2 Port current (A).

        :returns: Current of the USB A2 port or default float value.
        """
        return self._port_reading("a7", "current", scale=1000.0)

    @property
    def usb_a2_power(self) -> float:
        """USB A2 Port power (W).

        :returns: Power of the USB A2 port or default float value.
        """
        return self._port_reading("a7", "power", scale=100.0)

    @property
    def clock_display_enabled(self) -> bool | None:
        """Whether the screen shows the clock after the screen timeout.

        .. note::
           This is the app's Clock Display switch.

        :returns: True if on, False if off, or default bool value before any
            snapshot.
        """
        display = self._snapshot_struct("af", DISPLAY)
        if display is None:
            return DEFAULT_METADATA_BOOL

        return bool(display.on)

    @property
    def display_theme(self) -> ClockTheme:
        """Theme of the clock display.

        :returns: Theme or unknown if no snapshot has been received.
        """
        display = self._snapshot_struct("af", DISPLAY)
        if display is None:
            return ClockTheme.UNKNOWN

        try:
            return ClockTheme(display.theme)
        except ValueError:
            return ClockTheme.UNKNOWN

    @property
    def display_catalog_theme(self) -> CatalogTheme | None:
        """The catalog theme the clock display shows.

        :returns: The theme, unknown for one this library doesn't list, or
            None unless :attr:`display_theme` is a catalog theme.
        """
        if self.display_theme is not ClockTheme.CATALOG:
            return None

        display = self._snapshot_struct("af", DISPLAY_THEME)
        if display is None:
            return None

        try:
            return CatalogTheme(display.catalog_id)
        except ValueError:
            return CatalogTheme.UNKNOWN

    @property
    def display_timeout(self) -> int:
        """Display timeout in seconds, where 0 is always on.

        :returns: Timeout in seconds or default int value before any snapshot.
        """
        code = self._snapshot_int("b0")
        if code == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_INT

        return DISPLAY_TIMEOUTS.get(code, DisplayTimeout.UNKNOWN).value

    @property
    def display_brightness(self) -> int:
        """Brightness of the display in percent.

        :returns: Brightness or default int value if no snapshot has been
            received.
        """
        return self._snapshot_int("b3")

    @property
    def charging_mode(self) -> ChargingMode:
        """How the charger shares its output between its ports.

        :returns: Charging mode or unknown if no snapshot has been received.
        """
        try:
            return ChargingMode(self._snapshot_int("b1"))
        except ValueError:
            return ChargingMode.UNKNOWN

    @property
    def knob_direction(self) -> KnobDirection:
        """Turning direction of the knob.

        :returns: Knob direction or unknown if no snapshot has been received.
        """
        try:
            return KnobDirection(self._snapshot_int("b4"))
        except ValueError:
            return KnobDirection.UNKNOWN

    @property
    def screensaver_window(self) -> ScreensaverWindow | None:
        """Hours the screensaver shows; outside them the screen goes dark.

        :returns: The window or None if no snapshot has been received.
        """
        window = self._snapshot_struct("b9", SCREENSAVER_WINDOW)
        if window is None:
            return None

        return ScreensaverWindow(
            start_hour=window.start_hour,
            start_minute=window.start_minute,
            end_hour=window.end_hour,
            end_minute=window.end_minute,
            weekdays=window.weekdays,
        )

    @property
    def compatibility_mode_enabled(self) -> bool | None:
        """Whether the charger's compatibility mode is on.

        .. note::
           This is the app's "Maximum Compatibility", which can speed up
           charging of some drones' battery compartments.

        :returns: True if on, False if off, or default bool value before any
            snapshot.
        """
        setting = self._snapshot_int("bb")
        if setting == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_BOOL

        return bool(setting)

    @property
    def device_identification_enabled(self) -> bool | None:
        """Whether the charger shows the identified device's name on its screen.

        This is the app's Charging Device Identification.

        .. note::
           Device identification works only while compatibility mode
           (:attr:`compatibility_mode_enabled`) is off.

        :returns: True if on, False if off, or default bool value before any
            snapshot.
        """
        setting = self._snapshot_int("bf")
        if setting == DEFAULT_METADATA_INT:
            return DEFAULT_METADATA_BOOL

        return bool(setting)

    @property
    def device_name_display_supported(self) -> bool | None:
        """Whether the charger can show an identified device's name on its screen.

        .. note::
           :collapsible: closed

           This needs every port's USB-PD controller at a protocol revision
           that carries device identity. The ``usb_cN_device`` names work
           either way.

        :returns: True if supported, False if not, or default bool value
            before the charger has checked.
        """
        gate = self._snapshot_struct("b7", PD_REVISION_GATE)
        if gate is None or gate.revision not in (
            PD_REVISION_SUPPORTED,
            PD_REVISION_UNSUPPORTED,
        ):
            return DEFAULT_METADATA_BOOL

        return bool(gate.revision == PD_REVISION_SUPPORTED)

    @property
    def firmware_updating(self) -> bool | None:
        """Whether a firmware update is under way.

        .. note::
           The port readings stop updating while it is.

        :returns: True if updating, False if not, or default bool value
            before any snapshot.
        """
        update = self._snapshot_struct("b2", FIRMWARE_UPDATE)
        if update is None:
            return DEFAULT_METADATA_BOOL

        return bool(update.updating)

    @property
    def firmware_update_progress(self) -> int:
        """Progress of the firmware update in percent.

        :returns: Progress or default int value if no snapshot has been
            received.
        """
        update = self._snapshot_struct("b2", FIRMWARE_UPDATE)
        if update is None:
            return DEFAULT_METADATA_INT

        return int(update.progress)

    @property
    def clock_format(self) -> ClockFormat:
        """Format of the clock on the display.

        :returns: Clock format or unknown if no snapshot has been received.
        """
        try:
            return ClockFormat(self._snapshot_int("b5"))
        except ValueError:
            return ClockFormat.UNKNOWN

    @property
    def usb_c1_schedule(self) -> PortSchedule | None:
        """USB C1 Port daily on/off schedule.

        :returns: Schedule of the USB C1 port or None before any snapshot.
        """
        return self._port_schedule("aa")

    @property
    def usb_c1_timer(self) -> PortTimer | None:
        """USB C1 Port auto-off timer.

        :returns: Timer of the USB C1 port or None before any snapshot.
        """
        return self._port_timer("aa")

    @property
    def usb_c2_schedule(self) -> PortSchedule | None:
        """USB C2 Port daily on/off schedule.

        :returns: Schedule of the USB C2 port or None before any snapshot.
        """
        return self._port_schedule("ab")

    @property
    def usb_c2_timer(self) -> PortTimer | None:
        """USB C2 Port auto-off timer.

        :returns: Timer of the USB C2 port or None before any snapshot.
        """
        return self._port_timer("ab")

    @property
    def usb_c3_schedule(self) -> PortSchedule | None:
        """USB C3 Port daily on/off schedule.

        :returns: Schedule of the USB C3 port or None before any snapshot.
        """
        return self._port_schedule("ac")

    @property
    def usb_c3_timer(self) -> PortTimer | None:
        """USB C3 Port auto-off timer.

        :returns: Timer of the USB C3 port or None before any snapshot.
        """
        return self._port_timer("ac")

    @property
    def usb_c4_schedule(self) -> PortSchedule | None:
        """USB C4 Port daily on/off schedule.

        :returns: Schedule of the USB C4 port or None before any snapshot.
        """
        return self._port_schedule("ad")

    @property
    def usb_c4_timer(self) -> PortTimer | None:
        """USB C4 Port auto-off timer.

        :returns: Timer of the USB C4 port or None before any snapshot.
        """
        return self._port_timer("ad")

    @property
    def usb_a1_a2_schedule(self) -> PortSchedule | None:
        """USB A1 and A2 Port daily on/off schedule.

        :returns: Schedule of USB A1 and A2 or None before any snapshot.
        """
        return self._port_schedule("ae")

    @property
    def usb_a1_a2_timer(self) -> PortTimer | None:
        """USB A1 and A2 Port auto-off timer.

        :returns: Timer of USB A1 and A2 or None before any snapshot.
        """
        return self._port_timer("ae")

    def _usb_pd_identity(self, port: str) -> Container | None:
        """Read the USB-PD vendor and product ID a USB C port's device reports.

        :param port: The port's field name (``"usb_c1"`` - ``"usb_c4"``).
        :returns: The identity, or None if no device answered with one.
        """
        identities = self._stream_or_snapshot("a8", "bd", USB_PD_IDENTITIES)
        if identities is None or identities[port].vid in PD_VID_NONE:
            return None

        return identities[port]

    def _device_name(self, port: str) -> str | None:
        """Name the device the charger identified on a USB C port.

        :param port: The port's field name (``"usb_c1"`` - ``"usb_c4"``).
        :returns: The firmware's name for the device, else its vendor's, or
            None if the charger identified neither.
        """
        identities = self._stream_or_snapshot("a9", "be", DEVICE_IDENTITIES)
        if identities is None or identities[port].device_class == IDENTITY_NONE:
            return None

        identity = identities[port]
        return device_name(identity.device_class, identity.code) or vendor_name(
            identity.device_class,
        )

    @property
    def usb_c1_vendor_id(self) -> int:
        """USB vendor ID of the device on USB C1, from USB-PD.

        :returns: The vendor ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c1")
        return DEFAULT_METADATA_INT if identity is None else int(identity.vid)

    @property
    def usb_c1_product_id(self) -> int:
        """USB product ID of the device on USB C1, from USB-PD.

        :returns: The product ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c1")
        return DEFAULT_METADATA_INT if identity is None else int(identity.pid)

    @property
    def usb_c1_device(self) -> str | None:
        """Device the charger identified on USB C1.

        .. note::
           :collapsible: closed

           The charger names the models in its own table (iPhones, iPads,
           MacBooks, Lenovo laptops); any other device it recognises is named
           by its vendor. The name is the firmware's model name; the app may
           show the series instead. The device identification setting doesn't
           affect it.

        :returns: The device's name, or None if the charger identified none.
        """
        return self._device_name("usb_c1")

    @property
    def usb_c2_vendor_id(self) -> int:
        """USB vendor ID of the device on USB C2, from USB-PD.

        :returns: The vendor ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c2")
        return DEFAULT_METADATA_INT if identity is None else int(identity.vid)

    @property
    def usb_c2_product_id(self) -> int:
        """USB product ID of the device on USB C2, from USB-PD.

        :returns: The product ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c2")
        return DEFAULT_METADATA_INT if identity is None else int(identity.pid)

    @property
    def usb_c2_device(self) -> str | None:
        """Device the charger identified on USB C2.

        .. note::
           :collapsible: closed

           The charger names the models in its own table (iPhones, iPads,
           MacBooks, Lenovo laptops); any other device it recognises is named
           by its vendor. The name is the firmware's model name; the app may
           show the series instead. The device identification setting doesn't
           affect it.

        :returns: The device's name, or None if the charger identified none.
        """
        return self._device_name("usb_c2")

    @property
    def usb_c3_vendor_id(self) -> int:
        """USB vendor ID of the device on USB C3, from USB-PD.

        :returns: The vendor ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c3")
        return DEFAULT_METADATA_INT if identity is None else int(identity.vid)

    @property
    def usb_c3_product_id(self) -> int:
        """USB product ID of the device on USB C3, from USB-PD.

        :returns: The product ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c3")
        return DEFAULT_METADATA_INT if identity is None else int(identity.pid)

    @property
    def usb_c3_device(self) -> str | None:
        """Device the charger identified on USB C3.

        .. note::
           :collapsible: closed

           The charger names the models in its own table (iPhones, iPads,
           MacBooks, Lenovo laptops); any other device it recognises is named
           by its vendor. The name is the firmware's model name; the app may
           show the series instead. The device identification setting doesn't
           affect it.

        :returns: The device's name, or None if the charger identified none.
        """
        return self._device_name("usb_c3")

    @property
    def usb_c4_vendor_id(self) -> int:
        """USB vendor ID of the device on USB C4, from USB-PD.

        :returns: The vendor ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c4")
        return DEFAULT_METADATA_INT if identity is None else int(identity.vid)

    @property
    def usb_c4_product_id(self) -> int:
        """USB product ID of the device on USB C4, from USB-PD.

        :returns: The product ID or default int value if none was reported.
        """
        identity = self._usb_pd_identity("usb_c4")
        return DEFAULT_METADATA_INT if identity is None else int(identity.pid)

    @property
    def usb_c4_device(self) -> str | None:
        """Device the charger identified on USB C4.

        .. note::
           :collapsible: closed

           The charger names the models in its own table (iPhones, iPads,
           MacBooks, Lenovo laptops); any other device it recognises is named
           by its vendor. The name is the firmware's model name; the app may
           show the series instead. The device identification setting doesn't
           affect it.

        :returns: The device's name, or None if the charger identified none.
        """
        return self._device_name("usb_c4")

    def _port_priority(self, key: str) -> PortPriority:
        """Read a USB C port's priority from its snapshot record.

        :param key: Key of the port's record (aa-ad for USB C1-C4).
        :returns: Priority of the port or unknown if no snapshot has carried
            it.
        """
        record = self._port_record(key)
        if record is None or record.priority is None:
            return PortPriority.UNKNOWN

        try:
            return PortPriority(record.priority)
        except ValueError:
            return PortPriority.UNKNOWN

    @property
    def usb_c1_priority(self) -> PortPriority:
        """USB C1 Port priority in the Port Priority charging mode.

        :returns: Priority of the USB C1 port or unknown before any snapshot.
        """
        return self._port_priority("aa")

    @property
    def usb_c2_priority(self) -> PortPriority:
        """USB C2 Port priority in the Port Priority charging mode.

        :returns: Priority of the USB C2 port or unknown before any snapshot.
        """
        return self._port_priority("ab")

    @property
    def usb_c3_priority(self) -> PortPriority:
        """USB C3 Port priority in the Port Priority charging mode.

        :returns: Priority of the USB C3 port or unknown before any snapshot.
        """
        return self._port_priority("ac")

    @property
    def usb_c4_priority(self) -> PortPriority:
        """USB C4 Port priority in the Port Priority charging mode.

        :returns: Priority of the USB C4 port or unknown before any snapshot.
        """
        return self._port_priority("ad")

    @property
    def over_temperature(self) -> bool | None:
        """Whether the charger is holding its outputs back for heat.

        .. note::
           :collapsible: closed

           Set when either temperature sensor stays above 125 °C, and held
           until both are back below 95 °C.

        :returns: True if over temperature, False if not, or default bool
            value before any snapshot.
        """
        return self._port_fault("over_temperature")

    @property
    def usb_c1_fault(self) -> bool | None:
        """Whether USB C1 reports a port fault.

        .. note::
           :collapsible: closed

           The charger sets a port's fault after five faulty readings in a row
           and clears it after ten clean ones.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c1")

    @property
    def usb_c2_fault(self) -> bool | None:
        """Whether USB C2 reports a port fault.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c2")

    @property
    def usb_c3_fault(self) -> bool | None:
        """Whether USB C3 reports a port fault.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c3")

    @property
    def usb_c4_fault(self) -> bool | None:
        """Whether USB C4 reports a port fault.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_c4")

    @property
    def usb_a_fault(self) -> bool | None:
        """Whether either USB A port reports a port fault.

        :returns: True if faulted, False if not, or default bool value before
            any snapshot.
        """
        return self._port_fault("usb_a_undervoltage")

    async def turn_usb_c1_on(self) -> None:
        """Turn USB port C1 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c1"], on=True)

    async def turn_usb_c1_off(self) -> None:
        """Turn USB port C1 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c1"], on=False)

    async def set_timer_usb_c1(self, time: int) -> None:
        """Set auto off timer for USB C1.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c1"], time)

    async def turn_usb_c2_on(self) -> None:
        """Turn USB port C2 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c2"], on=True)

    async def turn_usb_c2_off(self) -> None:
        """Turn USB port C2 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c2"], on=False)

    async def set_timer_usb_c2(self, time: int) -> None:
        """Set auto off timer for USB C2.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c2"], time)

    async def turn_usb_c3_on(self) -> None:
        """Turn USB port C3 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c3"], on=True)

    async def turn_usb_c3_off(self) -> None:
        """Turn USB port C3 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c3"], on=False)

    async def set_timer_usb_c3(self, time: int) -> None:
        """Set auto off timer for USB C3.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c3"], time)

    async def turn_usb_c4_on(self) -> None:
        """Turn USB port C4 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c4"], on=True)

    async def turn_usb_c4_off(self) -> None:
        """Turn USB port C4 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_c4"], on=False)

    async def set_timer_usb_c4(self, time: int) -> None:
        """Set auto off timer for USB C4.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_c4"], time)

    async def turn_usb_a1_a2_on(self) -> None:
        """Turn USB port A1 and A2 on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_a1_a2"], on=True)

    async def turn_usb_a1_a2_off(self) -> None:
        """Turn USB port A1 and A2 off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._turn_port(PORT_INDEX["usb_a1_a2"], on=False)

    async def set_timer_usb_a1_a2(self, time: int) -> None:
        """Set auto off timer for USB A1 and A2.

        :param time: Seconds until shutdown. Pass 0 to cancel.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._set_port_timer(PORT_INDEX["usb_a1_a2"], time)

    async def set_schedule_usb_c1(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C1.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c1"], schedule)

    async def set_schedule_usb_c2(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C2.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c2"], schedule)

    async def set_schedule_usb_c3(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C3.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c3"], schedule)

    async def set_schedule_usb_c4(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB C4.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_c4"], schedule)

    async def set_schedule_usb_a1_a2(self, schedule: PortSchedule) -> None:
        """Set the daily on/off schedule for USB A1 and A2.

        :param schedule: The on-time and off-time to store.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_schedule(PORT_INDEX["usb_a1_a2"], schedule)

    async def set_display_timeout(self, timeout: DisplayTimeout) -> None:  # noqa: ASYNC109  # shared device API
        """Set the display timeout.

        :param timeout: One of S0 (always on), S30, S60, S300 and S1800.
        :raises ValueError: If the timeout is not supported by the device.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if timeout not in DISPLAY_TIMEOUT_CODES:
            msg = f"Display timeout {timeout} is not supported by this device"
            raise ValueError(msg)
        await self._send_setting(CMD_DISPLAY_TIMEOUT, DISPLAY_TIMEOUT_CODES[timeout])

    async def turn_clock_display_on(self) -> None:
        """Show the clock after the screen timeout, keeping the theme.

        .. note::
           :collapsible: closed

           This works only with a built-in theme selected. Turning the clock
           display on with a catalog theme or an uploaded image also needs
           that theme's ID and image checksum, which the snapshot doesn't
           carry.

        :raises ValueError: If no snapshot has been received, or a catalog
            theme or uploaded image is selected.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        theme = self.display_theme
        if theme not in BUILT_IN_THEMES:
            msg = f"Cannot turn the clock display on with the {theme.name} theme"
            raise ValueError(msg)
        await self._send_display(clock_display=True, theme=theme.value)

    async def turn_clock_display_off(self) -> None:
        """Stop showing the clock after the screen timeout.

        .. note::
           :collapsible: closed

           This also turns the holiday theme switch off.

        :raises ValueError: If no snapshot has been received.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        display = self._snapshot_struct("af", DISPLAY)
        if display is None:
            msg = "Cannot turn the clock display off before any snapshot"
            raise ValueError(msg)
        await self._send_display(clock_display=False, theme=display.theme)

    async def set_display_theme(self, theme: ClockTheme) -> None:
        """Set the theme of the clock display and turn the clock display on.

        .. note::
           :collapsible: closed

           Only the three built-in themes can be set here. A catalog theme or
           an uploaded image can need its image sent to the charger first,
           which the app does.

        :param theme: Theme 1, 2 or 3.
        :raises ValueError: If the theme isn't a built-in one.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if theme not in BUILT_IN_THEMES:
            msg = f"Cannot set the {theme.name} clock theme"
            raise ValueError(msg)
        await self._send_display(clock_display=True, theme=theme.value)

    async def _send_display(self, *, clock_display: bool, theme: int) -> None:
        """Send the display byte: the clock display switch and the theme index.

        :param clock_display: True to show the clock after the screen timeout.
        :param theme: The theme's wire index.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_setting(
            CMD_DISPLAY,
            DISPLAY.build({"on": clock_display, "theme": theme}),
        )

    async def set_display_brightness(self, brightness: int) -> None:
        """Set the brightness of the display.

        :param brightness: Brightness in percent, 0 to 100.
        :raises ValueError: If the brightness is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if not 0 <= brightness <= MAX_DISPLAY_BRIGHTNESS:
            msg = f"Display brightness must be 0 to {MAX_DISPLAY_BRIGHTNESS} %"
            raise ValueError(msg)
        await self._send_setting(CMD_DISPLAY_BRIGHTNESS, brightness)

    async def set_clock_format(self, clock_format: ClockFormat) -> None:
        """Set the format of the clock on the display.

        :param clock_format: The clock format.
        :raises ValueError: If the format is unknown.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if clock_format is ClockFormat.UNKNOWN:
            msg = "Cannot set an unknown clock format"
            raise ValueError(msg)
        await self._send_setting(CMD_CLOCK_FORMAT, clock_format.value)

    async def set_charging_mode(self, mode: ChargingMode) -> None:
        """Set how the charger shares its output between its ports.

        .. warning::
           Every port renegotiates when the mode changes, so all of them drop
           to 0 W for about eight seconds.

        :param mode: Any mode but custom, which is set up in the app.
        :raises ValueError: If the mode is unknown or custom.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if mode in (ChargingMode.UNKNOWN, ChargingMode.CUSTOM):
            msg = f"Cannot set the {mode.name} charging mode"
            raise ValueError(msg)
        await self._send_setting(CMD_CHARGING_MODE, mode.value)

    async def set_priority_ports(self, ports: Collection[int]) -> None:
        """Designate the USB C ports that take precedence.

        Designating ports switches the charger to the Port Priority charging
        mode.

        .. note::
           This is the app's "Port Priority Allocation" charging mode.

        :param ports: Up to two USB C port numbers (1-4), or none.
        :raises ValueError: If a port isn't a USB C port or more than two are
            given.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if len(ports) > MAX_PRIORITY_PORTS or not set(ports) <= set(PRIORITY_PORTS):
            msg = f"Up to {MAX_PRIORITY_PORTS} of the USB C ports {PRIORITY_PORTS}"
            raise ValueError(msg)
        await self._send_setting(
            CMD_PRIORITY_PORTS,
            PRIORITY_PORTS_MASK.build({f"usb_c{port}": True for port in ports}),
        )

    async def set_knob_direction(self, direction: KnobDirection) -> None:
        """Set the turning direction of the knob.

        :param direction: The direction.
        :raises ValueError: If the direction is unknown.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if direction is KnobDirection.UNKNOWN:
            msg = "Cannot set an unknown knob direction"
            raise ValueError(msg)
        await self._send_setting(CMD_KNOB_DIRECTION, direction.value)

    async def turn_compatibility_mode_on(self) -> None:
        """Turn the charger's compatibility mode on.

        .. note::
           Device identification stops working while compatibility mode is on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_setting(CMD_COMPATIBILITY_MODE, 1)

    async def turn_compatibility_mode_off(self) -> None:
        """Turn the charger's compatibility mode off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_setting(CMD_COMPATIBILITY_MODE, 0)

    async def turn_device_identification_on(self) -> None:
        """Turn on identifying the devices plugged into the charger.

        .. note::
           Device identification works only while compatibility mode is off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_setting(CMD_DEVICE_IDENTIFICATION, 1)

    async def turn_device_identification_off(self) -> None:
        """Turn off identifying the devices plugged into the charger.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_setting(CMD_DEVICE_IDENTIFICATION, 0)

    async def set_screensaver_window(self, window: ScreensaverWindow) -> None:
        """Set the hours the screensaver shows; outside them the screen goes dark.

        :param window: The window.
        :raises ValueError: If a time or day is out of range.
        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        if (
            not 0 <= window.start_hour <= LAST_HOUR
            or not 0 <= window.end_hour <= LAST_HOUR
            or not 0 <= window.start_minute <= LAST_MINUTE
            or not 0 <= window.end_minute <= LAST_MINUTE
            or not window.weekdays <= WEEKDAYS
        ):
            msg = "Screensaver window times must be 00:00-23:59 and days 0-6"
            raise ValueError(msg)
        await self._send_command(
            CMD_SCREENSAVER_WINDOW,
            PARAMETERS_SCREENSAVER_WINDOW,
            window=window,
        )
