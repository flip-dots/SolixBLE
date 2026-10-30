"""Tests for the Prime Charger 250W (A2345) snapshot, settings and keep-alive.

.. moduleauthor:: kb1ibt
"""

import dataclasses
import struct
import zlib
from collections.abc import Callable
from unittest import mock

import pytest

from SolixBLE import PrimeCharger250w
from SolixBLE.const import DEFAULT_METADATA_INT, DEFAULT_METADATA_STRING
from SolixBLE.constructs import Packet, Parameters
from SolixBLE.devices.prime_charger_250w import (
    CMD_UPLOAD_CHUNK,
    CMD_UPLOAD_PREPARE,
    KEEP_ALIVE_INTERVAL,
    THEME_IMAGE_LIMITS,
    THEME_IMAGE_TRANSFER,
    UPLOAD_RETRIES,
    CatalogTheme,
    ChargingMode,
    KnobDirection,
    ScreensaverWindow,
    ThemeImageState,
)
from SolixBLE.images import JpegLimits, check_jpeg
from SolixBLE.protocols import EncryptedOuter, NegotiatedSession
from SolixBLE.states import (
    ClockFormat,
    ClockTheme,
    PortPriority,
    PortSchedule,
    PortTimer,
)
from tests.const import MOCK_BLE_DEVICE, NEGOTIATION_RESPONSES_PRIME
from tests.helpers import (
    MockDevice,
    chunk_payload,
    connect_recorded,
    jpeg_image,
    jpeg_scan,
    jpeg_segment,
    sent_payloads,
    session_reply,
    window_acks,
    with_crc32,
)

#: A 4303 stream frame with the six ports at a2-a7 (USB C1 reads 0.297 A).
STREAM_PORTS = (
    "a10131a2080401881329016400a30804014024d8061c06a4080401004d9d08ee10a5080401"
    "084d1809b311a6080401801364003100a70804018013b7003100fe05033d7ab569"
)
C1_CURRENT = 0.297

#: A ca00 snapshot carrying only the software version, 2116 as a 16-bit integer.
SNAPSHOT_VERSION = "a203024408"

#: A serial number the device reports in negotiation stage 3.
TEST_SERIAL = "A2345TESTSN00001"

#: A full ca00 snapshot from the app's log (v2.1.1.6): no faults, the clock
#: off on the first theme, a 30 second timeout at 60 % brightness, AI Power, a
#: forward knob, no update under way, PD controllers without device identity,
#: the screensaver from 08:00 to 23:00 every day, compatibility and device
#: identification on and no port priorities.
SNAPSHOT_FULL = (
    "a10131a203024408a303020000a4080401004db3011403a5080401901362019600a608040000"
    "0014000000a7080401881314000a00a8080400000000000000a9080400000000000000aa1404"
    "01ff0c0000ff0c000000580200000000000000ab140401ff0c0000ff0c000000580200000000"
    "000000ac140401ff0c0000ff0c000000580200000000000000ad140401ff0c0000ff0c000000"
    "580200000000000000ae140401ff0c0000ff0c000000580200000000000000af060400000000"
    "00b0020101b1020101b203040000b302013cb4020100b5020100b6020101b70302ff02b80804"
    "010046412d2d18b90604080017007fba0d043b00003b00003b00003b0000bb020101bc020101"
    "bf020101bd1104ac051173ac051771fafffbff00000000be11040100ffff01003600ffffffff"
    "fffffffffe0503fb6ca06a"
)
FULL_TIMEOUT = 30
FULL_BRIGHTNESS = 60
FULL_SCREENSAVER = ScreensaverWindow(8, 0, 23, 0, frozenset(range(7)))

#: The clock on with the holiday bit and a catalog theme (index 3), Rhythmic
#: Hue by its catalog ID.
SNAPSHOT_CATALOG_THEME = "af0604c3d4f89e1d"

#: Port Priority with USB C2 designated: the priority byte closing each USB C
#: record reads 01 02 01 01.
SNAPSHOT_C2_DESIGNATED = (
    "aa140401ff0c0000ff0c000000580200000000000001"
    "ab140401ff0c0000ff0c000000580200000000000002"
    "ac140401ff0c0000ff0c000000580200000000000001"
    "ad140401ff0c0000ff0c000000580200000000000001"
)

#: The snapshot's port fault bitmap (a3, a u16 under type 02). Every logged
#: snapshot carries 0; faults set the bits by hand.
PORT_FAULTS_PREFIX = "a30302"

#: An update under way at 42 %, and PD controllers that let the screen show
#: device names.
SNAPSHOT_UPDATING = "b2030401" + "2a" + "b70302ff06"
UPDATE_PROGRESS = 42

#: Firmware that predates the PD revision check (v1.9.0.4) reports ff 00.
SNAPSHOT_PD_UNCHECKED = "b70302ff00"

#: A ca00 snapshot carrying only the USB C1 record: the port turns on at 08:00
#: and off at 22:00 every day, and the timer is armed for 3600 s with 1800 s
#: left.
SNAPSHOT_C1 = "a10131aa1404010108007f0116007f01100e00000807000000fe05033d7ab569"
EVERY_DAY = frozenset(range(7))
C1_SCHEDULE = PortSchedule(
    on_time_enabled=True,
    on_time_hour=8,
    on_time_minute=0,
    on_time_weekdays=EVERY_DAY,
    off_time_enabled=True,
    off_time_hour=22,
    off_time_minute=0,
    off_time_weekdays=EVERY_DAY,
)
C1_TIMER = PortTimer(enabled=True, seconds=3600, remaining=1800)

#: An idle port's record in SNAPSHOT_FULL: both times never set (12:00 kept
#: behind them) and the timer off, holding its 600 s default.
IDLE_SCHEDULE = PortSchedule(None, 12, 0, frozenset(), None, 12, 0, frozenset())
IDLE_TIMER = PortTimer(enabled=False, seconds=600, remaining=0)

#: SNAPSHOT_FULL's USB-PD identities: C1 and C2 report Apple's vendor ID, C3
#: has no device and C4 answered without an identity. The charger names C2's
#: model and only C1's vendor.
FULL_IDENTITIES = [
    (0x05AC, 0x7311, "Apple"),
    (0x05AC, 0x7117, "iPad Pro M4"),
    (DEFAULT_METADATA_INT, DEFAULT_METADATA_INT, None),
    (DEFAULT_METADATA_INT, DEFAULT_METADATA_INT, None),
]

