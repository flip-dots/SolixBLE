"""Helpers for the test.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from unittest import mock

from bleak import BleakClient

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

    expected: bytes | None
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

            # We give it a name so we can tell the difference between them in logs
            mock_bleak_client = mock.AsyncMock(
                name=f"bleak_client_{len(self._mock_bleak_clients)}",
            )

            # Set functions/properties
            mock_bleak_client.write_gatt_char.side_effect = self.write_gatt_char
            mock_bleak_client.start_notify.side_effect = self.start_notify
            # Emulate an Anker 256-byte ATT MTU so fragment reassembly (which gates on
            # the live ``mtu_size - 3`` notification cap) behaves as it does on device.
            mock_bleak_client.mtu_size = 256
            type(mock_bleak_client).is_connected = mock.PropertyMock(
                side_effect=lambda: self._is_connected,
            )

            # Add it to the list of all bleak clients
            self._mock_bleak_clients.append(
                (mock_bleak_client, [kwargs["disconnected_callback"]], []),
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

    def disconnect(self):
        """
        Set is_connected of all mocked bleak clients to False and
        trigger call on_disconnect callbacks.
        """
        self._is_connected = False
        for bleak_client, dc_callbacks, _ in self._mock_bleak_clients:
            for callback in dc_callbacks:
                callback(bleak_client)

    def expect_ordered(
        self,
        value: bytes | None = None,
        response: list[bytes] = [],
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
                name=f"num {len(self._assertions)}",
                expected=value,
                response=response,
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
                        f"Mock device sending '{packet.hex()}' to client '{client}' for callback '{callback}'...",
                    )
                    # Handle is not used
                    await callback(None, packet)

                # Wait between sending
                await asyncio.sleep(0.1)

    async def write_gatt_char(
        self,
        char_specifier: str,
        data: bytes,
        response: bool = False,
    ):
        """
        Patched version of the bleak clients write_gatt_char function
        which will raise an error if the data is not expected and
        will respond with the value to all bleak clients with callbacks
        set if a response is set.

        :param char_specifier: Not used, would be the UUID the module wants to write to.
        :param data: The data the module wants to write.
        :param response: Not used. Bool of if the module wants a response to its write.
        """
        _LOGGER.debug(f"Mock device has received data: '{data.hex()}'")

        # Find the request/response for this write
        request_response = None
        try:
            request_response = self._assertions[self._position]
        except IndexError:
            print(self._assertions)
            assert False, (
                f"Received an unexpected request '{data.hex()}'. Number: {self._position + 1}, Num expected: {len(self._assertions)}"
            )

        if request_response.expected is not None:
            # Assert it matches
            assert request_response.expected == data, (
                f"Expected bytes {request_response.expected.hex()}' for request '{request_response.name}' ({self._position + 1}) but got '{data.hex()}'!"
            )

        # Increment position
        self._position = self._position + 1
        request_response.called = True

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
            assert item.called, (
                f"Request '{item.name}' ({i}) with expected bytes '{item.expected.hex()}' was not called!"
            )

    async def __aexit__(self, *exc):
        """
        Exit context. Stops patching establish_connection.
        """
        self._patcher.stop()
        return False
