"""SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

# ruff: noqa: G004
import asyncio
import inspect
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import Enum

from bleak import BleakClient, BleakError, BleakScanner
from bleak.backends.client import BaseBleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

#: GATT Service UUID for device telemetry. Is subscribable. Handle 17.
UUID_TELEMETRY = "8c850003-0302-41c5-b46e-cf057c562025"

#: GATT Service UUID for identifying Solix devices (Tested on C300X and C1000).
UUID_IDENTIFIER = "0000ff09-0000-1000-8000-00805f9b34fb"

#: Time to wait before re-connecting on an unexpected disconnect.
RECONNECT_DELAY = 3

#: Maximum number of automatic re-connection attempts the program will make.
RECONNECT_ATTEMPTS_MAX = -1

#: Time to allow for a re-connect before considering the
#: device to be disconnected and running state changed callbacks.
DISCONNECT_TIMEOUT = 30

#: String value for unknown string attributes.
DEFAULT_METADATA_STRING = "Unknown"

#: Int value for unknown int attributes.
DEFAULT_METADATA_INT = -1

#: Float value for unknown float attributes.
DEFAULT_METADATA_FLOAT = -1.0


_LOGGER = logging.getLogger(__name__)


async def discover_devices(
    scanner: BleakScanner | None = None, timeout: int = 5
) -> list[BLEDevice]:
    """Scan feature.

    Scans the BLE neighborhood for Solix BLE device(s) and returns
    a list of nearby devices based upon detection of a known UUID.

    :param scanner: Scanner to use. Defaults to new scanner.
    :param timeout: Time to scan for devices (default=5).
    """

    if scanner is None:
        scanner = BleakScanner

    devices = []

    def callback(device, advertising_data):
        if UUID_IDENTIFIER in advertising_data.service_uuids and device not in devices:
            devices.append(device)

    async with BleakScanner(callback) as scanner:
        await asyncio.sleep(timeout)

    return devices


class PortStatus(Enum):
    """The status of a port on the device."""

    #: The status of the port is unknown.
    UNKNOWN = -1

    #: The port is not connected.
    NOT_CONNECTED = 0

    #: The port is an output.
    OUTPUT = 1

    #: The port is an input.
    INPUT = 2


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


class SolixBLEDevice:
    """Solix BLE device object."""

    def __init__(self, ble_device: BLEDevice) -> None:
        """Initialise device object. Does not connect automatically."""

        _LOGGER.debug(
            f"Initializing Solix device '{ble_device.name}' with"
            f"address '{ble_device.address}' and details '{ble_device.details}'"
        )

        self._ble_device: BLEDevice = ble_device
        self._client: BleakClient | None = None
        self._data: bytes | None = None
        self._last_data_timestamp: datetime | None = None
        self._supports_telemetry: bool = False
        self._state_changed_callbacks: list[Callable[[], None]] = []
        self._reconnect_task: asyncio.Task | None = None
        self._expect_disconnect: bool = True
        self._connection_attempts: int = 0

    def add_callback(self, function: Callable[[], None]) -> None:
        """Register a callback to be run on state updates.

        Triggers include changes to pretty much anything, including,
        battery percentage, output power, solar, connection status, etc.

        :param function: Function to run on state changes.
        """
        self._state_changed_callbacks.append(function)

    def remove_callback(self, function: Callable[[], None]) -> None:
        """Remove a registered state change callback.

        :param function: Function to remove from callbacks.
        :raises ValueError: If callback does not exist.
        """
        self._state_changed_callbacks.remove(function)

    async def connect(self, max_attempts: int = 3, run_callbacks: bool = True) -> bool:
        """Connect to device.

        This will connect to the device, determine if it is supported
        and subscribe to status updates, returning True if successful.

        :param max_attempts: Maximum number of attempts to try to connect (default=3).
        :param run_callbacks: Execute registered callbacks on successful connection (default=True).
        """

        # If we are not connected then connect
        if not self.connected:
            self._connection_attempts += 1
            _LOGGER.debug(
                f"Connecting to '{self.name}' with address '{self.address}'..."
            )

            try:
                # Make a new Bleak client and connect
                self._client = await establish_connection(
                    BleakClient,
                    device=self._ble_device,
                    name=self.address,
                    max_attempts=max_attempts,
                    disconnected_callback=self._disconnect_callback,
                )

            except BleakError as e:
                _LOGGER.error(f"Error connecting to '{self.name}'. E: '{e}'")

        # If we are still not connected then we have failed
        if not self.connected:
            _LOGGER.error(
                f"Failed to connect to '{self.name}' on attempt {self._connection_attempts}!"
            )
            return False

        _LOGGER.debug(f"Connected to '{self.name}'")

        # If we are not subscribed to telemetry then check that
        # we can and then subscribe
        if not self.available:
            try:
                await self._determine_services()
                await self._subscribe_to_services()

            except BleakError as e:
                _LOGGER.error(f"Error subscribing to '{self.name}'. E: '{e}'")
                return False

        # If we are still not subscribed to telemetry then we have failed
        if not self.available:
            return False

        # Else we have succeeded
        self._expect_disconnect = False
        self._connection_attempts = 0

        # Execute callbacks if enabled
        if run_callbacks:
            self._run_state_changed_callbacks()

        return True

    async def disconnect(self) -> None:
        """Disconnect from device.

        Disconnects from device and does not execute callbacks.
        """
        self._expect_disconnect = True

        # If there is a client disconnect and throw it away
        if self._client:
            self._client.disconnect()
            self._client = None

    @property
    def connected(self) -> bool:
        """Connected to device.

        :returns: True/False if connected to device.
        """
        return self._client is not None and self._client.is_connected

    @property
    def available(self) -> bool:
        """Connected to device and receiving data from it.

        :returns: True/False if the device is connected and sending telemetry.
        """
        return self.connected and self.supports_telemetry

    @property
    def address(self) -> str:
        """MAC address of device.

        :returns: The Bluetooth MAC address of the device.
        """
        return self._ble_device.address

    @property
    def name(self) -> str:
        """Bluetooth name of the device.

        :returns: The name of the device or default string value.
        """
        return self._ble_device.name or DEFAULT_METADATA_STRING

    @property
    def supports_telemetry(self) -> bool:
        """Device supports the libraries telemetry standard.

        :returns: True/False if telemetry supported.
        """
        return self._supports_telemetry

    @property
    def last_update(self) -> datetime | None:
        """Timestamp of last telemetry data update from device.

        :returns: Timestamp of last update or None.
        """
        return self._last_data_timestamp

    async def _determine_services(self) -> None:
        """Determine GATT services available on the device."""

        # Print services
        for service in self._client.services:
            _LOGGER.debug("[Service] %s", service)

            for char in service.characteristics:
                if "read" in char.properties:
                    try:
                        value = await self._client.read_gatt_char(char.uuid)
                        extra = f", Value: {value}"
                    except Exception as e:
                        extra = f", Error: {e}"
                else:
                    extra = ""

                _LOGGER.debug(
                    "  [Characteristic] %s (%s)%s",
                    char,
                    ",".join(char.properties),
                    extra,
                )

                for descriptor in char.descriptors:
                    try:
                        value = await self._client.read_gatt_descriptor(
                            descriptor.handle
                        )
                        _LOGGER.debug(
                            "    [Descriptor] %s, Value: %r", descriptor, value
                        )
                    except Exception as e:
                        _LOGGER.debug("    [Descriptor] %s, Error: %s", descriptor, e)

        # Populate supported services
        self._supports_telemetry = bool(
            self._client.services.get_characteristic(UUID_TELEMETRY)
        )
        if not self._supports_telemetry:
            _LOGGER.warning(
                f"Device '{self.name}' does not support the telemetry characteristic!"
            )

    def _parse_int(self, index: int) -> int:
        """Parse a 16-bit integer at the index in the telemetry bytes.

        :param index: Index of 16-bit integer in array.
        :returns: 16-bit integer.
        :raises IndexError: If index is out of range.
        """
        return int.from_bytes(self._data[index : index + 2], byteorder="little")

    def _parse_telemetry(self, data: bytearray) -> None:
        """Update internal values using the telemetry data.

        :param data: Bytes from status update message.
        """

        # If we are expecting a particular size and the data is not that size then the
        # data we received is not the telemetry data we want
        if (
            self._EXPECTED_TELEMETRY_LENGTH != 0
            and len(data) != self._EXPECTED_TELEMETRY_LENGTH
        ):
            _LOGGER.debug(
                f"Data is not telemetry data. The size is wrong ({len(data)} != {self._EXPECTED_TELEMETRY_LENGTH}). Data: '{data}'"
            )
            return

        if len(data) < 100:
            _LOGGER.debug(
                f"Data is not telemetry data. It is too small. We expect > 100 but got '{len(data)}'. Data: '{data}'"
            )
            return

        # If debugging and we have a previous status update to compare against
        if _LOGGER.isEnabledFor(logging.DEBUG) and self._data is not None:
            if data == self._data:
                _LOGGER.debug(f"No changes from previous status update")
            else:
                _LOGGER.debug(f"Changes detected compared to previous status update!")
                for index, old_byte in enumerate(self._data):
                    new_byte = data[index]
                    if new_byte != old_byte:
                        _LOGGER.debug(
                            f"Previous value at index '{index}' was '{old_byte}' but is now '{new_byte}'!"
                        )

        # Update internal data store
        self._data = data
        self._last_data_timestamp = datetime.now()

    def _run_state_changed_callbacks(self) -> None:
        """Execute all registered callbacks for a state change."""
        for function in self._state_changed_callbacks:
            function()

    async def _subscribe_to_services(self) -> None:
        """Subscribe to state updates from device."""
        if self._supports_telemetry:

            def _telemetry_update(handle: int, data: bytearray) -> None:
                """Update internal state and run callbacks."""

                # Parse data
                _LOGGER.debug(f"Received notification from '{self.name}'. Data: {data}")
                old_data = self._data
                self._parse_telemetry(data)

                # Print status update
                _LOGGER.debug(self)

                # Run callbacks if changed
                if data != old_data:
                    self._run_state_changed_callbacks()

            await self._client.start_notify(UUID_TELEMETRY, _telemetry_update)

    async def _reconnect(self) -> None:
        """Re-connect to device and run state change callbacks on timeout/failure."""
        try:
            async with asyncio.timeout(DISCONNECT_TIMEOUT):
                await asyncio.sleep(RECONNECT_DELAY)
                await self.connect(run_callbacks=False)
                if self.available:
                    _LOGGER.debug(f"Successfully re-connected to '{self.name}'")

        except TimeoutError as e:
            _LOGGER.error(f"Failed to re-connect to '{self.name}'. E: '{e}'")
            self._run_state_changed_callbacks()

    def _disconnect_callback(self, client: BaseBleakClient) -> None:
        """Re-connect on unexpected disconnect and run callbacks on failure.

        This function will re-connect if this is not an expected
        disconnect and if it fails to re-connect it will run
        state changed callbacks. If the re-connect is successful then
        no callbacks are executed.

        :param client: Bleak client.
        """

        # Ignore disconnect callbacks from old clients
        if client != self._client:
            return

        # Reset to false to ensure we
        self._supports_telemetry = False

        # If we expected the disconnect then we don't try to reconnect.
        if self._expect_disconnect:
            _LOGGER.info(f"Received expected disconnect from '{client}'.")
            return

        # Else we did not expect the disconnect and must re-connect if
        # there are attempts remaining
        _LOGGER.debug(f"Unexpected disconnect from '{client}'.")
        if (
            RECONNECT_ATTEMPTS_MAX == -1
            or self._connection_attempts < RECONNECT_ATTEMPTS_MAX
        ):
            # Try and reconnect
            self._reconnect_task = asyncio.create_task(self._reconnect())

        else:
            _LOGGER.warning(
                f"Maximum re-connect attempts to '{client}' exceeded. Auto re-connect disabled!"
            )

    def __str__(self) -> str:
        """Return string representation of device state."""
        self_str = f"{self.__class__.__name__}(\n"
        for name, value in {
            prop_name.upper(): prop.fget(self)
            for prop_name, prop in inspect.getmembers(type(self))
            if isinstance(prop, property)
        }.items():
            self_str += f"    {name}: {value},\n"
        self_str += ")"
        return self_str


class C300(SolixBLEDevice):

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    @property
    def ac_timer_remaining(self) -> int:
        """Time remaining on AC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int(16) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def ac_timer(self) -> datetime | None:
        """Timestamp of AC timer.

        :returns: Timestamp of when AC timer expires or None.
        """
        if (
            self.ac_timer_remaining != DEFAULT_METADATA_INT
            and self.ac_timer_remaining != 0
        ):
            return datetime.now() + timedelta(seconds=self.ac_timer_remaining)

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int(23) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def dc_timer(self) -> datetime | None:
        """Timestamp of DC timer.

        :returns: Timestamp of when DC timer expires or None.
        """
        if (
            self.dc_timer_remaining != DEFAULT_METADATA_INT
            and self.dc_timer_remaining != 0
        ):
            return datetime.now() + timedelta(seconds=self.dc_timer_remaining)

    @property
    def hours_remaining(self) -> float:
        """Time remaining to full/empty.

        Note that any hours over 24 are overflowed to the
        days remaining. Use time_remaining if you want
        days to be included.

        :returns: Hours remaining or default float value.
        """
        return (
            self._data[30] / 10.0 if self._data is not None else DEFAULT_METADATA_FLOAT
        )

    @property
    def days_remaining(self) -> int:
        """Time remaining to full/empty.

        :returns: Days remaining or default int value.
        """
        return self._data[31] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def time_remaining(self) -> float:
        """Time remaining to full/empty.

        This includes any hours which were overflowed
        into days.

        :returns: Hours remaining or default float value.
        """
        if (
            self.hours_remaining == DEFAULT_METADATA_FLOAT
            or self.days_remaining == DEFAULT_METADATA_INT
        ):
            return DEFAULT_METADATA_FLOAT

        return (self.days_remaining * 24) + self.hours_remaining

    @property
    def timestamp_remaining(self) -> datetime | None:
        """Timestamp of when device will be full/empty.

        :returns: Timestamp of when will be full/empty or None.
        """
        if self.time_remaining == DEFAULT_METADATA_FLOAT:
            return None
        return datetime.now() + timedelta(hours=self.time_remaining)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int(35) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: Total AC power out or default int value.
        """
        return self._parse_int(40) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._data[45] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._data[50] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_c3_power(self) -> int:
        """USB C3 Power.

        :returns: USB port C3 power or default int value.
        """
        return self._data[55] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._data[60] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def dc_power_out(self) -> int:
        """DC Power Out.

        :returns: DC power out or default int value.
        """
        return self._data[65] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int(70) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total power in or default int value.
        """
        return self._parse_int(75) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int(80) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def solar_port(self) -> PortStatus:
        """Solar Port Status.

        :returns: Status of the solar port.
        """
        return PortStatus(
            self._data[129] if self._data is not None else DEFAULT_METADATA_INT
        )

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._data[141] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_port_c1(self) -> PortStatus:
        """USB C1 Port Status.

        :returns: Status of the USB C1 port.
        """
        return PortStatus(
            self._data[149] if self._data is not None else DEFAULT_METADATA_INT
        )

    @property
    def usb_port_c2(self) -> PortStatus:
        """USB C2 Port Status.

        :returns: Status of the USB C2 port.
        """
        return PortStatus(
            self._data[153] if self._data is not None else DEFAULT_METADATA_INT
        )

    @property
    def usb_port_c3(self) -> PortStatus:
        """USB C3 Port Status.

        :returns: Status of the USB C3 port.
        """
        return PortStatus(
            self._data[157] if self._data is not None else DEFAULT_METADATA_INT
        )

    @property
    def usb_port_a1(self) -> PortStatus:
        """USB A1 Port Status.

        :returns: Status of the USB A1 port.
        """
        return PortStatus(
            self._data[161] if self._data is not None else DEFAULT_METADATA_INT
        )

    @property
    def dc_port(self) -> PortStatus:
        """DC Port Status.

        :returns: Status of the DC port.
        """
        return PortStatus(
            self._data[165] if self._data is not None else DEFAULT_METADATA_INT
        )

    @property
    def light(self) -> LightStatus:
        """Light Status.

        :returns: Status of the light bar.
        """
        return LightStatus(
            self._data[241] if self._data is not None else DEFAULT_METADATA_INT
        )