#: A 4303 stream frame whose a8 / a9 carry a Samsung device on C2 and an Anker
#: power bank on C3.
STREAM_IDENTITIES = (
    "a10131a2080401881329016400a30804014024d8061c06a4080401004d9d08ee10a5080401"
    "084d1809b311a6080401801364003100a70804018013b7003100a8110400000000e8040000"
    "1a290b1100000000a91104ffffffff0200ffff0a000200fffffffffe05033d7ab569"
)
STREAM_IDENTITY_LIST = [
    (DEFAULT_METADATA_INT, DEFAULT_METADATA_INT, None),
    (0x04E8, 0x0000, "Samsung"),
    (0x291A, 0x110B, "Power Bank 20K"),
    (DEFAULT_METADATA_INT, DEFAULT_METADATA_INT, None),
]

#: The charger's own negotiation, recorded on the encrypted outer with its serial
#: and MAC replaced: the reply to each request from 4001 to the 4027
#: registration, then the key exchange's device point and the ECDH secret logged
#: with it.
NEGOTIATION_RESPONSES_A2345 = [
    "ff091e000300014801ab273ed3e27270c3f4d676ac7d69a00572793732a6",
    (
        "ff092b000300014803ab273ed04438d4b25db54c6d4a6ec3d481f5ad58ff7cc2be8bc8369fd98c"
        "0b914e03"
    ),
    (
        "ff0948000300014829ab273ed1443f6ce1ae873a6a4c5f48e5ad49ade39ef481d3babeaa140461"
        "cb0ee0aafc774ea71639137ec8a415329a4c14fe733d70d8967c44c27aedf2bc49"
    ),
    "ff091b000300014805abab709a595a803dd04246b78a927453cf65",
    (
        "ff095d000300014821ab277febf6ce9532e6d27425a23af4fa577ba109982703a0ad73a3669c6b"
        "f8b13efb30a6a125bb85e8db4ae33e5441cdf40defd4adc7168c03a732476accbb5870685351e6"
        "4ea6516ec13857b1680eb7b49ab1c0"
    ),
    "ff091b0003000148221b909c47e3c3ab58249d97800bd59b132ed0",
    "ff091b0003000148271b909c47e3c3ab58249d97800bd59b132ed5",
]
DEVICE_POINT_A2345 = bytes.fromhex(
    "3910f4bc8018667cece955922fd40222d9a2c3c3225b9c4330a83a038fee61fce1dfb308ba51b7"
    "5cea95898a91a75cc185a5535912a8f5a51b87a137117c1b3d",
)
SHARED_SECRET_A2345 = bytes.fromhex(
    "69b28b02183f1c538565ddf215038801cb35c582c78e06f4b14393dd8ba12b97",
)

#: The same session's replies to the post-authorize requests: the ca00 snapshot
#: in two fragments for 4200, and 4a0a for 420a.
SNAPSHOT_A2345 = [
    (
        "ff09fd0003010fca00121b1d9a51688a7946b711df542f03516ac419448d297b9989d46290221b"
        "ea7e5867abe0f935cd6b4e760079acdbfd104f899512e130aef06b832d32733a929e1098796688"
        "bb100f65a70885c88ca730aefcbf9b939f3389f4c0dc7cf9d309ec2104c2a231b2130fdefc15a3"
        "73095e7b9017ee90902b42937d477f2c6fae4ef9eadc94caf0a1cb2bc8f384db619e6573b2bf00"
        "d2eb2edceb6c34aaa5b712e6d0875e93e163d958b60aa0a83a4aaa3f05a7c25eb4e55ff37a0306"
        "1826c4c23a766d92888b580a9d1bec8ff271418a916598490da974be9f075acb98f71e23ded198"
        "3df6109599a1729b989e629ca31788d79182c7"
    ),
    (
        "ff09650003010fca002243f98947e7cb9c9f467f4ee58a7ecf90572867f22ec71b9b25a19135ff"
        "eaf41994c2c1bf33904b4f1db4a4faa5d0f30671c39f61b8edace9361c1453abd379d010ed3e9a"
        "f5ae44556f1bb82359dc4bf9be39bdb5ea36ae43caa941"
    ),
]
REGION_REPLY_A2345 = "ff091e0003010f4a0a1b1d9a512416d6797545e461b5fdb94e0049fbde93"

#: The serial the recording carries in place of the charger's own.
RECORDED_SERIAL = "AQLQJB0000000001"


@pytest.mark.asyncio
async def test_snapshot_fills_snapshot_not_telemetry() -> None:
    """A ca00 snapshot fills the snapshot and leaves telemetry empty."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_VERSION),
        encrypted=False,
    )

    assert device.software_version == "2.1.1.6"
    assert device._data is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_stream_fills_telemetry_not_snapshot() -> None:
    """A 4303 stream frame fills telemetry and leaves the snapshot empty."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0x303,
        payload=bytes.fromhex(STREAM_PORTS),
        encrypted=False,
    )

    assert device.usb_c1_current == C1_CURRENT
    assert device._snapshot is None  # noqa: SLF001
    assert device.software_version == DEFAULT_METADATA_STRING


@pytest.mark.asyncio
async def test_snapshot_runs_state_changed_callbacks() -> None:
    """A snapshot runs the registered state-changed callbacks once."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    seen: list[bool] = []
    device.add_callback(lambda: seen.append(True))
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_VERSION),
        encrypted=False,
    )

    assert seen == [True]


@pytest.mark.asyncio
async def test_reset_clears_snapshot_with_data() -> None:
    """The snapshot survives a reset that keeps data, not one that drops it."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_VERSION),
        encrypted=False,
    )

    device._reset_session(reset_data=False)  # noqa: SLF001
    assert device.software_version == "2.1.1.6"

    device._reset_session()  # noqa: SLF001
    assert device.software_version == DEFAULT_METADATA_STRING


@pytest.mark.asyncio
@pytest.mark.usefixtures("fast_sleep")
async def test_keep_alive_requests_snapshot_then_stream() -> None:
    """The keep-alive requests a fresh snapshot, then re-arms the stream."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._client = mock.AsyncMock()  # noqa: SLF001
    with mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True):
        interval = await device._keep_alive()  # noqa: SLF001

    sent = [
        Packet.parse(call.args[1]).msgtype
        for call in device._client.write_gatt_char.call_args_list  # noqa: SLF001
    ]
    assert sent == [0x200, 0x20B]
    assert interval == KEEP_ALIVE_INTERVAL


def test_serial_number_from_announcement() -> None:
    """The serial the device announced in negotiation stage 3 reads back."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    assert device.serial_number == DEFAULT_METADATA_STRING

    device._session = NegotiatedSession(device._outer_class(), device)  # noqa: SLF001
    device._session.announcement.serial = TEST_SERIAL.encode()  # noqa: SLF001
    assert device.serial_number == TEST_SERIAL


