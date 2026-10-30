"""C2000(X) Gen 2 power station model.

.. moduleauthor:: kb1ibt

"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
    Flag,
    Int8sb,
    Int8ub,
    Int16ul,
    Int32ul,
    PascalString,
    Struct,
)

from SolixBLE.const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.constructs import (
    Channel,
    ParameterDict,
    Parameters,
    SummaryPayload,
)
from SolixBLE.devices.c1000g2 import (
    A3_STATUS,
    A4_SETTINGS,
    A5_BATTERY,
    C1000G2,
    CMD_AC_OUTPUT,
    CMD_SUBSCRIBE,
    CMD_SYSTEM,
    PARAMETERS_SUBSCRIBE,
    VERSION_QUAD,
    epoch_to_local,
)
from SolixBLE.devices.c2000g2_summary import SUMMARY_MAPS
from SolixBLE.parsing import SummaryField, name_summary, walk_protobuf
from SolixBLE.protocols import EncryptedOuter
from SolixBLE.states import ChargingStatus
from SolixBLE.utilities import _parse_guarded

_LOGGER = logging.getLogger(__name__)


class AcInputState(Enum):
    """Whether the device takes power from the AC input."""

    #: The state is unknown.
    UNKNOWN = -1

    #: AC input is accepted.
    ACCEPTED = 0

    #: AC input is switched off, so loads run from the battery only.
    DISABLED = 1

    #: AC input is off on its own: mains is unplugged or the main battery is
    #: at its discharge floor.
    AUTO_OFF = 2


class BmsFault(Enum):
    """A battery fault reported by the device."""

    #: The fault is unknown.
    UNKNOWN = -1

    #: No fault.
    NONE = 0

    #: Discharge over-temperature.
    DISCHARGE_OVER_TEMPERATURE = 1

    #: Discharge low temperature.
    DISCHARGE_LOW_TEMPERATURE = 2

    #: Low battery.
    LOW_BATTERY = 3

    #: Battery management system communication error.
    BMS_COMMUNICATION = 4

    #: Over-current.
    OVER_CURRENT = 5

    #: MOSFET over-temperature.
    MOS_OVER_TEMPERATURE = 6

    #: Pre-discharge MOSFET fault.
    PRE_DISCHARGE_MOS = 7

    #: Charge MOSFET fault.
    CHARGE_MOS = 8

    #: Discharge MOSFET fault.
    DISCHARGE_MOS = 9


class DeviceEventType(Enum):
    """An event the device reports on its own."""

    #: The event is unknown.
    UNKNOWN = -1

    #: A Storm Guard backup window started.
    STORM_GUARD_START = 0x07

    #: A Storm Guard backup window ended.
    STORM_GUARD_END = 0x08

    #: A Fast Charging Plan window started.
    FAST_CHARGING_PLAN_START = 0x0A

    #: A Fast Charging Plan window ended.
    FAST_CHARGING_PLAN_END = 0x0B

    #: The main battery is at 1 % or below.
    BATTERY_CRITICAL = 0x50

    #: The main battery is at 10 % or below.
    BATTERY_LOW = 0x52

    #: The AC output timer ran out.
    AC_TIMER_EXPIRED = 0x55

    #: The DC (car socket) output timer ran out.
    DC_TIMER_EXPIRED = 0x56

    #: The AC grid was lost.
    GRID_LOSS = 0x59


class OtaBlockReason(Enum):
    """Why the device would refuse a firmware update."""

    #: The reason is unknown.
    UNKNOWN = -1

    #: Nothing blocks an update.
    NONE = 0

    #: A battery is below 6 %.
    LOW_BATTERY = 2

    #: The battery level can't be read, and mains must be plugged in.
    CONNECT_AC = 4


@dataclass(frozen=True)
class DeviceEvent:
    """An event the device reported on its own.

    :param event: The event.
    :param code: The raw event code.
    :param start: Start of the window the event reports, if any.
    :param end: End of the window the event reports, if any.
    :param battery_percentage: Battery percentage at a grid loss, else None.
    :param received: When the event arrived.
    """

    event: DeviceEventType
    code: int
    start: datetime | None
    end: datetime | None
    battery_percentage: int | None
    received: datetime


C0_EXPANSION = Struct(
    "serial_number" / PascalString(Int8ub, "ascii"),
    "number" / Int8ub,
    "version" / VERSION_QUAD,
    "temperature" / Int8sb,
    "charge_discharge_status" / Int8ub,
    "battery_percentage" / Int8ub,
    "main_health" / Int8ub,
    "blink" / Int8ub,
    "output_on" / Flag,
    "error_code" / Int8ub,
    "connected" / Flag,
    "balance" / Int8ub,
    "type" / PascalString(Int8ub, "ascii"),
)
"""
Expansion battery (``c0``), emitted with or without a pack attached; its
values hold only while ``connected`` is set.
"""

DC_FAULT = Struct(
    "fault" / Int8ub,
    "fault_time" / Int32ul,
)
"""
Output-memory fault (``dc``): the battery fault blocking the restore and
when the outputs are due back, both 0 while there is none.
"""

EVENT_CODE = Int8ub
"""An event report's or event push's code (``a2``)."""

EPOCH = Int32ul
"""A window's start or end in an event report (``a3`` / ``a4``)."""

