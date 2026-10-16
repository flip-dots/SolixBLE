"""Tests for the Prime Charging Station 240W (A91B2).

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE import (
    ClockFormat,
    ClockTheme,
    DisplayTimeout,
    LightStatus,
    PortSchedule,
    PortStatus,
    PortTimer,
    PrimeChargingStation240w,
)
from SolixBLE.const import (
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
)
from SolixBLE.constructs import Packet, PacketCommand
from SolixBLE.device import UUID_STRING
from SolixBLE.devices.prime_charging_station_240w import (
    KEEP_ALIVE_INTERVAL,
    AcLightMode,
    ChargingMode,
    ChargingSubmode,
)
from SolixBLE.protocols import NegotiatedSession, PlainOuter
from tests.const import MOCK_BLE_DEVICE, NEGOTIATION_RESPONSES_SOLIX
from tests.helpers import MockDevice

#: The typed timestamp trailer every command ends with, under fake_time.
TIMESTAMP_TRAILER = "fe0503ef79b569"

#: A 4a00 snapshot from a v1.1.2.4 unit (prime.md, A91B2 worked frame): no
#: faults; AC 1 and 2 on with no schedule and their countdowns off; USB C1 on
#: with both schedule times disabled; the clock display on with theme index 1;
#: brightness 0 and the display always on; Smart Dynamic; no update; a 24 h
#: clock and the AC light normal.
SNAPSHOT = (
    "00a10131a203026404a303020000a4080400000000000000a5080400000000000000a6080400"
    "000000000000a70804019813db006900a8080400e11303000000a9080400e11300000000aa13"
    "0401ff0c0000ff0c000000302a0000302a0000ab130401ff0c0000ff0c000000580200005802"
    "0000ac020181ad020100ae03040000af03040000b01304010001007f00170004005802000000"
    "000000b1130401ff0c0000ff0c000000100e000000000000b2130401ff0c0000ff0c00000020"
    "1c000000000000b3130401ff0c0000ff0c0000005802000000000000b4020101b5020100fe05"
    "0300b95569"
)
UNSET_SCHEDULE = PortSchedule(None, 12, 0, frozenset(), None, 12, 0, frozenset())
C1_SCHEDULE = PortSchedule(
    on_time_enabled=False,
    on_time_hour=1,
    on_time_minute=0,
    on_time_weekdays=frozenset(range(7)),
    off_time_enabled=False,
    off_time_hour=23,
    off_time_minute=0,
    off_time_weekdays=frozenset({2}),
)
SECONDS_IN_3_HOURS = 10800

#: A 4303 stream frame from the same unit: USB C4 on at 5.016 V, 0.138 A and
#: 0.65 W, both USB A ports idle at 5.089 V.
STREAM = (
    "a10131a2080400000000000000a3080400000000000000a4080400000000000000a50804019813"
    "8a004100a6080400e11303000000a7080400e11300000000fe050300b95569"
)
C4_VOLTAGE = 5.016
C4_CURRENT = 0.138
C4_POWER = 0.65
A1_VOLTAGE = 5.089

#: The snapshot's port fault bitmap (a3, a u16 under type 02); faults set the
#: bits by hand.
PORT_FAULTS_PREFIX = "a30302"

#: The firmware update state (af): an update under way at 42 %.
SNAPSHOT_UPDATING = "af0304012a"
UPDATE_PROGRESS = 42

TEST_SERIAL = "A91B2TESTSN00001"

#: A schedule for set_schedule_*: on at 08:00 every day, off at 22:00 on
#: Wednesdays, both armed.
SCHEDULE = PortSchedule(
    on_time_enabled=True,
    on_time_hour=8,
    on_time_minute=0,
    on_time_weekdays=frozenset(range(7)),
    off_time_enabled=True,
    off_time_hour=22,
    off_time_minute=0,
    off_time_weekdays=frozenset({2}),
)


def test_defaults_before_any_frame() -> None:
    """Every reading has a default before the first negotiation, snapshot or stream."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)

    assert device.serial_number == DEFAULT_METADATA_STRING
    assert device.software_version == DEFAULT_METADATA_STRING
    assert device.usb_port_c1 == PortStatus.UNKNOWN
    assert device.usb_c1_voltage == DEFAULT_METADATA_FLOAT
    assert device.ac_output_1 == PortStatus.UNKNOWN
    assert device.ac_output_1_schedule is None
    assert device.ac_output_1_timer is None
    assert device.clock_display_enabled is None
    assert device.display_theme == ClockTheme.UNKNOWN
    assert device.display_mode == LightStatus.UNKNOWN
    assert device.display_timeout == DEFAULT_METADATA_INT
    assert device.charging_mode == ChargingMode.UNKNOWN
    assert device.charging_submode is None
    assert device.firmware_updating is None
    assert device.firmware_update_progress == DEFAULT_METADATA_INT
    assert device.clock_format == ClockFormat.UNKNOWN
    assert device.light_mode == AcLightMode.UNKNOWN
    assert device.over_temperature is None
    assert device.usb_c1_fault is None
    assert device.usb_a_fault is None