@pytest.mark.asyncio
async def test_connects_with_its_recorded_negotiation(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    pin_shared_secret: Callable[[bytes, bytes], None],
) -> None:
    """Its recorded negotiation runs on the encrypted outer, then 4200 and 420a."""
    pin_shared_secret(DEVICE_POINT_A2345, SHARED_SECRET_A2345)
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001
    assert device._outer_class is EncryptedOuter  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for response in NEGOTIATION_RESPONSES_A2345:
            mock_bluetooth.expect_ordered(None, [bytes.fromhex(response)])
        mock_bluetooth.expect_ordered(
            None,
            [bytes.fromhex(fragment) for fragment in SNAPSHOT_A2345],
        )
        mock_bluetooth.expect_ordered(None, [bytes.fromhex(REGION_REPLY_A2345)])
        assert await device.connect()
        mock_bluetooth.check_assertions()

    sent = [Packet.parse(write) for write in mock_bluetooth.writes]
    assert [(packet.encrypted, packet.msgtype) for packet in sent[-2:]] == [
        (True, 0x200),
        (True, 0x20A),
    ]
    assert device.serial_number == RECORDED_SERIAL
    assert device.software_version == "2.1.1.6"
    assert set(mock_bluetooth.write_responses) == {False}


def test_settings_default_before_any_snapshot() -> None:
    """Every setting has a default before the first snapshot."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)

    assert device.software_version == DEFAULT_METADATA_STRING
    assert device.clock_display_enabled is None
    assert device.display_theme == ClockTheme.UNKNOWN
    assert device.display_catalog_theme is None
    assert device.display_timeout == DEFAULT_METADATA_INT
    assert device.display_brightness == DEFAULT_METADATA_INT
    assert device.charging_mode == ChargingMode.UNKNOWN
    assert device.knob_direction == KnobDirection.UNKNOWN
    assert device.screensaver_window is None
    assert device.compatibility_mode_enabled is None
    assert device.device_identification_enabled is None
    assert device.device_name_display_supported is None
    assert device.firmware_updating is None
    assert device.firmware_update_progress == DEFAULT_METADATA_INT
    assert device.usb_c1_priority == PortPriority.UNKNOWN
    assert device.over_temperature is None
    assert device.usb_c1_fault is None
    assert device.usb_a_fault is None


@pytest.mark.asyncio
async def test_snapshot_decodes_settings() -> None:
    """A full snapshot from the app's log fills every setting it carries."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_FULL),
        encrypted=False,
    )

    assert device.software_version == "2.1.1.6"
    assert device.clock_display_enabled is False
    assert device.display_theme == ClockTheme.THEME_1
    assert device.display_timeout == FULL_TIMEOUT
    assert device.display_brightness == FULL_BRIGHTNESS
    assert device.charging_mode == ChargingMode.AI_POWER
    assert device.knob_direction == KnobDirection.FORWARD
    assert device.screensaver_window == FULL_SCREENSAVER
    assert device.compatibility_mode_enabled is True
    assert device.device_identification_enabled is True
    assert device.device_name_display_supported is False
    assert device.firmware_updating is False
    assert device.firmware_update_progress == 0
    assert device.usb_c1_priority == PortPriority.UNSET
    assert device.usb_c4_priority == PortPriority.UNSET
    assert device.over_temperature is False
    assert device.usb_a_fault is False


@pytest.mark.asyncio
async def test_snapshot_decodes_display_and_priorities() -> None:
    """The clock bit, the theme index and the per-port priority bytes."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_CATALOG_THEME + SNAPSHOT_C2_DESIGNATED),
        encrypted=False,
    )

    assert device.clock_display_enabled is True
    assert device.display_theme == ClockTheme.CATALOG
    assert [
        device.usb_c1_priority,
        device.usb_c2_priority,
        device.usb_c3_priority,
        device.usb_c4_priority,
    ] == [
        PortPriority.NORMAL,
        PortPriority.DESIGNATED,
        PortPriority.NORMAL,
        PortPriority.NORMAL,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "theme", "catalog_theme"),
    [
        pytest.param(
            SNAPSHOT_CATALOG_THEME,
            ClockTheme.CATALOG,
            CatalogTheme.RHYTHMIC_HUE,
            id="catalog_rhythmic_hue",
        ),
        # A built-in theme keeps the last catalog theme's ID behind it
        pytest.param("af0604c0d4f89e1d", ClockTheme.THEME_1, None, id="theme_1"),
        pytest.param(
            "af06048378563412",
            ClockTheme.CATALOG,
            CatalogTheme.UNKNOWN,
            id="catalog_not_listed",
        ),
        pytest.param("af06048500000000", ClockTheme.CUSTOM, None, id="custom"),
    ],
)
async def test_snapshot_decodes_theme(
    record: str,
    theme: ClockTheme,
    catalog_theme: CatalogTheme | None,
) -> None:
    """af[0] picks the theme, and a catalog theme is named by af's ID."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(record),
        encrypted=False,
    )

    assert device.display_theme == theme
    assert device.display_catalog_theme == catalog_theme


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "method", "arguments", "sent"),
    [
        # Setting a theme turns the clock display on, even from off
        pytest.param(
            "af06040000000000",
            "set_display_theme",
            [ClockTheme.THEME_3],
            "82",
            id="theme_3_turns_clock_on",
        ),
        pytest.param(
            "af06040200000000",
            "turn_clock_display_on",
            [],
            "82",
            id="on_keeps_theme_3",
        ),
        # Off clears the clock bit (and the holiday bit with it)
        pytest.param(
            "af0604c1d4f89e1d",
            "turn_clock_display_off",
            [],
            "01",
            id="off_keeps_theme_2",
        ),
    ],
)
async def test_display_byte_commands(  # noqa: PLR0913, PLR0917
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    record: str,
    method: str,
    arguments: list[object],
    sent: str,
) -> None:
    """4205 carries the clock display switch in bit 7 and the theme index."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )
        assert await device.connect()
        await device._process_session(  # noqa: SLF001
            msgtype=0xA00,
            payload=bytes.fromhex(record),
            encrypted=False,
        )
        mock_bluetooth.expect_ordered(None)
        await getattr(device, method)(*arguments)

    assert set(mock_bluetooth.write_responses) == {False}
    packet = Packet.parse(mock_bluetooth.writes[-1])
    assert (packet.encrypted, packet.msgtype) == (True, 0x205)
    payload = device._decrypt_payload(packet.payload_bytes).hex()  # noqa: SLF001
    assert payload.startswith("a10121a20201" + sent + "fe0503")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "method"),
    [
        pytest.param(None, "turn_clock_display_on", id="on_before_snapshot"),
        pytest.param(None, "turn_clock_display_off", id="off_before_snapshot"),
        pytest.param(SNAPSHOT_CATALOG_THEME, "turn_clock_display_on", id="on_catalog"),
        pytest.param("af06048500000000", "turn_clock_display_on", id="on_custom"),
    ],
)
async def test_clock_display_needs_a_known_built_in_theme(
    record: str | None,
    method: str,
) -> None:
    """The clock display switch can't be sent without the theme to keep."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    if record is not None:
        await device._process_session(  # noqa: SLF001
            msgtype=0xA00,
            payload=bytes.fromhex(record),
            encrypted=False,
        )

    with pytest.raises(ValueError, match="Cannot turn the clock display"):
        await getattr(device, method)()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mask", "faults"),
    [
        pytest.param("0000", (False,) * 6, id="none"),
        pytest.param("0100", (True, False, False, False, False, False), id="hot"),
        pytest.param("0a00", (False, True, False, True, False, False), id="c1_c3"),
        pytest.param("3000", (False, False, False, False, True, True), id="c4_a"),
    ],
)
async def test_snapshot_decodes_port_faults(
    mask: str,
    faults: tuple[bool, ...],
) -> None:
    """Bit 0 of a3 is over-temperature, 1-4 the USB C faults, 5 the USB A fault.

    :param mask: The bitmap's two bytes.
    :param faults: The fault properties the bitmap sets.
    """
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(PORT_FAULTS_PREFIX + mask),
        encrypted=False,
    )

    assert (
        device.over_temperature,
        device.usb_c1_fault,
        device.usb_c2_fault,
        device.usb_c3_fault,
        device.usb_c4_fault,
        device.usb_a_fault,
    ) == faults


