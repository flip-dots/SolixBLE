"""Tests for fragmented session-payload reassembly (SolixBLE #42).

``_reassemble`` runs below the cipher and serves telemetry and unknown session
frames alike, so these tests exercise it directly on raw (still-encrypted)
payloads.

Most cases run at each maximum notification size we have seen a device declare,
since the classification depends on it: 247 (an F2000, per #55), 253 (the A1783 /
A91B2 / A2345) and 297 (the Prime 160W charger).
"""

from unittest import mock

import pytest

from SolixBLE import SolixBLEDevice
from tests.const import MOCK_BLE_DEVICE

CMD = b"\xc4\x90"

#: Maximum notification sizes observed being declared by real devices.
DECLARED_MTUS = [247, 253, 297]


def _device(declared_mtu: int) -> SolixBLEDevice:
    """Return a device that has been told its maximum notification size."""
    device = SolixBLEDevice(MOCK_BLE_DEVICE)
    device._client = mock.Mock(mtu_size=declared_mtu + 3)
    device._record_declared_mtu({"a2": declared_mtu.to_bytes(2, "little")})
    return device


@pytest.mark.parametrize("cap", DECLARED_MTUS)
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        # A91B2-style: first byte 0xd8 is ciphertext (index 13 / total 8 is an
        # impossible header), so the whole payload is data and must be kept.
        pytest.param(
            bytes([0xD8]) + b"\x11" * 200,
            bytes([0xD8]) + b"\x11" * 200,
            id="no_frag_byte",
        ),
        # MagGo/Prime-style: 0x11 is a valid "fragment 1 of 1" marker, so it is
        # stripped before the payload reaches the (GCM/CBC) decrypt.
        pytest.param(bytes([0x11]) + b"\xcd" * 60, b"\xcd" * 60, id="frag_byte"),
    ],
)
def test_non_fragmented_payload(cap: int, payload: bytes, expected: bytes) -> None:
    """A payload short of the maximum notification size is passed through."""
    device = _device(cap)
    assert device._reassemble(CMD, payload) == expected
    assert device._fragment_buffers == {}


@pytest.mark.parametrize("cap", DECLARED_MTUS)
@pytest.mark.parametrize("tail", [40, None], ids=["short_tail", "no_short_tail"])
def test_two_fragment_payload(cap: int, tail: int | None) -> None:
    """Two fragments are merged, whether or not the second is a short tail.

    With no short tail (both fragments fill the notification) termination has to
    come from the ``<index><total>`` count rather than from a shorter packet
    closing the payload, otherwise it never completes.
    """
    tail_length = cap - 1 if tail is None else tail
    device = _device(cap)
    first = bytes([0x12]) + b"\xaa" * (cap - 1)
    second = bytes([0x22]) + b"\xbb" * tail_length

    assert device._reassemble(CMD, first) is None
    expected = b"\xaa" * (cap - 1) + b"\xbb" * tail_length
    assert device._reassemble(CMD, second) == expected
    assert device._fragment_buffers == {}


@pytest.mark.parametrize("cap", DECLARED_MTUS)
def test_fragment_arriving_without_its_first(cap: int) -> None:
    """A payload reading index != 1 with nothing buffered is kept whole.

    A fragmented payload always begins at index 1, so this cannot be joined onto
    anything. It is passed through rather than dropped, because devices that omit
    the header on non-fragmented payloads make a genuine stray fragment
    indistinguishable from ciphertext that happens to look like one. The decrypt
    is what tells them apart.
    """
    device = _device(cap)
    payload = bytes([0x35]) + b"\x00" * (cap - 1)  # index 3 / total 5
    assert device._reassemble(CMD, payload) == payload
    assert device._fragment_buffers == {}


def test_declared_size_preferred_over_att_mtu() -> None:
    """The declared size wins over ``mtu_size``, which BlueZ reports as 23.

    bleak's BlueZ backend returns a default of 23 unless ``_acquire_mtu()`` has
    been called, which would collapse the threshold to 20 and let almost any
    payload begin a fragmented one.
    """
    device = SolixBLEDevice(MOCK_BLE_DEVICE)
    device._client = mock.Mock(mtu_size=23)
    device._record_declared_mtu({"a2": (253).to_bytes(2, "little")})

    assert device._max_notification == 253

    # Well over the BlueZ default of 23 - 3, but well under 253, so this is
    # non-fragmented and must not begin a fragmented payload.
    payload = bytes([0x12]) + b"\xaa" * 59
    assert device._reassemble(CMD, payload) == payload
    assert device._fragment_buffers == {}


def test_att_mtu_used_when_nothing_declared() -> None:
    """Devices that omit the stage-2 field fall back to the negotiated ATT MTU."""
    device = SolixBLEDevice(MOCK_BLE_DEVICE)
    device._client = mock.Mock(mtu_size=256)

    assert device._declared_mtu is None
    assert device._max_notification == 253
