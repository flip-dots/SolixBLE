"""Tests for the interactive console.

.. moduleauthor:: kb1ibt
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from bleak.backends.device import BLEDevice

from SolixBLE import C300, DisplayTimeout
from SolixBLE.advertisement import ANKER_COMPANY_ID
from SolixBLE.cli import (
    Console,
    Frame,
    FrameLog,
    PythonConsole,
    coerce_arguments,
    split_args,
)
from tests.const import MOCK_BLE_DEVICE
from tests.helpers import (
    MockDevice,
    connect_console,
    console_seeing_c300,
    make_advertisement,
    scanner_reporting,
)

#: A2345 manufacturer record: MAC, product type b402, sku QJB, capability 04.
A2345_RECORD = "01aa12deadb34500b402514a4204"
OWNER = "owner-token"
OTHER_TOKEN = "other-token"  # noqa: S105  # a client id, not a secret
#: The C300 recorded flow's timestamp, as fake_time pins it.
TIMESTAMP = "42ad8c69"
#: How a frame line names the mock device.
DEVICE_TAG = f"[{MOCK_BLE_DEVICE.name}] "


@pytest.mark.asyncio
async def test_scan_lists_anker_devices_only() -> None:
    """``scan`` tabulates Anker adverts with their record and factory class."""
    anker = BLEDevice("AA:BB:CC:DD:EE:01", "A2345_B345", None)
    other = BLEDevice("AA:BB:CC:DD:EE:02", "headphones", None)
    results = [
        (
            anker,
            make_advertisement(
                manufacturer_data={ANKER_COMPANY_ID: bytes.fromhex(A2345_RECORD)},
                local_name="A2345_B345",
            ),
        ),
        (other, make_advertisement(local_name="headphones")),
    ]
    console = Console(scanner=scanner_reporting(results), reply_wait=0)

    lines = await console.run_line("scan 0")

    assert lines[0].split() == [
        "#",
        "address",
        "name",
        "mac",
        "type",
        "sku",
        "cap",
        "class",
        "rssi",
    ]
    assert lines[1].split() == [
        "0",
        "AA:BB:CC:DD:EE:01",
        "A2345_B345",
        "aa12deadb345",
        "b402",
        "QJB",
        "04",
        "PrimeCharger250w",
        "-60",
    ]
    assert len(lines) == len(("header", "anker"))


@pytest.mark.asyncio
async def test_connect_records_both_directions(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``connect`` negotiates and every frame is kept as cleartext with its tags."""
    console = console_seeing_c300(token=OWNER)
    async with MockDevice() as mock_bluetooth:
        lines = await connect_console(console, mock_bluetooth)
        mock_bluetooth.check_assertions()
        frames = await console.run_line("frames 50")
        devices = await console.run_line("devices")
        await console.close()

    assert lines[:2] == ["[0] connected", "class       C300"]
    assert "outer       plain  path ecdh" in lines
    assert console.devices == []
    assert devices == [
        f"*[0] {MOCK_BLE_DEVICE.name} {MOCK_BLE_DEVICE.address} C300 negotiated",
    ]
    fields = [line.split(DEVICE_TAG, 1)[1].split() for line in frames]
    assert fields[0][:3] == ["out", "030001", "0001"]
    assert ["in", "030001", "0801", "00a10101", "status=00", "a1=01"] in fields
    keyed = [field for field in fields if field[2] == "4022"]
    assert keyed
    assert keyed[0][3] != "undecryptable"