#: Realtime stream latch: ``a2`` 1 starts the ``c421`` pushes.
CMD_REALTIME = 0x057

PARAMETERS_REALTIME_ON = {
    "a1": {
        "value": "21",
    },
    "a2": {
        "type": 1,
        "value": 1,
    },
}

#: The AC group switches the AC input off with ab = 1 (a u16).
PARAMETERS_AC_INPUT = {
    "a1": {
        "value": "21",
    },
    "ab": {
        "type": 2,
        "value": lambda off: Int16ul.build(1 if off else 0),
    },
}

PARAMETERS_OUTAGE_ALERT = {
    "a1": {
        "value": "21",
    },
    "b0": {
        "type": 1,
        "value": lambda on: 1 if on else 0,
    },
}

#: Clock-screen read and its reply, which names the clock theme.
CMD_DISPLAY_THEME_NAME = 0x092
CMD_RESPONSE_DISPLAY_THEME_NAME = 0x892

#: Firmware-update readiness read and its reply.
CMD_OTA_STATUS = 0x089
CMD_RESPONSE_OTA_STATUS = 0x889

#: Telemetry reply drawn by the subscribe command when it is used as a poll.
CMD_RESPONSE_GET_STATUS = 0x900

#: Message types the device pushes on its own: the event report, the event
#: push, the firmware-update readiness and the device summary.
MSGTYPE_EVENT_REPORT = 0x425
MSGTYPE_EVENT_PUSH = 0x403
MSGTYPE_OTA_STATUS = 0x489
MSGTYPE_SUMMARY = 0x490

#: Work status while a firmware update runs; absent from ChargingStatus.
WORK_STATUS_UPDATING = 5

#: Watt-hours per kWh, and the kWh digits the 0.1 Wh energy counters carry.
WH_PER_KWH = 1000.0
KWH_DIGITS = 4


def _charging_status(code: int) -> ChargingStatus:
    """Map a flow code to a charging status.

    :param code: The device's flow code.
    :returns: The status, or UNKNOWN for a code outside the enum.
    """
    try:
        return ChargingStatus(code)
    except ValueError:
        return ChargingStatus.UNKNOWN


