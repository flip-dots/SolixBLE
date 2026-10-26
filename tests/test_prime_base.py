"""Tests for the commands, keep-alive and constructs shared by the Prime devices.

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE.const import DEFAULT_METADATA_STRING
from SolixBLE.constructs import DISPLAY, FIRMWARE_UPDATE, Packet, Parameters
from SolixBLE.prime_device import (
    CMD_CLOCK_FORMAT,
    CMD_DISPLAY_TIMEOUT,
    CMD_PORT_SCHEDULE,
    KEEP_ALIVE_INTERVAL,
    PARAMETERS_SCHEDULE,
    SCHEDULE_ON_TIME,
    PrimeDevice,
)
from SolixBLE.states import ClockTheme, PortSchedule
from tests.const import MOCK_BLE_DEVICE, NEGOTIATION_RESPONSES_PRIME
from tests.helpers import MockDevice

#: The typed timestamp trailer every command ends with, under fake_time.
TIMESTAMP_TRAILER = "fe0503ef79b569"

#: The firmware update state with no update running, and one at 42 %
#: (the A2345's b2, the A91B2's af).
FIRMWARE_IDLE = "0000"
FIRMWARE_UPDATING = "012a"
UPDATE_PROGRESS = 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "arguments", "msgtype", "payload"),
    [
        pytest.param(
            "_turn_port",
            {"port": 2, "on": False},
            0x207,
            "a10121a2020102a3020100",
            id="4207_port_2_off",
        ),
        pytest.param(
            "_turn_port",
            {"port": 0, "on": True},
            0x207,
            "a10121a2020100a3020101",
            id="4207_port_0_on",
        ),
        # prime.md: 5 min = 2c010000, armed
        pytest.param(
            "_set_port_timer",
            {"port": 0, "seconds": 300},
            0x209,
            "a10121a2020100a30604012c010000",
            id="4209_port_0_5_min",
        ),
        pytest.param(
            "_set_port_timer",
            {"port": 3, "seconds": 0},
            0x209,
            "a10121a2020103a306040000000000",
            id="4209_disarm",
        ),
        # prime.md 4308 example: port 2, on-time, enabled, 12:00, once
        pytest.param(
            "_send_command",
            {
                "message": CMD_PORT_SCHEDULE,
                "parameters": PARAMETERS_SCHEDULE,
                "port": 2,
                "time": SCHEDULE_ON_TIME,
                "enabled": True,
                "hour": 12,
                "minute": 0,
                "weekdays": frozenset(),
            },
            0x208,
            "a10121a2020102a3020101a40503010c0000",
            id="4208_port_2_on_time_12_00_once",
        ),
        pytest.param(
            "_send_setting",
            {"message": CMD_DISPLAY_TIMEOUT, "setting": 1},
            0x203,
            "a10121a2020101",
            id="4203_timeout_30_s",
        ),
        pytest.param(
            "_send_setting",
            {"message": CMD_CLOCK_FORMAT, "setting": 1},
            0x210,
            "a10121a2020101",
            id="4210_24_h",
        ),
    ],
)
async def test_port_and_setting_payloads(  # noqa: PLR0913, PLR0917
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    method: str,
    arguments: dict[str, object],
    msgtype: int,
    payload: str,
) -> None:
    """A port or settings command goes out as the captured frame's payload."""
    device = PrimeDevice(MOCK_BLE_DEVICE)

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        mock_bluetooth.expect_ordered(None)
        await getattr(device, method)(**arguments)

    packet = Packet.parse(mock_bluetooth.writes[-1])
    assert (packet.encrypted, packet.msgtype) == (True, msgtype)
    sent = device._decrypt_payload(packet.payload_bytes).hex()  # noqa: SLF001
    assert sent == payload + TIMESTAMP_TRAILER


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("snapshot_commands", "msgtypes"),
    [
        pytest.param((0xA00,), [0x200, 0x20B], id="snapshot_model"),
        pytest.param((), [0x20B], id="no_snapshot_model"),
    ],
)
async def test_keep_alive_requests_snapshot_first(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    snapshot_commands: tuple[int, ...],
    msgtypes: list[int],
) -> None:
    """A model with a snapshot asks for one before re-arming the stream."""
    device = PrimeDevice(MOCK_BLE_DEVICE)

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()

        # The connect's own keep-alive task ends at once with no interval set
        assert device._keep_alive_task is not None  # noqa: SLF001
        await device._keep_alive_task  # noqa: SLF001

        sent_before = len(mock_bluetooth.writes)
        device._KEEP_ALIVE_INTERVAL = KEEP_ALIVE_INTERVAL  # noqa: SLF001
        device._SNAPSHOT_COMMANDS = snapshot_commands  # noqa: SLF001
        for _ in msgtypes:
            mock_bluetooth.expect_ordered(None)
        interval = await device._keep_alive()  # noqa: SLF001

    sent = [Packet.parse(write) for write in mock_bluetooth.writes[sent_before:]]
    assert interval == KEEP_ALIVE_INTERVAL
    assert [(packet.encrypted, packet.msgtype) for packet in sent] == [
        (True, msgtype) for msgtype in msgtypes
    ]
    for packet in sent:
        plaintext = device._decrypt_payload(packet.payload_bytes).hex()  # noqa: SLF001
        assert plaintext == "a10121" + TIMESTAMP_TRAILER


