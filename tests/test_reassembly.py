"""Tests for multi-fragment session-frame reassembly (SolixBLE #42).

``_reassemble`` runs below the cipher and serves telemetry and unknown session
frames alike, so these tests exercise it directly on raw (still-encrypted)
payloads for a link with a 256-byte ATT MTU (``ATT_MTU - 3 == 253`` on the wire).
"""

from unittest import mock

from SolixBLE import SolixBLEDevice
from tests.const import MOCK_BLE_DEVICE

#: ``ATT_MTU - 3`` for a 256-byte link -- a full (fragmenting) notification value.
CAP = 253
CMD = b"\xc4\x90"


def _device() -> SolixBLEDevice:
    dev = SolixBLEDevice(MOCK_BLE_DEVICE)
    dev._client = mock.Mock(mtu_size=256)
    return dev


def test_short_single_without_frag_byte_kept_whole() -> None:
    # A91B2-style single: first byte 0xd8 is ciphertext (index 13 / total 8 is an
    # impossible header), so the whole payload is data and must be kept.
    device = _device()
    payload = bytes([0xD8]) + b"\x11" * 200
    assert device._reassemble(CMD, payload) == payload
    assert device._fragment_buffers == {}


def test_short_single_with_frag_byte_stripped() -> None:
    # MagGo/Prime-style single: 0x11 is a valid single marker (index 1 / total 1),
    # so the frag byte is stripped before it reaches the (GCM/CBC) decrypt.
    device = _device()
    payload = bytes([0x11]) + b"\xcd" * 60
    assert device._reassemble(CMD, payload) == b"\xcd" * 60
    assert device._fragment_buffers == {}


def test_two_fragment_reassembly_with_short_tail() -> None:
    device = _device()
    frag1 = bytes([0x12]) + b"\xaa" * (CAP - 1)  # full-length first fragment
    frag2 = bytes([0x22]) + b"\xbb" * 40  # short tail closes the run
    assert device._reassemble(CMD, frag1) is None  # still buffering
    assert device._reassemble(CMD, frag2) == b"\xaa" * (CAP - 1) + b"\xbb" * 40
    assert device._fragment_buffers == {}


def test_exact_multiple_no_short_tail() -> None:
    # Two full 253-byte notifications, no short tail (the 506-on-the-wire case).
    # Termination must come from the <index><total> count, not from a shorter
    # packet closing the run -- otherwise this hangs forever.
    device = _device()
    frag1 = bytes([0x12]) + b"\xaa" * (CAP - 1)
    frag2 = bytes([0x22]) + b"\xbb" * (CAP - 1)
    assert device._reassemble(CMD, frag1) is None
    assert device._reassemble(CMD, frag2) == b"\xaa" * (CAP - 1) + b"\xbb" * (CAP - 1)
    assert device._fragment_buffers == {}


def test_cold_non_first_fragment_decoded_whole() -> None:
    # A full-length frame whose header reads index != 1 with no open run cannot be a
    # joinable fragment (a run always opens on index 1). Treat it as a single and
    # keep the whole payload rather than opening a run that never completes.
    device = _device()
    payload = bytes([0x35]) + b"\x00" * (CAP - 1)  # index 3 / total 5, no buffer
    assert device._reassemble(CMD, payload) == payload
    assert device._fragment_buffers == {}
