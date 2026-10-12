"""Tests for the interactive console.

.. moduleauthor:: kb1ibt
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest
from bleak.backends.device import BLEDevice

from SolixBLE import C300, DisplayTimeout
from SolixBLE.advertisement import ANKER_COMPANY_ID
from SolixBLE.cli import (
    CAPTURE_NOTE,
    CONNECT_USAGE,
    CaptureHandler,
    Console,
    FrameLog,
    FrameTap,
    ManualSession,
    PythonConsole,
    coerce_arguments,
    configure_logging,
    new_frame,
    split_args,
)
from SolixBLE.const import LEGACY_SERVICE, SERVICE_2215, UUID_IDENTIFIER
from SolixBLE.constructs import Packet
from SolixBLE.device import SolixBLEDevice
from SolixBLE.protocols import EncryptedOuter, PlainOuter
from tests.const import (
    MOCK_BLE_DEVICE,
    NEGOTIATION_RESPONSES_PRIME,
    NEGOTIATION_RESPONSES_SOLIX,
)
from tests.helpers import (
    MockDevice,
    RecordingLink,
    connect_console,
    console_seeing_c300,
    make_advertisement,
    scanner_reporting,
)

#: A2345 manufacturer record: MAC, product type b402, sku QJB, capability 04.
A2345_RECORD = "01aa12deadb34500b402514a4204"
#: A91B2 record: capability byte present and clear.
A91B2_RECORD = "01aa12deadb1b200b4014a544200"
#: A1340 record (HaSolixBLE #48): on the 2215 transport.
A1340_RECORD = "01e8eeccc7011802010100000004"
#: F3800-shaped record: no capability byte.
F3800_RECORD = "01aabbccddeeff02b106373434"
#: A record version the library doesn't know.
UNKNOWN_RECORD = "03aabbccddeeff00b199"
OTHER_COMPANY_ID = 0x004C
OTHER_SERVICE = "0000fe2c-0000-1000-8000-00805f9b34fb"
OWNER = "owner-token"
OTHER_TOKEN = "other-token"  # noqa: S105  # a client id, not a secret
#: The C300 recorded flow's timestamp, as fake_time pins it.
TIMESTAMP = "42ad8c69"
#: The message of the failure logged in the capture test.
FAILURE = "link refused"
#: How a frame line names the mock device.
DEVICE_TAG = f"[{MOCK_BLE_DEVICE.name}] "


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "record", "transport"),
    [
        pytest.param(SERVICE_2215, A1340_RECORD, "2215", id="a1340"),
        pytest.param(LEGACY_SERVICE, "1fa63fcceee8", "legacy", id="legacy_767"),
    ],
)
async def test_device_without_a_class_names_its_transport(
    service: str,
    record: str,
    transport: str,
) -> None:
    """A device no class speaks shows its transport in the scan and on connect."""
    device = BLEDevice("AA:BB:CC:DD:EE:01", None, None)
    advertisement = make_advertisement(
        manufacturer_data={ANKER_COMPANY_ID: bytes.fromhex(record)},
        service_uuids=[service],
    )
    console = Console(
        scanner=scanner_reporting([(device, advertisement)]),
        reply_wait=0,
    )

    lines = await console.run_line("scan 0")
    connect = await console.run_line("connect 0")

    assert lines[1].split()[-2] == f"({transport})"
    assert connect == [
        f"! no class speaks the {transport} transport yet; name one to try",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "options", "opening"),
    [
        pytest.param(A2345_RECORD, "", "4001", id="capability_04_encrypted"),
        pytest.param(A2345_RECORD, "--no-advert", "0001", id="no_advert_class_default"),
        pytest.param(A91B2_RECORD, "--outer encrypted", "4001", id="forced_encrypted"),
        pytest.param(A2345_RECORD, "--outer plain", "0001", id="forced_plain"),
    ],
)
async def test_connect_options_choose_the_opening(  # noqa: PLR0913, PLR0917
    record: str,
    options: str,
    opening: str,
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``--no-advert`` drops the capability hint; ``--outer`` overrides it."""
    advertisement = make_advertisement(
        manufacturer_data={ANKER_COMPANY_ID: bytes.fromhex(record)},
        service_uuids=[UUID_IDENTIFIER],
    )
    console = Console(
        scanner=scanner_reporting([(MOCK_BLE_DEVICE, advertisement)]),
        reply_wait=0,
    )
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.refuse_after()
        mock_bluetooth.refuse_after()
        await console.run_line("scan 0")
        lines = await console.run_line(f"connect 0 C300 {options}")
        await console.close()

    assert lines[0].startswith("! could not connect")
    assert Packet.parse(mock_bluetooth.writes[0]).cmd.hex() == opening