@pytest.mark.asyncio
async def test_snapshot_decodes_update_and_pd_gate() -> None:
    """b2 carries the update flag and progress; b7's 6 allows name display."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_UPDATING),
        encrypted=False,
    )

    assert device.firmware_updating is True
    assert device.firmware_update_progress == UPDATE_PROGRESS
    assert device.device_name_display_supported is True


@pytest.mark.asyncio
async def test_snapshot_decodes_schedule_and_timer() -> None:
    """A port record carries its daily schedule and its countdown timer."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    assert device.usb_c1_schedule is None
    assert device.usb_c1_timer is None

    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_C1),
        encrypted=False,
    )

    assert device.usb_c1_schedule == C1_SCHEDULE
    assert device.usb_c1_timer == C1_TIMER
    assert device.usb_c2_schedule is None


@pytest.mark.asyncio
async def test_snapshot_decodes_idle_ports_and_clock() -> None:
    """Idle port records read as never-set schedules; b5 is the clock format."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    assert device.clock_format == ClockFormat.UNKNOWN

    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_FULL),
        encrypted=False,
    )

    assert device.clock_format == ClockFormat.HOUR_12
    assert device.usb_a1_a2_schedule == IDLE_SCHEDULE
    assert device.usb_a1_a2_timer == IDLE_TIMER


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time")
async def test_set_schedule_sends_on_time_then_off_time() -> None:
    """Setting a schedule sends the on-time, then the off-time."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._client = mock.AsyncMock()  # noqa: SLF001
    schedule = PortSchedule(
        on_time_enabled=True,
        on_time_hour=1,
        on_time_minute=0,
        on_time_weekdays=EVERY_DAY,
        off_time_enabled=None,
        off_time_hour=23,
        off_time_minute=0,
        off_time_weekdays=frozenset({2}),
    )
    with (
        mock.patch.object(device, "_encrypt_payload", side_effect=lambda x: x),
        mock.patch("SolixBLE.constructs.Packet.build") as build,
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
    ):
        await device.set_schedule_usb_c2(schedule)

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    sent = [call.args[0] for call in build.call_args_list]
    assert [block["msgtype"] for block in sent] == [0x208, 0x208]
    assert [block["payload_bytes"].hex() for block in sent] == [
        f"a10121a2020101a3020101a405030101007f{timestamp}",
        f"a10121a2020101a3020100a4050300170004{timestamp}",
    ]


@pytest.mark.asyncio
async def test_snapshot_decodes_usb_pd_identity() -> None:
    """Bd carries each port's USB-PD vendor and product, be what it names."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_FULL),
        encrypted=False,
    )

    assert [
        (
            getattr(device, f"usb_c{port}_vendor_id"),
            getattr(device, f"usb_c{port}_product_id"),
            getattr(device, f"usb_c{port}_device"),
        )
        for port in range(1, 5)
    ] == FULL_IDENTITIES


@pytest.mark.asyncio
async def test_stream_identity_overrides_snapshot() -> None:
    """The stream's a8 / a9 win over the snapshot's bd / be once they arrive."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    for msgtype, payload in ((0xA00, SNAPSHOT_FULL), (0x303, STREAM_IDENTITIES)):
        await device._process_session(  # noqa: SLF001
            msgtype=msgtype,
            payload=bytes.fromhex(payload),
            encrypted=False,
        )

    assert [
        (
            getattr(device, f"usb_c{port}_vendor_id"),
            getattr(device, f"usb_c{port}_product_id"),
            getattr(device, f"usb_c{port}_device"),
        )
        for port in range(1, 5)
    ] == STREAM_IDENTITY_LIST


