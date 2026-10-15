"""
Tests for the Anker Prime specific functionality.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
"""

from unittest import mock

import pytest

from SolixBLE.const import DEFAULT_METADATA_FLOAT, DEFAULT_METADATA_INT
from SolixBLE.constructs import PORT_RECORD, Channel, Packet, PacketCommand, Parameters
from SolixBLE.prime_device import PrimeDevice
from SolixBLE.states import PortSchedule, PortStatus, PortTimer
from tests.const import MOCK_BLE_DEVICE
from tests.helpers import install_session_keys

#: Client token the post-authorize test registers as the owner.
OWNER_TOKEN = "owner-token"  # noqa: S105

#: USB-C1 reading from a real captured 4303-stream record.
A4_VOLTAGE = 19.712
A4_CURRENT = 0.435
A4_POWER = 7.88


@pytest.mark.parametrize(
    "packet,decrypted_payload,shared_secret",
    [
        pytest.param(
            "ff094000030001402257ec69586f3500c8f858e0ba047f237f4e2ed8c50d2f39ba3587e4010275bea22242936f08788849272fb3f4cf7493be4a60bb9c9f0693",
            "a104f079b569a30400000000a518474d54304253542c4d332e352e302f312c4d31302e352e30",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_5_response",
        ),
        pytest.param(
            "ff094600030001402757ec69586f3501e8cf6185d8c4035707377af9af3a2e40b02b86e7531974f1c22440de6e43705566b77cf940e235b65abf4d413ece5f2c3781712f3742",
            "a104f079b569a22437396562656433352d646339632d343930342d623430632d373263346538363361613130",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_6_response",
        ),
        pytest.param(
            "ff09230003000f420057e9b8dfdeacda7991d3eb7f12093e55ff002aa9799bcc9216e3",
            "a10121fe04f079b569",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_7a_response",
        ),
        pytest.param(
            "ff09530003000f420a57e9b883d958e48e5b7de48d980206577e2dafbb3d604dea3686f3011969f0db2311906d142b5730ee2bfb11e3fbbe7485aac8877995310669156ec74645c962b419e579b385fd079967",
            "a10121a203044742a3250437396562656433352d646339632d343930342d623430632d373263346538363361613130a5020101fe04f079b569",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_7b_response",
        ),
        pytest.param(
            "ff092d0003000140221462ecff54785e445fd4ebc9c574f6e91ee4b316f4458b9bd1af3515b6b0820cdb4f1c4f",
            "a104b70eab69a304808fffffa5054353542d38",
            "c0779a39bfa7b290ba9cd3d96b6fdc22a1f6a9746d4fc81e942c3d95a3892d2f",
            id="from_external_logs",
        ),
    ],
)
def test_negotiation_encryption_session(
    packet: str,
    decrypted_payload: str,
    shared_secret: str,
):
    """
    Test that the encrypted packets produced by the library
    for negotiation are correct.

    This test takes a packet, extracts its payload, decrypts the
    payload, and then re-encrypts the payload and asserts that
    the encrypted and decrypted-then-re-encrypted payload are
    identical.

    This test also asserts that the decrypted payload matches
    the expected one.
    """

    prime = PrimeDevice(MOCK_BLE_DEVICE)

    payload = Packet.parse(bytes.fromhex(packet)).payload_bytes
    install_session_keys(prime, bytes.fromhex(shared_secret))

    decrypted = prime._decrypt_payload(payload)
    assert decrypted.hex() == decrypted_payload

    re_encrypted = prime._encrypt_payload(decrypted)
    assert payload.hex() == re_encrypted.hex()


@pytest.mark.asyncio
async def test_post_authorize_sends_region_and_owner(
    fake_time: None,  # noqa: ARG001
) -> None:
    """
    Test the requests sent once a Prime client is authorized.

    ``4200`` asks for all device information and ``420a`` carries the region
    (typed 02) and this client's token as the owner (typed 04), both followed
    by the typed timestamp trailer.
    """
    prime = PrimeDevice(MOCK_BLE_DEVICE)
    prime._client_token = OWNER_TOKEN
    prime._client = mock.AsyncMock()
    timestamp = prime._timestamp().hex()

    with (
        mock.patch.object(
            prime,
            "_encrypt_payload",
            side_effect=lambda payload: payload,
        ),
        mock.patch("SolixBLE.constructs.Packet.build") as mock_build,
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
        mock.patch("SolixBLE.prime_device.region", return_value="US"),
    ):
        await prime._post_authorize()

    assert [call.args[0] for call in mock_build.call_args_list] == [
        {
            **PacketCommand.parse(bytes.fromhex("4200")),
            "channel": Channel.SESSION,
            "payload_bytes": bytes.fromhex(f"a10121fe0503{timestamp}"),
        },
        {
            **PacketCommand.parse(bytes.fromhex("420a")),
            "channel": Channel.SESSION,
            "payload_bytes": bytes.fromhex(
                "a10121"
                "a203025553"
                "a30c04" + OWNER_TOKEN.encode().hex() + f"fe0503{timestamp}",
            ),
        },
    ]


