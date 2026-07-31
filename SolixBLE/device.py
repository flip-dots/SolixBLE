"""Base device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import inspect
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from functools import partial

from bleak import BleakClient, BleakError
from bleak.backends.client import BaseBleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePublicKey,
    derive_private_key,
)
from cryptography.hazmat.primitives.padding import PKCS7

from .const import (
    BASE_TIMESTAMP,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
    DISCONNECT_TIMEOUT,
    NEGOTIATION_COMMAND_0,
    NEGOTIATION_COMMAND_1,
    NEGOTIATION_COMMAND_2,
    NEGOTIATION_COMMAND_3,
    NEGOTIATION_COMMAND_4,
    NEGOTIATION_COMMAND_5,
    NEGOTIATION_RESPONSE_TIMEOUT,
    NEGOTIATION_TIMEOUT,
    PRIVATE_KEY,
    RECONNECT_ATTEMPTS_MAX,
    RECONNECT_DELAY,
    UUID_COMMAND,
    UUID_TELEMETRY,
)

_LOGGER = logging.getLogger(__name__)


class SolixBLEDevice:
    """Solix BLE device object."""

    #: Command codes (hex) that carry telemetry for this device. Subclasses can
    #: override this if their model uses different telemetry command codes
    #: (e.g the C1000 Gen 2 uses ``c421``/``c900`` instead of ``c402``/``c405``).
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("c402", "4300", "c405")

    def __init__(self, ble_device: BLEDevice) -> None:
        """Initialise device object. Does not connect automatically."""

        _LOGGER.debug(
            f"Initializing Solix device '{ble_device.name}' with"
            f"address '{ble_device.address}' and details '{ble_device.details}'"
        )

        self._ble_device: BLEDevice = ble_device
        self._client: BleakClient | None = None
        self._fragment_buffers: dict[bytes, dict[int, bytes]] = {}
        self._fragment_totals: dict[bytes, int] = {}
        self._data: dict[str, bytes] | None = None
        self._last_data_timestamp: datetime | None = None
        self._last_packet_timestamp: datetime | None = None
        self._negotiation_timestamp: float | None = None
        self._state_changed_callbacks: list[Callable[[], None]] = []
        self._packet_futures: dict[bytes, list[asyncio.Future]] = {}
        self._auto_reconnect_task: asyncio.Task | None = None
        self._disconnect_event: asyncio.Event = asyncio.Event()
        self._connection_attempts: int = 0
        self._shared_secret: bytes | None = None

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
        """Send the negotiation initiation command."""
        await self._client.write_gatt_char(
            UUID_COMMAND,
            bytes.fromhex(NEGOTIATION_COMMAND_0),
            response=True,
        )

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
                UUID_TELEMETRY, partial(self._process_notification, self._client)
            )
        except BleakError:
            _LOGGER.exception(f"Error subscribing/negotiating with '{self.name}'!")
            return False

        # Negotiate
        try:
            async with asyncio.timeout(NEGOTIATION_TIMEOUT):

                # While negotiations have not completed
                while not self.negotiated:

                    # If we have not received any packet from the device in
                    # any stage then restart negotiations from the start
                    if (
                        self._last_packet_timestamp is None
                        or (time.time() - self._last_packet_timestamp)
                        > NEGOTIATION_RESPONSE_TIMEOUT
                    ):

                        _LOGGER.debug(
                            f"Sending negotiation initiation request to '{self.name}'..."
                        )
                        await self._initiate_negotiations()

                    # Wait at this long to see if we get any response to
                    # our initial request in stage 0. This weird layout
                    # allows us to exit immediately when negotiation occurs
                    for _ in range(0, NEGOTIATION_RESPONSE_TIMEOUT):
                        await asyncio.sleep(1)
                        if self.negotiated:
                            break

        except TimeoutError:
            _LOGGER.exception(f"Timed out attempting to negotiate with '{self.name}'!")
            return False

        # If negotiations succeeded
        _LOGGER.debug(f"Negotiations with '{self.name}' succeeded!")
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

    async def disconnect(self) -> None:
        """Disconnect from device and reset internal state.

        Disconnects from device, resets internal state, including connection
        attempts, cancels the automatic reconnection task and will not execute
        state changes callbacks.
        """

        # Cancel the automatic reconnection task
        if self._auto_reconnect_task is not None:
            self._auto_reconnect_task.cancel()

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
        use the available property to determine that.

        :returns: True/False if session has been negotiated and connected.
        """
        return self.connected and self._shared_secret is not None

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
        int_bytes = self._data[key][begin:end]
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
            self._data[key][begin:end].decode("ascii")
            if self._data
            else DEFAULT_METADATA_STRING
        )

    def _split_packet(self, packet: bytes) -> tuple[bytes, bytes, bytes]:
        """Validate packet and split into pattern, command, and payload bytes."""

        packet_copy = bytearray(packet)

        # Validate header is correct
        packet_header = bytes([packet_copy.pop(0), packet_copy.pop(0)])
        if packet_header != bytes.fromhex("ff09"):
            raise ValueError("Packet does not start with FF09!")

        # Validate encoded length is correct
        packet_length = int.from_bytes(
            bytes([packet_copy.pop(0), packet_copy.pop(0)]), byteorder="little"
        )
        if packet_length != len(packet):
            raise ValueError(
                f"Packet length is encoded as {packet_length} but its length was {len(packet)}!"
            )

        # Validate checksum is correct
        packet_checksum = packet_copy.pop(-1).to_bytes()
        if packet_checksum != self._checksum(packet[:-1]):
            raise ValueError(
                f"Packet checksum is encoded as {packet_checksum.hex()} but it is actually {self._checksum(packet[:-1]).hex()}!"
            )

        # Extract pattern
        packet_pattern = bytes(
            [packet_copy.pop(0), packet_copy.pop(0), packet_copy.pop(0)]
        )

        # Extract command
        packet_cmd = bytes([packet_copy.pop(0), packet_copy.pop(0)])

        # Extract payload
        packet_payload = bytes(packet_copy)

        return packet_pattern, packet_cmd, packet_payload

    def _parse_payload(self, payload: bytearray | bytes) -> dict[str, bytes]:
        """
        Parse payload bytes into parameters.

        Payloads contain a list of parameters and these parameters
        have a format of: <id 1B> <len 1-2B> <type 1B> <data nB>.

        If an error occurs when decoding a parameter it prevents all
        further parameters from being parsed and logs an exception,
        but the successfully parsed parameters (if any) will be returned.

        :param payload: Payload to parse into parameters.
        :returns: Dictionary mapping parameter ids (a1, a2, ...) to data.
        """

        def _verbose_pop(data: bytearray, length: int, name: str) -> bytes:
            """
            Pop specified number of bytes from bytearray and log if error.

            :param data: Data to be popped.
            :param length: Number of bytes to pop and return.
            :param name: Name of value being popped to put in logs if error.
            :raises IndexError: If popping fails.
            """

            # Copy of bytes to use in error message if needed
            data_copy = bytes(data)

            # Bytes extracted so far
            new_bytes = bytes([])

            try:
                # Pop length bytes from data and return
                for _ in range(length):
                    new_bytes = new_bytes + bytes([data.pop(0)])
                return new_bytes

            # Build error message
            except IndexError as e:
                message = (
                    f"Error extracting {name} (len={length}) from '{data_copy.hex()}'"
                    f" (len={len(data_copy)}) at index {len(new_bytes)}. We extracted:"
                    f" '{new_bytes.hex()}' but expected {length - len(data_copy)}"
                    f" more bytes!"
                )
                _LOGGER.exception(message)
                raise IndexError(message) from e

        parsed_data: dict[str, bytes] = {}
        remaining_data = bytearray(payload)

        # Payloads sometimes start with 00 and we must strip that
        if remaining_data.startswith(bytes.fromhex("00")):
            _LOGGER.debug("Stripped 00 from start of payload")
            _verbose_pop(remaining_data, 1, "special 00 header")

        while len(remaining_data) != 0:
            try:
                # Extract param id (e.g a1, a2, ...)
                param_id = _verbose_pop(remaining_data, 1, "param_id").hex()

                # Sometimes there is just a param_id with no length or values
                if len(remaining_data) == 0:
                    parsed_data[param_id] = bytes()
                    break

                # Extract encoded length of parameter
                param_len = int.from_bytes(
                    _verbose_pop(remaining_data, 1, f"param_len (id={param_id})")
                )

                # Extract data/body from parameter
                param_data = _verbose_pop(
                    remaining_data, param_len, f"param_data (id={param_id})"
                )
                parsed_data[param_id] = param_data

            except IndexError:
                _LOGGER.exception(
                    f"Unexpected end of packet! Data may be missing or invalid!"
                    f" Extracted so far: '{self._parameters_to_str(parsed_data)}'."
                    f" Payload: '{payload.hex()}'"
                )

        return parsed_data

    def _parameters_to_str(
        self, parameters: dict[str, bytes], types: bool = False
    ) -> str:
        if types:
            with_types = {
                k: {
                    "bytes": f"""{v}""",
                    "hex": f"""{v.hex()}""",
                    "uint": f"""{int.from_bytes(v[1:], byteorder="little")}""",
                    "int": f"""{int.from_bytes(v[1:], byteorder="little", signed=True)}""",
                }
                for k, v in parameters.items()
            }
            return json.dumps(with_types, indent=4, sort_keys=True)
        else:
            return str({k: v.hex() for k, v in parameters.items()})

    def _log_diff(self, old: dict[str, bytes], new: dict[str, bytes]) -> None:
        """Log any differences between parameters."""
        differences = {
            k: {
                "bytes": f"""{old[k]} -> {new[k]}""",
                "hex": f"""{old[k].hex()} -> {new[k].hex()}""",
                "uint": f"""{int.from_bytes(old[k][1:], byteorder="little")} -> {int.from_bytes(new[k][1:], byteorder="little")}""",
                "int": f"""{int.from_bytes(old[k][1:], byteorder="little", signed=True)} -> {int.from_bytes(new[k][1:], byteorder="little", signed=True)}""",
            }
            for k in old.keys() & new.keys()
            if new[k] != old[k]
        }
        _LOGGER.debug(
            f"Parameter changes: \n{json.dumps(differences, indent=4, sort_keys=True)}"
        )

    def _decrypt_payload(self, payload: bytes) -> bytes:
        """Decrypt telemetry packet using negotiated shared secret and IV."""
        cipher = AES.new(
            self._shared_secret[:16], AES.MODE_CBC, iv=self._shared_secret[16:]
        )
        decrypted = cipher.decrypt(payload)
        unpadder = PKCS7(128).unpadder()
        unpadded_data = unpadder.update(decrypted)
        return unpadded_data + unpadder.finalize()

    def _encrypt_payload(self, payload: bytes) -> bytes:
        """Encrypt telemetry packet using negotiated shared secret and IV."""

        # Pad and encrypt payload
        padder = PKCS7(128).padder()
        padded_data = padder.update(payload)
        padded_data += padder.finalize()
        cipher = AES.new(
            self._shared_secret[:16], AES.MODE_CBC, iv=self._shared_secret[16:]
        )
        return cipher.encrypt(padded_data)

    async def _process_telemetry_packet(
        self, payload: bytes, cmd: bytes = None
    ) -> None:
        """Process a telemetry packet from the device.

        This performs the default processing of telemetry packets in which
        telemetry payloads are spread across multiple packets. This is
        overridden for devices which do not use multi-packet payloads for
        telemetry.
        """

        # First byte encodes fragment info (high nibble = index, low = total)
        fragment_index = (payload[0] >> 4) & 0x0F
        fragment_total = payload[0] & 0x0F

        # Multi-part message
        if fragment_total > 1:
            fragment_data = payload[1:]
            cmd_key = bytes(cmd)
            _LOGGER.debug(
                f"Fragment {fragment_index}/{fragment_total} for cmd {cmd.hex()}, {len(fragment_data)} bytes"
            )

            # Store fragment
            if cmd_key not in self._fragment_buffers or fragment_index == 1:
                self._fragment_buffers[cmd_key] = {}
                self._fragment_totals[cmd_key] = fragment_total

            self._fragment_buffers[cmd_key][fragment_index] = fragment_data

            # Wait until all fragments have arrived
            if len(self._fragment_buffers[cmd_key]) < fragment_total:
                _LOGGER.debug("Waiting for remaining fragments...")
                return

            # Reassemble in order
            payload = b"".join(
                self._fragment_buffers[cmd_key][i]
                for i in sorted(self._fragment_buffers[cmd_key])
            )
            del self._fragment_buffers[cmd_key]
            del self._fragment_totals[cmd_key]
            _LOGGER.debug(f"Reassembled payload: {len(payload)} bytes")

        else:
            # Strip fragment info
            payload = payload[1:]

        decrypted_payload = self._decrypt_payload(payload)
        _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
        parameters = self._parse_payload(decrypted_payload)
        return await self._process_telemetry(parameters)

    async def _process_telemetry(self, parameters: dict[str, bytes]) -> None:
        """Process telemetry data from the device."""

        state_changed = self._data is None or parameters != self._data

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                f"Telemetry parameters: {self._parameters_to_str(parameters)}"
            )

            # Print state update if changes
            if state_changed:

                # If we have previous data to compare against log the diff
                if self._data is not None:
                    _LOGGER.debug("Parameters have changed since previous update!")
                    self._log_diff(self._data, parameters)

                # Else log the parameters but with the types
                else:
                    _LOGGER.debug(
                        f"Telemetry parameters: {self._parameters_to_str(parameters, types=True)}"
                    )

        # Update internal parameters
        self._data = parameters
        self._last_data_timestamp = datetime.now()

        # Run callbacks if state changed
        if state_changed:

            _LOGGER.debug(self)
            self._run_state_changed_callbacks()

    async def _process_notification(
        self, client: BleakClient, handle: int, data: bytearray
    ) -> None:
        """Process a notification from the device."""

        _LOGGER.debug(f"The client the notification is from: {client}")

        if self._client is not client:
            _LOGGER.debug("Ignoring notification from old client")
            return

        # Split packet into pattern, command, and payload
        _LOGGER.debug(
            f"Received notification from '{self.name}'. length: {len(data)}, packet: '{data.hex()}'"
        )
        self._last_packet_timestamp = time.time()
        pattern, cmd, payload = self._split_packet(data)
        _LOGGER.debug(f"Pattern: {pattern.hex()}")
        _LOGGER.debug(f"CMD: {cmd.hex()}")
        _LOGGER.debug(f"Payload: {payload.hex()}")
        _LOGGER.debug(f"Payload length: {len(payload)}")

        # If the packet has a future registered then we just trigger that
        # future instead of processing it here
        if pattern + cmd in self._packet_futures:
            _LOGGER.debug(
                "Packet has future(s) registered. Triggering future(s) and ignoring packet..."
            )
            for future in self._packet_futures[pattern + cmd]:
                future.set_result(payload)
            return

        # Match against common message types
        match pattern.hex():

            # Negotiation messages
            case "030001":
                _LOGGER.debug("Received negotiation message!")
                return await self._process_negotiation(cmd, payload)

            # Session messages
            case "03010f" | "030111":

                # Non-encrypted telemetry messages
                if cmd.hex() == "0300":
                    _LOGGER.debug("Received non-encrypted telemetry message!")
                    parameters = self._parse_payload(payload)
                    return await self._process_telemetry(parameters)

                # Encrypted telemetry messages
                elif cmd.hex() in self._TELEMETRY_COMMANDS:
                    _LOGGER.debug("Received encrypted telemetry message!")
                    return await self._process_telemetry_packet(payload, cmd)

                # Unknown messages
                else:
                    _LOGGER.debug(f"Received unknown message of type: {cmd.hex()}")
                    try:

                        # If the payload is one byte too short and we are
                        # using the default AES (CBC) then try putting the
                        # last byte of the cmd in front of it
                        if (
                            len(payload) % 16 == 15
                            and self._decrypt_payload
                            is SolixBLEDevice._decrypt_payload
                        ):
                            _LOGGER.debug(
                                "Using special trick of embedded part of CMD in payload..."
                            )
                            payload = cmd[1].to_bytes() + payload

                        decrypted_payload = self._decrypt_payload(payload)
                        _LOGGER.debug(
                            f"Decrypted payload: {decrypted_payload.hex()}"
                        )
                        parameters = self._parse_payload(decrypted_payload)
                        _LOGGER.debug(
                            f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                        )
                    except Exception:
                        _LOGGER.exception(
                            "Exception decrypting unknown message type"
                        )

            case _:
                _LOGGER.warning(
                    f"Unexpected packet type '{pattern}' sent by device! Packet: {data.hex()}"
                )

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """Negotiate encryption with the device."""

        match cmd.hex():

            # There is a "stage 0" in which we automatically send a negotiation
            # request as soon as we establish the initial connection. That
            # should lead to the power station sending a response landing us
            # in stage 1.

            # Negotiation stage 1
            case "0801":
                _LOGGER.debug(
                    "Entered negotiation stage 1 due to response from device!"
                )
                parameters = self._parse_payload(payload)
                _LOGGER.debug(f"Parameters: {self._parameters_to_str(parameters)}")
                _LOGGER.debug("Sending stage 1 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND, bytes.fromhex(NEGOTIATION_COMMAND_1)
                )

            # Negotiation stage 2
            case "0803":
                _LOGGER.debug(
                    "Entered negotiation stage 2 due to response from device!"
                )
                parameters = self._parse_payload(payload)
                _LOGGER.debug(f"Parameters: {self._parameters_to_str(parameters)}")
                _LOGGER.debug("Sending stage 2 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND, bytes.fromhex(NEGOTIATION_COMMAND_2)
                )

            # Negotiation stage 3
            case "0829":
                _LOGGER.debug(
                    "Entered negotiation stage 3 due to response from device!"
                )
                parameters = self._parse_payload(payload)
                _LOGGER.debug(f"Parameters: {self._parameters_to_str(parameters)}")
                self._negotiation_timestamp = time.time()
                _LOGGER.debug("Sending stage 3 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND, bytes.fromhex(NEGOTIATION_COMMAND_3)
                )

            # Negotiation stage 4
            case "0805":
                _LOGGER.debug(
                    "Entered negotiation stage 4 due to response from device!"
                )
                parameters = self._parse_payload(payload)
                _LOGGER.debug(f"Parameters: {self._parameters_to_str(parameters)}")
                _LOGGER.debug("Sending stage 4 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND, bytes.fromhex(NEGOTIATION_COMMAND_4)
                )

            # Negotiation stage 5
            case "0821":
                _LOGGER.debug(
                    "Entered negotiation stage 5 due to response from device!"
                )
                parameters = self._parse_payload(payload)
                _LOGGER.debug(f"Parameters: {self._parameters_to_str(parameters)}")

                # Extract public key of device from payload
                device_public_key_bytes = bytes.fromhex("04") + parameters["a1"]
                _LOGGER.debug(f"Public key of device: {device_public_key_bytes.hex()}")
                device_public_key = EllipticCurvePublicKey.from_encoded_point(
                    SECP256R1(), device_public_key_bytes
                )

                # Calculate the shared secret
                # The first half of the shared secret is the encryption key
                # and the second half is the IV
                private_value = int.from_bytes(
                    bytes.fromhex(PRIVATE_KEY), byteorder="big"
                )
                private_key = derive_private_key(private_value, SECP256R1())
                self._shared_secret = private_key.exchange(ECDH(), device_public_key)
                _LOGGER.debug(f"Shared secret: {self._shared_secret.hex()}")

                _LOGGER.debug("Sending stage 5 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND, bytes.fromhex(NEGOTIATION_COMMAND_5)
                )

            # Negotiation stage 6 (Optional)
            # Some devices (e.g C300X) sometimes send an extra message after
            # stage 5 but others (e.g C1000) do not. No response is needed
            # but it does not hurt to decrypt it anyway.
            case "4822":
                _LOGGER.debug(
                    "Entered negotiation stage 6 (optional) due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(f"Parameters: {self._parameters_to_str(parameters)}")

            case _:
                _LOGGER.warning(
                    f"Received unexpected negotiation request response from device! cmd: '{cmd}', parameters: '{self._parameters_to_str(parameters)}'"
                )

    def _checksum(self, packet: bytes) -> bytes:
        """Calculate the checksum byte for a packet."""
        checksum_value = 0
        for b in packet:
            checksum_value = checksum_value ^ b
        return checksum_value.to_bytes(1)

    async def _send_command(self, cmd: bytes, payload: bytes) -> None:
        """Send a command to the device.

        :param cmd: 2 bytes containing command type.
        :param payload: Variable number of bytes containing arguments.
        :raises ConnectionError: If not connected/negotiated to device.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        # Commands include a timestamp in the payload to prevent replay attacks
        # and that timestamp is set during negotiations
        time_passed = int(time.time() - self._negotiation_timestamp)
        base_timestamp = int.from_bytes(
            bytes.fromhex(BASE_TIMESTAMP), byteorder="little"
        )
        new_timestamp = (base_timestamp + time_passed).to_bytes(
            length=4, byteorder="little"
        )
        new_payload = payload + bytes.fromhex("fe0503") + new_timestamp
        await self._send_encrypted_packet(cmd, new_payload)

    def _build_packet(self, pattern: bytes, cmd: bytes, payload: bytes) -> bytes:
        """
        Build a packet to be send to a device.

        Packet format: <HEADER 2B> <LENGTH 2B> <PATTERN 3B> <CMD 2B> <PAYLOAD bB> <CHECKSUM 1B>.

        :param pattern: Pattern of packet (e.g encrypted, negotiation, etc).
        :param cmd: Command in packet (e.g telemetry, power on, etc).
        :param payload: Payload of command (e.g a1...).
        :returns: Packet bytes ready to be sent.
        """

        # Calculate length of message
        length = 2 + 2 + 3 + 2 + len(payload) + 1
        length_bytes = length.to_bytes(length=2, byteorder="little")

        # Build packet
        packet = bytes.fromhex("ff09") + length_bytes + pattern + cmd + payload
        return packet + self._checksum(packet)

    async def _send_encrypted_packet(self, cmd: bytes, payload: bytes) -> None:
        """Send an encrypted packet using negotiated shared secret and IV."""
        _LOGGER.debug(
            f"Building packet with cmd: {cmd.hex()} and payload: {payload.hex()}"
        )
        encrypted_payload = self._encrypt_payload(payload)

        packet = self._build_packet(bytes.fromhex("03000f"), cmd, encrypted_payload)
        _LOGGER.debug(f"Sending encrypted packet: {packet.hex()}")

        # Send packet
        await self._client.write_gatt_char(UUID_COMMAND, packet)

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
        """Reset negotiated variables and data and futures."""

        if reset_data:
            self._data = None
            self._last_data_timestamp = None

        self._fragment_buffers = {}
        self._fragment_totals = {}
        self._shared_secret = None
        self._last_packet_timestamp = None
        self._negotiation_timestamp = None
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
