"""Tests for the BLE transports.

.. moduleauthor:: kb1ibt
"""

import logging

import pytest
from bleak.backends.device import BLEDevice

from SolixBLE import C300, SolixBLEDevice, discover_devices
from SolixBLE.advertisement import ANKER_COMPANY_ID
from SolixBLE.const import (
    LEGACY_SERVICE,
    SERVICE_2215,
    UUID_COMMAND,
    UUID_COMMAND_2215,
    UUID_IDENTIFIER,
    UUID_TELEMETRY,
    UUID_TELEMETRY_2215,
    UUID_TELEMETRY_LEGACY,
)
from SolixBLE.transport import LegacyTransport, Transport2215
from tests.const import MOCK_BLE_DEVICE, NEGOTIATION_RESPONSES_SOLIX
from tests.helpers import MockDevice, make_advertisement, scanner_reporting


@pytest.mark.asyncio
async def test_legacy_transport_connects_without_negotiation(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A device on the legacy transport subscribes to ``8888`` and sends nothing."""

    class LegacyDevice(SolixBLEDevice):
        _TRANSPORT = LegacyTransport

    device = LegacyDevice(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        assert await device.connect()
        assert device.negotiated
        assert mock_bluetooth.notify_uuids == [UUID_TELEMETRY_LEGACY]
        assert mock_bluetooth.write_uuids == []
        await device.disconnect()


@pytest.mark.asyncio
async def test_negotiating_transport_uuids(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A negotiating device subscribes to ``8c850003`` and writes ``8c850002``."""
    device = C300(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        assert mock_bluetooth.notify_uuids == [UUID_TELEMETRY]
        assert set(mock_bluetooth.write_uuids) == {UUID_COMMAND}
        await device.disconnect()


@pytest.mark.asyncio
async def test_transport_2215_uuids(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A device on the 2215 transport negotiates on its own characteristics."""

    class Device2215(C300):
        _TRANSPORT = Transport2215

    device = Device2215(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        assert mock_bluetooth.notify_uuids == [UUID_TELEMETRY_2215]
        assert set(mock_bluetooth.write_uuids) == {UUID_COMMAND_2215}
        await device.disconnect()


@pytest.mark.asyncio
async def test_requested_disconnect_is_not_another_clients(
    caplog: pytest.LogCaptureFixture,
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """The link drop that follows ``disconnect()`` is logged as the one asked for."""
    device = C300(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        with caplog.at_level(logging.DEBUG, logger="SolixBLE.device"):
            await device.disconnect()
            mock_bluetooth.disconnect()

    assert f"Disconnected from '{device.name}'." in caplog.text
    assert "came from other client" not in caplog.text


def test_init_message_names_the_address(caplog: pytest.LogCaptureFixture) -> None:
    """The device's debug line on creation separates its name from its address."""
    with caplog.at_level(logging.DEBUG, logger="SolixBLE.device"):
        C300(MOCK_BLE_DEVICE)

    assert f"' with address '{MOCK_BLE_DEVICE.address}'" in caplog.text


@pytest.mark.asyncio
async def test_discover_matches_the_record_or_a_service() -> None:
    """Discovery keeps devices with the Anker record or any transport's service."""
    negotiating = BLEDevice("AA:BB:CC:DD:EE:01", "negotiating", None)
    legacy = BLEDevice("AA:BB:CC:DD:EE:02", "legacy", None)
    transport_2215 = BLEDevice("AA:BB:CC:DD:EE:03", "2215", None)
    passive = BLEDevice("AA:BB:CC:DD:EE:04", "passive scan", None)
    other = BLEDevice("AA:BB:CC:DD:EE:05", "other", None)
    results = [
        (negotiating, make_advertisement(service_uuids=[UUID_IDENTIFIER])),
        (legacy, make_advertisement(service_uuids=[LEGACY_SERVICE])),
        (transport_2215, make_advertisement(service_uuids=[SERVICE_2215])),
        # HaSolixBLE #17: a passive scan carries the record but no services
        (
            passive,
            make_advertisement(
                manufacturer_data={
                    ANKER_COMPANY_ID: bytes.fromhex("01f49d8a8a022602b103445a4204"),
                },
            ),
        ),
        (
            other,
            make_advertisement(service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"]),
        ),
    ]

    devices = await discover_devices(scanner=scanner_reporting(results), timeout=0)

    assert devices == [negotiating, legacy, transport_2215, passive]