@pytest.mark.asyncio
async def test_stream_port_reading() -> None:
    """A port's status, voltage, current and power come from the 4303 stream."""
    prime = PrimeDevice(MOCK_BLE_DEVICE)
    await prime._process_telemetry(  # noqa: SLF001
        Parameters.parse(bytes.fromhex("a4080401004db3011403")),
    )

    assert prime._port_status("a4") is PortStatus.OUTPUT  # noqa: SLF001
    assert prime._port_reading("a4", "voltage", scale=1000.0) == A4_VOLTAGE  # noqa: SLF001
    assert prime._port_reading("a4", "current", scale=1000.0) == A4_CURRENT  # noqa: SLF001
    assert prime._port_reading("a4", "power", scale=100.0) == A4_POWER  # noqa: SLF001


def test_stream_port_absent_defaults() -> None:
    """A port never reported in the stream reads as unknown/default."""
    prime = PrimeDevice(MOCK_BLE_DEVICE)

    assert prime._port_status("a4") is PortStatus.UNKNOWN  # noqa: SLF001
    reading = prime._port_reading("a4", "voltage", scale=1000.0)  # noqa: SLF001
    assert reading == DEFAULT_METADATA_FLOAT


@pytest.mark.asyncio
async def test_snapshot_int_and_struct() -> None:
    """A snapshot tag parses through a plain integer field or a construct."""
    prime = PrimeDevice(MOCK_BLE_DEVICE)
    await prime._process_snapshot(  # noqa: SLF001
        Parameters.parse(
            bytes.fromhex(
                "b0020101aa140401ff0c0000ff0c000000580200000000000000",
            ),
        ),
    )

    assert prime._snapshot_int("b0") == 1  # noqa: SLF001

    record = prime._snapshot_struct("aa", PORT_RECORD)  # noqa: SLF001
    assert record is not None
    assert record.switch is True
    assert record.priority == 0


@pytest.mark.asyncio
async def test_snapshot_struct_too_short_for_required_prefix() -> None:
    """A record shorter than PORT_RECORD's 18-byte required prefix reads as None.

    ``priority`` has no static size (it's optional), so the length guard
    must fall back to the required prefix rather than crash computing it.
    """
    prime = PrimeDevice(MOCK_BLE_DEVICE)
    await prime._process_snapshot(  # noqa: SLF001
        Parameters.parse(bytes.fromhex("aa0f04" + "01ff0c0000ff0c00000058020000")),
    )

    record = prime._snapshot_struct("aa", PORT_RECORD)  # noqa: SLF001
    assert record is None


def test_snapshot_absent_defaults() -> None:
    """A snapshot tag never received reads as the default/None."""
    prime = PrimeDevice(MOCK_BLE_DEVICE)

    assert prime._snapshot_int("b0") == DEFAULT_METADATA_INT  # noqa: SLF001
    assert prime._snapshot_struct("aa", PORT_RECORD) is None  # noqa: SLF001
    assert prime._port_schedule("aa") is None  # noqa: SLF001
    assert prime._port_timer("aa") is None  # noqa: SLF001


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "schedule", "timer"),
    [
        pytest.param(
            "01ff0c0000ff0c0000005802000000000000" + "00",
            PortSchedule(
                on_time_enabled=None,
                on_time_hour=12,
                on_time_minute=0,
                on_time_weekdays=frozenset(),
                off_time_enabled=None,
                off_time_hour=12,
                off_time_minute=0,
                off_time_weekdays=frozenset(),
            ),
            PortTimer(enabled=False, seconds=600, remaining=0),
            id="idle_port_never_set",
        ),
        pytest.param(
            "01" + "01071e1f" + "0016007f" + "01" + "100e0000" + "2c010000" + "02",
            PortSchedule(
                on_time_enabled=True,
                on_time_hour=7,
                on_time_minute=30,
                on_time_weekdays=frozenset(range(5)),
                off_time_enabled=False,
                off_time_hour=22,
                off_time_minute=0,
                off_time_weekdays=frozenset(range(7)),
            ),
            PortTimer(enabled=True, seconds=3600, remaining=300),
            id="weekday_on_time_and_armed_timer",
        ),
    ],
)
async def test_port_schedule_and_timer(
    record: str,
    schedule: PortSchedule,
    timer: PortTimer,
) -> None:
    """A port's snapshot record reads as its schedule and countdown timer.

    The idle record is prime-a2345-a91b2.md's: both schedule halves unset
    (``ff``, stale 12:00) and a disarmed timer keeping its 600 s duration.
    """
    prime = PrimeDevice(MOCK_BLE_DEVICE)
    await prime._process_snapshot(  # noqa: SLF001
        Parameters.parse(bytes.fromhex("aa1404" + record)),
    )

    assert prime._port_schedule("aa") == schedule  # noqa: SLF001
    assert prime._port_timer("aa") == timer  # noqa: SLF001
