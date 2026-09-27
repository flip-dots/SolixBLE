"""Tests for the Prime Charger 250W (A2345) snapshot, schedule and timer.

.. moduleauthor:: kb1ibt
"""

import time
from unittest import mock

import pytest

from SolixBLE import PortSchedule, PortTimer, PrimeCharger250w
from SolixBLE.const import DEFAULT_METADATA_STRING
from SolixBLE.constructs import Packet
from tests.const import MOCK_BLE_DEVICE

#: A ca00 snapshot carrying only the USB C1 record: the schedule turns the port
#: on at 08:00 and off at 22:00 every day, and the timer is armed for 3600 s
#: with 1800 s left.
SNAPSHOT_C1_SCHEDULE_AND_TIMER = (
    "a10131aa1404010108007f0116007f01100e00000807000000fe05033d7ab569"
)
#: A 4303 stream frame with the six ports at a2-a7.
STREAM_PORTS = (
    "a10131a2080401881329016400a30804014024d8061c06a4080401004d9d08ee10a5080401"
    "084d1809b311a6080401801364003100a70804018013b7003100fe05033d7ab569"
)
#: A ca00 snapshot carrying only the software version, 2116 as a 16-bit integer.
SNAPSHOT_VERSION = "a203024408"
#: The device's negotiation stage 3 reply, with its serial number at a4.
PLAIN_4829 = (
    "00a10103a2054553503332a307302e302e302e33a410"
    + b"A2345TESTSN00001".hex()
    + "a5067ce91346c50c"
)
SESSION_PATTERN = "030111"
TEST_SECRET = bytes(range(32))

C1_SCHEDULE = PortSchedule(1, 8, 0, 0x7F, 1, 22, 0, 0x7F)
C1_TIMER = PortTimer(1, 3600, 1800)
C1_CURRENT = 0.297


def _device() -> PrimeCharger250w:
    """Build an authorized charger with a fixed secret and a live client."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._shared_secret = TEST_SECRET
    device._authorized = True
    device._client = mock.Mock(is_connected=True)
    return device


async def _receive(device: PrimeCharger250w, cmd: str, plaintext: str) -> None:
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


@pytest.mark.asyncio
async def test_snapshot_decodes_schedule_and_timer() -> None:
    """A ca00 snapshot fills the schedule and timer without touching telemetry."""
    device = _device()
    await _receive(device, "ca00", SNAPSHOT_C1_SCHEDULE_AND_TIMER)

    assert device.usb_c1_schedule == C1_SCHEDULE
    assert device.usb_c1_timer == C1_TIMER
    assert device.usb_c2_schedule is None
    assert device.usb_c2_timer is None
    assert device._data is None


@pytest.mark.asyncio
async def test_stream_fills_telemetry_not_snapshot() -> None:
    """A 4303 stream frame fills telemetry and leaves the snapshot empty."""
    device = _device()
    await _receive(device, "4303", STREAM_PORTS)

    assert device.usb_c1_current == C1_CURRENT
    assert device._data_snapshot is None
    assert device.usb_c1_timer is None


@pytest.mark.asyncio
async def test_snapshot_runs_state_changed_callbacks() -> None:
    """A snapshot runs the registered state-changed callbacks once."""
    device = _device()
    seen: list[bool] = []
    device.add_callback(lambda: seen.append(True))
    await _receive(device, "ca00", SNAPSHOT_C1_SCHEDULE_AND_TIMER)

    assert seen == [True]


@pytest.mark.asyncio
async def test_reset_session_clears_snapshot_with_data() -> None:
    """The snapshot survives a session reset that keeps data and not one that drops it."""
    device = _device()
    await _receive(device, "ca00", SNAPSHOT_C1_SCHEDULE_AND_TIMER)

    device._reset_session(reset_data=False)
    assert device.usb_c1_timer == C1_TIMER

    device._reset_session()
    assert device._record("aa") == b""
    assert device.usb_c1_timer is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("fast_sleep")
async def test_keep_alive_requests_snapshot_then_stream() -> None:
    """The keep-alive requests a fresh snapshot, then re-arms the stream."""
    device = _device()
    device._client = mock.AsyncMock()

    await device._keep_alive()

    sent = [
        Packet.parse(call.args[1]).cmd.hex()
        for call in device._client.write_gatt_char.call_args_list
    ]
    assert sent == ["4200", "420b"]


@pytest.mark.asyncio
async def test_software_version_from_snapshot() -> None:
    """The snapshot's 16-bit version integer reads as its four decimal digits."""
    device = _device()
    assert device.software_version == DEFAULT_METADATA_STRING

    await _receive(device, "ca00", SNAPSHOT_VERSION)
    assert device.software_version == "2.1.1.6"


@pytest.mark.asyncio
async def test_serial_number_from_negotiation() -> None:
    """The serial number the device reports in negotiation stage 3 is kept."""
    device = _device()
    assert device.serial_number == DEFAULT_METADATA_STRING

    with mock.patch.object(device, "_send_packet", new=mock.AsyncMock()):
        await device._process_negotiation_encrypted(
            bytes.fromhex("4829"),
            bytes.fromhex(PLAIN_4829),
        )
    assert device.serial_number == "A2345TESTSN00001"


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_time")
async def test_set_schedule_sends_both_triggers() -> None:
    """Setting a schedule sends the on-time trigger then the off-time trigger."""
    device = PrimeCharger250w(MOCK_BLE_DEVICE)
    device._negotiation_timestamp = time.time()
    device._client = mock.AsyncMock()
    with (
        mock.patch.object(device, "_encrypt_payload", side_effect=lambda x: x),
        mock.patch("SolixBLE.constructs.Packet.build") as mock_build,
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
    ):
        await device.set_schedule_usb_c1(PortSchedule(1, 1, 0, 0x7F, 1, 23, 0, 0x04))

    timestamp = device._timestamp().hex()
    built = [c.args[0] for c in mock_build.call_args_list]
    assert [b["cmd"] for b in built] == [bytes.fromhex("4208")] * 2
    assert [b["payload_bytes"].hex() for b in built] == [
        f"a10121a2020100a3020101a405030101007ffe04{timestamp}",
        f"a10121a2020100a3020100a4050301170004fe04{timestamp}",
    ]
