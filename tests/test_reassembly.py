"""Tests for multi-fragment session-frame reassembly (SolixBLE #42).

``_reassemble`` runs below the cipher and serves telemetry and unknown session
frames alike, so these tests exercise it directly on raw (still-encrypted)
payloads for a link with a 256-byte ATT MTU (``ATT_MTU - 3 == 253`` on the wire).
"""

from unittest import mock

import pytest

from SolixBLE import SolixBLEDevice
from tests.const import MOCK_BLE_DEVICE

#: ``ATT_MTU - 3`` for a 256-byte link -- a full (fragmenting) notification value.
CAP = 253
CMD = b"\xc4\x90"

#: Smallest payload that counts as full-length. ``_reassemble`` gates on
#: ``len(payload) + _FRAME_OVERHEAD >= mtu_size - 3`` (i.e. ``>= CAP``), so the
#: threshold is ``CAP - _FRAME_OVERHEAD`` -- derived, not hardcoded, so it tracks
#: the overhead constant rather than silently drifting if it changes.
FULL_LEN = CAP - SolixBLEDevice._FRAME_OVERHEAD


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


def test_empty_payload_returned_as_is() -> None:
    device = _device()
    assert device._reassemble(CMD, b"") == b""
    assert device._fragment_buffers == {}


@pytest.mark.parametrize(
    "first_byte,body,stripped",
    [
        # A short frame is a single. Its first byte is stripped only when it is a
        # valid single marker (0x11 = index 1 / total 1); otherwise it is ciphertext.
        (0x11, b"\xcd" * 60, True),  # MagGo/Prime single: frag byte stripped
        (0xD8, b"\x11" * 200, False),  # A91B2 single: no frag byte, first byte is data
        (0x21, b"\xab" * 50, False),  # index 2 / total 1 (impossible) -> data
        (0x35, b"\x00" * 40, False),  # index 3 / total 5 but short -> data
    ],
)
def test_short_single_classification(
    first_byte: int,
    body: bytes,
    stripped: bool,
) -> None:
    device = _device()
    payload = bytes([first_byte]) + body
    expected = body if stripped else payload
    assert device._reassemble(CMD, payload) == expected
    assert device._fragment_buffers == {}


@pytest.mark.parametrize(
    "body_len,is_fragment",
    [(FULL_LEN, True), (FULL_LEN - 1, False)],
)
def test_full_length_threshold_opens_run(body_len: int, is_fragment: bool) -> None:
    # A run only opens on a full-length (>= FULL_LEN) index-1 first fragment. One byte
    # under that is a single (kept whole here: first byte 0x12 is not the 0x11 marker).
    device = _device()
    payload = bytes([0x12]) + b"\xaa" * (body_len - 1)
    result = device._reassemble(CMD, payload)
    if is_fragment:
        assert result is None
        assert device._fragment_buffers[CMD] == {1: b"\xaa" * (body_len - 1)}
    else:
        assert result == payload
        assert device._fragment_buffers == {}


def test_three_fragment_reassembly() -> None:
    device = _device()
    frag1 = bytes([0x13]) + b"\xaa" * (CAP - 1)  # index 1 / total 3
    frag2 = bytes([0x23]) + b"\xbb" * (CAP - 1)  # index 2 / total 3
    frag3 = bytes([0x33]) + b"\xcc" * 30  # index 3 / total 3, short tail
    assert device._reassemble(CMD, frag1) is None
    assert device._reassemble(CMD, frag2) is None
    joined = device._reassemble(CMD, frag3)
    assert joined == b"\xaa" * (CAP - 1) + b"\xbb" * (CAP - 1) + b"\xcc" * 30
    assert device._fragment_buffers == {}


def test_interleaved_runs_buffered_per_command() -> None:
    # Two commands fragmenting at once keep independent buffers keyed by cmd.
    device = _device()
    cmd_a, cmd_b = b"\xc4\x90", b"\xc4\x21"
    assert device._reassemble(cmd_a, bytes([0x12]) + b"\xaa" * (CAP - 1)) is None
    assert device._reassemble(cmd_b, bytes([0x12]) + b"\x11" * (CAP - 1)) is None
    assert set(device._fragment_buffers) == {cmd_a, cmd_b}
    assert device._reassemble(cmd_a, bytes([0x22]) + b"\xaa" * 20) == b"\xaa" * (
        CAP - 1 + 20
    )
    assert device._reassemble(cmd_b, bytes([0x22]) + b"\x11" * 20) == b"\x11" * (
        CAP - 1 + 20
    )
    assert device._fragment_buffers == {}