@pytest.mark.asyncio
async def test_pd_gate_unknown_before_the_check() -> None:
    """Firmware that predates the PD revision check reads as unknown."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_PD_UNCHECKED),
        encrypted=False,
    )

    assert device.device_name_display_supported is None


#: The app's theme frames for Rhythmic Hue (BLE, app 3.23.0), before their
#: timestamps: 4205 choosing the catalog theme with the placeholder URL, the
#: 4311 pushes asking for its image and reporting it stored, and 4220 opening
#: the upload of its 26 242-byte image (CRC32 b5d0abf9) in 137 chunks of 192 B,
#: the last carrying 130 image bytes and 62 zero bytes of padding.
RHYTHMIC_HUE_SET_THEME = (
    "a10121a2020183a30503d4f89e1da40503f9abd0b5a50503ffffffff"
    "a6110431323334353637383930313233343536"
)
RHYTHMIC_HUE_NEEDS_UPLOAD = "a10131a20504d4f89e1da3020104a4020103"
RHYTHMIC_HUE_STORED = "a10131a20504d4f89e1da3020101a4020103"
RHYTHMIC_HUE_PREPARE = (
    "a10121a2020100a30503d4f89e1da40503f9abd0b5a5050382660000a602010a"
    "a70302c000a803028900a9110431323334353637383930313233343536"
)
RHYTHMIC_HUE_SIZE = 26242
RHYTHMIC_HUE_CRC = 0xB5D0ABF9
RHYTHMIC_HUE_CHUNKS = 137
RHYTHMIC_HUE_LAST_CHUNK = 130

#: The charger's ack to 4205 and 4220, and its last 4a21 for that upload:
#: done, 137 chunks.
ACK = "00a10131"
RHYTHMIC_HUE_DONE = "10a10131a203028900"

#: A 4311 push: the theme ID (u32 LE), the image state and the kind (03
#: catalog, 05 custom).
THEME_STATE = "a10131a20504{theme}a30201{state:02x}a40201{kind:02x}"
KIND_CATALOG = 3
KIND_CUSTOM = 5

#: The placeholder URL's TLV body (type 04, 16 ASCII digits), sent in 4205 a6
#: and 4220 a9 when no URL is given.
PLACEHOLDER = "110431323334353637383930313233343536"

#: An image URL for the charger to fetch itself.
THEME_URL = "https://example.com/themes/rhythmic-hue.jpg"

#: The app's catalog JPEGs from SOI through the scan header: SOI, JFIF, an
#: sRGB ICC profile, two quantisation tables, a 480x200 4:2:0 baseline frame,
#: four Huffman tables and the scan header.
CELESTIAL_HEADER = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffe201d84943435f50524f46494c45000101"
    "000001c800000000043000006d6e74725247422058595a2007e0000100010000000000006163"
    "7370000000000000000000000000000000000000000000000000000000010000f6d600010000"
    "0000d32d00000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000964657363000000f0000000247258595a00000114"
    "000000146758595a00000128000000146258595a0000013c0000001477747074000001500000"
    "0014725452430000016400000028675452430000016400000028625452430000016400000028"
    "637072740000018c0000003c6d6c756300000000000000010000000c656e5553000000080000"
    "001c007300520047004258595a200000000000006fa2000038f50000039058595a2000000000"
    "000062990000b785000018da58595a2000000000000024a000000f840000b6cf58595a200000"
    "00000000f6d6000100000000d32d706172610000000000040000000266660000f2a700000d59"
    "000013d000000a5b00000000000000006d6c756300000000000000010000000c656e55530000"
    "00200000001c0047006f006f0067006c006500200049006e0063002e00200032003000310036"
    "ffdb004300010101010101010101010101010101010101010101010101010101010101010101"
    "01010102020101020101010202020202020202020102020202020202020202ffdb0043010101"
    "0101010101010101020101010202020202020202020202020202020202020202020202020202"
    "020202020202020202020202020202020202020202020202ffc000110800c801e00301220002"
    "1101031101ffc4001e0001010001050101010000000000000000000605010204070803090aff"
    "c40047100001020403050506040404020b010000010002030411210531410612516171078191"
    "a1f0081322b1c1d11432e1f115234252163372a20962182425344344536392a3d2e2ffc4001c"
    "0101000105010100000000000000000000000503040607080201ffc4003b1100020102030602"
    "09020503050000000000010203110421310512415161f0067113228191a1b1c1d1e132421423"
    "62b2f107154324527282a2ffda000c03010002110311003f00",
)
RHYTHMIC_HUE_HEADER = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffe201d84943435f50524f46494c45000101"
    "000001c800000000043000006d6e74725247422058595a2007e0000100010000000000006163"
    "7370000000000000000000000000000000000000000000000000000000010000f6d600010000"
    "0000d32d00000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000964657363000000f0000000247258595a00000114"
    "000000146758595a00000128000000146258595a0000013c0000001477747074000001500000"
    "0014725452430000016400000028675452430000016400000028625452430000016400000028"
    "637072740000018c0000003c6d6c756300000000000000010000000c656e5553000000080000"
    "001c007300520047004258595a200000000000006fa2000038f50000039058595a2000000000"
    "000062990000b785000018da58595a2000000000000024a000000f840000b6cf58595a200000"
    "00000000f6d6000100000000d32d706172610000000000040000000266660000f2a700000d59"
    "000013d000000a5b00000000000000006d6c756300000000000000010000000c656e55530000"
    "00200000001c0047006f006f0067006c006500200049006e0063002e00200032003000310036"
    "ffdb004300010101010101010101010101010101010101010101010101010101010101010101"
    "01010102020101020101010202020202020202020102020202020202020202ffdb0043010101"
    "0101010101010101020101010202020202020202020202020202020202020202020202020202"
    "020202020202020202020202020202020202020202020202ffc000110800c801e00301220002"
    "1101031101ffc4001e0001000104030101000000000000000000000504060809020307010aff"
    "c4006b100001000803040506050d061109080300010002030405061121073141081251610913"
    "718191142232a1b1f01752c1d1f1151623242526273334425472e13544556294d53637454647"
    "535664667582859295a2b2c2192843576793b5c6d318636573748697a6b3d2d4ffc4001d0101"
    "00020203010100000000000000000000050604070203080109ffc40062110001020403030508"
    "090c0d080b0000000102030004051106071221315108131441612232527191d1d2f015166263"
    "81a1b1c1d324253334535564729293d5e1171823354354657382838494d40926424574b2c2c3"
    "274466a2a3a5b3b5c5d6f1ffda000c03010002110311003f00",
)

#: Limits of a display other than the 250W charger's: 320x240, 4:4:4 only.
OTHER_LIMITS = JpegLimits(
    width=320,
    height=240,
    max_size=4096,
    components=3,
    luma_sampling=frozenset({(1, 1)}),
)


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_catalog_theme_upload_matches_the_app() -> None:
    """A catalog theme the charger lacks: the app's 4205 and 4220, then 137 chunks."""
    image = with_crc32(
        jpeg_scan(RHYTHMIC_HUE_HEADER, RHYTHMIC_HUE_SIZE),
        RHYTHMIC_HUE_CRC,
    )
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(device, "4311", RHYTHMIC_HUE_NEEDS_UPLOAD),
            ],
        )
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for replies in window_acks(
            device,
            RHYTHMIC_HUE_CHUNKS,
            [
                session_reply(device, "4311", RHYTHMIC_HUE_STORED),
                session_reply(device, "4a21", RHYTHMIC_HUE_DONE),
            ],
        ):
            mock_bluetooth.expect_ordered(None, replies)
        await device.set_display_catalog_theme(CatalogTheme.RHYTHMIC_HUE, image)
        mock_bluetooth.check_assertions()

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    sent = sent_payloads(device, mock_bluetooth.writes[start:])
    assert sent == [
        (0x205, RHYTHMIC_HUE_SET_THEME + timestamp),
        (0x220, RHYTHMIC_HUE_PREPARE + timestamp),
        *(
            (0x221, chunk_payload(image, index) + timestamp)
            for index in range(RHYTHMIC_HUE_CHUNKS)
        ),
    ]
    last = image[(RHYTHMIC_HUE_CHUNKS - 1) * 192 :]
    assert len(last) == RHYTHMIC_HUE_LAST_CHUNK
    assert sent[-1] == (
        0x221,
        f"a10121a203028800a3c104{last.hex()}{'00' * 62}{timestamp}",
    )
    assert set(mock_bluetooth.write_responses) == {False}


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_catalog_theme_already_stored_sends_no_image() -> None:
    """A theme the charger already holds is reported stored at once: no upload."""
    image = with_crc32(
        jpeg_scan(RHYTHMIC_HUE_HEADER, RHYTHMIC_HUE_SIZE),
        RHYTHMIC_HUE_CRC,
    )
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(device, "4311", RHYTHMIC_HUE_STORED),
            ],
        )
        await device.set_display_catalog_theme(CatalogTheme.RHYTHMIC_HUE, image)
        mock_bluetooth.check_assertions()

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    assert sent_payloads(device, mock_bluetooth.writes[start:]) == [
        (0x205, RHYTHMIC_HUE_SET_THEME + timestamp),
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
@pytest.mark.parametrize(
    ("size", "count"),
    [
        pytest.param(1000, 6, id="one_short_window"),
        pytest.param(2200, 12, id="two_windows"),
        pytest.param(1920, 10, id="exactly_one_window"),
    ],
)
async def test_custom_theme_upload(size: int, count: int) -> None:
    """A custom image goes up as kind 2 under its CRC32, in windows of 10 chunks."""
    image = jpeg_image(size=size)
    crc = struct.pack("<I", zlib.crc32(image)).hex()
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=crc,
                        state=ThemeImageState.NEEDS_UPLOAD,
                        kind=KIND_CUSTOM,
                    ),
                ),
            ],
        )
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for replies in window_acks(
            device,
            count,
            [
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=crc,
                        state=ThemeImageState.STORED,
                        kind=KIND_CUSTOM,
                    ),
                ),
                session_reply(
                    device,
                    "4a21",
                    f"10a10131a20302{struct.pack('<H', count).hex()}",
                ),
            ],
        ):
            mock_bluetooth.expect_ordered(None, replies)
        await device.set_display_custom_theme(image)
        mock_bluetooth.check_assertions()

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    assert sent_payloads(device, mock_bluetooth.writes[start:]) == [
        (
            0x205,
            f"a10121a2020185a30503{crc}a40503{crc}a50503ffffffffa6{PLACEHOLDER}"
            + timestamp,
        ),
        (
            0x220,
            f"a10121a2020102a30503{crc}a40503{crc}"
            f"a50503{struct.pack('<I', size).hex()}a602010aa70302c000"
            f"a80302{struct.pack('<H', count).hex()}a9{PLACEHOLDER}" + timestamp,
        ),
        *((0x221, chunk_payload(image, index) + timestamp) for index in range(count)),
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_custom_theme_pads_the_last_chunk() -> None:
    """A last chunk of 1 byte goes as 192 B; size and CRC32 cover the image only."""
    size = 385
    image = jpeg_image(size=size)
    crc = zlib.crc32(image)
    theme = struct.pack("<I", crc).hex()
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=theme,
                        state=ThemeImageState.NEEDS_UPLOAD,
                        kind=KIND_CUSTOM,
                    ),
                ),
            ],
        )
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for replies in window_acks(
            device,
            3,
            [session_reply(device, "4a21", "10a10131a203020300")],
        ):
            mock_bluetooth.expect_ordered(None, replies)
        await device.set_display_custom_theme(image)
        mock_bluetooth.check_assertions()

    sent = [
        (msgtype, Parameters.parse(bytes.fromhex(payload)))
        for msgtype, payload in sent_payloads(device, mock_bluetooth.writes[start:])
    ]
    prepare = next(params for msgtype, params in sent if msgtype == CMD_UPLOAD_PREPARE)
    chunks = [
        params["a3"].value for msgtype, params in sent if msgtype == CMD_UPLOAD_CHUNK
    ]
    sent_data = b"".join(chunks)

    assert size % 16
    assert prepare["a4"].value == struct.pack("<I", crc)
    assert prepare["a5"].value == struct.pack("<I", size)
    assert prepare["a8"].value == struct.pack("<H", 3)
    assert [len(chunk) for chunk in chunks] == [192, 192, 192]
    assert sent_data[:size] == image
    assert sent_data[size:] == bytes(191)
    assert zlib.crc32(sent_data) != crc


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
@pytest.mark.parametrize(
    "final",
    [
        pytest.param(("4311", "4a21"), id="stored_then_done"),
        pytest.param(("4a21",), id="done_only"),
        pytest.param(("4311",), id="stored_only"),
    ],
)
async def test_upload_ends_on_stored_or_done(final: tuple[str, ...]) -> None:
    """Our 4311 stored or a 4a21 done, whichever comes first, ends the upload."""
    image = jpeg_image(size=1000)
    crc = struct.pack("<I", zlib.crc32(image)).hex()
    replies = {
        "4311": THEME_STATE.format(
            theme=crc,
            state=ThemeImageState.STORED,
            kind=KIND_CUSTOM,
        ),
        "4a21": "10a10131a203020600",
    }
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=crc,
                        state=ThemeImageState.NEEDS_UPLOAD,
                        kind=KIND_CUSTOM,
                    ),
                ),
            ],
        )
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for chunk_replies in window_acks(
            device,
            6,
            [session_reply(device, cmd, replies[cmd]) for cmd in final],
        ):
            mock_bluetooth.expect_ordered(None, chunk_replies)
        await device.set_display_custom_theme(image)
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_upload_file_without_padding_sends_a_short_last_chunk() -> None:
    """A transfer that doesn't pad sends the last chunk at its own length."""
    image = jpeg_image(size=1000)
    crc = zlib.crc32(image)
    transfer = dataclasses.replace(THEME_IMAGE_TRANSFER, pad_last_chunk=False)
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for replies in window_acks(
            device,
            6,
            [session_reply(device, "4a21", "10a10131a203020600")],
        ):
            mock_bluetooth.expect_ordered(None, replies)
        await device._upload_file(  # noqa: SLF001
            image,
            transfer,
            kind=2,
            theme_id=crc,
            crc=crc,
        )
        mock_bluetooth.check_assertions()

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    theme = struct.pack("<I", crc).hex()
    sent = sent_payloads(device, mock_bluetooth.writes[start:])
    assert sent == [
        (
            0x220,
            f"a10121a2020102a30503{theme}a40503{theme}"
            f"a50503e8030000a602010aa70302c000a803020600a9{PLACEHOLDER}" + timestamp,
        ),
        *(
            (0x221, chunk_payload(image, index, pad=False) + timestamp)
            for index in range(6)
        ),
    ]
    assert sent[-1][1].startswith("a10121a203020500a32904")


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_upload_resends_from_the_index_the_charger_asks_for() -> None:
    """A 12 at a window's end resends from its index to the end of that window."""
    image = jpeg_image(size=2200)
    crc = struct.pack("<I", zlib.crc32(image)).hex()
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001
    resent = [*range(10), *range(4, 10), 10, 11]

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=crc,
                        state=ThemeImageState.NEEDS_UPLOAD,
                        kind=KIND_CUSTOM,
                    ),
                ),
            ],
        )
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for _ in range(9):
            mock_bluetooth.expect_ordered(None)
        mock_bluetooth.expect_ordered(
            None,
            [session_reply(device, "4a21", "12a10131a203020400")],
        )
        for _ in range(5):
            mock_bluetooth.expect_ordered(None)
        mock_bluetooth.expect_ordered(
            None,
            [session_reply(device, "4a21", "00a10131a203020a00")],
        )
        mock_bluetooth.expect_ordered(None)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=crc,
                        state=ThemeImageState.STORED,
                        kind=KIND_CUSTOM,
                    ),
                ),
                session_reply(device, "4a21", "10a10131a203020c00"),
            ],
        )
        await device.set_display_custom_theme(image)
        mock_bluetooth.check_assertions()

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    assert sent_payloads(device, mock_bluetooth.writes[start + 2 :]) == [
        (0x221, chunk_payload(image, index) + timestamp) for index in resent
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_upload_checksum_mismatch_raises() -> None:
    """A 11 after the last chunk means the charger's CRC32 didn't match."""
    image = jpeg_image(size=1000)
    crc = struct.pack("<I", zlib.crc32(image)).hex()
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=crc,
                        state=ThemeImageState.NEEDS_UPLOAD,
                        kind=KIND_CUSTOM,
                    ),
                ),
            ],
        )
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for replies in window_acks(
            device,
            6,
            [session_reply(device, "4a21", "11a10131a203020600")],
        ):
            mock_bluetooth.expect_ordered(None, replies)
        with pytest.raises(ValueError, match="checksum"):
            await device.set_display_custom_theme(image)
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_upload_to_a_silent_charger_times_out() -> None:
    """With no window ack the window is resent a bounded number of times."""
    image = jpeg_image(size=1000)
    crc = struct.pack("<I", zlib.crc32(image)).hex()
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001
    sent = list(range(6)) * (UPLOAD_RETRIES + 1)

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                session_reply(
                    device,
                    "4311",
                    THEME_STATE.format(
                        theme=crc,
                        state=ThemeImageState.NEEDS_UPLOAD,
                        kind=KIND_CUSTOM,
                    ),
                ),
            ],
        )
        mock_bluetooth.expect_ordered(None, [session_reply(device, "4a20", ACK)])
        for _ in sent:
            mock_bluetooth.expect_ordered(None)
        with pytest.raises(TimeoutError):
            await device.set_display_custom_theme(image)
        mock_bluetooth.check_assertions()

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    assert sent_payloads(device, mock_bluetooth.writes[start + 2 :]) == [
        (0x221, chunk_payload(image, index) + timestamp) for index in sent
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
@pytest.mark.parametrize(
    ("set_theme_reply", "states", "match"),
    [
        pytest.param(ACK, [ThemeImageState.FAILED], "could not store", id="failed"),
        pytest.param(
            ACK,
            [ThemeImageState.FETCHING],
            "fetch",
            id="fetching_without_url",
        ),
        pytest.param("01a10131", [], "rejected", id="set_theme_rejected"),
    ],
)
async def test_catalog_theme_refused(
    set_theme_reply: str,
    states: list[ThemeImageState],
    match: str,
) -> None:
    """A rejected 4205, a failed image or a fetch with no URL raises; no upload."""
    image = with_crc32(
        jpeg_scan(RHYTHMIC_HUE_HEADER, RHYTHMIC_HUE_SIZE),
        RHYTHMIC_HUE_CRC,
    )
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", set_theme_reply),
                *(
                    session_reply(
                        device,
                        "4311",
                        THEME_STATE.format(
                            theme="d4f89e1d",
                            state=state,
                            kind=KIND_CATALOG,
                        ),
                    )
                    for state in states
                ),
            ],
        )
        with pytest.raises(ValueError, match=match):
            await device.set_display_catalog_theme(CatalogTheme.RHYTHMIC_HUE, image)

    assert [
        msgtype
        for msgtype, _ in sent_payloads(
            device,
            mock_bluetooth.writes[start:],
        )
    ] == [0x205]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
