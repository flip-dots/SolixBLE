"""F2000 (pre-P) / 767 PowerHouse power station model.

Note this module supports older Anker SOLIX 767 / F2000, model number A1780.
This model was a different control scheme from the revised F2000P, model number A1780P, introduced in roughly 2024.

.. moduleauthor:: Chuck Claunch <cclaunch@gmail.com>

Thanks to Silverstone-ui and his github.com/Silverstone-ui/SolixBLEF2000 repo for discovery of the
extended packet.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from bleak import BleakClient

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from ..device import SolixBLEDevice
from ..states import ChargingStatus, LightStatus, PortStatus, TemperatureUnit

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

    # overriding the header, apparently that last byte is some undiscovered field
    HEADER = b"\x08\xee\x00\x00\x00\x01"
    parameters: bytearray = field(init=False)
    command_id: CommandType = field(init=False, default=CommandType.POLL_EXTENDED)
    length: int = field(init=False, default=10)

    def __post_init__(self):
        self.parameters = bytearray(b"\x00")

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
            
        
        self.battery_remaining = timedelta(0)
        self.time_remaining = DEFAULT_METADATA_FLOAT
        self.days_remaining = DEFAULT_METADATA_INT
        self.hours_remaining = DEFAULT_METADATA_FLOAT
        self.ac_outlet = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.twelve_volt_1 = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.twelve_volt_2 = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.usb_c_1 = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.usb_c_2 = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.usb_c_3 = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.usb_a_1 = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.usb_a_2 = Output(is_on=DEFAULT_METADATA_BOOL, watts=DEFAULT_METADATA_INT, time_remaining=None)
        self.total_output_watts = DEFAULT_METADATA_INT
        self.ac_input_watts = DEFAULT_METADATA_INT # Note this is only while charging and includes the output wattage (which is confusing but confirmed by Anker).
        self.solar_input_watts = DEFAULT_METADATA_INT
        self.total_input_watts = DEFAULT_METADATA_INT
        self.internal_battery = Battery(temperature=DEFAULT_METADATA_INT, percentage=DEFAULT_METADATA_INT)
        self.external_battery = Battery(temperature=DEFAULT_METADATA_INT, percentage=DEFAULT_METADATA_INT)
        self.charging_status = ChargingStatus.UNKNOWN
        self.battery_health = DEFAULT_METADATA_INT
        self.device_serial = DEFAULT_METADATA_STRING
        self.recharge_power_limit = DEFAULT_METADATA_INT
        self.screen_timeout = DEFAULT_METADATA_INT
        self.screen_brightness = LightStatus.UNKNOWN
        self.power_save_status = DEFAULT_METADATA_INT
        self.led_light_level = LightStatus.UNKNOWN
        self.temperature_unit = TemperatureUnit.UNKNOWN
        self.firmware_version = DEFAULT_METADATA_STRING
        self.last_command_type = None

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
            telemetry_type = TelemetryType.TELEMETRY

            # If a command was issued, the next telemetry packet's telemetry ID is the Command ID
            # of the last command sent, so just keep it and parse the telemetry as normal.
            if header.telemetry_id in [t.value for t in TelemetryType]:
                telemetry_type = TelemetryType(header.telemetry_id)
            else:
                self.last_command_type = CommandType(header.telemetry_id)

            try:
                if telemetry_type in [TelemetryType.TELEMETRY, TelemetryType.EXTENDED]:
                    self.days_remaining = data[18]
                    self.hours_remaining = data[17] / 10.0
                    self.battery_remaining = timedelta(days=self.days_remaining, hours=self.hours_remaining)
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
                    self.usb_c_2 = Output(is_on=data[76], watts=extract16(data, 25))
                    self.usb_c_3 = Output(is_on=data[77], watts=extract16(data, 27))
                    self.usb_a_1 = Output(is_on=data[78], watts=extract16(data, 29))
                    self.usb_a_2 = Output(is_on=data[79], watts=extract16(data, 31))
                    self.total_output_watts = extract16(data, 41)
                    self.ac_input_watts = extract16(data, 19)
                    self.solar_input_watts = extract16(data, 37)
                    self.total_input_watts = extract16(data, 39)
                    self.firmware_version = ".".join(str(data[47]))
                    self.internal_battery = Battery(temperature=data[66], percentage=data[70])
                    self.external_battery = Battery(temperature=data[67], percentage=data[71])
                    # There's an odd thing when sending some commands, the charging status briefly goes
                    # to 3, which is an unknown value at this point.
                    tmp_charging_status = data[68]
                    if tmp_charging_status in [c.value for c in ChargingStatus]:
                        self.charging_status = ChargingStatus(data[68])
                    else:
                        self.charging_status = ChargingStatus.UNKNOWN
                    self.battery_health = data[72]
                    self.device_serial = data[85:101].decode("utf-8")

                    if telemetry_type == TelemetryType.EXTENDED:
                        self.recharge_power_limit = extract16(data, 101)
                        self.screen_timeout = extract16(data, 105)
                        self.screen_brightness = LightStatus(data[115])
                        self.power_save_status = data[117]
                        self.led_light_level = LightStatus(data[118])
                        self.temperature_unit = TemperatureUnit(data[119])

                if telemetry_type == TelemetryType.STATE_ACK:
                    self.ac_outlet.is_on = data[9]
                    self.twelve_volt_1.is_on = data[10]
                    self.twelve_volt_2.is_on = data[10]
                    self.power_save_status = data[11]
                    self.led_light_level = LightStatus(data[12])
            except Exception as ex:
                _LOGGER.error(f"{ex}: {header.telemetry_id}: bytes: {data.hex(' ')}")
            
        elif header.packet_type == PacketType.COMMAND_ACK:
            self.last_command_type = CommandType(header.telemetry_id)


class F2000Legacy(SolixBLEDevice):
    """
    F2000 (non-P) Power Station.

    Use this class to connect and monitor a F2000(non-P, pre-2024) power station.
    This model is also known as the A1780 or the 767 PowerHouse.

    """

    # These are specific to the older firmware
    UUID_TELEMETRY = "00008888-0000-1000-8000-00805f9b34fb"
    UUID_COMMAND = "00007777-0000-1000-8000-00805f9b34fb"

    telemetry = Telemetry()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._data_received = False

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

        # First time around poll for the extended data
        if not self._data_received:
            await self.send_poll_extended()
            self._data_received = True

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

    @property
    def time_remaining(self) -> float:
        """Total time in hours remaining"""
        return self.telemetry.days_remaining * 24.0 + self.telemetry.hours_remaining

    @property
    def timestamp_remaining(self) -> datetime | None:
        """Time remaining as a datetime
        
        We only return this if we're actually discharging otheriwse
        the value jumps around wildly and causes HA to record state changes with
        every new value.  The value is useless in idle mode anyways.
        """
        if self.telemetry.charging_status == ChargingStatus.DISCHARGING:
            return datetime.now() + self.telemetry.battery_remaining
        else:
            return None

    @property
    def hours_remaining(self) -> float:
        """Hours portion of timestamp remaining"""
        return self.telemetry.hours_remaining

    @property
    def days_remaining(self) -> int:
        """Days portion of timestamp remaining"""
        return self.telemetry.days_remaining

    @property
    def battery_percentage(self) -> int:
        """Battery percentage remaining"""
        return self.telemetry.internal_battery.percentage

    @property
    def battery_percentage_expansion(self) -> int | None:
        """Battery percentage remaining of the expansion battery
        
        Whether or not an expansion battery is currently connected still hasn't been
        discovered, so we just assume if percentage is zero we don't have one
        connected.  Testing with an actual expansion battery is needed to confirm.
        """
        if self.telemetry.external_battery.percentage > 0:
            return self.telemetry.external_battery.percentage
        else:
            return None

    @property
    def temperature(self) -> int:
        """Temperature of the internal battery"""
        return self.telemetry.internal_battery.temperature

    @property
    def temperature_expansion(self) -> int | None:
        """Temperature of the expansion battery
        
        Similar to the expansion battery percentage we'll assume if percentage is
        zero, we do not have an external battery.
        """
        if self.battery_percentage_expansion is not None:
            return self.telemetry.external_battery.temperature
        else:
            return None

    @property
    def battery_health(self) -> int:
        """Health of the battery as a percentage
        
        This has not been 100% confirmed as the correct value.
        """
        return self.telemetry.battery_health

    @property
    def power_in(self) -> int:
        """Total input power in watts"""
        return self.telemetry.total_input_watts

    @property
    def ac_power_in(self) -> int:
        """AC input power in watts"""
        return self.telemetry.ac_input_watts

    @property
    def ac_power_in_limit(self) -> int:
        """AC input power limit in watts"""
        return self.telemetry.recharge_power_limit

    @property
    def ac_power_out(self) -> int:
        """AC output power in watts"""
        return self.telemetry.ac_outlet.watts

    @property
    def ac_output(self) -> PortStatus:
        """AC output status
        
        Note this simply maps 0 or 1 on the F2000, which works out in the
        PortStatus enum.
        """
        if self.telemetry.ac_outlet.is_on:
            return PortStatus(value=PortStatus.OUTPUT)
        else:
            return PortStatus(value=PortStatus.NOT_CONNECTED)

    @property
    def solar_power_in(self) -> int:
        """Solar power input in watts"""
        return self.telemetry.solar_input_watts

    @property
    def dc_power_out(self) -> int:
        """DC output power in watts
        
        We total the two ports to get total DC output watts
        """
        return self.telemetry.twelve_volt_1.watts + self.telemetry.twelve_volt_2.watts

    @property
    def dc_1_power_out(self) -> int:
        """DC power output for port 1"""
        return self.telemetry.twelve_volt_1.watts

    @property
    def dc_2_power_out(self) -> int:
        """DC power output for port 2"""
        return self.telemetry.twelve_volt_2.watts    

    @property
    def dc_output(self) -> PortStatus:
        """Whether DC output is on or not"""
        if (self.telemetry.twelve_volt_1.is_on or self.telemetry.twelve_volt_2.is_on):
            return PortStatus(value=PortStatus.OUTPUT)
        else:
            return PortStatus(value=PortStatus.NOT_CONNECTED)

    @property
    def dc_timer_remaining(self) -> int:
        """Time remaining on DC timer in seconds"""
        if self.telemetry.twelve_volt_1.time_remaining and self.telemetry.twelve_volt_1.time_remaining.total_seconds() > 0.0:
            return int(self.telemetry.twelve_volt_1.time_remaining.total_seconds())
        else:
            return DEFAULT_METADATA_INT

    @property
    def dc_timer(self) -> datetime | None:
        """Timestamp of when the DC timer will expire"""
        if self.dc_timer_remaining > 0.0:
            return datetime.now() + self.telemetry.twelve_volt_1.time_remaining
    
    @property
    def usb_c1_power(self) -> int:
        """Top USB-C port power in watts"""
        return self.telemetry.usb_c_1.watts

    @property
    def usb_c2_power(self) -> int:
        """Middle USB-C port power in watts"""
        return self.telemetry.usb_c_2.watts

    @property
    def usb_c3_power(self) -> int:
        """Bottom USB-C port power in watts"""
        return self.telemetry.usb_c_3.watts

    @property
    def usb_a1_power(self) -> int:
        """Top USB-A port power in watts"""
        return self.telemetry.usb_a_1.watts

    @property
    def usb_a2_power(self) -> int:
        """Bottom USB-A port power in watts"""
        return self.telemetry.usb_a_2.watts

    @property
    def usb_port_c1(self) -> PortStatus:
        """Top USB-C port output status"""
        if self.telemetry.usb_c_1.is_on:
            return PortStatus(value=PortStatus.OUTPUT)
        else:
            return PortStatus(value=PortStatus.NOT_CONNECTED)

    @property
    def usb_port_c2(self) -> PortStatus:
        """Middle USB-C port output status"""
        if self.telemetry.usb_c_2.is_on:
            return PortStatus(value=PortStatus.OUTPUT)
        else:
            return PortStatus(value=PortStatus.NOT_CONNECTED)

    @property
    def usb_port_c3(self) -> PortStatus:
        """Bottom USB-C port output status"""
        if self.telemetry.usb_c_3.is_on:
            return PortStatus(value=PortStatus.OUTPUT)
        else:
            return PortStatus(value=PortStatus.NOT_CONNECTED)

    @property
    def usb_port_a1(self) -> PortStatus:
        """Top USB-A port output status"""
        if self.telemetry.usb_a_1.is_on:
            return PortStatus(value=PortStatus.OUTPUT)
        else:
            return PortStatus(value=PortStatus.NOT_CONNECTED)

    @property
    def usb_port_a2(self) -> PortStatus:
        """Bottom USB-A port output status"""
        if self.telemetry.usb_a_2.is_on:
            return PortStatus(value=PortStatus.OUTPUT)
        else:
            return PortStatus(value=PortStatus.NOT_CONNECTED)

    @property
    def charging_status(self) -> ChargingStatus:
        """What state the device is in, charging/discharging/etc"""
        return self.telemetry.charging_status

    @property
    def software_version(self) -> str:
        """Firmware version of the unit"""
        return self.telemetry.firmware_version

    @property
    def serial_number(self) -> str:
        """Serial number of the unit"""
        return self.telemetry.device_serial

    @property
    def power_saving_mode_enabled(self) -> bool | None:
        if self.telemetry.power_save_status != DEFAULT_METADATA_BOOL:
            return (self.telemetry.power_save_status == 1)
        return self.telemetry.power_save_status

    @property
    def screen_timeout(self) -> int | None:
        return self.telemetry.screen_timeout

    @property
    def screen_brightness(self) -> LightStatus:
        return self.telemetry.screen_brightness

    async def send_command(self, command: Command) -> None:
        """Send a command to the unit"""
        if not self.connected:
            raise ConnectionError(f"Not connected to '{self.name}', could not send command {type(command)}")
        await self._client.write_gatt_char(self.UUID_COMMAND, command.to_bytes(), response=False)

    async def set_light_mode(self, mode: LightStatus) -> None:
        """Set the light bar mode"""
        command = LedCommand(light_level=mode.value)
        await self.send_command(command=command)
        # optimistically set the light here because it doesn't update in the nominal telemetry
        self.telemetry.led_light_level = mode
        await self.send_poll_extended()

    async def send_poll_extended(self) -> None:
        """Send the unit a request for the extended data
        
        This is a one shot request
        """
        command = PollExtendedCommand()
        await self.send_command(command=command)

    async def turn_power_saving_mode_on(self) -> None:
        """Turn the power saving mode on"""
        command = PowerSaveCommand(is_on=1)
        await self.send_command(command=command)
        self.telemetry.power_save_status = 1
        await self.send_poll_extended()

    async def turn_power_saving_mode_off(self) -> None:
        """Turn the power saving mode on"""
        command = PowerSaveCommand(is_on=0)
        await self.send_command(command=command)
        self.telemetry.power_save_status = 0
        await self.send_poll_extended()

    async def set_screen_brightness(self, brightness: LightStatus) -> None:
        """Set screen brightness"""
        command = ScreenBrightnessCommand(brightness=brightness.value)
        await self.send_command(command=command)
        self.telemetry.screen_brightness = brightness
        await self.send_poll_extended()

    async def set_ac_power_in_limit(self, limit: int) -> None:
        """Set the limit of the AC input power in watts"""
        command = RechargePowerCommand(power=limit)
        await self.send_command(command=command)
        self.telemetry.recharge_power_limit=limit
        await self.send_poll_extended()

    async def turn_dc_on(self) -> None:
        """Turn the DC (12V) output on"""
        command = TwelveVoltOutputCommand(is_on=1)
        await self.send_command(command=command)

    async def turn_dc_off(self) -> None:
        """Turn the DC (12V) output off"""
        command = TwelveVoltOutputCommand(is_on=0)
        await self.send_command(command=command)

    async def turn_ac_on(self) -> None:
        """Turn the ac output on"""
        command = AcOutputCommand(is_on=1)
        await self.send_command(command=command)

    async def turn_ac_off(self) -> None:
        """Turn the ac output off"""
        command = AcOutputCommand(is_on=0)
        await self.send_command(command=command)

    async def set_screen_timeout(self, seconds: int) -> None:
        """Set the timeout for the screen in seconds"""
        command = ScreenTimeoutCommand(seconds=seconds)
        await self.send_command(command=command)
        self.telemetry.screen_timeout = seconds
        await self.send_poll_extended()

    async def set_dc_timer(self, duration: timedelta) -> None:
        """Set a timer which will turn off the DC output when elapsed"""
        seconds = int(duration.total_seconds())
        command = TwelveVoltTimerCommand(seconds=seconds)
        await self.send_command(command=command)
