"""Utilities for SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import importlib.resources as resources
import inspect
import logging
from typing import Callable

import tzlocal
from bleak import BleakScanner, BLEDevice

from .const import UUID_IDENTIFIER

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
        if UUID_IDENTIFIER in advertising_data.service_uuids and device not in devices:
            _LOGGER.debug(
                f"Found Anker device '{device}' with advertising data: '{advertising_data}'"
            )
            devices.append(device)

    async with BleakScanner(callback) as scanner:
        await asyncio.sleep(timeout)

    return devices

def _filter_kwargs(function: Callable, args: dict) -> dict:
    """
    Return only the keyword arguments which are valid for the function.

    :param function: Function to filter arguments for.
    :param args: Arguments to filter.
    :returns: Filtered arguments.
    """
    signature = inspect.signature(function)
    return {
        k: v for k, v in args.items()
        if k in signature.parameters and k != "self"
    }

def _to_bytes(data: bytes | str | int | Callable | None, **kwargs: dict) -> bytes:
    """Return input in byte form.

    Lambda functions are executed using keyword arguments.
    Keyword arguments are passed through to conversion functions.

    :param data: Data to convert to bytes.
    :returns: Byte form of input.
    :raises ValueError: If input type unsupported.
    """
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if type(data) is str:
        return bytes.fromhex(data)
    if type(data) is int:
        return int.to_bytes(data, **_filter_kwargs(int.to_bytes, kwargs))
    if isinstance(data, Callable):
        return _to_bytes(data(*[kwargs[x] for x in data.__code__.co_varnames]), **kwargs)
    raise ValueError(f"Unable to convert '{type(data)}' to bytes!")

def get_posix_tz() -> str | None:
    """Return the current time zone as a POSIX timezone string.

    Examples: `EST5EDT,M3.2.0,M11.1.0`, `GMT0BST,M3.5.0/1,M10.5.0`

    :returns: String of the systems timezone in POSIX format or None if unable.
    """

    try:
        local_zone = tzlocal.get_localzone_name()

        # The POSIX tz string is present on the last line of the tz db
        with resources.files("tzdata.zoneinfo").joinpath(local_zone).open("rb") as f:
            lines = f.readlines()
            return lines[-1].decode("ascii").strip()
    except Exception:
        _LOGGER.exception("Unable to determine system time zone!")