@pytest.mark.parametrize(
    ("value", "updating", "progress"),
    [
        pytest.param(FIRMWARE_IDLE, False, 0, id="idle"),
        pytest.param(FIRMWARE_UPDATING, True, UPDATE_PROGRESS, id="updating"),
    ],
)
def test_firmware_update(value: str, updating: bool, progress: int) -> None:  # noqa: FBT001
    """The firmware update pair parses and rebuilds."""
    state = FIRMWARE_UPDATE.parse(bytes.fromhex(value))
    assert (state.updating, state.progress) == (updating, progress)
    assert FIRMWARE_UPDATE.build(state).hex() == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("snapshot", "version"),
    [
        pytest.param("a203024408", "2.1.1.6", id="a2345_v2116"),
        pytest.param("a203026404", "1.1.2.4", id="a91b2_v1124"),
        pytest.param("b0020101", DEFAULT_METADATA_STRING, id="absent"),
    ],
)
async def test_snapshot_version(snapshot: str, version: str) -> None:
    """A snapshot's decimal-digit firmware version reads as its four parts."""
    device = PrimeDevice(MOCK_BLE_DEVICE)
    await device._process_snapshot(Parameters.parse(bytes.fromhex(snapshot)))  # noqa: SLF001

    assert device._snapshot_version("a2") == version  # noqa: SLF001


@pytest.mark.asyncio
async def test_send_schedule(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A schedule goes out as two 4208s, on-time then off-time.

    The on-time is prime.md's captured 4208 (port 2, enabled, 12:00, once);
    an off-time never set (None) goes out switched off.
    """
    device = PrimeDevice(MOCK_BLE_DEVICE)
    schedule = PortSchedule(
        on_time_enabled=True,
        on_time_hour=12,
        on_time_minute=0,
        on_time_weekdays=frozenset(),
        off_time_enabled=None,
        off_time_hour=12,
        off_time_minute=0,
        off_time_weekdays=frozenset(),
    )

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        mock_bluetooth.expect_ordered(None)
        mock_bluetooth.expect_ordered(None)
        await device._send_schedule(2, schedule)  # noqa: SLF001

    sent = [Packet.parse(write) for write in mock_bluetooth.writes[-2:]]
    assert [(packet.encrypted, packet.msgtype) for packet in sent] == [
        (True, 0x208),
        (True, 0x208),
    ]
    assert [
        device._decrypt_payload(packet.payload_bytes).hex()  # noqa: SLF001
        for packet in sent
    ] == [
        "a10121a2020102a3020101a40503010c0000" + TIMESTAMP_TRAILER,
        "a10121a2020102a3020100a40503000c0000" + TIMESTAMP_TRAILER,
    ]


@pytest.mark.parametrize(
    ("value", "on", "theme"),
    [
        pytest.param("83", True, 3, id="a2345_clock_on_network_theme"),
        pytest.param("02", False, 2, id="a2345_clock_off_theme_3"),
        pytest.param("82", True, 2, id="a91b2_clock_on_theme_3"),
    ],
)
def test_display(value: str, on: bool, theme: int) -> None:  # noqa: FBT001
    """The display byte reads as the clock's on/off state and theme index."""
    display = DISPLAY.parse(bytes.fromhex(value))
    assert (display.on, display.theme) == (on, theme)
    assert DISPLAY.build(display).hex() == value


@pytest.mark.parametrize(
    ("value", "theme"),
    [
        pytest.param("80", ClockTheme.THEME_1, id="theme_1"),
        pytest.param("81", ClockTheme.THEME_2, id="theme_2"),
        pytest.param("82", ClockTheme.THEME_3, id="theme_3"),
        pytest.param("83", ClockTheme.CATALOG, id="catalog"),
        pytest.param("85", ClockTheme.CUSTOM, id="custom"),
    ],
)
def test_clock_theme(value: str, theme: ClockTheme) -> None:
    """The display byte's theme index is the ClockTheme value (4205 a2 0x80 | index)."""
    display = DISPLAY.parse(bytes.fromhex(value))
    assert ClockTheme(display.theme) is theme
    assert DISPLAY.build({"on": True, "theme": theme.value}).hex() == value
