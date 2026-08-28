"""Fixtures for tests for SolixBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
from collections.abc import Generator
from unittest import mock

import pytest

from SolixBLE.const import FALLBACK_TZ
from SolixBLE.device import SolixBLEDevice
from SolixBLE.prime_device import PrimeDevice


@pytest.fixture
def fast_timeouts():
    """Use to make asyncio.Timeout finish 100x faster."""
    original_timeout = asyncio.timeout

    def scaled_timeout(delay):
        return original_timeout(delay / 100 if delay else None)

    with mock.patch("asyncio.timeout", side_effect=scaled_timeout):
        yield


@pytest.fixture
def fast_sleep():
    """Use to make asyncio.sleep finish 100x faster."""
    original_sleep = asyncio.sleep

    async def scaled_sleep(delay):
        return await original_sleep(delay / 100)

    with mock.patch("asyncio.sleep", side_effect=scaled_sleep):
        yield


@pytest.fixture
def fake_time() -> Generator[None, None, None]:
    """Use the timestamp used in the test data for all packets."""

    solix = bytes.fromhex("42ad8c69")
    prime = bytes.fromhex("ef79b569")

    def _mocked_timestamp(self) -> bytes:  # noqa: ANN001
        return prime if isinstance(self, PrimeDevice) else solix

    with (
        mock.patch.object(SolixBLEDevice, "_timestamp", new=_mocked_timestamp),
        mock.patch("SolixBLE.device.get_posix_tz", return_value=FALLBACK_TZ),
        mock.patch("SolixBLE.prime_device.get_posix_tz", return_value=FALLBACK_TZ),
    ):
        yield