@pytest.mark.asyncio
async def test_snapshot_decodes_outlets_records_and_settings() -> None:
    """A real 4a00 snapshot fills the outlets, records and settings, not telemetry."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT),
        encrypted=False,
    )

    assert device.software_version == "1.1.2.4"
    assert device.ac_output_1 == PortStatus.OUTPUT
    assert device.ac_output_2 == PortStatus.OUTPUT
    assert device.ac_output_1_schedule == UNSET_SCHEDULE
    assert device.ac_output_1_timer == PortTimer(
        enabled=False,
        seconds=SECONDS_IN_3_HOURS,
        remaining=SECONDS_IN_3_HOURS,
    )
    assert device.ac_output_2_timer == PortTimer(
        enabled=False,
        seconds=600,
        remaining=600,
    )
    assert device.usb_c1_schedule == C1_SCHEDULE
    assert device.usb_c1_timer == PortTimer(enabled=False, seconds=600, remaining=0)
    assert device.usb_c2_timer == PortTimer(enabled=False, seconds=3600, remaining=0)
    assert device.usb_c3_timer == PortTimer(enabled=False, seconds=7200, remaining=0)
    assert device.usb_c4_schedule == UNSET_SCHEDULE
    assert device.clock_display_enabled is True
    assert device.display_theme == ClockTheme.THEME_2
    assert device.display_mode == LightStatus.LOW
    assert device.display_timeout == DisplayTimeout.S0.value
    assert device.charging_mode == ChargingMode.SMART_DYNAMIC
    assert device.charging_submode is None
    assert device.firmware_updating is False
    assert device.firmware_update_progress == 0
    assert device.clock_format == ClockFormat.HOUR_24
    assert device.light_mode == AcLightMode.NORMAL
    assert device.over_temperature is False
    assert device.usb_a_fault is False
    assert device._data is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_stream_fills_ports_not_snapshot() -> None:
    """A real 4303 stream frame fills the six ports and leaves the snapshot empty."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0x303,
        payload=bytes.fromhex(STREAM),
        encrypted=False,
    )

    assert device.usb_port_c1 == PortStatus.NOT_CONNECTED
    assert device.usb_port_c4 == PortStatus.OUTPUT
    assert device.usb_c4_voltage == C4_VOLTAGE
    assert device.usb_c4_current == C4_CURRENT
    assert device.usb_c4_power == C4_POWER
    assert device.usb_a1_voltage == A1_VOLTAGE
    assert device.usb_a2_power == 0.0
    assert device._snapshot is None  # noqa: SLF001
    assert device.ac_output_1 == PortStatus.UNKNOWN


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
    """a3 bit 0 is over temperature, 1-4 the USB C faults and 5 the USB A rail."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
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
@pytest.mark.parametrize(
    ("record", "mode", "submode"),
    [
        pytest.param(
            "ae03040000",
            ChargingMode.SMART_DYNAMIC,
            None,
            id="smart_dynamic",
        ),
        pytest.param(
            "ae03040100",
            ChargingMode.HIGH_POWER,
            ChargingSubmode.MODE_1,
            id="high_power_1",
        ),
        pytest.param(
            "ae03040102",
            ChargingMode.HIGH_POWER,
            ChargingSubmode.MODE_3,
            id="high_power_3",
        ),
        pytest.param(
            "ae03040103",
            ChargingMode.HIGH_POWER,
            ChargingSubmode.UNKNOWN,
            id="high_power_unknown",
        ),
        pytest.param("ae03040500", ChargingMode.UNKNOWN, None, id="unknown_mode"),
    ],
)
async def test_snapshot_decodes_charging_mode(
    record: str,
    mode: ChargingMode,
    submode: ChargingSubmode | None,
) -> None:
    """Ae carries the mode, then the High-Power sub-mode, read only under High-Power."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(record),
        encrypted=False,
    )

    assert device.charging_mode == mode
    assert device.charging_submode == submode


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "mode", "display_timeout"),
    [
        pytest.param(
            "ad020123",
            LightStatus.HIGH,
            DisplayTimeout.S300,
            id="high_5_min",
        ),
        pytest.param(
            "ad020111",
            LightStatus.MEDIUM,
            DisplayTimeout.S30,
            id="medium_30_s",
        ),
        pytest.param(
            "ad020157",
            LightStatus.UNKNOWN,
            DisplayTimeout.UNKNOWN,
            id="unknown",
        ),
    ],
)
async def test_snapshot_decodes_display_settings(
    record: str,
    mode: LightStatus,
    display_timeout: DisplayTimeout,
) -> None:
    """The ad tag's high nibble is the brightness level, the low one the timeout."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(record),
        encrypted=False,
    )

    assert device.display_mode == mode
    assert device.display_timeout == display_timeout.value


@pytest.mark.asyncio
async def test_snapshot_decodes_firmware_update() -> None:
    """Af carries the update flag and its progress."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        msgtype=0xA00,
        payload=bytes.fromhex(SNAPSHOT_UPDATING),
        encrypted=False,
    )

    assert device.firmware_updating is True
    assert device.firmware_update_progress == UPDATE_PROGRESS


