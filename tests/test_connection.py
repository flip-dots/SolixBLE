"""Tests for the automatic reconnection to devices.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio

import pytest

from SolixBLE import C300, PrimeCharger160w, SolixBLEDevice
from tests.const import (
    MOCK_BLE_DEVICE,
    NEGOTIATION_RESPONSES_PRIME,
    NEGOTIATION_RESPONSES_SOLIX,
)
from tests.helpers import MockDevice


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,negotiation",
    [
        pytest.param(C300, NEGOTIATION_RESPONSES_SOLIX, id="solix"),
        pytest.param(PrimeCharger160w, NEGOTIATION_RESPONSES_PRIME, id="prime"),
    ],
)
async def test_automatic_retry(
    fast_sleep,
    fast_timeouts,
    frozen_time,
    device_class: type[SolixBLEDevice],
    negotiation: dict,
):
    """
    Test the automatic retrying of a lost connection when the
    reconnection happens within the timeout.

    This test expects the module to connect the the mock device
    and then the mock device drops the connection and we expect
    the module to automatically reconnect and not run any callbacks.

    :param device_class: Device class under test (e.g C300).
    :param negotiation: Expected negotiation for the device to mock it.
    """

    async with MockDevice() as mock_bluetooth:
        device = device_class(MOCK_BLE_DEVICE)

        def my_callback(*args, **kwargs):
            """We do not expect this callback to be triggered."""
            assert False

        # We first expect a negotiation
        for expected, responses in negotiation.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected) if expected is not None else None,
                [bytes.fromhex(response) for response in responses],
            )

        # We expect the negotiations to succeed
        assert await device.connect(), "Expected connect to return True"
        await asyncio.sleep(0.5)
        assert device.connected, "Expected connected to be True"
        assert device.negotiated, "Expected connected to be True"
        mock_bluetooth.check_assertions()

        # We then add our callback that should not be run as we should
        # silently reconnect
        device.add_callback(my_callback)

        # We will soon expect a renegotiation
        for expected, responses in negotiation.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected) if expected is not None else None,
                [bytes.fromhex(response) for response in responses],
            )

        # We then trigger a disconnect from the device
        mock_bluetooth.disconnect()
        await asyncio.sleep(0.5)
        assert not device.connected, "Expected connected to be False"
        assert not device.negotiated, "Expected connected to be False"

        # Set .is_connected to True
        mock_bluetooth.allow_connect()

        # We expect to have been automatically reconnected
        await asyncio.sleep(30)
        assert device.connected, "Expected connected to be True"
        assert device.negotiated, "Expected connected to be True"
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,negotiation",
    [
        pytest.param(C300, NEGOTIATION_RESPONSES_SOLIX, id="solix"),
        pytest.param(PrimeCharger160w, NEGOTIATION_RESPONSES_PRIME, id="prime"),
    ],
)
async def test_automatic_retry_timeout(
    fast_sleep,
    fast_timeouts,
    frozen_time,
    device_class: type[SolixBLEDevice],
    negotiation: dict,
):
    """
    Test the automatic retrying of a lost connection when
    the reconnection takes longer than the timeout.

    This test expects the module to connect the the mock device
    and then the mock device drops the connection and we expect
    callbacks to be run as the module will not be able to establish
    the connection within the silent reconnect timeout and then
    we allow a reconnect and expect the module to automatically
    reconnect and run callbacks again on successful connection.

    :param device_class: Device class under test (e.g C300).
    :param negotiation: Expected negotiation for the device to mock it.
    """

    async with MockDevice() as mock_bluetooth:
        device = device_class(MOCK_BLE_DEVICE)

        num_calls = 0

        def my_callback(*args, **kwargs):
            """We expect this to be triggered on timeout limit and on reconnect."""
            nonlocal num_calls
            num_calls = num_calls + 1

        # We first expect a negotiation
        for expected, responses in negotiation.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected) if expected is not None else None,
                [bytes.fromhex(response) for response in responses],
            )

        # We expect the negotiations to succeed
        assert await device.connect(), "Expected connect to return True"
        await asyncio.sleep(1)
        assert device.connected, "Expected connected to be True"
        assert device.negotiated, "Expected connected to be True"
        mock_bluetooth.check_assertions()

        # We then add our callback that should be run both when the timeout
        # is exceeded and again when we successfully reconnect
        device.add_callback(my_callback)

        # We then trigger a disconnect from the device
        mock_bluetooth.disconnect()
        await asyncio.sleep(160)
        assert not device.connected, "Expected connected to be False"
        assert not device.negotiated, "Expected connected to be False"

        # Expect callback to be triggered due to timeout limit being
        # exceeded
        assert num_calls == 1

        # Set .is_connected to True
        mock_bluetooth.allow_connect()

        # We then expect a renegotiation
        for expected, responses in negotiation.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected) if expected is not None else None,
                [bytes.fromhex(response) for response in responses],
            )

        # We expect to have been automatically reconnected
        await asyncio.sleep(30)
        assert device.connected, "Expected connected to be True"
        assert device.negotiated, "Expected connected to be True"
        mock_bluetooth.check_assertions()

        # Expect callback to have been triggered again due to
        # successful reconnection after running callbacks due to
        # disconnection
        assert num_calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,negotiation",
    [
        pytest.param(C300, NEGOTIATION_RESPONSES_SOLIX, id="solix"),
        pytest.param(PrimeCharger160w, NEGOTIATION_RESPONSES_PRIME, id="prime"),
    ],
)
async def test_disconnect(
    fast_timeouts,
    fast_sleep,
    frozen_time,
    device_class: type[SolixBLEDevice],
    negotiation: dict,
):
    """
    Test the mock device is disconnected and no automatic
    reconnection attempts are executed when disconnect is called.

    We also expect no callbacks to be run and multiple calls
    to disconnect to do nothing.

    :param device_class: Device class under test (e.g C300).
    :param negotiation: Expected negotiation for the device to mock it.
    """

    async with MockDevice() as mock_bluetooth:
        device = device_class(MOCK_BLE_DEVICE)

        async def assert_still_disconnected():
            """Assert that device is still disconnected."""
            for i in range(100):
                await asyncio.sleep(1)
                assert not device.connected, (
                    f"Expected connected to be False after {i} seconds"
                )
                assert not device.negotiated, (
                    f"Expected negotiated to be False after {i} seconds"
                )
                assert device._client is None, (
                    f"Expected client to be None after {i} seconds"
                )

        def my_callback(*args, **kwargs):
            """We expect this to not be called."""
            assert False

        # We first expect a negotiation
        for expected, responses in negotiation.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected) if expected is not None else None,
                [bytes.fromhex(response) for response in responses],
            )

        # We expect the negotiations to succeed
        assert await device.connect(), "Expected connect to return True"
        await asyncio.sleep(5)
        assert device.connected, "Expected connected to be True"
        assert device.negotiated, "Expected negotiated to be True"
        mock_bluetooth.check_assertions()

        # We then add our callback that should not be run when we call
        # disconnect
        device.add_callback(my_callback)

        # We then call disconnect and expect to remain disconnected and that
        # disconnect on the client was called
        await device.disconnect()
        await assert_still_disconnected()
        mock_bluetooth._current_mock_bleak_client.disconnect.assert_called_once()

        # We call disconnect again and expect no changes (still disconnected)
        await device.disconnect()
        await assert_still_disconnected()
