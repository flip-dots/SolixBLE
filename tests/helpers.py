"""Helpers for the test.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Self, Union
from unittest import mock

from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePrivateKey,
    derive_private_key,
)

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
)

from SolixBLE.const import FALLBACK_TZ
from SolixBLE.constructs import Composer, Packet, PacketCommand, PacketPattern
from SolixBLE.device import SolixBLEDevice
from SolixBLE.protocols import EcdhPath, Keys, NegotiatedSession
from SolixBLE.utilities import _to_bytes
from tests.const import SOLIX_TEST_PRIVATE_KEY

_LOGGER = logging.getLogger(__name__)


@dataclass
class RequestResponse:
    """
    Internal data class used by MockDevice to keep track of which
    requests have been executed and what the correct response to
    the request is.
    """

    name: str
    """
    Name of request to produce more useful error messages.
    """

    expected: Union[bytes, None]
    """
    The bytes expected by this request. Use none to accept any bytes.
    """

    response: list[bytes]
    """
    The bytes (if any) that should be sent in response to a matching request.
    """

    called: bool = field(default=False)
    """
    Has this request been fulfilled.
    """

    refuse: bool = field(default=False)
    """
    Drop the connection instead of responding, as a device does when it
    refuses a request.
    """

    refuse_during_write: bool = field(default=False)
    """
    Drop the connection before the refused write returns, so the write
    raises as bleak's does.
    """


class MockDevice:
    """
    Class designed to emulate the behavior of an Anker device.

    This is designed to be used as a context manager and allows for the
    easy defining of expected requests and the appropriate responses as
    well as built in assertions for checking that all the requests were
    made.

    This implementation is a tad cursed to allow us to test some strange
    edge cases that seem to keep popping up.
    """

    def __init__(self) -> None:
        """Initialise mock device."""

        # Tuple used to keep track of all the bleak clients that have been
        # created. Each tuple contains the client, the clients disconnect
        # callbacks, and the clients notification callbacks
        self._mock_bleak_clients: list[
            tuple[BleakClient, list[Callable], list[Callable]]
        ] = []

        # This is the result of the mock.patch and used to return our
        # modified bleak client when establish connection is called
        self._establish = None

        # This is the function we are patching so instead of an actual
        # bleak client its getting our mocked one
        self._patcher = mock.patch("SolixBLE.device.establish_connection")

        # List of assertions (requests and responses) we expect to be made
        self._assertions: list[RequestResponse] = []

        # The most freshly created mock bleak client
        self._current_mock_bleak_client = None

        # The position of the next request we expect to get in the list
        # of assertions
        self._position = 0

        # The value that all our mocked bleak clients will return for
        # client.is_connected. This can be changed dynamically
        self._is_connected = True

        # The GATT UUIDs the module under test subscribed to and wrote to
        self.notify_uuids: list[str | bytes] = []
        self.write_uuids: list[str | bytes] = []

        # The response argument of every write, None where it was left out
        self.write_responses: list[bool | None] = []

        # Every packet the module under test wrote, in order
        self.writes: list[bytes] = []

        # Set by a refusal so the next connection succeeds again
        self._connect_next = False

    def new_connection_mock(self):
        """
        Executing this causes all new bleak clients created using
        establish_connection to be our mocked versions.
        """

        def custom_init(*args, **kwargs):
            """
            This function is used to create new mock bleak clients whenever
            establish_connection is called.
            """
            _LOGGER.debug(f"New mock bleak client created with '{args}', '{kwargs}'!")

            # A device that refused the last connection accepts the next one
            if self._connect_next:
                self._is_connected = True
                self._connect_next = False

            # We give it a name so we can tell the difference between them in logs
            mock_bleak_client = mock.AsyncMock(
                name=f"bleak_client_{len(self._mock_bleak_clients)}"
            )

            # Set functions/properties
            mock_bleak_client.write_gatt_char.side_effect = self.write_gatt_char
            mock_bleak_client.start_notify.side_effect = self.start_notify
            type(mock_bleak_client).is_connected = mock.PropertyMock(
                side_effect=lambda: self._is_connected
            )

            # Add it to the list of all bleak clients
            self._mock_bleak_clients.append(
                (mock_bleak_client, [kwargs["disconnected_callback"]], [])
            )

            # Set this as the most current bleak client and return it
            self._current_mock_bleak_client = mock_bleak_client
            return mock_bleak_client

        # Use custom_init to manufacture all new bleak clients
        self._establish.side_effect = custom_init

    async def __aenter__(self):
        """Enter the context. Patches establish_connection so all new clients are mocks."""
        self._establish = self._patcher.start()
        self.new_connection_mock()
        return self

    def new_connection_error(self, side_effect: Any):
        """
        Executing this causes all new bleak clients created using
        establish_connection to trigger this side effect.

        :param side_effect: Side effect to trigger (e.g exception).
        """
        if self._establish is None:
            raise ValueError("Context manager not active!")
        self._establish.side_effect = side_effect

    def allow_connect(self):
        """
        Set is_connected of all mocked bleak clients to True.
        """
        self._is_connected = True

    def disconnect(self) -> None:
        """
        Set is_connected of all mocked bleak clients to False and
        trigger call on_disconnect callbacks.
        """
        self._is_connected = False
        for bleak_client, dc_callbacks, _ in self._mock_bleak_clients:
            for callback in dc_callbacks:
                callback(bleak_client)

    def expect_ordered(
        self, value: Union[bytes, None] = None, response: list[bytes] = []
    ):
        """
        Expect an ordered request to be made to the mock device with
        the specified value and optionally respond with bytes.

        If an unexpected or out of order request is made an error will be
        raised.

        :param value: Expected bytes value or None to accept any.
        :param response: List of bytes to respond with.
        """
        self._assertions.append(
            RequestResponse(
                name=f"num {len(self._assertions)}", expected=value, response=response
            )
        )

    def refuse_after(
        self,
        value: bytes | None = None,
        *,
        during_write: bool = False,
    ) -> None:
        """
        Expect an ordered request and drop the connection when it is made.

        Nothing is answered, as a device does when it refuses a request. The
        next connection made to the mock device succeeds.

        :param value: Expected bytes value or None to accept any.
        :param during_write: Drop before the write returns, so it raises.
        """
        self._assertions.append(
            RequestResponse(
                name=f"num {len(self._assertions)} (refused)",
                expected=value,
                response=[],
                refuse=True,
                refuse_during_write=during_write,
            ),
        )

    def expect_ordered_all(self, requests: list[RequestResponse]):
        """
        Expect an list of requests.

        If an unexpected or out of order request is made an error will be
        raised.

        :param request_response: Expected request and/or response.
        """
        self._assertions.extend(requests)

    async def start_notify(self, uuid: bytes, callback: Callable):
        """
        Patched version of the bleak clients start_notify function
        which will add the callback to the currently active bleak
        client only.

        :param uuid: The UUID the module under test wants notifications of.
        :param callback: The callback the module under test wants executed.
        """
        self.notify_uuids.append(uuid)
        for client, _, n_callbacks in self._mock_bleak_clients:
            if client is self._current_mock_bleak_client:
                n_callbacks.append(callback)

    async def send_data(self, data: list[bytes]) -> None:
        """
        Write the specified data as a notification to all clients
        registered callbacks.

        :param data: Data to send.
        """

        for client, _, n_callbacks in self._mock_bleak_clients:
            for callback in n_callbacks:
                for packet in data:
                    _LOGGER.debug(
                        f"Mock device sending '{packet.hex()}' to client '{client}' for callback '{callback}'..."
                    )
                    # Handle is not used
                    await callback(None, packet)

                # Wait between sending
                await asyncio.sleep(0.1)

    async def write_gatt_char(
        self, char_specifier: str, data: bytes, response: bool | None = None
    ):
        """
        Patched version of the bleak clients write_gatt_char function
        which will raise an error if the data is not expected and
        will respond with the value to all bleak clients with callbacks
        set if a response is set.

        :param char_specifier: Not used, would be the UUID the module wants to write to.
        :param data: The data the module wants to write.
        :param response: Recorded in write_responses. The ATT write type, None if left out.
        """
        _LOGGER.debug(f"Mock device has received data: '{data.hex()}'")
        self.write_uuids.append(char_specifier)
        self.write_responses.append(response)

        # Find the request/response for this write
        request_response = None
        try:
            request_response = self._assertions[self._position]
        except IndexError:
            print(self._assertions)
            assert (
                False
            ), f"Received an unexpected request '{data.hex()}'. Number: {self._position+1}, Num expected: {len(self._assertions)}"

        if request_response.expected is not None:
            # Assert it matches
            assert (
                request_response.expected == data
            ), f"Expected bytes {request_response.expected.hex()}' for request '{request_response.name}' ({self._position+1}) but got '{data.hex()}'!"

        # Increment position
        self._position = self._position + 1
        request_response.called = True
        self.writes.append(bytes(data))

        # A refused request drops the connection and answers nothing
        if request_response.refuse:
            self.disconnect()
            self._connect_next = True
            if request_response.refuse_during_write:
                msg = "disconnected"
                raise BleakError(msg)
            return

        # Wait a little
        await asyncio.sleep(0.1)

        # If no response return
        if request_response.response is None:
            return

        # Respond with data to all clients on all callbacks
        await self.send_data(request_response.response)

    def check_assertions(self):
        """
        Check that all specified requests have been made by the module.
        """
        for i, item in enumerate(self._assertions):
            assert (
                item.called
            ), f"Request '{item.name}' ({i}) with expected bytes '{item.expected.hex()}' was not called!"

    async def __aexit__(self, *exc):
        """
        Exit context. Stops patching establish_connection.
        """
        self._patcher.stop()
        return False


def make_advertisement(
    manufacturer_data: dict[int, bytes] | None = None,
    service_uuids: list[str] | None = None,
    local_name: str | None = None,
) -> AdvertisementData:
    """
    Build a bleak scan result with the given fields.

    :param manufacturer_data: Manufacturer data by company identifier.
    :param service_uuids: Advertised service UUIDs.
    :param local_name: Advertised local name.
    """
    return AdvertisementData(
        local_name=local_name,
        manufacturer_data=manufacturer_data or {},
        service_data={},
        service_uuids=service_uuids or [],
        tx_power=None,
        rssi=-60,
        platform_data=(),
    )


def scanner_reporting(results: list[tuple[BLEDevice, AdvertisementData]]) -> type:
    """
    Return a stand-in for BleakScanner that reports the given scan results.

    The results are passed to the detection callback as soon as the scanner
    is entered, as a real scanner would while it runs.

    :param results: Pairs of device and scan result to report.
    """

    class _Scanner:

        def __init__(
            self, callback: Callable[[BLEDevice, AdvertisementData], None],
        ) -> None:
            self._callback = callback

        async def __aenter__(self) -> Self:
            for device, advertisement in results:
                self._callback(device, advertisement)
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

    return _Scanner


def install_session_keys(device: SolixBLEDevice, secret: bytes) -> None:
    """
    Give a device the session keys an ECDH negotiation derives from a secret.

    The device keeps its current session (or starts one on its class's outer
    protocol) and its path holds ``secret[:16]`` as the key and
    ``secret[16:32]`` as the IV, as after a real key exchange. An empty
    secret leaves the keys as they are.

    :param device: Device under test.
    :param secret: The 32-byte ECDH shared secret, or empty.
    """
    if device._session is None:
        device._session = NegotiatedSession(device._outer_class(), device)
    if device._session.path is None:
        device._session.path = EcdhPath()
    if secret:
        device._session.path.keys = Keys.parse(secret)


#: Client UUID and token reported by RecordingLink.
RECORDING_CLIENT_ID = "b2dc0b17-b75d-4abf-ba6e-ec7c997c23e7"


class RecordingLink:
    """
    Stand-in for the device a negotiation runs on.

    Every packet the negotiation sends is recorded as a tuple of pattern,
    cmd and parameters, with each parameter value resolved to bytes the way
    the device resolves it. The clock, time zone, client id and private key
    are fixed so the recorded bytes are reproducible.
    """

    _UUID_STRING = RECORDING_CLIENT_ID
    _client_token = RECORDING_CLIENT_ID

    def __init__(self) -> None:
        """Initialise with nothing sent."""

        # Every packet sent, in order, as (pattern, cmd, parameters)
        self.sent: list[tuple[str, str, dict[str, bytes]]] = []

    async def _send_packet(
        self, channel: int, command: Container, parameters: dict[str, Any],
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """
        Record a packet instead of sending it.

        :param channel: Channel of the packet.
        :param command: The command's fields.
        :param parameters: Parameters by tag, values may be lambdas taking self.
        """
        pattern = PacketPattern.build({"composer": Composer.REPLY, "channel": channel})
        self.sent.append((pattern.hex(), PacketCommand.build(command).hex(), {
            tag: _to_bytes(data=item["value"], **kwargs | { "self": self })
            for tag, item in parameters.items()
        }))

    def _timestamp(self) -> bytes:
        """Return a fixed timestamp."""
        return bytes.fromhex("42ad8c69")

    def _timezone_offset(self) -> bytes:
        """Return a fixed UTC offset of zero seconds west."""
        return bytes(4)

    def _posix_timezone(self) -> str:
        """Return the fallback POSIX time zone."""
        return FALLBACK_TZ

    def _generate_private_key(self) -> EllipticCurvePrivateKey:
        """Return the key derived from the fixed private value."""
        return derive_private_key(
            int.from_bytes(bytes.fromhex(SOLIX_TEST_PRIVATE_KEY), byteorder="big"),
            SECP256R1(),
        )


async def feed_negotiation(
    session: NegotiatedSession, replies: list[tuple[str, str]],
) -> None:
    """
    Feed a negotiation session decrypted device replies in order.

    :param session: Session under test.
    :param replies: Pairs of command and plaintext payload, both as hex.
    """
    for cmd, plaintext in replies:
        await session.on_plaintext(frame_header(cmd), bytes.fromhex(plaintext))


def build_frame(pattern: str, cmd: str, payload: bytes = b"") -> bytes:
    """
    Build a frame from its header bytes as written on the wire.

    :param pattern: The 3-byte pattern as hex (e.g. ``03010f``).
    :param cmd: The 2-byte command as hex (e.g. ``c402``).
    :param payload: The payload bytes.
    :returns: The whole frame, checksum included.
    """
    header = PacketPattern.parse(bytes.fromhex(pattern))
    command = PacketCommand.parse(bytes.fromhex(cmd))
    return Packet.build({
        "composer": header.composer,
        "channel": header.channel,
        "fragmented": command.fragmented,
        "encrypted": command.encrypted,
        "msgtype": command.msgtype,
        "payload_bytes": payload,
    })


def frame_header(cmd: str, pattern: str = "030001") -> Container:
    """
    Return the parsed header of a frame, as the device hands it on.

    :param cmd: The 2-byte command as hex (e.g. ``4801``).
    :param pattern: The 3-byte pattern as hex.
    :returns: The parsed packet, with an empty payload.
    """
    return Packet.parse(build_frame(pattern, cmd))


def session_reply(device: SolixBLEDevice, cmd: str, plaintext: str) -> bytes:
    """
    Build a session frame from the device, sealed under its negotiated session.

    :param device: The negotiated device under test.
    :param cmd: The 2-byte command as hex (e.g. ``4a05``).
    :param plaintext: The payload as hex.
    :returns: The whole frame, as the device notifies it.
    """
    sealed = device._encrypt_payload(bytes.fromhex(plaintext))  # noqa: SLF001
    return build_frame("03010f", cmd, sealed)


def sent_payloads(device: SolixBLEDevice, writes: list[bytes]) -> list[tuple[int, str]]:
    """
    Return the message type and the decrypted payload of each written frame.

    :param device: The negotiated device that wrote the frames.
    :param writes: The frames, e.g. ``MockDevice.writes``.
    :returns: Pairs of message type and payload as hex.
    """
    packets = [Packet.parse(write) for write in writes]
    return [
        (packet.msgtype, device._decrypt_payload(packet.payload_bytes).hex())  # noqa: SLF001
        for packet in packets
    ]


async def connect_recorded(
    device: SolixBLEDevice,
    mock_bluetooth: MockDevice,
    responses: dict[str, list[str]],
) -> None:
    """
    Connect a device through a recorded negotiation on the mock device.

    :param device: Device under test.
    :param mock_bluetooth: The active mock device.
    :param responses: Maps each sent frame (as hex) to its replies (as hex),
        e.g. NEGOTIATION_RESPONSES_PRIME.
    """
    for expected, replies in responses.items():
        mock_bluetooth.expect_ordered(
            bytes.fromhex(expected), [bytes.fromhex(reply) for reply in replies],
        )
    assert await device.connect()


def window_acks(
    device: SolixBLEDevice, count: int, final: list[bytes], window: int = 10,
) -> list[list[bytes]]:
    """
    Return the device's replies to each chunk of an upload that goes through.

    A ``4a21`` status 00 with the next index after each full window, and
    ``final`` after the last chunk.

    :param device: The negotiated device under test.
    :param count: Number of chunks.
    :param final: The replies to the last chunk.
    :param window: Chunks per window.
    """
    replies: list[list[bytes]] = []
    for index in range(count):
        if index == count - 1:
            replies.append(final)
        elif (index + 1) % window == 0:
            next_index = struct.pack("<H", index + 1).hex()
            replies.append(
                [session_reply(device, "4a21", f"00a10131a20302{next_index}")],
            )
        else:
            replies.append([])
    return replies


def chunk_payload(
    image: bytes, index: int, chunk_size: int = 192, *, pad: bool = True,
) -> str:
    """
    Return a ``4221`` chunk's payload before its timestamp, as hex.

    The index as u16 LE in ``a2``; ``a3`` a type byte then the chunk, the last
    one zero-padded to ``chunk_size`` unless ``pad`` is off.

    :param image: The whole image.
    :param index: The chunk's index.
    :param chunk_size: Bytes per chunk.
    :param pad: Zero-pad the last chunk.
    """
    chunk = image[index * chunk_size:(index + 1) * chunk_size]
    if pad:
        chunk = chunk.ljust(chunk_size, b"\x00")
    return (
        f"a10121a20302{struct.pack('<H', index).hex()}"
        f"a3{len(chunk) + 1:02x}04{chunk.hex()}"
    )


def jpeg_segment(marker: int, body: bytes) -> bytes:
    """
    Build a JPEG marker segment: ``ff``, the marker, the length, the body.

    :param marker: The marker byte (e.g. ``0xdb``).
    :param body: The segment's body.
    """
    return struct.pack(">BBH", 0xFF, marker, len(body) + 2) + body


def jpeg_scan(header: bytes, size: int = 0) -> bytes:
    """
    Complete a JPEG header with scan bytes free of ``ff`` and an EOI.

    :param header: The bytes from SOI through the scan header.
    :param size: The whole image's length, or 0 for 64 scan bytes.
    """
    length = size - len(header) - 2 if size else 64
    return header + bytes(index % 0xFF for index in range(length)) + b"\xff\xd9"


def jpeg_image(  # noqa: PLR0913
    *,
    width: int = 480,
    height: int = 200,
    precision: int = 8,
    components: int = 3,
    luma_sampling: int = 0x22,
    frame_marker: int = 0xC0,
    before_frame: bytes = b"",
    size: int = 0,
) -> bytes:
    """
    Build a JPEG in a baseline encoder's segment order.

    SOI, JFIF, the quantisation tables, the frame header, the Huffman tables
    and the scan header, then the scan bytes and EOI.

    :param width: Frame width in pixels.
    :param height: Frame height in pixels.
    :param precision: Sample precision in bits.
    :param components: Number of colour components.
    :param luma_sampling: The first component's sampling byte (h << 4 | v).
    :param frame_marker: The frame header's marker (``0xc0`` baseline).
    :param before_frame: Bytes placed just before the frame header.
    :param size: The whole image's length, or 0 for a short scan.
    """
    jfif = jpeg_segment(0xE0, bytes.fromhex("4a46494600010100000100010000"))
    quantisation = jpeg_segment(0xDB, b"\x00" + bytes(64) + b"\x01" + bytes(64))
    frame = jpeg_segment(frame_marker, struct.pack(
        ">BHHB", precision, height, width, components,
    ) + b"".join(
        bytes([index + 1, luma_sampling if index == 0 else 0x11, min(index, 1)])
        for index in range(components)
    ))
    huffman = jpeg_segment(0xC4, b"".join(
        bytes([table]) + b"\x01" + bytes(15) + b"\x00"
        for table in (0x00, 0x10, 0x01, 0x11)
    ))
    scan = jpeg_segment(0xDA, bytes([components]) + b"".join(
        bytes([index + 1, 0x00 if index == 0 else 0x11])
        for index in range(components)
    ) + b"\x00\x3f\x00")
    header = (
        b"\xff\xd8" + jfif + quantisation + before_frame + frame + huffman + scan
    )
    return jpeg_scan(header, size)


def with_crc32(image: bytes, crc: int) -> bytes:
    """
    Return the image with the four bytes before its EOI set so its CRC32 is ``crc``.

    :param image: An image ending in four scan bytes and EOI.
    :param crc: The CRC32 to reach.
    """
    table = []
    for byte in range(256):
        entry = byte
        for _ in range(8):
            entry = (entry >> 1) ^ 0xEDB88320 if entry & 1 else entry >> 1
        table.append(entry)
    by_top_byte = {entry >> 24: index for index, entry in enumerate(table)}
    prefix, suffix = image[:-6], image[-2:]

    # The CRC register after the four bytes, run back from the end
    register = crc ^ 0xFFFFFFFF
    for byte in reversed(suffix):
        index = by_top_byte[register >> 24]
        register = ((register ^ table[index]) << 8 & 0xFFFFFFFF) | (index ^ byte)

    # The table indices that register needs depend on its top bytes alone
    indices: list[int] = []
    for _ in range(4):
        index = by_top_byte[register >> 24]
        indices.insert(0, index)
        register = (register ^ table[index]) << 8 & 0xFFFFFFFF

    register = zlib.crc32(prefix) ^ 0xFFFFFFFF
    forged = bytearray()
    for index in indices:
        forged.append((register ^ index) & 0xFF)
        register = table[index] ^ (register >> 8)
    return prefix + bytes(forged) + suffix


def negotiation_steps_through(
    responses: dict[str, list[str]], stop_after: int,
) -> list[tuple[bytes, list[bytes]]]:
    """
    Return a recorded negotiation's steps, up to and including one request.

    Use to script a :class:`MockDevice` through a prefix of a recorded
    negotiation (e.g. up to the clock/time zone exchange), before swapping in
    a substitute reply for whatever request comes next.

    :param responses: Maps a sent frame's bytes (as hex) to its replies
        (as hex), in order, e.g. NEGOTIATION_RESPONSES_PRIME.
    :param stop_after: The request's message (e.g. ``Negotiation.GET_AES_KEY``)
        to stop after, inclusive.
    """
    steps = []
    for sent, replies in responses.items():
        steps.append((bytes.fromhex(sent), [bytes.fromhex(reply) for reply in replies]))
        if Packet.parse(bytes.fromhex(sent)).message == stop_after:
            break
    return steps
