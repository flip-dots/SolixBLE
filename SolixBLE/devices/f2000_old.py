"""F2000 (pre-P) / 767 PowerHouse power station model.

Note this module supports older Anker SOLIX 767 / F2000, model number A1780.
This model was a different control scheme from the revised F2000P, model number A1780P, introduced in roughly 2024.

.. moduleauthor:: Chuck Claunch <cclaunch@gmail.com>

Thanks to Silverstone-ui and his github.com/Silverstone-ui/SolixBLEF2000 repo for discovery of the
extended packet.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import json
import logging

from bleak import BleakClient
from ..device import SolixBLEDevice
from ..states import ChargingStatus, LightStatus, TemperatureUnit
from ..const import DEFAULT_METADATA_BOOL, DEFAULT_METADATA_INT, DEFAULT_METADATA_STRING

#: GATT Service UUID for sending commands / negotiating.
UUID_COMMAND = "00007777-0000-1000-8000-00805f9b34fb"

_LOGGER = logging.getLogger(__name__)

class CommandType(Enum):
    """Various command types supported by the Anker."""
    POLL_EXTENDED = 0x01
    AC_TIMER = 0x02
    TWELVE_VOLT_TIMER = 0x03
    RECHARGE_POWER = 0x80
    SCREEN_TIMEOUT = 0x82
    AC_OUTPUT = 0x86
    TWELVE_VOLT_OUTPUT = 0x87
    SCREEN_BRIGHTNESS = 0x88
    POWER_SAVE = 0x8A
    LED = 0x8B


@dataclass
class Command:
    """Generic command class all other commands inherit from."""
    parameters: bytearray
    command_id: CommandType
    length: int

    HEADER = b"\x08\xee\x00\x00\x00\x02"

    def to_bytes(self):
        """Generate bytes to actually send to the Anker."""
        output = (
            self.HEADER
            + self.command_id.value.to_bytes(1, byteorder="little")
            + self.length.to_bytes(1, byteorder="little")
            + self.parameters
        )
        checksum = sum(output) & 0xFF
        command = output + bytes([checksum])
        return command

@dataclass
class PollExtendedCommand(Command):
    """Requests an extended telemetry packet."""
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.POLL_EXTENDED)
    length: int = field(init=False, default=11)

    def __post_init__(self):
        self.parameters = bytearray(b"\x00" + b"\x00")

@dataclass
class PowerSaveCommand(Command):
    """Turns Power Save mode on and off."""
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.POWER_SAVE)
    length: int = field(init=False, default=11)
    is_on: int

    def __post_init__(self):
        if 0 <= self.is_on <= 1:
            self.parameters = bytearray(
                b"\x00" + self.is_on.to_bytes(1, byteorder="little")
            )
        else:
            raise ValueError(f"is_on must be either 0 to 1. {self.is_on} was given.")


@dataclass
class AcOutputCommand(Command):
    """Turns the AC output on and off."""
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.AC_OUTPUT)
    length: int = field(init=False, default=11)
    is_on: int

    def __post_init__(self):
        if 0 <= self.is_on <= 1:
            self.parameters = bytearray(
                b"\x00" + self.is_on.to_bytes(1, byteorder="little")
            )
        else:
            raise ValueError(f"is_on must be either 0 to 1. {self.is_on} was given.")


@dataclass
class TwelveVoltOutputCommand(Command):
    """Turns the 12V output on and off."""
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.TWELVE_VOLT_OUTPUT)
    length: int = field(init=False, default=11)
    is_on: int

    def __post_init__(self):
        if 0 <= self.is_on <= 1:
            self.parameters = bytearray(
                b"\x00" + self.is_on.to_bytes(1, byteorder="little")
            )
        else:
            raise ValueError(f"is_on must be either 0 to 1. {self.is_on} was given.")


@dataclass
class ScreenBrightnessCommand(Command):
    """Sets the display screen brightness."""
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.SCREEN_BRIGHTNESS)
    length: int = field(init=False, default=11)
    brightness: int

    def __post_init__(self):
        if 0 <= self.brightness <= 3:
            self.parameters = bytearray(
                b"\x00" + self.brightness.to_bytes(1, byteorder="little")
            )
        else:
            raise ValueError(
                f"brightness must be a value from 0 to 3. {self.brightness} was given."
            )


@dataclass
class LedCommand(Command):
    """Sets the long LED strip on the side to various levels."""
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.LED)
    length: int = field(init=False, default=11)
    light_level: int

    def __post_init__(self):
        if 0 <= self.light_level <= 4:
            self.parameters = bytearray(
                b"\x00" + self.light_level.to_bytes(1, byteorder="little")
            )
        else:
            raise ValueError(
                f"light_level must be a value from 0 to 4. {self.light_level} was given."
            )


@dataclass
class RechargePowerCommand(Command):
    """
    Sets the amount of power (in watts) that the battery will draw from the AC input.
    
    Note: Not all values have been tested for this and it may be that only the canned values which appear in the Anker application are valid.
    Those values are: 200, 300, 400, 500, 600, 750, 1440.  "silent" = 749, "high speed" = 1439
    Note: When the battery is in charging mode, the ac_input_watts value in the Telemetry stream will include both any output wattage +
    this recharge value.  This is confusing because that value reads zero when the battery is not charging.  This behavior is confirmed
    working as intended via emails with Anker support.
    """
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.RECHARGE_POWER)
    length: int = field(init=False, default=12)
    power: int

    def __post_init__(self):
        if 200 <= self.power <= 1440:
            self.parameters = bytearray(
                b"\x00" + self.power.to_bytes(2, byteorder="little")
            )
        else:
            raise ValueError(
                f"power must be a value from 200 to 1440. {self.power} was given."
            )


@dataclass
class ScreenTimeoutCommand(Command):
    """Sets the display screen timeout."""
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.SCREEN_TIMEOUT)
    length: int = field(init=False, default=12)
    seconds: int

    def __post_init__(self):
        if 0 <= self.seconds <= 65535:
            self.parameters = bytearray(
                b"\x00" + self.seconds.to_bytes(2, byteorder="little")
            )
        else:
            raise ValueError(
                f"seconds must be a value from 0 to 65,535. {self.seconds} was given."
            )


@dataclass
class AcTimerCommand(Command):
    """
    Sets a timer for the AC output. 
    
    The output will turn off after this time expires.  A value of zero disables the timer.  Setting this while the output is off does nothing.
    """
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.AC_TIMER)
    length: int = field(init=False, default=14)
    seconds: int

    def __post_init__(self):
        if 0 <= self.seconds <= 65535:
            self.parameters = bytearray(
                b"\x00" + self.seconds.to_bytes(2, byteorder="little") + b"\x00\x00"
            )
        else:
            raise ValueError(
                f"seconds must be a value from 0 to 65,535. {self.seconds} was given."
            )


@dataclass
class TwelveVoltTimerCommand(Command):
    """
    Sets a timer for the 12V output. 
    
    The output will turn off after this time expires.  A value of zero disables the timer.  Setting this while the output is off does nothing.
    """
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.TWELVE_VOLT_TIMER)
    length: int = field(init=False, default=14)
    seconds: int

    def __post_init__(self):
        if 0 <= self.seconds <= 65535:
            self.parameters = bytearray(
                b"\x00" + self.seconds.to_bytes(2, byteorder="little") + b"\x00\x00"
            )
        else:
            raise ValueError(
                f"seconds must be a value from 0 to 65,535. {self.seconds} was given."
            )

class PacketType(Enum):
    """All notification data received is either telemetry or an ack from a command sent."""
    TELEMETRY = 1
    COMMAND_ACK = 2


class TelemetryType(Enum):
    """When a packet is telemetry it's either a state change or just telemetry."""
    EXTENDED = 0x01 # Extended telemetry packet (only comes when polled)
    STATE_ACK = 0x48  # Ack that gets received when command changes an output or the LED.
    TELEMETRY = 0x49  # Telemetry that gets received when starting the notify service.


