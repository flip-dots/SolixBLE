"""Tests for the capability-driven encrypted negotiation on the base device.

The device response frames and plaintexts below were captured from a live
C2000 Gen 2 (A1783) on comms-module firmware v0.3.3.0.

.. moduleauthor:: kb1ibt
"""

from unittest import mock

import pytest

from SolixBLE import C300, PrimeDevice
from SolixBLE.constructs import Packet
from SolixBLE.device import SolixBLEDevice
from tests.const import MOCK_BLE_DEVICE

#: Static-key GCM negotiation frames as sent by the device, and their plaintexts.
FRAME_4801 = "ff091e000300014801ab273ed3e27270c3f4d676ac7d69a00572793732a6"
FRAME_4803 = (
    "ff092b000300014803ab273ed04438d4b25db54c6d4a6ec3d481f5ad58ff7cc2be8bc8369"
    "fd98c0b914e03"
)
PLAIN_4801 = "00a10101"
PLAIN_4803 = "00a10102a202fd00a30144a40101a50102"
PLAIN_4829 = (
    "00a10103a2054553503332a307302e302e302e33a411415043444b4b4530463339363030"
    "303131a5067ce91346c50c"
)
PLAIN_4805 = "00"
PLAIN_4821 = (
    "00a1405dff69533d15aae7194ccfce70978889ed3b090f0ea76c9d1b44bfcb145c80f8eb5"
    "59e5734fd9a17ea03a903eb6024786c009faa14d837031c9636c42910e490"
)
PLAIN_4822 = "00"
PLAIN_4827_OK = "00"

EXPECTED_MTU = 253
AUTH_MODE_ENCRYPTED = b"\x02"


def _device() -> SolixBLEDevice:
    """Build a base device on the encrypted path with a negotiation key ready."""
    device = SolixBLEDevice(MOCK_BLE_DEVICE, capability=4)
    device._private_key = device._generate_private_key()
    return device


async def _feed(device: SolixBLEDevice, cmd: str, plaintext: str) -> None:
    """Feed one decrypted negotiation response into the state machine."""
    await device._process_negotiation_encrypted(
        bytes.fromhex(cmd),
        bytes.fromhex(plaintext),
    )


def test_path_selected_from_capability() -> None:
    """The ECDH capability bit selects the encrypted path; its absence the plain one."""
    assert SolixBLEDevice(MOCK_BLE_DEVICE, capability=4)._encrypted_negotiation is True
    assert SolixBLEDevice(MOCK_BLE_DEVICE, capability=0)._encrypted_negotiation is False


def test_path_defaults_per_class() -> None:
    """Without a capability byte the class default decides the path."""
    assert PrimeDevice(MOCK_BLE_DEVICE)._encrypted_negotiation is True
    assert C300(MOCK_BLE_DEVICE)._encrypted_negotiation is False
    assert C300(MOCK_BLE_DEVICE, capability=4)._encrypted_negotiation is True


@pytest.mark.parametrize(
    ("frame", "plaintext"),
    [
        pytest.param(FRAME_4801, PLAIN_4801, id="stage1"),
        pytest.param(FRAME_4803, PLAIN_4803, id="stage2"),
    ],
)
def test_static_key_gcm_decrypt(frame: str, plaintext: str) -> None:
    """The base device recovers real device frames under the static key."""
    payload = Packet.parse(bytes.fromhex(frame)).payload_bytes
    assert _device()._decrypt_payload(payload).hex() == plaintext


def test_gcm_round_trip_under_shared_secret() -> None:
    """Encrypt then decrypt round-trips once a shared secret is in place."""
    device = _device()
    device._shared_secret = bytes(range(32))
    assert device._decrypt_payload(device._encrypt_payload(b"a10121")) == b"a10121"


@pytest.mark.asyncio
async def test_encrypted_negotiation_stages() -> None:
    """Driving the stages sends the expected commands and derives the secret."""
    device = _device()
    with mock.patch.object(device, "_send_packet", new=mock.AsyncMock()) as send:
        await _feed(device, "4801", PLAIN_4801)
        await _feed(device, "4803", PLAIN_4803)
        assert device._mtu == EXPECTED_MTU
        assert device._auth_mode == AUTH_MODE_ENCRYPTED
        await _feed(device, "4829", PLAIN_4829)
        await _feed(device, "4805", PLAIN_4805)
        await _feed(device, "4821", PLAIN_4821)
        assert device._shared_secret is not None
        await _feed(device, "4822", PLAIN_4822)

        # The 4005 echo carries the device's declared MTU and auth mode.
        cmd_4005 = next(c for c in send.await_args_list if c.kwargs["cmd"] == "4005")
        params = cmd_4005.kwargs["parameters"]
        assert params["a4"]["value"] == EXPECTED_MTU.to_bytes(2, "little")
        assert params["a5"]["value"] == bytes.fromhex("44")
        assert params["a6"]["value"] == AUTH_MODE_ENCRYPTED

        # The 4021 exchange sends the raw X||Y point of this negotiation's key.
        cmd_4021 = next(c for c in send.await_args_list if c.kwargs["cmd"] == "4021")
        assert len(cmd_4021.kwargs["parameters"]["a1"]["value"]) == 64

    sent = [c.kwargs["cmd"] for c in send.await_args_list]
    assert sent == ["4003", "4029", "4005", "4021", "4022", "4027"]


@pytest.mark.asyncio
async def test_registration_result_runs_post_authorize() -> None:
    """The 4827 registration result hands off to the post-authorize hook."""
    device = _device()
    with mock.patch.object(device, "_post_authorize", new=mock.AsyncMock()) as post:
        await _feed(device, "4827", PLAIN_4827_OK)
    post.assert_awaited_once()


@pytest.mark.asyncio
async def test_each_negotiation_gets_a_fresh_key() -> None:
    """Initiating a negotiation generates a new ECDH key every time."""
    device = SolixBLEDevice(MOCK_BLE_DEVICE, capability=4)
    with mock.patch.object(device, "_send_packet", new=mock.AsyncMock()):
        await device._initiate_negotiations()
        first = device._private_key
        await device._initiate_negotiations()
        second = device._private_key
    assert first is not None
    assert second is not None
    assert first.private_numbers() != second.private_numbers()
