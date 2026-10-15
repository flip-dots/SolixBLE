"""Tests for routing received frames by their decoded header.

.. moduleauthor:: kb1ibt
"""

import asyncio
import logging

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from SolixBLE import C300, C1000G2, PrimeCharger160w, Solarbank2
from SolixBLE.constructs import Packet, Parameters
from tests.const import (
    MOCK_BLE_DEVICE,
    NEGOTIATION_RESPONSES_PRIME,
    NEGOTIATION_RESPONSES_SOLIX,
    SOLARBANK2_CLEAR_TELEMETRY,
    SOLARBANK2_SERIAL,
)
from tests.helpers import MockDevice, install_session_keys

SECRET = bytes(range(32))
STATUS_CONFIRM = 0x09
CONFIRMATION_WINDOW = 30

# A 4900 01 on 03000f and a c900 on 03010f carrying the "c1000g2" telemetry
# from tests/test_devices.py, both under the C1000 telemetry secret
C1000G2_SECRET = bytes.fromhex(
    "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
)
C1000G2_SERIAL = b"APCDK961F37400290"
C1000G2_STATUS_ONLY = "ff091a0003000f4900a451c312c33d39d6d8aa4c1e080c2331aa"
C1000G2_C900 = (
    "ff092b0103010fc90011224e04412b2fafda5bef3c3e2b9f8b6e54f1a26604abd9767926af3e"
    "3916b42c4c1123e96abb2e8b8de6c51194a732957b2a20914d578c15b5474dca0af68aa31ecf"
    "1407b6d598a1e0f392388b09c3f33beff099ab21db546fb84888da68b07ba1feb33d613ac06f"
    "323d2a078c76683d09a57e18276cba0ef0cc7b04327353a05ca10a0a0acf40257c3531ffbe00"
    "444cb5887fc6629c541bbf071c50e70b78d5e7a7d4018faee05c941ee95c73afc832b038df61"
    "d02aa25b1cff15bd031289a8ffcc701a779c15d42d97a4c66f0a85ae90fd16e0fa806fa2470e"
    "9a67189c63ca93cd948a6da6578d91d61acc94399fd4b4af041007302ade58ea6112444e6a49"
    "52306a267e7a79706ca3c1c00700537f81f4044d11c36b1be33b721d8d09735c29"
)


@pytest.mark.asyncio
async def test_grant_pattern_reaches_negotiation(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A ``4827`` pushed on ``030101`` reaches the negotiation's path."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        mock_bluetooth.check_assertions()

        # A device-initiated 4827 under the session key, here asking for the
        # button (status 09, a 30 s window)
        grant = Packet.build(
            {
                "pattern": bytes.fromhex("030101"),
                "cmd": bytes.fromhex("4827"),
                "payload_bytes": device._encrypt_payload(bytes.fromhex("09a1021e00")),  # noqa: SLF001
            },
        )
        await mock_bluetooth.send_data([grant])

    assert device.announcement is not None
    assert device.announcement.registration_status == STATUS_CONFIRM
    assert device.announcement.confirmation_window == CONFIRMATION_WINDOW


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
        install_session_keys(device, SECRET)
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
        install_session_keys(device, SECRET)
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
@pytest.mark.parametrize(
    ("pattern", "cmd", "resolves"),
    [
        pytest.param("03010f", "c840", True, id="fragmented_encrypted"),
        pytest.param("03010f", "4840", True, id="unfragmented_encrypted"),
        pytest.param("03010f", "0840", True, id="clear"),
        pytest.param("03000f", "4840", True, id="other_composer"),
        pytest.param("03010f", "4841", False, id="other_msgtype"),
        pytest.param("030111", "4840", False, id="other_channel"),
    ],
)
async def test_future_matches_channel_and_msgtype(  # noqa: PLR0913, PLR0917
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    pattern: str,
    cmd: str,
    resolves: bool,  # noqa: FBT001
) -> None:
    """A reply future waits for a channel and msgtype, whatever the flags."""
    device = C300(MOCK_BLE_DEVICE)
    plaintext = bytes.fromhex("00a10101")
    flags = bytes.fromhex(cmd)[0]
    payload = (
        AES.new(SECRET[:16], AES.MODE_CBC, iv=SECRET[16:]).encrypt(pad(plaintext, 16))
        if flags & 0x40
        else plaintext
    )
    # A 0x80 frame opens its payload with index << 4 | total; one fragment is 11
    fragment = b"\x11" if flags & 0x80 else b""
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
        install_session_keys(device, SECRET)

        # Registered the way get_status_update() listens for its reply
        future = asyncio.get_running_loop().create_future()
        device._register_future(  # noqa: SLF001
            future,
            bytes.fromhex("03010f"),
            bytes.fromhex("c840"),
        )
        await mock_bluetooth.send_data([frame])

    assert future.done() is resolves
    if resolves:
        assert future.result() == plaintext


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


@pytest.mark.asyncio
async def test_snapshot_messages_are_stored_separately_from_telemetry() -> None:
    """A snapshot command is dispatched and stored apart from the telemetry stream."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    device._SNAPSHOT_COMMANDS = ("4a00",)  # noqa: SLF001

    await device._process_session(  # noqa: SLF001
        bytes.fromhex("4a00"),
        bytes.fromhex("b0020101"),
        encrypted=False,
    )

    assert device._snapshot is not None  # noqa: SLF001
    assert device._data is None  # noqa: SLF001
    assert device._snapshot["b0"].value_legacy[1:].hex() == "01"  # noqa: SLF001


@pytest.mark.asyncio
async def test_status_only_reply_keeps_snapshot(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A bare status reply on a snapshot command leaves the stored snapshot."""
    device = C300(MOCK_BLE_DEVICE)
    device._SNAPSHOT_COMMANDS = ("4a00",)  # noqa: SLF001
    frames = [
        Packet.build(
            {
                "pattern": bytes.fromhex("03010f"),
                "cmd": bytes.fromhex("0a00"),
                "payload_bytes": bytes.fromhex(payload),
            },
        )
        for payload in ("b0020101", "01")
    ]

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        await mock_bluetooth.send_data(frames)

    assert device._snapshot is not None  # noqa: SLF001
    assert device._snapshot["b0"].value_legacy[1:].hex() == "01"  # noqa: SLF001


@pytest.mark.asyncio
async def test_status_only_reply_never_resolves_a_waiter(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A status update in flight gets the c900 after a 4900 01, not the 01."""
    device = C1000G2(MOCK_BLE_DEVICE)

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        install_session_keys(device, C1000G2_SECRET)

        # Listening the way get_status_update() does for its reply
        reply = asyncio.create_task(
            device._listen_for_packet(  # noqa: SLF001
                bytes.fromhex("03010f"),
                bytes.fromhex("c900"),
            ),
        )
        await asyncio.sleep(0)
        await mock_bluetooth.send_data(
            [bytes.fromhex(C1000G2_STATUS_ONLY), bytes.fromhex(C1000G2_C900)],
        )
        payload = await reply

    assert payload is not None
    parameters = Parameters.parse(payload)
    assert parameters.status == 0
    assert C1000G2_SERIAL in parameters["a2"].value_legacy