@staticmethod
def extract16(data: bytes, index: int) -> int:
    """
    Helper function to get a 16 bit integer from an array of bytes.

    Args:
        data (bytes): Array of bytes
        index: (int): Index to get the 16 bit int from.

    Returns:
        int: The 16 bit integer extracted.

    Raises:
        IndexError: If the index given doesn't allow for a 16 bit int to be extracted.
    """
    return int.from_bytes(data[index : index + 2], byteorder="little")


@dataclass
class Header:
    """
    Header which contains the header bytes, packet ID, and packet length.
    """

    packet_type: PacketType
    packet_length: int
    telemetry_id: int

    EXPECTED_PACKET_LENGTH = 10

    @staticmethod
    def from_bytes(data: bytes) -> Optional["Header"]:
        """
        Parse a byte sequence into a Header for an incoming Anker PowerHouse packet.

        Args:
            data (bytes): The raw byte data from the Anker PowerHouse.

        Returns:
            Header: A Header instance parsed from the given data.

        Raises:
            ValueError: If the data length is incorrect.
            ValueError: If the packet_id field does not match a known TelemetryType.
        """
        # Make sure there are enough bytes for the smallest packet.
        if len(data) < Header.EXPECTED_PACKET_LENGTH:
            raise ValueError(
                f"Data length not correct expected {Header.EXPECTED_PACKET_LENGTH} got {len(data)}."
            )

        packet_id = data[5]
        telemetry_id = data[6]
        packet_length = int.from_bytes(data[7:9], byteorder="little")
        packet_type = PacketType(packet_id)

        return Header(
            packet_type=packet_type,
            telemetry_id=telemetry_id,
            packet_length=packet_length,
        )