@pytest.mark.asyncio
async def test_connect_outer_plain_is_not_reopened_encrypted(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A refused ``0001`` under ``--outer plain`` ends the connect."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.refuse_after()
        await console.run_line("scan 0")
        lines = await console.run_line("connect 0 C300 --outer plain")
        mock_bluetooth.check_assertions()
        await console.close()

    assert lines[0].startswith("! could not connect")
    assert [Packet.parse(write).cmd.hex() for write in mock_bluetooth.writes] == [
        "0001",
    ]


@pytest.mark.asyncio
async def test_connect_outer_needs_a_known_outer() -> None:
    """``--outer`` takes plain or encrypted."""
    console = Console(reply_wait=0)
    assert await console.run_line("connect 0 --outer gcm") == [f"! {CONNECT_USAGE}"]


@pytest.mark.asyncio
async def test_connect_no_register_withholds_4027(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``--no-register`` negotiates the encrypted outer through ``4022`` only."""
    console = Console(
        scanner=scanner_reporting(
            [(MOCK_BLE_DEVICE, make_advertisement(service_uuids=[UUID_IDENTIFIER]))],
        ),
        reply_wait=0,
    )
    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            if Packet.parse(bytes.fromhex(expected)).cmd.hex() != "4027":
                mock_bluetooth.expect_ordered(
                    bytes.fromhex(expected),
                    [bytes.fromhex(response) for response in responses],
                )
        await console.run_line("scan 0")
        lines = await console.run_line("connect 0 PrimeCharger160w --no-register")
        mock_bluetooth.check_assertions()
        await console.close()

    assert lines[0] == "[0] connected"
    assert "4027" not in [
        Packet.parse(write).cmd.hex() for write in mock_bluetooth.writes
    ]


@pytest.mark.asyncio
async def test_connect_manual_sends_nothing_and_never_negotiates(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``--manual`` connects and subscribes but sends no negotiation frame."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await console.run_line("scan 0")
        lines = await console.run_line("connect 0 C300 --manual")
        devices = await console.run_line("devices")
        await console.close()

    assert lines[0] == "[0] connected"
    assert mock_bluetooth.writes == []
    assert devices == [
        f"*[0] {MOCK_BLE_DEVICE.name} {MOCK_BLE_DEVICE.address} C300 connected",
    ]


@pytest.mark.asyncio
async def test_manual_nego_unflagged_frame_goes_in_clear(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """An unflagged ``nego`` frame under ``--manual`` is sent exactly as typed."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.expect_ordered()
        await console.run_line("scan 0")
        await console.run_line("connect 0 C300 --manual")
        lines = await console.run_line("nego 0027 {'a1': {'value': '21'}}")
        await console.close()

    sent = Packet.parse(mock_bluetooth.writes[-1])
    assert DEVICE_TAG in lines[0]
    assert sent.cmd.hex() == "0027"
    assert sent.payload_bytes.hex() == "a10121"


@pytest.mark.asyncio
async def test_manual_nego_flagged_frame_uses_the_static_key(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A flagged ``nego`` frame under ``--manual`` uses the outer's static key."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.expect_ordered()
        await console.run_line("scan 0")
        await console.run_line("connect 0 C300 --outer encrypted --manual")
        await console.run_line("nego 4027 {'a1': {'value': '21'}}")
        await console.close()

    sealed = Packet.parse(mock_bluetooth.writes[-1]).payload_bytes
    assert sealed.hex() != "a10121"
    assert EncryptedOuter().decrypt(bytes(sealed), None).hex() == "a10121"


@pytest.mark.asyncio
async def test_manual_session_notes_a_reply_but_answers_nothing() -> None:
    """A manual session marks a reply received but sends nothing back."""
    link = RecordingLink()
    session = ManualSession(PlainOuter(), link)

    await session.on_plaintext(
        bytes.fromhex("030001"),
        bytes.fromhex("0801"),
        bytes.fromhex("00a10101"),
    )

    assert session.replied is True
    assert link.sent == []


def test_manual_session_never_authorizes() -> None:
    """A manual session stays unauthorized even after a session push."""
    session = ManualSession(PlainOuter(), RecordingLink())

    session.on_session_push()

    assert session.authorized is False


@pytest.mark.asyncio
async def test_manual_negotiate_installs_a_manual_session_without_sending() -> None:
    """``--manual`` skips the negotiation loop and installs an unauthorized session."""
    tapped = type("Tapped", (FrameTap, SolixBLEDevice), {})
    device = tapped(MOCK_BLE_DEVICE)
    device.manual = True

    negotiated = await device._negotiate()  # noqa: SLF001

    assert negotiated is True
    assert isinstance(device._session, ManualSession)  # noqa: SLF001
    assert device._session.authorized is False  # noqa: SLF001


@pytest.mark.asyncio
@pytest.mark.parametrize("manual", [True, False], ids=["manual", "negotiated"])
async def test_manual_gates_the_models_connect_hooks(
    manual: bool,  # noqa: FBT001
) -> None:
    """``--manual`` skips post-connect, post-authorize and auto-reconnect."""
    tapped = type("Tapped", (FrameTap, SolixBLEDevice), {})
    device = tapped(MOCK_BLE_DEVICE)
    device.manual = manual

    with (
        mock.patch.object(
            SolixBLEDevice,
            "_post_connect",
            mock.AsyncMock(),
        ) as post_connect,
        mock.patch.object(
            SolixBLEDevice,
            "_post_authorize",
            mock.AsyncMock(),
        ) as post_authorize,
        mock.patch.object(
            SolixBLEDevice,
            "_auto_reconnect",
            mock.AsyncMock(),
        ) as auto_reconnect,
    ):
        await device._post_connect()  # noqa: SLF001
        await device._post_authorize()  # noqa: SLF001
        await device._auto_reconnect()  # noqa: SLF001

    assert post_connect.called is not manual
    assert post_authorize.called is not manual
    assert auto_reconnect.called is not manual


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
async def test_scan_raw_shows_the_advertisement_bytes() -> None:
    """``scan raw`` adds each record's bytes, flagging one that doesn't parse."""
    parsed = BLEDevice("AA:BB:CC:DD:EE:01", "Anker SOLIX F3800", None)
    unparsed = BLEDevice("AA:BB:CC:DD:EE:02", None, None)
    results = [
        (
            parsed,
            make_advertisement(
                manufacturer_data={ANKER_COMPANY_ID: bytes.fromhex(F3800_RECORD)},
                service_uuids=[UUID_IDENTIFIER],
            ),
        ),
        (
            unparsed,
            make_advertisement(
                manufacturer_data={
                    ANKER_COMPANY_ID: bytes.fromhex(UNKNOWN_RECORD),
                    OTHER_COMPANY_ID: bytes.fromhex("0215"),
                },
                service_data={OTHER_SERVICE: bytes.fromhex("01")},
            ),
        ),
    ]
    console = Console(scanner=scanner_reporting(results), reply_wait=0)

    lines = await console.run_line("scan 0 raw")

    assert lines[len(("header", "parsed", "unparsed")) :] == [
        f"0  ffff={F3800_RECORD}",
        f"0  services {UUID_IDENTIFIER}",
        f"1  ffff={UNKNOWN_RECORD} (unparsed)",
        f"1  mfr {OTHER_COMPANY_ID:04x}=0215",
        f"1  data {OTHER_SERVICE}=01",
    ]


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

    info = [line.split() for line in lines]
    assert info[:2] == [["[0]", "connected"], ["class", "C300"]]
    assert ["outer", "plain", "path", "ecdh"] in info
    assert ["encrypt_method", "0x44"] in info
    value_columns = {
        line.index(field[1]) for line, field in zip(lines[1:], info[1:], strict=True)
    }
    assert len(value_columns) == 1
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
async def test_nego_refuses_a_released_device(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``nego`` refuses a released device instead of sending on a dead link."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await connect_console(console, mock_bluetooth)
        await console.run_line("release")

        lines = await console.run_line("nego 4027 {'a1': {'value': '21'}}")
        await console.close()

    assert lines == [
        f"! [0] {MOCK_BLE_DEVICE.name} is down; reconnect 0 retakes it",
    ]


@pytest.mark.asyncio
async def test_release_then_reconnect_the_same_device(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """``release`` drops the link but keeps the device; ``reconnect`` retakes it."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await connect_console(console, mock_bluetooth)
        device = console.current
        assert device is not None

        released = await console.run_line("release")
        assert not device.connected
        listed = await console.run_line("devices")

        for expected, responses in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        reconnected = await console.run_line("reconnect")
        mock_bluetooth.check_assertions()
        await console.close()

    assert released == [f"released [0] {MOCK_BLE_DEVICE.name}; reconnect 0 retakes it"]
    assert listed[0].endswith("C300 down")
    assert reconnected[0] == "[0] reconnected"
    assert console.devices == []


@pytest.mark.asyncio
async def test_connect_after_release_takes_the_released_slot(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A device keeps one slot: connecting it again needs a release, then reuses it."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await connect_console(console, mock_bluetooth)
        while_connected = await console.run_line("connect 0 C300")
        await console.run_line("release")
        released_again = await console.run_line("release 0")
        reconnected = await connect_console(console, mock_bluetooth)
        mock_bluetooth.check_assertions()
        slots = len(console.devices)
        await console.close()

    assert while_connected == [
        f"! [0] is connected to {MOCK_BLE_DEVICE.address}; release it first",
    ]
    assert released_again == [f"[0] {MOCK_BLE_DEVICE.name} is already down"]
    assert reconnected[0] == "[0] connected"
    assert slots == 1


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
async def test_send_names_a_missing_constant(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A constant the model lacks is named as such, not parsed as a literal."""
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await connect_console(console, mock_bluetooth)
        lines = await console.run_line("send 4057 PARAMETERS_SUBSCRIBE")
        await console.close()

    assert lines == [
        "! C300 has no constant PARAMETERS_SUBSCRIBE; constants lists them",
    ]


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


@pytest.mark.asyncio
async def test_capture_warns_what_it_holds(tmp_path: Path) -> None:
    """Starting a capture says the file holds tokens and serials in clear."""
    path = tmp_path / "capture.txt"
    console = Console(reply_wait=0)

    started = await console.run_line(f"capture {path}")
    stopped = await console.run_line("capture off")

    assert started == [f"capturing to {path} (appending)", CAPTURE_NOTE]
    assert stopped == ["capture off"]


@pytest.mark.asyncio
async def test_capture_holds_the_session(
    tmp_path: Path,
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """Commands and their output are captured with the frames, each frame once."""
    path = tmp_path / "session.log"
    console = console_seeing_c300()
    async with MockDevice() as mock_bluetooth:
        await console.run_line(f"capture {path}")
        await connect_console(console, mock_bluetooth)
        mock_bluetooth.expect_ordered()
        await console.run_line("send 404a PARAMETERS_ON")
        await console.close()

    bodies = [line.split(" ", 2)[2] for line in path.read_text().splitlines()]
    assert "solixble> connect 0 C300" in bodies
    assert "[0] connected" in bodies
    assert "solixble> send 404a PARAMETERS_ON" in bodies
    sent = [body for body in bodies if body.startswith(f"{DEVICE_TAG}out 03000f 404a")]
    assert len(sent) == 1


def test_bleak_logs_apart_from_the_library() -> None:
    """``--log-level`` reaches SolixBLE's loggers; bleak keeps its own level."""
    names = ("SolixBLE", "bleak", "bleak_retry_connector")
    try:
        configure_logging("debug", "warning")
        assert logging.getLogger("SolixBLE.device").getEffectiveLevel() == logging.DEBUG
        assert (
            logging.getLogger(
                "bleak.backends.corebluetooth.CentralManagerDelegate",
            ).getEffectiveLevel()
            == logging.WARNING
        )
        assert (
            logging.getLogger("bleak_retry_connector").getEffectiveLevel()
            == logging.WARNING
        )
    finally:
        for name in names:
            logging.getLogger(name).setLevel(logging.NOTSET)


def test_log_records_reach_the_capture(tmp_path: Path) -> None:
    """Log records, tracebacks included, are captured as dated lines."""
    path = tmp_path / "log.log"
    frames = FrameLog()
    frames.capture(path)
    handler = CaptureHandler(frames)
    logger = logging.getLogger("SolixBLE.test_cli")
    logger.addHandler(handler)
    error = ValueError(FAILURE)
    try:
        logger.error("connect failed", exc_info=(ValueError, error, None))
    finally:
        logger.removeHandler(handler)
        frames.capture(None)

    lines = path.read_text().splitlines()
    bodies = [line.split(" ", 2)[2] for line in lines]
    assert bodies[0] == "ERROR:SolixBLE.test_cli:connect failed"
    assert f"ValueError: {FAILURE}" in bodies
    assert all(line[:4].isdigit() for line in lines)


def test_capture_appends(tmp_path: Path) -> None:
    """The capture file is appended to, never truncated, one dated line a frame."""
    path = tmp_path / "capture.log"
    path.write_text("earlier\n")
    frames = FrameLog()
    frames.capture(path)
    frames.record(
        new_frame(
            time=datetime(2026, 10, 5, 12, 0, 0).astimezone(),
            device="device",
            direction="in",
            pattern=bytes.fromhex("030001"),
            cmd=bytes.fromhex("0801"),
            cleartext=bytes.fromhex("00a10101"),
            raw=bytes.fromhex("ff090e00030001080100a1010152"),
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
