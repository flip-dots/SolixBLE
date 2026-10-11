"""Tests for routing received frames by their decoded header.

.. moduleauthor:: kb1ibt
"""

import asyncio
import logging

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from SolixBLE import C300, PrimeCharger160w, Solarbank2
from SolixBLE.constructs import Packet
from tests.const import (
    MOCK_BLE_DEVICE,
    NEGOTIATION_RESPONSES_PRIME,
    NEGOTIATION_RESPONSES_SOLIX,
    SOLARBANK2_CLEAR_TELEMETRY,
    SOLARBANK2_SERIAL,
)
from tests.helpers import MockDevice

SECRET = bytes(range(32))


@pytest.mark.asyncio
async def test_grant_pattern_reaches_negotiation(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A ``4827`` pushed on ``030101`` is handled as the negotiation's ``4827``."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    requests = list(NEGOTIATION_RESPONSES_PRIME.items())
    registration = next(
        response
        for _, responses in requests
        for response in responses
        if Packet.parse(bytes.fromhex(response)).cmd.hex() == "4827"
    )
    grant = Packet.build(
        {
            "pattern": bytes.fromhex("030101"),
            "cmd": bytes.fromhex("4827"),
            "payload_bytes": Packet.parse(bytes.fromhex(registration)).payload_bytes,
        },
    )

    async with MockDevice() as mock_bluetooth:
        for expected, responses in requests:
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        mock_bluetooth.check_assertions()

        # The post-registration requests are sent again for the grant
        for expected, _ in requests[-2:]:
            mock_bluetooth.expect_ordered(bytes.fromhex(expected), [])
        await mock_bluetooth.send_data([grant])
        await asyncio.sleep(1)
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
async def test_unhandled_channel_is_logged_not_routed(
    caplog: pytest.LogCaptureFixture,
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A frame on a channel without a handler is logged and dropped."""
    device = C300(MOCK_BLE_DEVICE)
    frame = Packet.build(
        {
            "pattern": bytes.fromhex("030002"),
            "cmd": bytes.fromhex("4830"),
            "payload_bytes": bytes.fromhex("00a10106"),
        },
    )

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()

        with caplog.at_level(logging.DEBUG):
            await mock_bluetooth.send_data([frame])

    assert "Unhandled channel 02 (composer 00), cmd 4830" in caplog.text
    assert "Failed to process" not in caplog.text
    assert device._data is None  # noqa: SLF001


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pattern", "cmd", "encrypted"),
    [
        pytest.param("03010f", "0300", False, id="clear_flag_not_decrypted"),
        pytest.param("03010f", "4300", True, id="encrypted_flag_decrypted"),
        pytest.param("03000f", "0300", False, id="composer_00_session_reply"),
        pytest.param("030111", "4300", True, id="app_channel"),
        pytest.param("03010f", "c402", True, id="single_fragment"),
        pytest.param("03010f", "8402", False, id="clear_fragment"),
    ],
)
async def test_flag_decides_decryption_and_reassembly(  # noqa: PLR0913, PLR0917
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    pattern: str,
    cmd: str,
    encrypted: bool,  # noqa: FBT001
) -> None:
    """Session frames decrypt iff ``0x40`` is set and reassemble iff ``0x80`` is."""
    device = C300(MOCK_BLE_DEVICE)
    plaintext = bytes.fromhex("00a10131")
    payload = (
        AES.new(SECRET[:16], AES.MODE_CBC, iv=SECRET[16:]).encrypt(pad(plaintext, 16))
        if encrypted
        else plaintext
    )
    # A 0x80 frame opens its payload with index << 4 | total; one fragment is 11
    fragment = b"\x11" if bytes.fromhex(cmd)[0] & 0x80 else b""
    frame = Packet.build(
        {
            "pattern": bytes.fromhex(pattern),
            "cmd": bytes.fromhex(cmd),
            "payload_bytes": fragment + payload,
        },
    )

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        device._shared_secret = SECRET  # noqa: SLF001
        await mock_bluetooth.send_data([frame])

    assert device._data is not None  # noqa: SLF001
    assert device._data["a1"].value_legacy.hex() == "31"  # noqa: SLF001


@pytest.mark.asyncio
async def test_two_futures_one_decrypt(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """Every future registered on a frame gets the same plaintext."""
    device = C300(MOCK_BLE_DEVICE)
    plaintext = bytes.fromhex("00a10101")
    ciphertext = AES.new(SECRET[:16], AES.MODE_CBC, iv=SECRET[16:]).encrypt(
        pad(plaintext, 16),
    )
    # c840 carries the fragment flag, so the payload opens with index 1 / total 1
    frame = Packet.build(
        {
            "pattern": bytes.fromhex("03010f"),
            "cmd": bytes.fromhex("c840"),
            "payload_bytes": b"\x11" + ciphertext,
        },
    )

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        device._shared_secret = SECRET  # noqa: SLF001
        loop = asyncio.get_running_loop()
        futures = [loop.create_future(), loop.create_future()]
        for future in futures:
            device._register_future(  # noqa: SLF001
                future,
                bytes.fromhex("03010f"),
                bytes.fromhex("c840"),
            )
        await mock_bluetooth.send_data([frame])

    assert [future.result() for future in futures] == [plaintext, plaintext]


@pytest.mark.asyncio
async def test_clear_fragmented_telemetry_is_telemetry(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A clear ``8405`` in three fragments reassembles and reads as ``c405`` would."""
    device = Solarbank2(MOCK_BLE_DEVICE)

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        await mock_bluetooth.send_data(
            [bytes.fromhex(frame) for frame in SOLARBANK2_CLEAR_TELEMETRY],
        )

    assert device._data is not None  # noqa: SLF001
    assert device._data["a2"].value_legacy[1:].decode() == SOLARBANK2_SERIAL  # noqa: SLF001