async def test_catalog_theme_fetched_by_the_charger() -> None:
    """Given a URL the charger fetches the image itself: 2, 3, then 1."""
    image = with_crc32(
        jpeg_scan(RHYTHMIC_HUE_HEADER, RHYTHMIC_HUE_SIZE),
        RHYTHMIC_HUE_CRC,
    )
    url = THEME_URL.encode()
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        start = len(mock_bluetooth.writes)
        mock_bluetooth.expect_ordered(
            None,
            [
                session_reply(device, "4a05", ACK),
                *(
                    session_reply(
                        device,
                        "4311",
                        THEME_STATE.format(
                            theme="d4f89e1d",
                            state=state,
                            kind=KIND_CATALOG,
                        ),
                    )
                    for state in (
                        ThemeImageState.FETCHING,
                        ThemeImageState.FETCH_STARTED,
                        ThemeImageState.STORED,
                    )
                ),
            ],
        )
        await device.set_display_catalog_theme(
            CatalogTheme.RHYTHMIC_HUE,
            image,
            url=THEME_URL,
        )
        mock_bluetooth.check_assertions()

    timestamp = f"fe0503{device._timestamp().hex()}"  # noqa: SLF001
    assert sent_payloads(device, mock_bluetooth.writes[start:]) == [
        (
            0x205,
            (
                "a10121a2020183a30503d4f89e1da40503f9abd0b5a50503ffffffff"
                f"a6{len(url) + 1:02x}04{url.hex()}{timestamp}"
            ),
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep", "fast_timeouts")
@pytest.mark.parametrize(
    "ours_follows",
    [
        pytest.param(True, id="other_then_ours"),
        pytest.param(False, id="other_only"),
    ],
)
async def test_theme_state_for_another_theme_is_ignored(
    ours_follows: bool,  # noqa: FBT001
) -> None:
    """A 4311 for another theme ID neither ends nor fails the call."""
    image = with_crc32(
        jpeg_scan(RHYTHMIC_HUE_HEADER, RHYTHMIC_HUE_SIZE),
        RHYTHMIC_HUE_CRC,
    )
    other = THEME_STATE.format(
        theme="57058f38",
        state=ThemeImageState.STORED,
        kind=KIND_CATALOG,
    )
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        await connect_recorded(device, mock_bluetooth, NEGOTIATION_RESPONSES_PRIME)
        replies = [
            session_reply(device, "4a05", ACK),
            session_reply(device, "4311", other),
        ]
        if ours_follows:
            replies.append(session_reply(device, "4311", RHYTHMIC_HUE_STORED))
        mock_bluetooth.expect_ordered(None, replies)
        if ours_follows:
            await device.set_display_catalog_theme(CatalogTheme.RHYTHMIC_HUE, image)
        else:
            with pytest.raises(TimeoutError):
                await device.set_display_catalog_theme(
                    CatalogTheme.RHYTHMIC_HUE,
                    image,
                )
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "arguments", "match"),
    [
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(), "https://a.b/c.j"],
            "url",
            id="url_15_chars",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(), "https://example.com/" + "a" * 235],
            "url",
            id="url_255_chars",
        ),
        pytest.param(
            "set_display_catalog_theme",
            [CatalogTheme.UNKNOWN, jpeg_image()],
            "UNKNOWN",
            id="catalog_unknown",
        ),
        pytest.param(
            "set_display_custom_theme",
            [with_crc32(jpeg_image(), 0)],
            "checksum of 0",
            id="checksum_0",
        ),
        pytest.param("set_display_custom_theme", [b""], "size", id="empty"),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(size=65535)],
            "size",
            id="over_65534_bytes",
        ),
        pytest.param(
            "set_display_catalog_theme",
            [CatalogTheme.CELESTIAL, jpeg_image(size=65535)],
            "size",
            id="catalog_over_65534_bytes",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image()[2:]],
            "JPEG",
            id="no_soi",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(frame_marker=0xC2)],
            "marker",
            id="progressive",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(before_frame=jpeg_segment(0xDD, b"\x00\x10"))],
            "marker",
            id="restart_interval",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(before_frame=b"\xff\xd0")],
            "marker",
            id="restart_marker",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(components=1)],
            "components",
            id="grayscale",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(precision=12)],
            "precision",
            id="12_bit",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(luma_sampling=0x12)],
            "sampling",
            id="sampling_1x2",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(width=481)],
            "480x200",
            id="width_481",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(height=199)],
            "480x200",
            id="height_199",
        ),
        pytest.param(
            "set_display_custom_theme",
            [jpeg_image(width=200, height=480)],
            "480x200",
            id="portrait",
        ),
    ],
)
async def test_theme_checks_before_writing(
    method: str,
    arguments: list[object],
    match: str,
) -> None:
    """A bad image, URL or theme raises before anything is written."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._client = mock.AsyncMock()  # noqa: SLF001
    with (
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
        pytest.raises(ValueError, match=match),
    ):
        await getattr(device, method)(*arguments)

    device._client.write_gatt_char.assert_not_called()  # noqa: SLF001


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(jpeg_scan(CELESTIAL_HEADER), id="celestial"),
        pytest.param(jpeg_scan(RHYTHMIC_HUE_HEADER), id="rhythmic_hue"),
        pytest.param(jpeg_image(luma_sampling=0x11), id="sampling_4_4_4"),
        pytest.param(jpeg_image(luma_sampling=0x21), id="sampling_4_2_2"),
        pytest.param(jpeg_image(size=65534), id="65534_bytes"),
    ],
)
def test_theme_image_check_accepts(image: bytes) -> None:
    """The app's catalog JPEGs and every baseline layout the charger decodes pass."""
    check_jpeg(image, THEME_IMAGE_LIMITS)