@dataclass
class CommandAck:
    """
    Received in response to a sent command confirming it was received.
    """

    command_type: CommandType

    def pretty_print(self):
        """Prints CommandAck nicely."""
        command_ack = asdict(self)

        # Custom encoder function for custom types that can't be serialized by json.
        def custom_encoder(obj):
            if isinstance(obj, CommandType):
                return str(obj)
            raise TypeError(
                f"Object of type {obj.__class__.__name__} is not JSON serializable"
            )

        print(json.dumps(command_ack, indent=4, default=custom_encoder))


@dataclass
class StateAck:
    """
    Received when various physical buttons are pressed or commands are sent to change the state of the outputs.
    """

    ac_outlet_on: bool
    twelve_volt_on: bool
    power_save_on: bool
    light_status: LightStatus

    def pretty_print(self):
        """Prints StateAck nicely."""
        state_ack = asdict(self)

        # Custom encoder function just for LightStatus
        def custom_encoder(obj):
            if isinstance(obj, LightStatus):
                return str(obj)
            raise TypeError(
                f"Object of type {obj.__class__.__name__} is not JSON serializable"
            )

        print(json.dumps(state_ack, indent=4, default=custom_encoder))


@dataclass
class Output:
    """Outputs have on/off state, the output wattage, and if supported, timer remaining."""

    is_on: bool
    watts: int
    time_remaining: Optional[timedelta] = (
        None  # If the output supports this, time remaining before this output is turned off.
    )


@dataclass
class Battery:
    """Battries have temperature and percentage.  Currently only the internal battery and a single external battery appear to be supported"""
    temperature: int
    percentage: int

