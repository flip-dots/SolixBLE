"""Tests for the Prime Charging Station 240W (A91B2).

.. moduleauthor:: kb1ibt
"""

from typing import cast
from unittest import mock

import pytest

from SolixBLE import (
    AcLightMode,
    ChargingMode,
    ClockFormat,
    DisplayTimeout,
    PortSchedule,
    PortStatus,
    PortTimer,
    PrimeChargingStation240w,
)
from SolixBLE.const import DEFAULT_METADATA_INT, DEFAULT_METADATA_STRING
from SolixBLE.constructs import Packet
from SolixBLE.devices.prime_charging_station_240w import KEEP_ALIVE_INTERVAL
from tests.const import MOCK_BLE_DEVICE

SESSION_PATTERN = "03010f"
TEST_SECRET = bytes(range(32))
TEST_SERIAL = b"A91B2TESTSN00001"
#: The timestamp fake_time pins for devices on the plain-text path.
FAKE_TIMESTAMP = "42ad8c69"


def _port(
    key: str,
    status: int,
    millivolts: int,
    milliamps: int,
    centiwatts: int,
) -> str:
    """Build a port parameter: the status then voltage, current and power."""
    value = (
        bytes([0x04, status])
        + millivolts.to_bytes(2, "little")
        + milliamps.to_bytes(2, "little")
        + centiwatts.to_bytes(2, "little")
    )
    return key + f"{len(value):02x}" + value.hex()