@pytest.mark.parametrize(
    ("image", "limits", "match"),
    [
        pytest.param(
            jpeg_image(width=320, height=240, luma_sampling=0x11),
            OTHER_LIMITS,
            None,
            id="other_display",
        ),
        pytest.param(
            jpeg_image(luma_sampling=0x11),
            OTHER_LIMITS,
            "320x240",
            id="wrong_size",
        ),
        pytest.param(
            jpeg_image(width=320, height=240),
            OTHER_LIMITS,
            "sampling",
            id="sampling_4_2_0",
        ),
        pytest.param(
            jpeg_image(width=320, height=240, luma_sampling=0x11, size=4097),
            OTHER_LIMITS,
            "size",
            id="over_4096_bytes",
        ),
        pytest.param(
            jpeg_image(width=320, height=240, components=1, luma_sampling=0x11),
            dataclasses.replace(OTHER_LIMITS, components=1),
            None,
            id="grayscale_display",
        ),
    ],
)
def test_image_check_follows_its_limits(
    image: bytes,
    limits: JpegLimits,
    match: str | None,
) -> None:
    """The check takes its size, sampling and component limits from its argument."""
    if match is None:
        check_jpeg(image, limits)
    else:
        with pytest.raises(ValueError, match=match):
            check_jpeg(image, limits)
