"""Utilities for SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging

from bleak import BleakScanner, BLEDevice

from .const import UUID_IDENTIFIERS

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
        _LOGGER.debug(
            f"Found generic BT device '{device}' with advertising data: '{advertising_data}'"
        )
        if UUID_IDENTIFIERS.intersection(advertising_data.service_uuids) and device not in devices:
            _LOGGER.debug(
                f"Found Anker device '{device}' with advertising data: '{advertising_data}'"
            )
            devices.append(device)

    async with BleakScanner(callback) as scanner:
        await asyncio.sleep(timeout)

    return devices