def test_serial_number_from_announcement() -> None:
    """The serial the device announced in negotiation stage 3 reads back."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    device._session = NegotiatedSession(device._outer_class(), device)  # noqa: SLF001
    device._session.announcement.serial = TEST_SERIAL.encode()  # noqa: SLF001

    assert device.serial_number == TEST_SERIAL


@pytest.mark.asyncio
async def test_negotiates_plainly_then_requests_only_the_snapshot(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """With no advertisement it opens on the plain outer, then sends just 4200."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001
    assert device._outer_class is PlainOuter  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for responses in NEGOTIATION_RESPONSES_SOLIX.values():
            mock_bluetooth.expect_ordered(
                None,
                [bytes.fromhex(response) for response in responses],
            )
        mock_bluetooth.expect_ordered(None)
        assert await device.connect()
        mock_bluetooth.check_assertions()

    assert set(mock_bluetooth.write_responses) == {False}
    opening = Packet.parse(mock_bluetooth.writes[0])
    assert PacketCommand.build(opening).hex() == "0001"
    assert UUID_STRING.encode() in opening.payload_bytes
    after = Packet.parse(mock_bluetooth.writes[-1])
    assert PacketCommand.build(after).hex() == "4200"
    sent = device._decrypt_payload(after.payload_bytes).hex()  # noqa: SLF001
    assert sent == "a10121" + TIMESTAMP_TRAILER


