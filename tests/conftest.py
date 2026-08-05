"""Fixtures for tests for SolixBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
from unittest import mock

import pytest


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


#: Unix time the frozen_time fixture pins. Its little-endian 4 bytes are ``42ad8c69``,
#: which the negotiation fixtures encode as the ``a1`` timestamp.
FROZEN_TIME = 1770827074


#: POSIX timezone the frozen_time fixture pins for the stage-5 confer, so the encrypted
#: confer fixture is reproducible regardless of the host's actual timezone.
FROZEN_TZ = "EST5EDT,M3.2.0,M11.1.0"


@pytest.fixture
def frozen_time():
    """Pin ``time.time()`` and the local timezone so negotiation/confer frames are stable.

    Devices stamp each negotiation and session command with the live time, and the
    stage-5 confer also carries the local POSIX timezone, so the on-wire bytes vary run
    to run and host to host; pinning both makes the expected fixtures stable (and the
    encrypted frames reproducible). Only ``time.time`` is frozen for the clock -- asyncio
    scheduling uses the monotonic loop clock, so retry/timeout timing is unaffected.
    """
    with (
        mock.patch("time.time", return_value=FROZEN_TIME),
        mock.patch(
            "SolixBLE.device.SolixBLEDevice._local_posix_tz",
            return_value=FROZEN_TZ,
        ),
    ):
        yield