class C1000(SolixBLEDevice):

    _EXPECTED_TELEMETRY_LENGTH: int = 246

    @property
    def ac_timer_remaining(self) -> int:
        """Time remaining on AC timer.

        :returns: Seconds remaining or default int value.
        """
        return self._parse_int(15) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def ac_timer(self) -> datetime | None:
        """Timestamp of AC timer.

        :returns: Timestamp of when AC timer expires or None.
        """
        if (
            self.ac_timer_remaining != DEFAULT_METADATA_INT
            and self.ac_timer_remaining != 0
        ):
            return datetime.now() + timedelta(seconds=self.ac_timer_remaining)

    @property
    def hours_remaining(self) -> float:
        """Time remaining to full/empty.

        Note that any hours over 24 are overflowed to the
        days remaining. Use time_remaining if you want
        days to be included.

        :returns: Hours remaining or default float value.
        """
        return (
            self._data[29] / 10.0 if self._data is not None else DEFAULT_METADATA_FLOAT
        )

    @property
    def days_remaining(self) -> int:
        """Time remaining to full/empty.

        :returns: Days remaining or default int value.
        """
        return self._data[30] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def time_remaining(self) -> float:
        """Time remaining to full/empty.

        This includes any hours which were overflowed
        into days.

        :returns: Hours remaining or default float value.
        """
        if (
            self.hours_remaining == DEFAULT_METADATA_FLOAT
            or self.days_remaining == DEFAULT_METADATA_INT
        ):
            return DEFAULT_METADATA_FLOAT

        return (self.days_remaining * 24) + self.hours_remaining

    @property
    def timestamp_remaining(self) -> datetime | None:
        """Timestamp of when device will be full/empty.

        :returns: Timestamp of when will be full/empty or None.
        """
        if self.time_remaining == DEFAULT_METADATA_FLOAT:
            return None
        return datetime.now() + timedelta(hours=self.time_remaining)

    @property
    def ac_power_in(self) -> int:
        """AC Power In.

        :returns: Total AC power in or default int value.
        """
        return self._parse_int(34) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def ac_power_out(self) -> int:
        """AC Power Out.

        :returns: Total AC power out or default int value.
        """
        return self._parse_int(39) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_c1_power(self) -> int:
        """USB C1 Power.

        :returns: USB port C1 power or default int value.
        """
        return self._data[44] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_c2_power(self) -> int:
        """USB C2 Power.

        :returns: USB port C2 power or default int value.
        """
        return self._data[49] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_a1_power(self) -> int:
        """USB A1 Power.

        :returns: USB port A1 power or default int value.
        """
        return self._data[54] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def usb_a2_power(self) -> int:
        """USB A2 Power.

        :returns: USB port A2 power or default int value.
        """
        return self._data[59] if self._data is not None else DEFAULT_METADATA_INT

    @property
    def solar_power_in(self) -> int:
        """Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return self._parse_int(79) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def power_in(self) -> int:
        """Total Power In.

        :returns: Total power in or default int value.
        """
        return self._parse_int(84) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return self._parse_int(89) if self._data is not None else DEFAULT_METADATA_INT

    @property
    def solar_port(self) -> PortStatus:
        """Solar Port Status.

        :returns: Status of the solar port.
        """
        return PortStatus(
            self._data[149] if self._data is not None else DEFAULT_METADATA_INT
        )

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._data[169] if self._data is not None else DEFAULT_METADATA_INT


class Generic(SolixBLEDevice):
    """
    Generic to be used for adding support for an unsupported device.

    Add support for a device like this:

    1. Copy this subclass to a new class with a name of the device.
    2. Initialise the new class inside example.py and connect to it.
    3. Change values (e.g turn things on and off) to cause changes in the device state.
    4. Observe which values change in the log and add properties to your subclass that parse them (see C300, C1000, etc for examples).
    5. Profit???
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 0