class C2000G2(C1000G2):
    """
    C2000(X) Gen 2 Power Station.

    Use this class to connect, monitor and control a Gen 2 C2000(X) power
    station. This model is also known as the A1783.

    .. note::
       :collapsible: closed

       The device negotiates on the encrypted outer protocol. On connect it
       is subscribed (``4100``) and its realtime stream (``4057``) is
       started, so it pushes every change.

       It also posts a ``c490`` device summary about every nine minutes, a
       protobuf decoded into :attr:`summary` against the schema the frame
       names. The post can't be requested, and the device sends it only
       after it has reached the vendor cloud, so a unit kept off the network
       may never post one.
    """

    _OUTER_HINT = EncryptedOuter

    #: Write without response, as the app writes every packet to this station.
    _COMMAND_WRITE_RESPONSE = False

    def __init__(
        self,
        ble_device: BLEDevice,
        advertisement: AdvertisementData | None = None,
        client_token: str | None = None,
    ) -> None:
        """Initialise device object. Does not connect automatically.

        :param ble_device: The bleak device to wrap.
        :param advertisement: The device's scan result, if available.
        :param client_token: Sent in the ECDH path's registration.
        """
        super().__init__(ble_device, advertisement, client_token)
        self._summary: dict[str, object] = {}
        self._summary_schema: str | None = None
        self._last_summary_timestamp: datetime | None = None
        self._unmapped_summary_schemas: set[str | None] = set()
        self._last_event: DeviceEvent | None = None
        self._ota_allowed: bool | None = None
        self._ota_block_reason = OtaBlockReason.UNKNOWN

    ###########
    # Battery #
    ###########

    @property
    def battery_health(self) -> int:
        """Battery health.

        .. note::
           :collapsible: closed

           Read from the device summary (see :attr:`summary`), the only place
           the device reports the whole value, so it stays unknown until a
           summary from firmware v1.2.1.6 or later arrives.

        :returns: Percentage battery health or default int value.
        """
        return self._summary_percentage("battery_health")

    @property
    def charging_status(self) -> ChargingStatus:
        """Whether the battery is charging, discharging or idle.

        .. note::
           :collapsible: closed

           Follows the port powers: charging while input exceeds output,
           discharging while anything is drawn. It reads whichever battery
           is on the bus, main or expansion, and changes 2-3 s ahead of
           :attr:`charging_status_main`.

        :returns: Charging status, or UNKNOWN if there is no data.
        """
        battery = self._tag("a5", A5_BATTERY)
        if battery is None:
            return ChargingStatus.UNKNOWN

        code: int = battery.charge_discharge_status
        expansion = self._expansion()
        if code == 0 and expansion is not None:
            code = expansion.charge_discharge_status
        return _charging_status(code)

    @property
    def charging_status_main(self) -> ChargingStatus:
        """Whether the main battery's current is charging or discharging it.

        .. note::
           :collapsible: closed

           Follows the main battery's current (0.3 A for about 2 s), so it
           lags :attr:`charging_status` by 2-3 s and reads IDLE while the
           expansion battery carries the load. A firmware update puts it in a
           state outside the enum; see :attr:`firmware_updating`.

        :returns: Charging status, or UNKNOWN if there is no data.
        """
        status = self._tag("a3", A3_STATUS)
        if status is None:
            return ChargingStatus.UNKNOWN
        return _charging_status(status.work_status)

    @property
    def firmware_updating(self) -> bool | None:
        """Whether a firmware update is in progress.

        :returns: True while updating, else False, or default bool value if
            there is no data.
        """
        status = self._tag("a3", A3_STATUS)
        if status is None:
            return DEFAULT_METADATA_BOOL
        work_status: int = status.work_status
        return work_status == WORK_STATUS_UPDATING

    @property
    def max_battery_percentage(self) -> int:
        """Maximum charge percentage.

        :returns: Battery charge percentage upper limit or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return (
            DEFAULT_METADATA_INT
            if settings is None
            else settings.max_battery_percentage
        )

    @property
    def min_battery_percentage(self) -> int:
        """Minimum charge percentage.

        :returns: Battery charge percentage lower limit or default int value.
        """
        settings = self._tag("a4", A4_SETTINGS)
        return (
            DEFAULT_METADATA_INT
            if settings is None
            else settings.min_battery_percentage
        )

    @property
    def memory_switch_error(self) -> BmsFault:
        """Battery fault that stopped the outputs returning after a restart.

        :returns: The fault, NONE while there is none, or UNKNOWN.
        """
        fault = self._tag("dc", DC_FAULT)
        if fault is None:
            return BmsFault.UNKNOWN
        try:
            return BmsFault(fault.fault)
        except ValueError:
            return BmsFault.UNKNOWN

    @property
    def memory_switch_error_time(self) -> datetime | None:
        """When the outputs are due to return after :attr:`memory_switch_error`.

        :returns: Local time, or None while there is no fault.
        """
        fault = self._tag("dc", DC_FAULT)
        return None if fault is None else epoch_to_local(fault.fault_time)

    #####################
    # Expansion battery #
    #####################

    @property
    def num_expansion(self) -> int:
        """Number of expansion batteries.

        .. note::
           The expansion block is sent whether or not a pack is attached; the
           C2000 Gen 2 has one expansion slot.

        :returns: Number of expansion batteries or default int value.
        """
        if self._tag("c0", C0_EXPANSION) is None:
            return DEFAULT_METADATA_INT
        return 0 if self._expansion() is None else 1

    @property
    def serial_number_expansion(self) -> str:
        """Serial number of the expansion battery.

        :returns: Serial number, or default str value if no pack is attached.
        """
        expansion = self._expansion()
        return DEFAULT_METADATA_STRING if expansion is None else expansion.serial_number

    @property
    def temperature_expansion(self) -> int:
        """Temperature of the expansion battery (C).

        :returns: Temperature in degrees C, or default int value if no pack is
            attached.
        """
        expansion = self._expansion()
        return DEFAULT_METADATA_INT if expansion is None else expansion.temperature

    @property
    def battery_percentage_expansion(self) -> int:
        """Battery percentage of the expansion battery.

        :returns: Percentage charge, or default int value if no pack is attached.
        """
        expansion = self._expansion()
        return (
            DEFAULT_METADATA_INT if expansion is None else expansion.battery_percentage
        )

    @property
    def battery_health_expansion(self) -> int:
        """Battery health of the expansion battery.

        .. note::
           Read from the device summary, like :attr:`battery_health`.

        :returns: Percentage battery health or default int value.
        """
        if self._expansion() is None:
            return DEFAULT_METADATA_INT
        return self._summary_percentage("battery_health_expansion")

    @property
    def expansion_output_on(self) -> bool | None:
        """Whether the expansion battery's output is switched on.

        .. note::
           This is the state the pack reports. Switching it off doesn't stick:
           the pack closes its output again within about two seconds.

        :returns: True if on, False if off, or None if no pack is attached.
        """
        expansion = self._expansion()
        if expansion is None:
            return None
        output_on: bool = expansion.output_on
        return output_on

    @property
    def software_version_expansion(self) -> str:
        """Software version of the expansion battery.

        :returns: Firmware version, or default str value if no pack is attached.
        """
        expansion = self._expansion()
        return DEFAULT_METADATA_STRING if expansion is None else expansion.version

    #########
    # Power #
    #########

    @property
    def ac_input_state(self) -> AcInputState:
        """Whether the device takes power from the AC input.

        .. note::
           Switched off, the AC input comes back on by itself when the main
           battery reaches its discharge floor or mains is unplugged.

        :returns: AC input state, or UNKNOWN (also on firmware that doesn't
            report it).
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None or settings.flags is None:
            return AcInputState.UNKNOWN
        try:
            return AcInputState(settings.flags.flags.ac_input_state)
        except ValueError:
            return AcInputState.UNKNOWN

    ############
    # Settings #
    ############

    @property
    def outage_alert_enabled(self) -> bool | None:
        """Whether the device alerts when the AC grid is lost.

        :returns: True if enabled, False if disabled, or default bool value
            (also on firmware that doesn't report it).
        """
        settings = self._tag("a4", A4_SETTINGS)
        if settings is None or settings.flags is None:
            return DEFAULT_METADATA_BOOL
        enabled: bool = settings.flags.flags.outage_alert_enabled
        return enabled

    ##########
    # Pushes #
    ##########

    @property
    def last_event(self) -> DeviceEvent | None:
        """The latest event the device reported on its own.

        .. note::
           :collapsible: closed

           The device reports when a Storm Guard or Fast Charging Plan window
           starts or ends, when the AC grid is lost, when the main battery
           falls to 10 % and to 1 %, and when an output timer runs out. Each
           new event runs the state change callbacks.

        :returns: The latest event, or None until one arrives.
        """
        return self._last_event

    @property
    def ota_allowed(self) -> bool | None:
        """Whether the device would accept a firmware update now.

        Pushed by the device when it changes, and read with
        :meth:`get_ota_status`.

        :returns: True if allowed, False if not, or None until reported.
        """
        return self._ota_allowed

    @property
    def ota_block_reason(self) -> OtaBlockReason:
        """Why the device would refuse a firmware update.

        :returns: The reason, NONE when allowed, or UNKNOWN until reported.
        """
        return self._ota_block_reason

    ##################
    # Device summary #
    ##################

    @property
    def summary(self) -> dict[str, object]:
        """Fields from the latest device summary.

        .. note::
           :collapsible: closed

           The device posts a protobuf summary about every nine minutes,
           against a schema it names in the frame. Fields of a known schema
           appear under their names with scaling applied, the expansion
           battery's with an ``_expansion`` suffix; anything else is kept
           under its protobuf ``.path``. The summary can't be requested, so
           this stays empty until one arrives.

        :returns: Mapping of field name to value.
        """
        return self._summary

    @property
    def summary_schema(self) -> str | None:
        """The schema name of the latest device summary.

        :returns: The schema name, or None until a summary has been received.
        """
        return self._summary_schema

    @property
    def last_summary_update(self) -> datetime | None:
        """Timestamp of the last device summary.

        :returns: Timestamp of the last summary or None.
        """
        return self._last_summary_timestamp

    @property
    def ac_charged_energy(self) -> float | None:
        """Total energy charged through the AC input in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_input_energy")

    @property
    def dc_charged_energy(self) -> float | None:
        """Total energy charged through the DC input in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_input_energy")

    @property
    def ac_output_energy(self) -> float | None:
        """Total energy discharged through the AC output in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("ac_output_energy")

    @property
    def dc_output_energy(self) -> float | None:
        """Total energy discharged through the DC and USB outputs in kWh.

        :returns: Energy in kWh, or None until a summary has been received.
        """
        return self._summary_kwh("dc_output_energy")

    @property
    def dc_input_voltage(self) -> float | None:
        """Voltage at the DC (XT-60i) input in volts.

        Reported in the device summary, so it is at most about nine minutes old.

        :returns: Voltage in V, or None until a summary has been received.
        """
        value = self._summary.get("dc_input_voltage")
        return float(value) if isinstance(value, (int, float)) else None

    ############
    # Commands #
    ############

    async def turn_ac_input_on(self) -> None:
        """Take power from the AC input again.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_AC_OUTPUT,
            PARAMETERS_AC_INPUT,
            off=False,
        )

    async def turn_ac_input_off(self) -> None:
        """Stop taking power from the AC input, so loads run from the battery.

        .. note::
           The device turns the AC input back on by itself when the main
           battery reaches its discharge floor and when mains is unplugged;
           :attr:`ac_input_state` shows it. While it is off, no time-of-use
           period takes effect (:attr:`active_tariff`).

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_AC_OUTPUT,
            PARAMETERS_AC_INPUT,
            off=True,
        )

    async def turn_outage_alert_on(self) -> None:
        """Turn the alert for a lost AC grid on.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_SYSTEM,
            PARAMETERS_OUTAGE_ALERT,
            on=True,
        )

    async def turn_outage_alert_off(self) -> None:
        """Turn the alert for a lost AC grid off.

        :raises ConnectionError: If not connected to device.
        :raises BleakError: If command transmission fails.
        """
        await self._send_command(
            CMD_SYSTEM,
            PARAMETERS_OUTAGE_ALERT,
            on=False,
        )

    async def get_status_update(self) -> ParameterDict:
        """Request and retrieve a status update from the device.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: Dictionary containing telemetry parameters.
        """
        payload = await self._request(CMD_SUBSCRIBE, CMD_RESPONSE_GET_STATUS)
        parameters: ParameterDict = Parameters.parse(payload)
        await self._process_telemetry(parameters)
        return parameters

    async def get_ota_status(self) -> bool | None:
        """Ask the device whether it would accept a firmware update now.

        Updates :attr:`ota_allowed` and :attr:`ota_block_reason`.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: True if an update would be accepted, else False.
        """
        payload = await self._request(CMD_OTA_STATUS, CMD_RESPONSE_OTA_STATUS)
        self._process_ota_status(Parameters.parse(payload))
        self._run_state_changed_callbacks()
        return self._ota_allowed

    async def get_display_theme_name(self) -> str:
        """Read the name of the display's clock theme.

        :raises ConnectionError: If not connected to device.
        :raises TimeoutError: If no response from device.
        :raises BleakError: If command transmission fails.
        :returns: The theme name, empty if the theme has none.
        """
        payload = await self._request(
            CMD_DISPLAY_THEME_NAME,
            CMD_RESPONSE_DISPLAY_THEME_NAME,
        )
        parameters = Parameters.parse(payload)
        # A theme with no name is sent as a bare type byte (a3 01 04)
        if "a3" not in parameters or parameters["a3"].get("type") is None:
            return ""
        name = bytes(parameters["a3"].value or b"")
        return name.rstrip(b"\x00").decode("utf-8", errors="replace")

    ############
    # Internal #
    ############

    async def _post_connect(self) -> None:
        """Subscribe to telemetry and start the realtime stream once connected.

        The device streams nothing until it is subscribed, and pushes changes
        on its own only while the realtime stream runs; on a connected link
        that stream runs until it is stopped.
        """
        await self._send_command(CMD_SUBSCRIBE, PARAMETERS_SUBSCRIBE)
        await self._send_command(
            CMD_REALTIME,
            PARAMETERS_REALTIME_ON,
        )

    async def _request(self, message: int | str, response: int) -> bytes:
        """Send a bare request and wait for its reply.

        :param message: The request's message type.
        :param response: The reply's message type.
        :raises TimeoutError: If no response from device.
        :returns: The reply's payload.
        """
        await self._send_command(message, PARAMETERS_SUBSCRIBE)
        payload = await self._listen_for_packet(Channel.SESSION, response)
        if not payload:
            msg = "Timed out waiting for payload!"
            raise TimeoutError(msg)
        return payload

    def _expansion(self) -> Container | None:
        """Parse the expansion block, if a pack is attached.

        :returns: The parsed block, or None without data or with no pack.
        """
        expansion = self._tag("c0", C0_EXPANSION)
        return expansion if expansion is not None and expansion.connected else None

    def _summary_percentage(self, name: str) -> int:
        """Read a percentage from the summary as a whole number.

        :param name: Summary field name.
        :returns: The percentage, or default int value until it is reported.
        """
        value = self._summary.get(name)
        return round(value) if isinstance(value, (int, float)) else DEFAULT_METADATA_INT

    def _summary_kwh(self, name: str) -> float | None:
        """Read an energy counter from the summary as kWh.

        :param name: Summary field name holding watt-hours.
        :returns: Energy in kWh, or None until a summary has been received.
        """
        value = self._summary.get(name)
        if not isinstance(value, (int, float)):
            return None
        return round(value / WH_PER_KWH, KWH_DIGITS)

    async def _process_session(
        self,
        msgtype: int,
        payload: bytes,
        *,
        encrypted: bool,
    ) -> None:
        """Take the summary and the pushes, then hand the rest to the base.

        :param msgtype: The packet's message type.
        :param payload: The plain-text payload.
        :param encrypted: Whether the packet arrived encrypted.
        """
        if msgtype not in (
            MSGTYPE_SUMMARY,
            MSGTYPE_EVENT_REPORT,
            MSGTYPE_EVENT_PUSH,
            MSGTYPE_OTA_STATUS,
        ):
            return await super()._process_session(msgtype, payload, encrypted=encrypted)

        # A session push the client could decrypt proves it is authorized
        if encrypted and self._session is not None:
            self._session.on_session_push()

        if msgtype == MSGTYPE_SUMMARY:
            self._process_summary(payload)
        elif msgtype == MSGTYPE_OTA_STATUS:
            self._process_ota_status(Parameters.parse(payload))
        else:
            self._process_event(Parameters.parse(payload))
        self._run_state_changed_callbacks()
        return None

    def _process_summary(self, payload: bytes) -> None:
        """Decode a device summary into :attr:`summary`.

        :param payload: The plain-text summary payload.
        """
        post = SummaryPayload.parse(payload)
        schema = (
            bytes(post.schema.value).rstrip(b"\x00").decode("ascii")
            if post.schema is not None and post.schema.value
            else None
        )
        fields: dict[str, SummaryField] | None = (
            SUMMARY_MAPS.get(schema) if schema is not None else None
        )
        if fields is None and schema not in self._unmapped_summary_schemas:
            self._unmapped_summary_schemas.add(schema)
            _LOGGER.warning(
                f"'{self.name}' posts summary schema '{schema}', which has no "
                f"field map; its fields are kept by path only!",
            )

        fields = fields or {}
        arrays = {path: field.array for path, field in fields.items() if field.array}
        signed = {path for path, field in fields.items() if field.signed}
        raw = walk_protobuf(post.protobuf, arrays=arrays, signed=signed)
        self._summary = name_summary(raw, fields)
        self._summary_schema = schema
        self._last_summary_timestamp = datetime.now()  # noqa: DTZ005  # as last_update

    def _process_event(self, parameters: ParameterDict) -> None:
        """Record an event report or event push as :attr:`last_event`.

        :param parameters: The event's parameters.
        """
        code = self._parameter(parameters, "a2", EVENT_CODE)
        try:
            event = DeviceEventType(code)
        except ValueError:
            event = DeviceEventType.UNKNOWN

        start = end = None
        battery_percentage = None
        if event is DeviceEventType.GRID_LOSS:
            battery_percentage = self._parameter(parameters, "a3", Int8ub)
        else:
            start = self._parameter(parameters, "a3", EPOCH)
            end = self._parameter(parameters, "a4", EPOCH)

        self._last_event = DeviceEvent(
            event=event,
            code=DEFAULT_METADATA_INT if code is None else code,
            start=None if start is None else epoch_to_local(start),
            end=None if end is None else epoch_to_local(end),
            battery_percentage=battery_percentage,
            received=datetime.now(),  # noqa: DTZ005  # naive local, as last_update
        )

    def _process_ota_status(self, parameters: ParameterDict) -> None:
        """Record the firmware-update readiness the device reported.

        :param parameters: The readiness push or reply's parameters.
        """
        allowed = self._parameter(parameters, "a2", Int8ub)
        if allowed is not None:
            self._ota_allowed = bool(allowed)
        reason = self._parameter(parameters, "a3", Int8ub)
        if reason is not None:
            try:
                self._ota_block_reason = OtaBlockReason(reason)
            except ValueError:
                self._ota_block_reason = OtaBlockReason.UNKNOWN

    @staticmethod
    def _parameter(parameters: ParameterDict, key: str, field: Struct) -> int | None:
        """Parse one parameter of a push with the given construct.

        :param parameters: The push's parameters.
        :param key: The parameter (e.g ``"a2"``) to read.
        :param field: The construct to parse its value with.
        :returns: The value, or None if absent or too short.
        """
        if key not in parameters:
            return None
        value: int | None = _parse_guarded(parameters[key].value or b"", field)
        return value

    def _reset_session(self, reset_data: bool = True) -> None:  # noqa: FBT001, FBT002  # base signature
        """Reset negotiated variables, and the summary along with the data.

        :param reset_data: Whether the cached data is cleared too.
        """
        super()._reset_session(reset_data)
        if reset_data:
            self._summary = {}
            self._summary_schema = None
            self._last_summary_timestamp = None