def _outlet(
    key: str,
    switch: int,
    timer: tuple[int, int, int] = (0, 0, 0),
    start: tuple[int, int, int, int] = (0, 0, 0, 0),
    end: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> str:
    """Build a switchable port's record: switch, both schedule triggers, timer."""
    value = (
        bytes([0x04, switch])
        + bytes(start)
        + bytes(end)
        + bytes([timer[0]])
        + timer[1].to_bytes(4, "little")
        + timer[2].to_bytes(4, "little")
    )
    return key + f"{len(value):02x}" + value.hex()


#: USB C1 active at 5.0 V, 3.0 A and 15.0 W, the other five ports idle.
STREAM_PORTS = _port("a2", 1, 5000, 3000, 1500) + "".join(
    _port(key, 0, 0, 0, 0) for key in ("a3", "a4", "a5", "a6", "a7")
)
AC_1_TIMER = PortTimer(1, 10800, 9000)
AC_1_SCHEDULE = PortSchedule(1, 1, 0, 0x7F, 1, 23, 0, 0x04)
C1_VOLTAGE = 5.0
C1_CURRENT = 3.0
C1_POWER = 15.0
DISPLAY_THEME = 3
DISPLAY_BRIGHTNESS = 2
DISPLAY_TIMEOUT = 300
CHARGING_SUBMODE = 2
#: A 4a00 snapshot: version 1.1.2.4, AC outlet 1 on with a timer and schedule,
#: AC outlet 2 off, USB C1 on with nothing set, display on with theme 3,
#: brightness 2 and a five minute timeout, high power mode sub-mode 2, a 24
#: hour clock and the AC light dimmed.
SNAPSHOT = (
    "a203026404"
    + _outlet(
        "aa",
        1,
        timer=(1, 10800, 9000),
        start=(1, 1, 0, 0x7F),
        end=(1, 23, 0, 0x04),
    )
    + _outlet("ab", 0)
    + _outlet("b0", 1)
    + "ac020182ad020123ae03040101b4020101b5020101"
)
#: Negotiation stage 3 reply with the serial number at a4.
PLAIN_0829 = (
    "a104f079b569a203000000a303000000a410" + TEST_SERIAL.hex() + "a506000000000000"
)


def _device() -> PrimeChargingStation240w:
    """Build a negotiated station with a fixed secret and a live client."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    device._shared_secret = TEST_SECRET
    device._client = mock.AsyncMock()
    return device


async def _receive(device: PrimeChargingStation240w, cmd: str, plaintext: str) -> None:
    """Deliver one encrypted session frame to the device as a notification."""
    packet = Packet.build(
        {
            "pattern": bytes.fromhex(SESSION_PATTERN),
            "cmd": bytes.fromhex(cmd),
            "payload_bytes": device._encrypt_payload(bytes.fromhex(plaintext)),
        },
    )
    client = device._client
    assert client is not None
    await device._process_notification(client, 0, bytearray(packet))


def _sent(device: PrimeChargingStation240w) -> list[tuple[str, str]]:
    """Return the command and decrypted payload of every packet the device wrote."""
    frames = []
    client = cast("mock.AsyncMock", device._client)
    for call in client.write_gatt_char.call_args_list:
        packet = Packet.parse(call.args[1])
        frames.append(
            (packet.cmd.hex(), device._decrypt_payload(packet.payload_bytes).hex()),
        )
    return frames


def test_defaults_before_any_frame() -> None:
    """Every reading has a default before the first negotiation, snapshot or stream."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)

    assert device.serial_number == DEFAULT_METADATA_STRING
    assert device.software_version == DEFAULT_METADATA_STRING
    assert device.ac_output_1 == PortStatus.UNKNOWN
    assert device.ac_output_1_timer is None
    assert device.is_display_on is False
    assert device.display_theme == DEFAULT_METADATA_INT
    assert device.display_timeout == DEFAULT_METADATA_INT
    assert device.charging_mode == ChargingMode.UNKNOWN
    assert device.clock_format == ClockFormat.UNKNOWN
    assert device.ac_light_mode == AcLightMode.UNKNOWN


@pytest.mark.asyncio
async def test_snapshot_decodes_outlets_records_and_settings() -> None:
    """A 4a00 snapshot fills the outlet states, records and settings, not telemetry."""
    device = _device()
    await _receive(device, "4a00", SNAPSHOT)

    assert device.software_version == "1.1.2.4"
    assert device.ac_output_1 == PortStatus.OUTPUT
    assert device.ac_output_2 == PortStatus.NOT_CONNECTED
    assert device.ac_output_1_timer == AC_1_TIMER
    assert device.ac_output_1_schedule == AC_1_SCHEDULE
    assert device.usb_c1_timer == PortTimer(0, 0, 0)
    assert device.usb_c4_timer is None
    assert device.is_display_on is True
    assert device.display_theme == DISPLAY_THEME
    assert device.display_brightness == DISPLAY_BRIGHTNESS
    assert device.display_timeout == DISPLAY_TIMEOUT
    assert device.charging_mode == ChargingMode.HIGH_POWER
    assert device.charging_submode == CHARGING_SUBMODE
    assert device.clock_format == ClockFormat.HOUR_24
    assert device.ac_light_mode == AcLightMode.SLEEP
    assert device._data is None


@pytest.mark.asyncio
async def test_stream_fills_ports_not_snapshot() -> None:
    """A 4303 stream frame fills the six ports and leaves the snapshot empty."""
    device = _device()
    await _receive(device, "4303", STREAM_PORTS)

    assert device.usb_port_c1 == PortStatus.OUTPUT
    assert device.usb_c1_voltage == C1_VOLTAGE
    assert device.usb_c1_current == C1_CURRENT
    assert device.usb_c1_power == C1_POWER
    assert device.usb_a2_power == 0.0
    assert device._data_snapshot is None
    assert device.ac_output_1 == PortStatus.UNKNOWN


@pytest.mark.asyncio
async def test_serial_number_from_negotiation() -> None:
    """The serial number the device reports in negotiation stage 3 is kept."""
    device = PrimeChargingStation240w(MOCK_BLE_DEVICE)
    with mock.patch.object(device, "_send_packet", new=mock.AsyncMock()):
        await device._process_negotiation(
            bytes.fromhex("0829"),
            bytes.fromhex(PLAIN_0829),
        )

    assert device.serial_number == TEST_SERIAL.decode()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time", "fast_sleep")
async def test_post_connect_confers_then_requests_stream() -> None:
    """Connecting confers timezone and serial, then requests snapshot and stream."""
    device = _device()
    device._serial_number = TEST_SERIAL

    await device._post_connect()

    frames = _sent(device)
    assert [cmd for cmd, _ in frames] == ["4022", "4023", "4200", "420b"]
    assert frames[0][1].startswith(f"a104{FAKE_TIMESTAMP}a30400000000a5")
    assert frames[1][1] == f"a104{FAKE_TIMESTAMP}a310{TEST_SERIAL.hex()}"
    assert frames[2][1] == f"a10121fe0503{FAKE_TIMESTAMP}"


@pytest.mark.asyncio
@pytest.mark.usefixtures("fast_sleep")
async def test_keep_alive_requests_snapshot_then_stream() -> None:
    """The keep-alive requests a fresh snapshot, then re-arms the stream."""
    device = _device()

    assert await device._keep_alive() == KEEP_ALIVE_INTERVAL
    assert [cmd for cmd, _ in _sent(device)] == ["4200", "420b"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time")
@pytest.mark.parametrize(
    ("call", "arguments", "expected"),
    [
        pytest.param("turn_ac_1_on", [], "4207a10121a2020100a3020101", id="ac_1_on"),
        pytest.param("turn_ac_2_off", [], "4207a10121a2020101a3020100", id="ac_2_off"),
        pytest.param(
            "turn_usb_c1_on",
            [],
            "4207a10121a2020102a3020101",
            id="usb_c1_on",
        ),
        pytest.param(
            "turn_usb_c4_off",
            [],
            "4207a10121a2020105a3020100",
            id="usb_c4_off",
        ),
        pytest.param(
            "set_timer_usb_c1",
            [300],
            "4209a10121a2020102a30604012c010000",
            id="usb_c1_timer_5m",
        ),
        pytest.param(
            "set_timer_ac_1",
            [0],
            "4209a10121a2020100a306040000000000",
            id="ac_1_timer_disarm",
        ),
        pytest.param(
            "set_display_brightness",
            [2],
            "4204a10121a2020102",
            id="display_brightness",
        ),
        pytest.param(
            "set_display_timeout",
            [DisplayTimeout.S300],
            "4203a10121a2020102",
            id="display_timeout_5m",
        ),
        pytest.param(
            "set_display_timeout",
            [DisplayTimeout.S0],
            "4203a10121a2020104",
            id="display_timeout_always",
        ),
        pytest.param(
            "set_charging_mode",
            [ChargingMode.HIGH_POWER, 2],
            "4206a10121a203030101",
            id="charging_mode",
        ),
        pytest.param(
            "set_clock_format",
            [ClockFormat.HOUR_24],
            "4210a10121a2020101",
            id="clock_format",
        ),
        pytest.param(
            "set_ac_light_mode",
            [AcLightMode.SLEEP],
            "4214a10121a2020101",
            id="ac_light_mode",
        ),
    ],
)
async def test_command_frames(call: str, arguments: list, expected: str) -> None:
    """Each command sends one session frame with the expected command and payload."""
    device = _device()

    await getattr(device, call)(*arguments)

    frames = _sent(device)
    assert len(frames) == 1
    assert frames[0][0] + frames[0][1] == f"{expected}fe0503{FAKE_TIMESTAMP}"


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time")
async def test_set_schedule_sends_both_triggers() -> None:
    """Setting a schedule sends the on-time trigger then the off-time trigger."""
    device = _device()

    await device.set_schedule_usb_c1(AC_1_SCHEDULE)

    assert _sent(device) == [
        ("4208", f"a10121a2020102a3020101a405030101007ffe0503{FAKE_TIMESTAMP}"),
        ("4208", f"a10121a2020102a3020100a4050301170004fe0503{FAKE_TIMESTAMP}"),
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time")
async def test_display_commands_keep_the_other_half_of_the_byte() -> None:
    """Turning the display off keeps the snapshot's theme, and a new theme the state."""
    device = _device()
    await _receive(device, "4a00", SNAPSHOT)

    await device.turn_display_off()
    await device.set_display_theme(1)

    assert [payload[:14] for _, payload in _sent(device)] == [
        "a10121a2020102",
        "a10121a2020180",
    ]


@pytest.mark.asyncio
async def test_unsupported_settings_are_rejected() -> None:
    """Values the device cannot store raise before anything is sent."""
    device = _device()

    with pytest.raises(ValueError, match="not supported"):
        await device.set_display_timeout(DisplayTimeout.S20)
    with pytest.raises(ValueError, match="Theme"):
        await device.set_display_theme(4)
    with pytest.raises(ValueError, match="charging mode"):
        await device.set_charging_mode(ChargingMode.UNKNOWN)
    cast("mock.AsyncMock", device._client).write_gatt_char.assert_not_called()