class Telemetry: # pylint: disable=too-many-instance-attributes
    """All data received in the notification from the Anker."""
    def __init__(self):
            
        
        self.battery_remaining: timedelta = timedelta(0)
        self.ac_outlet: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.twelve_volt_1: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.twelve_volt_2: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.usb_c_1: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.usb_c_2: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.usb_c_3: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.usb_a_1: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.usb_a_2: Output = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=0)
        self.total_output_watts: int = DEFAULT_METADATA_INT
        self.ac_input_watts: int = DEFAULT_METADATA_INT # Note this is only while charging and includes the output wattage (which is confusing but confirmed by Anker).
        self.solar_input_watts: int = DEFAULT_METADATA_INT
        self.total_input_watts: int = DEFAULT_METADATA_INT
        self.internal_battery: Battery = field(default_factory=Battery)
        self.external_battery: Battery = field(default_factory=Battery)
        self.charging_status: ChargingStatus = ChargingStatus.UNKNOWN
        self.battery_health: int = DEFAULT_METADATA_INT
        self.device_serial: str = ""
        self.recharge_power_limit: int = DEFAULT_METADATA_INT
        self.screen_timeout: int = DEFAULT_METADATA_INT
        self.screen_brightness: int = DEFAULT_METADATA_INT
        self.power_save_status: int = DEFAULT_METADATA_INT
        self.led_light_level: LightStatus = LightStatus.UNKNOWN
        self.temperature_unit: TemperatureUnit = TemperatureUnit.UNKNOWN
        self.last_command_type: CommandType = field(default_factory=CommandType)

    def from_bytes(self, data: bytes) -> None: # pylint: disable=too-many-locals
        """
        Parse a byte sequence into a Anker PowerHouse Telemetry instance.

        Args:
            data (bytes): The raw byte data from the Anker PowerHouse.

        Returns:
            Telemetry: A Telemetry instance parsed from the given data.

        Raises:
            ValueError: If the data length is incorrect.
            ValueError: If Header can't be parsed.
        """

        if len(data) < Header.EXPECTED_PACKET_LENGTH:
            raise ValueError(
                f"Data not long enough, expected at least {Header.EXPECTED_PACKET_LENGTH} got {len(data)}."
            )

        header = Header.from_bytes(data)

        if header.packet_type == PacketType.TELEMETRY:
            telemetry_type = TelemetryType(header.telemetry_id)
            if telemetry_type in [TelemetryType.TELEMETRY, TelemetryType.EXTENDED]:
                self.battery_remaining = timedelta(days=data[18], hours=data[17] / 10.0)
                self.ac_outlet = Output(is_on=data[63], watts=extract16(data, 21))
                self.twelve_volt_1 = Output(
                        is_on=data[80],
                        watts=extract16(data, 33),
                        time_remaining=timedelta(seconds=extract16(data, 13)),
                    )
                self.twelve_volt_2 = Output(
                        is_on=data[81],
                        watts=extract16(data, 35),
                        time_remaining=timedelta(seconds=extract16(data, 13)),
                    )
                self.usb_c_1 = Output(is_on=data[75], watts=extract16(data, 23))
                self.usb_c_1 = Output(is_on=data[76], watts=extract16(data, 25))
                self.usb_c_1 = Output(is_on=data[77], watts=extract16(data, 27))
                self.usb_a_1 = Output(is_on=data[78], watts=extract16(data, 29))
                self.usb_a_1 = Output(is_on=data[79], watts=extract16(data, 31))
                self.total_output_watts = extract16(data, 41)
                self.ac_input_watts = extract16(data, 19)
                self.solar_input_watts = extract16(data, 37)
                self.total_input_watts = extract16(data, 39)
                self.internal_battery = Battery(temperature=data[66], percentage=data[70])
                self.external_battery = Battery(temperature=data[67], percentage=data[71])
                self.charging_status = ChargingStatus(data[68])
                self.battery_health = data[72]
                self.device_serial = data[85:101].decode("utf-8")

                if telemetry_type == TelemetryType.EXTENDED:
                    self.recharge_power_limit = extract16(data, 101)
                    self.screen_timeout = extract16(data, 105)
                    self.screen_brightness = data[115]
                    self.power_save_status = data[117]
                    self.led_light_level = LightStatus(data[118])
                    self.temperature_unit = TemperatureUnit(data[119])

            if telemetry_type == TelemetryType.STATE_ACK:
                self.ac_outlet.is_on = data[9]
                self.twelve_volt_1.is_on = data[10]
                self.twelve_volt_2.is_on = data[10]
                self.power_save_on = data[11]
                self.led_light_level = LightStatus(data[12])
            
        elif header.packet_type == PacketType.COMMAND_ACK:
            self.last_command_type = CommandType(header.telemetry_id)


class F2000Old(SolixBLEDevice):
    """
    F2000 (non-P) Power Station.

    Use this class to connect and monitor a F2000(non-P, pre-2024) power station.
    This model is also known as the A1780 or the 767 PowerHouse.

    """

    UUID_TELEMETRY = "00008888-0000-1000-8000-00805f9b34fb"
    telemetry = Telemetry(

    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    async def _process_notification(
        self, client: BleakClient, handle: int, data: bytearray
    ) -> None:
        """Process a notification from the device."""

        _LOGGER.debug(f"The client the notification is from: {client}")

        if self._client is not client:
            _LOGGER.debug("Ignoring notification from old client")
            return

        _LOGGER.debug(
            f"Received notification from '{self.name}'. length: {len(data)}, packet: '{data.hex()}'"
        )

        try:
            self.telemetry.from_bytes(data)
        except ValueError as ex:
            _LOGGER.error(f"failed to parse telemetry packet: {ex}")

        self._last_data_timestamp = datetime.now()
        self._run_state_changed_callbacks()

    @property
    def negotiated(self) -> bool:
        """There's no encryption here so just use connected."""
        return self.connected

    @property
    def available(self) -> bool:
        """We're available once we have data"""
        return self.connected and self._last_data_timestamp is not None

    @property
    def power_out(self) -> int:
        """Total output power in watts"""
        return self.telemetry.total_output_watts

    @property
    def light(self) -> LightStatus:
        """State of the unit's LED light"""
        return self.telemetry.led_light_level