@pytest.mark.asyncio
async def test_token_is_the_client_token(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """The console's token is sent as the client token, and ``token`` changes it."""
    console = console_seeing_c300(token=OWNER)
    async with MockDevice() as mock_bluetooth:
        await connect_console(console, mock_bluetooth)
        device = console.current
        assert device is not None
        assert device._client_token == OWNER  # noqa: SLF001
        assert await console.run_line(f"token {OTHER_TOKEN}") == [
            f"token {OTHER_TOKEN}",
        ]
        assert device._client_token == OTHER_TOKEN  # noqa: SLF001
        await console.close()


@pytest.mark.asyncio
async def test_send_resolves_constants_and_appends_the_trailer(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``send`` takes a PARAMETERS_* name and adds the typed timestamp trailer."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await connect_console(console, mock_bluetooth)
        mock_bluetooth.expect_ordered()
        lines = await console.run_line("send 404a PARAMETERS_ON")
        await console.close()

    sent = lines[0].split(DEVICE_TAG, 1)[1].split()
    assert sent[:3] == ["out", "03000f", "404a"]
    assert sent[3].endswith("fe0503" + TIMESTAMP)


@pytest.mark.asyncio
async def test_nego_sends_on_the_negotiation_pattern(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``nego`` sends as typed on ``030001``; ``@ts`` is the live timestamp."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await connect_console(console, mock_bluetooth)
        mock_bluetooth.expect_ordered()
        lines = await console.run_line("nego 4027 {'a1': {'value': '@ts'}}")
        await console.close()

    assert lines[0].split(DEVICE_TAG, 1)[1].split()[:4] == [
        "out",
        "030001",
        "4027",
        "a104" + TIMESTAMP,
    ]


@pytest.mark.asyncio
async def test_factory_channel_needs_the_flag() -> None:
    """``packet`` refuses channel ``0c`` unless the console allows it."""
    refused = await Console(reply_wait=0).run_line("packet 03000c 4001 {}")
    allowed = await Console(allow_factory_channel=True, reply_wait=0).run_line(
        "packet 03000c 4001 {}",
    )

    assert refused == [
        "! channel 0c (factory) is refused; start with --allow-factory-channel",
    ]
    assert allowed == ["! no current device; connect or use one"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("line", "output"),
    [
        pytest.param(
            "bogus",
            ["! unknown command 'bogus'; help lists them"],
            id="unknown",
        ),
        pytest.param("call", ["! call <method> [args]"], id="usage"),
        pytest.param(
            "info",
            ["! no current device; connect or use one"],
            id="no_device",
        ),
        pytest.param("connect 3", ["! 3 was not seen advertising"], id="not_seen"),
        pytest.param("", [], id="empty"),
    ],
)
async def test_command_errors(
    line: str,
    output: list[str],
    fast_sleep: None,  # noqa: ARG001
) -> None:
    """A command that cannot run says why and leaves the console running."""
    console = Console(scanner=scanner_reporting([]), reply_wait=0)
    assert await console.run_line(line) == output
    assert not console.finished


def test_capture_appends(tmp_path: Path) -> None:
    """The capture file is appended to, never truncated, one dated line a frame."""
    path = tmp_path / "capture.log"
    path.write_text("earlier\n")
    frames = FrameLog()
    frames.capture(path)
    frames.record(
        Frame(
            datetime(2026, 10, 5, 12, 0, 0).astimezone(),
            "device",
            "in",
            bytes.fromhex("030001"),
            bytes.fromhex("0801"),
            bytes.fromhex("00a10101"),
            bytes.fromhex("ff090e00030001080100a1010152"),
        ),
    )
    frames.capture(None)

    assert path.read_text().splitlines() == [
        "earlier",
        (
            "2026-10-05 12:00:00.000 [device] in  030001 0801 00a10101"
            "  status=00 a1=01 raw=ff090e00030001080100a1010152"
        ),
    ]


def test_split_args_keeps_literals_whole() -> None:
    """Spaces inside brackets and quotes don't split a command line."""
    assert split_args("send 4001 {'a1': {'value': '21'}} {'seconds': 3}") == [
        "send",
        "4001",
        "{'a1': {'value': '21'}}",
        "{'seconds': 3}",
    ]


def test_enum_arguments_by_name() -> None:
    """A string argument becomes the enum member the method's parameter takes."""
    device = C300(MOCK_BLE_DEVICE)
    assert coerce_arguments(device.set_display_timeout, ["S30"]) == [
        DisplayTimeout.S30,
    ]


@pytest.mark.asyncio
async def test_python_console(capsys: pytest.CaptureFixture[str]) -> None:
    """Statements run on the loop, expressions print, ``await`` works at the top."""
    python = PythonConsole({"asyncio": asyncio})

    await python.push("x = 6 * 7")
    await python.push("x")
    await python.push("await asyncio.sleep(0)")
    await python.push("def five():")
    assert python.prompt == "... "
    await python.push("    return 5")
    await python.push("")
    await python.push("five()")
    await python.push("1 / 0")

    captured = capsys.readouterr()
    assert captured.out == "42\n5\n"
    assert "ZeroDivisionError" in captured.err
    assert python.prompt == ">>> "