@pytest.mark.asyncio
async def test_keep_alive_requests_snapshot_then_stream(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """The keep-alive requests a fresh snapshot, then re-arms the stream."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for responses in NEGOTIATION_RESPONSES_SOLIX.values():
            mock_bluetooth.expect_ordered(
                None,
                [bytes.fromhex(response) for response in responses],
            )
        mock_bluetooth.expect_ordered(None)
        assert await device.connect()

        # The connect's own keep-alive task ends at once with no interval set
        assert device._keep_alive_task is not None  # noqa: SLF001
        await device._keep_alive_task  # noqa: SLF001

        sent_before = len(mock_bluetooth.writes)
        device._KEEP_ALIVE_INTERVAL = KEEP_ALIVE_INTERVAL  # noqa: SLF001
        mock_bluetooth.expect_ordered(None)
        mock_bluetooth.expect_ordered(None)
        interval = await device._keep_alive()  # noqa: SLF001

    sent = [Packet.parse(write) for write in mock_bluetooth.writes[sent_before:]]
    assert interval == KEEP_ALIVE_INTERVAL
    assert [PacketCommand.build(packet).hex() for packet in sent] == ["4200", "420b"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "arguments", "cmd", "payload"),
    [
        pytest.param(
            "turn_ac_1_on",
            [],
            "4207",
            "a10121a2020100a3020101",
            id="ac_1_on",
        ),
        pytest.param(
            "turn_ac_2_off",
            [],
            "4207",
            "a10121a2020101a3020100",
            id="ac_2_off",
        ),
        pytest.param(
            "turn_usb_c1_on",
            [],
            "4207",
            "a10121a2020102a3020101",
            id="c1_on",
        ),
        pytest.param(
            "turn_usb_c4_off",
            [],
            "4207",
            "a10121a2020105a3020100",
            id="c4_off",
        ),
        # prime-a2345-a91b2.md: the app's ac_1 countdown of 10800 s
        pytest.param(
            "set_timer_ac_1",
            [SECONDS_IN_3_HOURS],
            "4209",
            "a10121a2020100a3060401302a0000",
            id="ac_1_timer_3_h",
        ),
        pytest.param(
            "set_timer_usb_c2",
            [0],
            "4209",
            "a10121a2020103a306040000000000",
            id="c2_timer_disarm",
        ),
        pytest.param(
            "set_display_mode",
            [LightStatus.HIGH],
            "4204",
            "a10121a2020102",
            id="display_high",
        ),
        pytest.param(
            "set_display_timeout",
            [DisplayTimeout.S300],
            "4203",
            "a10121a2020103",
            id="display_timeout_5_min",
        ),
        # The app's captured a203020101 (type 02)
        pytest.param(
            "set_charging_mode",
            [ChargingMode.HIGH_POWER, ChargingSubmode.MODE_2],
            "4206",
            "a10121a203020101",
            id="high_power_2",
        ),
        pytest.param(
            "set_clock_format",
            [ClockFormat.HOUR_12],
            "4210",
            "a10121a2020100",
            id="clock_12_h",
        ),
        pytest.param(
            "set_light_mode",
            [AcLightMode.SLEEP],
            "4214",
            "a10121a2020101",
            id="light_sleep",
        ),
    ],
)
async def test_command_payloads(  # noqa: PLR0913, PLR0917
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    method: str,
    arguments: list[object],
    cmd: str,
    payload: str,
) -> None:
    """Each command sends one frame with the expected command and payload."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for responses in NEGOTIATION_RESPONSES_SOLIX.values():
            mock_bluetooth.expect_ordered(
                None,
                [bytes.fromhex(response) for response in responses],
            )
        mock_bluetooth.expect_ordered(None)
        assert await device.connect()
        mock_bluetooth.expect_ordered(None)
        await getattr(device, method)(*arguments)

    packet = Packet.parse(mock_bluetooth.writes[-1])
    assert PacketCommand.build(packet).hex() == cmd
    sent = device._decrypt_payload(packet.payload_bytes).hex()  # noqa: SLF001
    assert sent == payload + TIMESTAMP_TRAILER


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("display", "method", "arguments", "sent"),
    [
        # Clock display off on theme index 2: on keeps the theme
        pytest.param("02", "turn_clock_display_on", [], "82", id="on_keeps_theme_3"),
        pytest.param("81", "turn_clock_display_off", [], "01", id="off_keeps_theme_2"),
        # A theme turns the clock display on, as the app's 4205 does
        pytest.param(
            "02",
            "set_display_theme",
            [ClockTheme.THEME_1],
            "80",
            id="theme_1_turns_clock_on",
        ),
        pytest.param(
            "80",
            "set_display_theme",
            [ClockTheme.THEME_3],
            "82",
            id="theme_3",
        ),
    ],
)
async def test_display_byte_commands(  # noqa: PLR0913, PLR0917
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    display: str,
    method: str,
    arguments: list[object],
    sent: str,
) -> None:
    """4205 carries the clock display switch in bit 7 and the theme index."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for responses in NEGOTIATION_RESPONSES_SOLIX.values():
            mock_bluetooth.expect_ordered(
                None,
                [bytes.fromhex(response) for response in responses],
            )
        mock_bluetooth.expect_ordered(None)
        assert await device.connect()
        await device._process_session(  # noqa: SLF001
            msgtype=0xA00,
            payload=bytes.fromhex("ac0201" + display),
            encrypted=False,
        )
        mock_bluetooth.expect_ordered(None)
        await getattr(device, method)(*arguments)

    packet = Packet.parse(mock_bluetooth.writes[-1])
    assert PacketCommand.build(packet).hex() == "4205"
    payload = device._decrypt_payload(packet.payload_bytes).hex()  # noqa: SLF001
    assert payload == "a10121a20201" + sent + TIMESTAMP_TRAILER


@pytest.mark.asyncio
async def test_set_schedule_sends_on_time_then_off_time(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A schedule for AC outlet 2 goes out as two 4208s on port 1."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    device._KEEP_ALIVE_INTERVAL = None  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for responses in NEGOTIATION_RESPONSES_SOLIX.values():
            mock_bluetooth.expect_ordered(
                None,
                [bytes.fromhex(response) for response in responses],
            )
        mock_bluetooth.expect_ordered(None)
        assert await device.connect()
        mock_bluetooth.expect_ordered(None)
        mock_bluetooth.expect_ordered(None)
        await device.set_schedule_ac_2(SCHEDULE)

    sent = [Packet.parse(write) for write in mock_bluetooth.writes[-2:]]
    assert [PacketCommand.build(packet).hex() for packet in sent] == ["4208", "4208"]
    assert [
        device._decrypt_payload(packet.payload_bytes).hex()  # noqa: SLF001
        for packet in sent
    ] == [
        "a10121a2020101a3020101a405030108007f" + TIMESTAMP_TRAILER,
        "a10121a2020101a3020100a4050301160004" + TIMESTAMP_TRAILER,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        pytest.param("set_display_timeout", [DisplayTimeout.S20], id="timeout_20_s"),
        pytest.param("set_display_mode", [LightStatus.OFF], id="display_off"),
        pytest.param("set_display_mode", [LightStatus.SOS], id="display_sos"),
        pytest.param("set_display_mode", [LightStatus.UNKNOWN], id="display_unknown"),
        pytest.param("set_charging_mode", [ChargingMode.UNKNOWN], id="mode_unknown"),
        pytest.param(
            "set_charging_mode",
            [ChargingMode.HIGH_POWER, ChargingSubmode.UNKNOWN],
            id="submode_unknown",
        ),
        pytest.param("set_clock_format", [ClockFormat.UNKNOWN], id="clock_unknown"),
        pytest.param("set_light_mode", [AcLightMode.UNKNOWN], id="light_unknown"),
        pytest.param("set_display_theme", [ClockTheme.CATALOG], id="theme_catalog"),
        pytest.param("set_display_theme", [ClockTheme.CUSTOM], id="theme_custom"),
    ],
)
async def test_unsupported_settings_are_rejected(
    method: str,
    arguments: list[object],
) -> None:
    """A value the station can't take raises before anything is sent."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)

    with pytest.raises(ValueError, match=r"not supported|Cannot set"):
        await getattr(device, method)(*arguments)
