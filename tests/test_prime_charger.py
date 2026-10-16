"""Tests for the Prime Charger 250W (A2345) snapshot, settings and keep-alive.

.. moduleauthor:: kb1ibt
"""

from collections.abc import Callable
from unittest import mock

import pytest

from SolixBLE import PrimeCharger250w
from SolixBLE.const import DEFAULT_METADATA_INT, DEFAULT_METADATA_STRING
from SolixBLE.constructs import Packet
from SolixBLE.devices.prime_charger_250w import (
    KEEP_ALIVE_INTERVAL,
    CatalogTheme,
    ChargingMode,
    KnobDirection,
    ScreensaverWindow,
)
from SolixBLE.protocols import EncryptedOuter, NegotiatedSession
from SolixBLE.states import (
    ClockFormat,
    ClockTheme,
    PortPriority,
    PortSchedule,
    PortTimer,
)
from tests.const import MOCK_BLE_DEVICE, NEGOTIATION_RESPONSES_PRIME
from tests.helpers import MockDevice

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
        cmd=bytes.fromhex("ca00"),
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
        cmd=bytes.fromhex("4303"),
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
        cmd=bytes.fromhex("ca00"),
        payload=bytes.fromhex(SNAPSHOT_VERSION),
        encrypted=False,
    )

    assert seen == [True]


@pytest.mark.asyncio
async def test_reset_clears_snapshot_with_data() -> None:
    """The snapshot survives a reset that keeps data, not one that drops it."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        cmd=bytes.fromhex("ca00"),
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
        Packet.parse(call.args[1]).cmd.hex()
        for call in device._client.write_gatt_char.call_args_list  # noqa: SLF001
    ]
    assert sent == ["4200", "420b"]
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

    sent = [Packet.parse(write).cmd.hex() for write in mock_bluetooth.writes]
    assert sent[-2:] == ["4200", "420a"]
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
        cmd=bytes.fromhex("ca00"),
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
        cmd=bytes.fromhex("ca00"),
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
        cmd=bytes.fromhex("ca00"),
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
            cmd=bytes.fromhex("ca00"),
            payload=bytes.fromhex(record),
            encrypted=False,
        )
        mock_bluetooth.expect_ordered(None)
        await getattr(device, method)(*arguments)

    assert set(mock_bluetooth.write_responses) == {False}
    packet = Packet.parse(mock_bluetooth.writes[-1])
    assert packet.cmd.hex() == "4205"
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
            cmd=bytes.fromhex("ca00"),
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
        cmd=bytes.fromhex("ca00"),
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
        cmd=bytes.fromhex("ca00"),
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
        cmd=bytes.fromhex("ca00"),
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
        cmd=bytes.fromhex("ca00"),
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
    assert [block["cmd"].hex() for block in sent] == ["4208", "4208"]
    assert [block["payload_bytes"].hex() for block in sent] == [
        f"a10121a2020101a3020101a405030101007f{timestamp}",
        f"a10121a2020101a3020100a4050300170004{timestamp}",
    ]


@pytest.mark.asyncio
async def test_snapshot_decodes_usb_pd_identity() -> None:
    """Bd carries each port's USB-PD vendor and product, be what it names."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        cmd=bytes.fromhex("ca00"),
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
    for cmd, payload in (("ca00", SNAPSHOT_FULL), ("4303", STREAM_IDENTITIES)):
        await device._process_session(  # noqa: SLF001
            cmd=bytes.fromhex(cmd),
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
        cmd=bytes.fromhex("ca00"),
        payload=bytes.fromhex(SNAPSHOT_PD_UNCHECKED),
        encrypted=False,
    )

    assert device.device_name_display_supported is None
