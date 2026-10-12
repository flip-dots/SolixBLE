"""Base device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import copy
import inspect
import logging
import time
from collections.abc import Callable
from datetime import datetime
from functools import partial

from bleak import BleakClient, BleakError
from bleak.backends.client import BaseBleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import establish_connection
from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
)
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

from SolixBLE.advertisement import (
    CAPABILITY_ENCRYPTED_ECDH,
    capability_from_advertisement,
)
from SolixBLE.constructs import (
    CHANNEL_APP,
    CHANNEL_NEGOTIATION,
    CHANNEL_SESSION,
    FragmentedPayload,
    Packet,
    PacketCommand,
    PacketPattern,
    ParameterDict,
    Parameters,
)
from SolixBLE.protocols import (
    EncryptedOuter,
    NegotiatedSession,
    Outer,
    PlainOuter,
    UnsupportedNegotiation,
)
from SolixBLE.utilities import (
    _offset_seconds_west,
    _to_bytes,
    generate_ecdh_key,
    get_posix_tz,
)

from .const import (
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
    DISCONNECT_TIMEOUT,
    FALLBACK_TZ,
    NEGOTIATION_RESPONSE_TIMEOUT,
    NEGOTIATION_TIMEOUT,
    RECONNECT_ATTEMPTS_MAX,
    RECONNECT_DELAY,
)
from .transport import LegacyTransport, NegotiatingTransport, Transport2215

_LOGGER = logging.getLogger(__name__)

#: The UUID sent to the device during negotiation
UUID_STRING = "b2dc0b17-b75d-4abf-ba6e-ec7c997c23e7"

#: Message type handled as telemetry on every model (``0300`` / ``4300``)
TELEMETRY_MSGTYPE = 0x300


class SolixBLEDevice:
    """Solix BLE device object."""

    #: Command codes (hex) that carry telemetry for this device. Subclasses can
    #: override this if their model uses different telemetry command codes
    #: (e.g the C1000 Gen 2 uses ``c421``/``c900`` instead of ``c402``/``c405``).
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("c402", "4300", "c405")

    #: The BLE transport this device uses. Subclasses on the legacy transport
    #: (GATT service ``1780``) set :class:`~SolixBLE.transport.LegacyTransport`,
    #: those on service ``2215`` :class:`~SolixBLE.transport.Transport2215`.
    _TRANSPORT: type[NegotiatingTransport | Transport2215 | LegacyTransport] = NegotiatingTransport

    #: The outer protocol this model negotiates with when nothing better is
    #: known (no advertisement, no earlier connection on this instance).
    _OUTER_HINT: type[Outer] = PlainOuter

    #: The client identifier sent to the device during negotiation.
    _UUID_STRING: str = UUID_STRING

    @property
    def UUID_TELEMETRY(self) -> str:  # noqa: N802
        """GATT characteristic the device sends telemetry on."""
        return self._TRANSPORT.telemetry

    @property
    def UUID_COMMAND(self) -> str:  # noqa: N802
        """GATT characteristic the device takes commands on."""
        return self._TRANSPORT.command

    def __init__(
        self,
        ble_device: BLEDevice,
        advertisement: AdvertisementData | None = None,
    ) -> None:
        """Initialise device object. Does not connect automatically.

        :param ble_device: The bleak device to wrap.
        :param advertisement: The device's scan result, if available. Its
            capability byte tells which negotiation the device accepts; without
            it the class default is tried first and corrected if refused.
        """

        _LOGGER.debug(
            f"Initializing Solix device '{ble_device.name}' with"
            f"address '{ble_device.address}' and details '{ble_device.details}'"
        )

        self._ble_device: BLEDevice = ble_device
        self._client: BleakClient | None = None
        self._fragment_buffers: dict[bytes, list[FragmentedPayload]] = {}
        self._data: ParameterDict | None = None
        self._last_data_timestamp: datetime | None = None
        self._last_packet_timestamp: datetime | None = None
        self._state_changed_callbacks: list[Callable[[], None]] = []
        self._packet_futures: dict[bytes, list[asyncio.Future]] = {}
        self._auto_reconnect_task: asyncio.Task | None = None
        self._keep_alive_task: asyncio.Task | None = None
        self._disconnect_event: asyncio.Event = asyncio.Event()
        self._connection_attempts: int = 0
        self._session: NegotiatedSession | None = None
        self._outer_class: type[Outer] = self._initial_outer(advertisement)
        self._negotiation_error: UnsupportedNegotiation | None = None
        self._client_token: str = self._UUID_STRING

    def _initial_outer(
        self, advertisement: AdvertisementData | None,
    ) -> type[Outer]:
        """Return the outer protocol to open with, from the best hint available.

        :param advertisement: The device's scan result, if available.
        :returns: The encrypted outer if the capability byte asks for it, the
            plain outer if the byte is present without it, else the class hint.
        """
        capability = (
            capability_from_advertisement(advertisement)
            if advertisement is not None
            else None
        )
        if capability is None:
            return self._OUTER_HINT
        if capability & CAPABILITY_ENCRYPTED_ECDH:
            return EncryptedOuter
        return PlainOuter

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

    async def _initiate_negotiations(self) -> None:
        """Start a negotiation on the current outer protocol.

        A device that refuses the opening can drop the link before the write
        returns; that write's error is the refusal, left to the caller to see
        as a dropped link.

        :raises BleakError: If the write fails while the link is still up.
        """
        self._session = NegotiatedSession(self._outer_class(), self)
        try:
            await self._session.open()
        except BleakError:
            if self.connected:
                raise

    async def connect(self, max_attempts: int = 3, run_callbacks: bool = True) -> bool:
        """Connect to device.

        This will connect to the device, determine if it is supported
        and subscribe to status updates, returning True if successful.

        :param max_attempts: Maximum number of attempts to try to connect (default=3).
        :param run_callbacks: Execute registered callbacks on successful connection (default=True).
        """
        self._connection_attempts = self._connection_attempts + 1

        try:

            # If we have an old client get rid of it
            if self._client is not None:
                await self._dispose_of_client()

            # Reset negotiated details but keep any data
            self._reset_session(reset_data=False)
            self._session = None

            # Make new client and connect
            self._client = await establish_connection(
                BleakClient,
                device=self._ble_device,
                name=self.address,
                max_attempts=max_attempts,
                use_services_cache=False,
                disconnected_callback=self._disconnect_callback,
            )

        except BleakError:
            _LOGGER.exception(
                f"Error establishing initial connection to '{self.name}'!"
            )

        # If we are still not connected then we have failed
        if not self.connected:
            _LOGGER.error(
                f"Failed to establish initial connection to '{self.name}' on attempt {self._connection_attempts}!"
            )
            return False

        _LOGGER.debug(
            f"Established initial connection to '{self.name}' on attempt {self._connection_attempts}!"
        )
        try:
            _LOGGER.debug(f"Subscribing to notifications from device '{self.name}'!")
            await self._client.start_notify(
                self.UUID_TELEMETRY,
                partial(self._process_notification, self._client),
            )
        except BleakError:
            _LOGGER.exception(f"Error subscribing/negotiating with '{self.name}'!")
            return False

        # Negotiate (a no-op on a transport without negotiation, where
        # negotiated is already True)
        if not await self._negotiate():
            return await self._reopen_if_refused(max_attempts, run_callbacks)

        _LOGGER.debug(f"Negotiations with '{self.name}' succeeded!")
        await self._on_authorized()
        self._connection_attempts = 0

        # Clear disconnect event if set
        if self._disconnect_event.is_set():
            self._disconnect_event.clear()

        # Run any device-specific post-connect setup (e.g sending a subscribe
        # command to start telemetry). This runs on every (re)connection. Errors
        # are logged but do not abort the connection; the automatic reconnect
        # task will retry.
        try:
            await self._post_connect()
        except Exception:
            _LOGGER.exception(f"Error running post-connect setup for '{self.name}'!")

        # Start an automatic reconnect task if its not running already
        if self._auto_reconnect_task is None:
            self._auto_reconnect_task = asyncio.create_task(self._auto_reconnect())

        # Start a keep-alive task if its not running already
        if self._keep_alive_task is None:
            self._keep_alive_task = asyncio.create_task(self._keep_alive_fn())

        # Execute callbacks if enabled
        if run_callbacks:
            self._run_state_changed_callbacks()

        return True

    async def _post_connect(self) -> None:
        """Run device-specific setup after a negotiated connection is established.

        Called by :meth:`connect` once the encrypted session has been negotiated
        (so :meth:`_send_command` may be used) and on every automatic reconnect.
        The default implementation does nothing; subclasses can override it to,
        for example, send a subscribe command to start a telemetry stream (see
        :class:`~SolixBLE.devices.c1000g2.C1000G2`).
        """
        pass

    async def _negotiate(self) -> bool:
        """Run the negotiation until it succeeds, fails, or the link drops.

        :returns: True once negotiated, else False.
        """
        try:
            async with asyncio.timeout(self._negotiation_deadline()):

                # While negotiations have not completed and the link is up
                while not self.negotiated and self.connected:

                    # If we have not received any packet from the device in
                    # any stage then restart negotiations from the start
                    if self._negotiation_should_restart():
                        _LOGGER.debug(
                            "Sending negotiation initiation request to "
                            f"'{self.name}'...",
                        )
                        await self._initiate_negotiations()

                    # Wait at this long to see if we get any response to
                    # our initial request in stage 0. This weird layout
                    # allows us to exit immediately when negotiation occurs
                    for _ in range(0, NEGOTIATION_RESPONSE_TIMEOUT):
                        await asyncio.sleep(1)
                        if (
                            self.negotiated
                            or not self.connected
                            or self._negotiation_error is not None
                        ):
                            break

                    # The device announced something no path handles
                    if self._negotiation_error is not None:
                        _LOGGER.error(
                            f"Cannot negotiate with '{self.name}': "
                            f"{self._negotiation_error}",
                        )
                        return False

        except TimeoutError:
            _LOGGER.exception(f"Timed out attempting to negotiate with '{self.name}'!")
            return False

        if not self.negotiated:
            _LOGGER.error(f"Connection to '{self.name}' was lost while negotiating!")
        return self.negotiated

    async def _reopen_if_refused(
        self, max_attempts: int, run_callbacks: bool,  # noqa: FBT001
    ) -> bool:
        """Reconnect with the encrypted outer if the device refused the plain one.

        Dropping the link before any reply to the plain opening is how hardened
        firmware refuses it. The outer changes at most once per connect and
        never steps down from encrypted.

        :param max_attempts: Passed on to :meth:`connect`.
        :param run_callbacks: Passed on to :meth:`connect`.
        :returns: The reconnection's result, or False if nothing was refused.
        """
        replied = self._session is not None and self._session.replied
        if self.connected or replied or self._outer_class is not PlainOuter:
            return False

        _LOGGER.info(
            f"'{self.name}' refused the plain negotiation, "
            "reopening with the encrypted one...",
        )
        self._outer_class = EncryptedOuter
        return await self.connect(
            max_attempts=max_attempts, run_callbacks=run_callbacks,
        )

    async def _on_authorized(self) -> None:
        """Remember the outer that worked and send the post-authorize requests."""

        # Use the same outer first on the next connection to this device
        if self._session is not None:
            self._outer_class = type(self._session.outer)

        # Run any device-specific requests the device expects once the client
        # is authorized (e.g the Prime chargers' region and owner)
        try:
            await self._post_authorize()
        except Exception:
            _LOGGER.exception(
                f"Error running post-authorize requests for '{self.name}'!",
            )

    def _negotiation_should_restart(self) -> bool:
        """Whether :meth:`connect` should send the opening request (again).

        The default restarts when the device has sent nothing, or nothing for
        ``NEGOTIATION_RESPONSE_TIMEOUT`` seconds.

        :returns: True to send the opening request now.
        """
        return (
            self._last_packet_timestamp is None
            or (time.time() - self._last_packet_timestamp)
            > NEGOTIATION_RESPONSE_TIMEOUT
        )

    def _negotiation_deadline(self) -> float:
        """Seconds :meth:`connect` allows the negotiation before giving up.

        :returns: The default ``NEGOTIATION_TIMEOUT``.
        """
        return NEGOTIATION_TIMEOUT

    async def _post_authorize(self) -> None:
        """Send the requests the device expects once this client is authorized.

        Called by :meth:`connect` before :meth:`_post_connect`. The default does
        nothing; :class:`~SolixBLE.prime_device.PrimeDevice` sends its region
        and owner here.
        """

    async def _keep_alive(self) -> int | None:
        """Execute designated keep-alive command periodically after good negotiation.

        Use this to execute code periodically that is needed to keep the
        connection. For example some devices need a special keep alive command
        to keep receiving telemetry updates that must be sent every ~10 seconds.

        This is automatically executed in a task created by :meth:`connect` once
        the encrypted session has been negotiated (so :meth:`_send_command`
        may be used) and on every automatic reconnect, with it not being
        executed when not connected or negotiated.

        The default implementation does nothing; subclasses can override it to,
        for example, send a subscribe command to keep a telemetry stream (see
        :class:`~SolixBLE.devices.prime_charger_250w.PrimeCharger250w`).

        :returns: Seconds to wait before calling again or None for not implemented.
        """
        return None

    async def disconnect(self) -> None:
        """Disconnect from device and reset internal state.

        Disconnects from device, resets internal state, including connection
        attempts, cancels the automatic reconnection task and will not execute
        state changes callbacks.
        """

        # Cancel the automatic reconnection task
        if self._auto_reconnect_task is not None:
            self._auto_reconnect_task.cancel()

        # Cancel the keep-alive task
        if self._keep_alive_task is not None:
            self._keep_alive_task.cancel()

        # If there is a client disconnect and throw it away
        if self._client is not None:
            await self._dispose_of_client()

        # Reset session
        self._connection_attempts = 0
        self._reset_session()

    @property
    def connected(self) -> bool:
        """Connected to device.

        This does not mean that an encrypted connection has been
        established or that any data values have been populated,
        use the available property to determine that.

        :returns: True/False if connected to device.
        """
        return self._client is not None and self._client.is_connected

    @property
    def negotiated(self) -> bool:
        """Has an encrypted session been successfully negotiated.

        This does not mean that any data values have been populated,
        use the available property to determine that. On a transport
        without negotiation this is True as soon as the device is connected.

        :returns: True/False if session has been negotiated and connected.
        """
        return self.connected and (
            not self._TRANSPORT.negotiates
            or (self._session is not None and self._session.authorized)
        )

    @property
    def announcement(self) -> Container | None:
        """What the device declared in its latest negotiation.

        .. note::
           :collapsible: closed

           Holds the MTU, the capability and auth methods, the serial number
           and MAC the device sent, and its client registration status.

        :returns: The announcement, or None before a negotiation started.
        """
        return self._session.announcement if self._session is not None else None

    @property
    def available(self) -> bool:
        """Connected to device and data is available.

        :returns: True/False if the device is connected and sending telemetry.
        """
        return self.negotiated and self._data is not None

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
    def last_update(self) -> datetime | None:
        """Timestamp of last telemetry data update from device.

        :returns: Timestamp of last update or None.
        """
        return self._last_data_timestamp

    def _parse_int(
        self, key: str, begin: int = None, end: int = None, signed: bool = False
    ) -> int:
        """Parse an integer at the specified key in the telemetry data.

        :param key: Key of parameter the int is in (e.g a1, a2, a3, ...).
        :param begin: Slice bytes from this index when parsing integer from bytes at the key.
        :param begin: Slice bytes to this index when parsing integer from bytes at the key.
        :param signed: If the integer is signed.
        :returns: Integer or default int value if no data.
        :raises KeyError: If key does not exist.
        :raises IndexError: If slices invalid.
        """
        if self._data is None:
            return DEFAULT_METADATA_INT
        int_bytes = self._data[key].value_legacy[begin:end]
        return int.from_bytes(int_bytes, byteorder="little", signed=signed)

    def _parse_string(self, key: str, begin: int = None, end: int = None) -> str:
        """Parse ASCII text at the specified key in the telemetry data.

        :param key: Key of parameter the string is in (e.g a1, a2, a3, ...).
        :param begin: Slice bytes from this index when parsing string from bytes at the key.
        :param begin: Slice bytes to this index when parsing string from bytes at the key.
        :returns: String of parsed data from telemetry or default str if no data.
        :raises UnicodeDecodeError: If bytes are not ASCII text.
        """
        return (
            self._data[key].value_legacy[begin:end].decode("ascii")
            if self._data
            else DEFAULT_METADATA_STRING
        )

    def _decrypt_payload(self, payload: bytes) -> bytes:
        """Decrypt payload with the negotiated session, if one has started."""

        if self._session is None:
            _LOGGER.debug("Skipping decryption as no negotiation has started...")
            return payload
        return self._session.decrypt(payload)

    def _encrypt_payload(self, payload: bytes) -> bytes:
        """Encrypt payload with the negotiated session, if one has started."""

        if self._session is None:
            _LOGGER.debug("Skipping encryption as no negotiation has started...")
            return payload
        return self._session.encrypt(payload)

    async def _process_telemetry(self, parameters: ParameterDict) -> None:
        """Process telemetry data from the device."""

        state_changed = self._data is None or parameters != self._data

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(f"Telemetry parameters: {parameters.to_str(verbose=True)}")

            # Log state update if changes
            if state_changed and self._data is not None:
                _LOGGER.debug(f"Telemetry changes: {parameters.diff(self._data)}")

        # Update internal parameters
        self._data = parameters
        self._last_data_timestamp = datetime.now()

        # Run callbacks if state changed
        if state_changed:

            _LOGGER.debug(self)
            self._run_state_changed_callbacks()

    def _reassemble(self, packet: Packet) -> bytes | None:
        """
        Re-assemble a packet.

        Given a packet containing a fragment of a payload, re-assemble
        it if all fragments are available and return it, else return
        None.

        :param packet: The packet to be re-assembled.
        :returns: Payload bytes if re-assembled.
        :returns: None if not all fragments are available.
        """
        # Parse payload
        payload = FragmentedPayload.parse(packet.payload_bytes)

        _LOGGER.debug(f"Received fragment {payload.frag.index}/{payload.frag.total} for p: {packet.pattern.hex()}, c: {packet.cmd.hex()}")

        # Get existing fragments or create list of one does not exist
        fragments = self._fragment_buffers.get(packet.pattern + packet.cmd)
        if fragments is None:
            fragments = []
            self._fragment_buffers[packet.pattern + packet.cmd] = fragments

        # Add to list of fragments
        fragments.append(payload)

        # If out of order then ignore and clear buffers
        if payload.frag.index != len(fragments):
            _LOGGER.debug("Fragment is out of order, ignoring and clearing buffers!")
            fragments.clear()
            return None

        # If not all fragments available return
        if payload.frag.total != len(fragments):
            _LOGGER.debug("Not all fragments available for reassembly!")
            return None

        _LOGGER.debug("Re-assembling payload from fragments...")

        # Assemble fragment payloads in order
        complete_payload = bytearray()
        for x in sorted(fragments, key=lambda p: int(p.frag.index)):
            complete_payload.extend(x.data)

        # Clear fragment cache for this message cmd and return
        fragments.clear()
        return bytes(complete_payload)

    async def _process_notification(
        self, client: BleakClient, handle: int, data: bytearray
    ) -> None:
        """Process a notification from the device."""

        try:

            _LOGGER.debug(f"The client the notification is from: {client}")

            if self._client is not client:
                _LOGGER.debug("Ignoring notification from old client")
                return None

            # Log reception of packet
            _LOGGER.debug(
                f"Received notification from '{self.name}'. length: {len(data)}, packet: '{data.hex()}'"
            )
            self._last_packet_timestamp = time.time()

            # Parse packet and decode its header
            packet = Packet.parse(data)
            _LOGGER.debug(f"Packet: {packet}")
            pattern = packet.pattern
            cmd = packet.cmd
            payload = packet.payload_bytes
            header = PacketPattern.parse(pattern)
            command = PacketCommand.parse(cmd)

            # Fragments are handed to the re-assembler which will
            # re-assemble the payload when all fragments are available
            if command.fragmented:
                payload = self._reassemble(packet)
                if payload is None:
                    return None

            # Negotiation messages (requests, replies and the grant the
            # device pushes after its button is pressed) decrypt themselves
            if header.channel == CHANNEL_NEGOTIATION:
                _LOGGER.debug("Received negotiation message!")
                return await self._process_negotiation(pattern, cmd, payload)

            if header.channel not in (CHANNEL_SESSION, CHANNEL_APP):
                _LOGGER.debug(
                    f"Unhandled channel {header.channel:02x} "
                    f"(composer {header.composer:02x}), cmd {cmd.hex()}",
                )
                return None

            # Session messages are decrypted once, if the frame says so
            if command.encrypted:
                payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Plain-text payload: {payload.hex()}")

            # If the packet has a future registered then we just trigger that
            # future instead of processing it here
            if pattern + cmd in self._packet_futures:
                _LOGGER.debug(
                    "Packet has future(s) registered. Triggering future(s) and ignoring packet..."
                )
                for future in self._packet_futures[pattern + cmd]:
                    future.set_result(payload)
                return None

            return await self._process_session(
                cmd, payload, encrypted=command.encrypted,
            )

        except Exception:
            _LOGGER.exception(f"Failed to process packet from {self.name}!")

            return None

    def _telemetry_msgtypes(self) -> set[int]:
        """Return the message types of this model's telemetry commands."""
        return {
            PacketCommand.parse(bytes.fromhex(cmd)).msgtype
            for cmd in self._TELEMETRY_COMMANDS
        }

    async def _process_session(
        self, cmd: bytes, payload: bytes, *, encrypted: bool,
    ) -> None:
        """
        Process a session message from the device.

        :param cmd: The command code of the packet.
        :param payload: The plain-text payload.
        :param encrypted: Whether the packet arrived encrypted.
        """

        # Telemetry messages, matched on the message type whatever the
        # fragment and encryption flags (a clear 8405 is a c405)
        msgtype = PacketCommand.parse(cmd).msgtype
        if msgtype == TELEMETRY_MSGTYPE or msgtype in self._telemetry_msgtypes():
            _LOGGER.debug(
                "Received encrypted telemetry message!"
                if encrypted
                else "Received non-encrypted telemetry message!",
            )
            parameters = Parameters.parse(payload)

            # A session push the client could decrypt proves it is authorized
            if encrypted and self._session is not None:
                self._session.on_session_push()

            return await self._process_telemetry(parameters)

        # Unknown messages
        _LOGGER.debug(f"Received unknown message of type: {cmd.hex()}")
        return None

    async def _send_packet(self, pattern: str, cmd: str, parameters: dict, **kwargs: dict) -> None:
        """
        Build and send packet to device.

        Parameter values may use lambda functions which will be executed at
        this point, where variables may be passed in as keyword arguments.
        """
        _LOGGER.debug(f"Building payload with parameters: {parameters}")

        parameters = copy.deepcopy(parameters)
        for key, item in parameters.items():
            item["key"] = bytes.fromhex(key)
            item["type"] = item.get("type", None)
            item["value"] = _to_bytes(data=item["value"], **kwargs | { "self": self })
        _LOGGER.debug(f"Generated payload parameters: {parameters}")

        payload = Parameters.build(parameters)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(f"Parameters: {Parameters.parse(payload).to_str(verbose=True)}")
        _LOGGER.debug(f"Payload bytes: {payload.hex()}")
        encrypted_payload = self._encrypt_payload(payload)

        _LOGGER.debug(f"Building packet with pattern: {pattern} and cmd: {cmd}...")
        packet = Packet.build({
            "pattern": bytes.fromhex(pattern),
            "cmd": bytes.fromhex(cmd),
            "payload_bytes": encrypted_payload,
        })
        _LOGGER.debug(f"Built packet: {packet.hex()}")
        _LOGGER.debug("Sending packet...")
        await self._client.write_gatt_char(self.UUID_COMMAND, packet)
        _LOGGER.debug("Packet sent!")

    async def _process_negotiation(
        self, pattern: bytes, cmd: bytes, payload: bytes,
    ) -> None:
        """Hand a negotiation frame to the session negotiating with the device.

        :param pattern: The frame's pattern.
        :param cmd: The frame's command.
        :param payload: The frame's reassembled payload.
        """

        if self._session is None:
            _LOGGER.warning(
                f"Received negotiation message from '{self.name}' "
                f"before negotiating! cmd: '{cmd.hex()}'",
            )
            return

        # The device announced something no path handles; connect() reports it
        try:
            await self._session.on_reply(pattern, cmd, payload)
        except UnsupportedNegotiation as error:
            self._negotiation_error = error

    def _timezone_offset(self) -> bytes:
        """Return the local UTC offset as int32 LE seconds west, for ``x022``."""
        return _offset_seconds_west()

    def _posix_timezone(self) -> str:
        """Return the local POSIX time zone string, for ``x022``."""
        return get_posix_tz() or FALLBACK_TZ

    def _generate_private_key(self) -> EllipticCurvePrivateKey:
        """Return a fresh P-256 private key for one negotiation."""
        return generate_ecdh_key()

    def _timestamp(self) -> bytes:
        """Unix timestamp in byte form (4B)."""
        return int(time.time()).to_bytes(length=4, byteorder="little", signed=False)

    async def _send_command(self, cmd: str, parameters: dict, **kwargs: dict) -> None:
        """Send a command to the device.

        Parameter values may use lambda functions which will be executed at
        this point, where variables may be passed in as keyword arguments.

        :param cmd: 2 bytes containing command type.
        :param parameters: Parameter dictionary to send.
        :raises ConnectionError: If not connected/negotiated to device.
        """

        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        await self._send_packet(
            pattern="03000f",
            cmd=cmd,
            parameters=parameters | { "fe": {
                "key": bytes.fromhex("fe"),
                "type": 3,
                "value": lambda self: self._timestamp(),
            }},
            **kwargs,
        )

    def _register_future(
        self, future: asyncio.Future, pattern: bytes, cmd: bytes
    ) -> None:
        """Register a future to be triggered when the pattern and cmd bytes are received."""

        # If there are no futures registered for these bytes then we need to
        # create the list
        if pattern + cmd not in self._packet_futures:
            self._packet_futures[pattern + cmd] = [future]

        # Else we add our future to the futures for these bytes
        else:
            self._packet_futures[pattern + cmd].append(future)

    def _deregister_future(
        self, future: asyncio.Future, pattern: bytes, cmd: bytes
    ) -> None:
        """Deregister a future to be triggered when the pattern and cmd bytes are received."""

        # If there are no futures registered for these bytes we do nothing
        if pattern + cmd not in self._packet_futures:
            return

        # If the future is not set for these bytes we do nothing
        if future not in self._packet_futures.get(pattern + cmd):
            return

        # Otherwise remove the future from the list of futures for these bytes
        self._packet_futures.get(pattern + cmd).remove(future)

        # If there are no futures left for these bytes then remove the key
        if len(self._packet_futures.get(pattern + cmd)) == 0:
            self._packet_futures.pop(pattern + cmd)

    async def _listen_for_packet(
        self, pattern: bytes, cmd: bytes, timeout: int = 10
    ) -> bytes | None:
        """Wait for a response and return its payload bytes.

        Use this to listen for a response to a command and get the payload
        returned. This will block until a matching packet is received or
        the timeout is reached.

        Note that this will override any built in parsing of the
        packet (i.e if you listen for a regular telemetry packet that packet
        will not be used to automatically populate device attributes).

        :param pattern: 3 byte pattern (e.g 03010f).
        :param cmd: 2 byte command (e.g c402).
        :param timeout: Maximum time to wait for matching response.
        :returns: Payload bytes if response found else None.
        """
        future = asyncio.Future()
        try:
            self._register_future(future, pattern, cmd)
            return await asyncio.wait_for(future, timeout)
        except asyncio.CancelledError:
            return None
        finally:
            self._deregister_future(future, pattern, cmd)

    def _run_state_changed_callbacks(self) -> None:
        """Execute all registered callbacks for a state change."""
        for function in self._state_changed_callbacks:
            try:
                function()
            except Exception:
                _LOGGER.exception(
                    f"Exception raised by a registered state change callback '{function}'!"
                )

    async def _auto_reconnect(self) -> None:
        """Task designed to be run in background to automatically reconnect.

        This task is executed automatically when a successful connection
        is made and while the connection attempt limit is not exceeded it
        will attempt to re-connect when a disconnect event is signalled.

        This background task is cancelled when disconnect is called.
        """

        def _can_retry() -> bool:
            return (
                self._connection_attempts < RECONNECT_ATTEMPTS_MAX
                or RECONNECT_ATTEMPTS_MAX == -1
            )

        try:

            # If callbacks need to be run on reconnection, we silently
            # reconnect if the timeout has not been exceeded, else we
            # run callbacks to let subscribers know we were disconnected
            run_callbacks_on_reconnect = False

            while _can_retry():

                # If we are already connected and negotiated then wait for disconnection
                if self.negotiated:
                    _LOGGER.debug(
                        f"Automatic reconnect task ready and waiting for disconnect event from '{self.name}'!"
                    )
                    await self._disconnect_event.wait()
                    _LOGGER.debug(
                        f"Disconnection event signalled by '{self.name}', starting reconnection..."
                    )
                else:
                    _LOGGER.debug(
                        f"We are still not connected to '{self.name}', starting reconnection..."
                    )

                # If we have reached this stage we are not connected

                try:
                    # Limit on amount of time we can stay disconnected before
                    # we have to trigger callbacks to let subscribers know we
                    # are disconnected
                    async with asyncio.timeout(DISCONNECT_TIMEOUT):

                        while _can_retry():

                            await asyncio.sleep(RECONNECT_DELAY)

                            try:
                                attempt_number = self._connection_attempts
                                if await self.connect(
                                    run_callbacks=run_callbacks_on_reconnect
                                ):
                                    _LOGGER.debug(
                                        f"""Successfully reconnected to '{self.name}' {"silently" if not run_callbacks_on_reconnect else ""} on attempt {attempt_number}!"""
                                    )

                                    # Reset back to false on successful connection
                                    run_callbacks_on_reconnect = False

                                    # Break out of this loop back to loop waiting for disconnect event
                                    break
                            except Exception:
                                _LOGGER.exception(
                                    f"""Exception raised attempting to {"silently" if not run_callbacks_on_reconnect else ""} reconnect to '{self.name}'!"""
                                )

                # If timeout exceeded
                except asyncio.TimeoutError:
                    _LOGGER.warning(
                        f"Timed out attempting to silently reconnect to '{self.name}', callbacks will be triggered due to disconnect!"
                    )
                    self._reset_session(reset_data=True)
                    self._run_state_changed_callbacks()

                    # If we ran callbacks due to a disconnect we will
                    # need to run them again on reconnect
                    run_callbacks_on_reconnect = True

            else:
                _LOGGER.warning("Maximum reconnect limit exceeded!")

        except asyncio.CancelledError:
            _LOGGER.debug("Automatic reconnect task has been canceled/stopped")

        except Exception:
            _LOGGER.exception("Unexpected exception in automatic reconnect task!")


    async def _keep_alive_fn(self) -> None:
        """Task designed to be run in background to execute keep-alive.

        This task is executed automatically when a successful connection
        is made and will periodically execute the keep alive function if
        one exists.

        This background task is cancelled when the connection is lost.
        """
        try:
            while self.negotiated:

                try:
                    _LOGGER.debug("Executing keep-alive...")
                    result = await self._keep_alive()

                    if result is None:
                        _LOGGER.debug("No keep-alive task registered, stopping task...")
                        return

                    _LOGGER.debug(f"Executing keep-alive in {result}s")
                    await asyncio.sleep(result)

                except Exception:
                    _LOGGER.exception("Exception raised executing keep-alive function!")

        except asyncio.CancelledError:
            _LOGGER.debug("Keep-alive task has been canceled/stopped")

        except Exception:
            _LOGGER.exception("Unexpected exception in keep-alive task!")

    def _disconnect_callback(self, client: BaseBleakClient) -> None:
        """Callback executed by bleak when the connection is lost.

        This clears the negotiated values which are now invalid
        and will need to be re-negotiated. This does not clear the
        cached properties of the device, that will only be cleared
        if the re-connection fails. This also triggers the
        disconnection event which will result in the automatic
        reconnection task attempting to reconnect.

        :param client: Bleak client.
        """

        # Ignore disconnect callbacks from old clients
        if client is not self._client:
            _LOGGER.debug(
                f"Disconnect of '{self.name}' came from other client. Ignoring..."
            )
            return

        _LOGGER.debug(f"Connection lost to '{self.name}'!")

        # Reset session specific state variables but keep the cached data
        self._reset_session(reset_data=False)

        # Trigger disconnection event
        self._disconnect_event.set()

    async def _dispose_of_client(self) -> None:
        """Dispose of current bleak client."""
        client = self._client
        self._client = None
        try:
            await client.disconnect()
        except Exception:
            _LOGGER.exception(
                f"Exception raised when disposing of bleak client '{client}'!"
            )

    def _reset_session(self, reset_data: bool = True) -> None:
        """Reset negotiated variables and data and futures.

        The last session is kept, so :meth:`connect` can still tell after a
        drop whether the device answered it; a new connection replaces it.
        """

        if reset_data:
            self._data = None
            self._last_data_timestamp = None

        self._fragment_buffers = {}
        self._negotiation_error = None
        self._last_packet_timestamp = None
        self._packet_futures: dict[bytes, list[asyncio.Future]] = {}

    def __str__(self) -> str:
        """Return string representation of device state.

        If any of the values fail to parse the error type will be
        placed instead of the value.

        Example: C300(
          AC_OUTPUT: PortStatus.NOT_CONNECTED,
          AC_POWER_IN: 0,
          AC_OUTPUT: ValueError: 1280 is not a valid PortStatus,
          ...
        )
        """

        def _safe_get(name: str, prop: property) -> str:
            try:
                return prop.fget(self)
            except Exception as e:
                _LOGGER.exception(
                    f"Failed to parse property '{name}' when stringifying class! Is there an undocumented state?"
                )
                return f"{type(e).__name__}: {e}"

        self_str = f"{self.__class__.__name__}(\n"
        for name, value in {
            prop_name.upper(): _safe_get(prop_name, prop)
            for prop_name, prop in inspect.getmembers(type(self))
            if isinstance(prop, property)
        }.items():
            self_str += f"    {name}: {value},\n"
        self_str += ")"
        return self_str
