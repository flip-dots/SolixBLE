"""Tests for the payload constructs.

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE.constructs import Parameters


@pytest.mark.parametrize(
    ("payload", "status", "tags"),
    [
        pytest.param("00a10101", 0x00, {"a1": "01"}, id="ok_reply"),
        pytest.param(
            "09a1021e00",
            0x09,
            {"a1": "1e00"},
            id="pairing_required_keeps_a1",
        ),
        pytest.param("01", 0x01, {}, id="status_only_failure"),
        pytest.param(
            "a10121a2020101",
            None,
            {"a1": "21", "a2": "0101"},
            id="push_without_status",
        ),
    ],
)
def test_status_prefix(payload: str, status: int | None, tags: dict[str, str]) -> None:
    """Any status byte below the first TLV tag is the prefix; pushes have none."""
    parsed = Parameters.parse(bytes.fromhex(payload))
    assert parsed.status == status
    assert {k: v.value_legacy.hex() for k, v in parsed.items()} == tags


@pytest.mark.parametrize("payload", ["00a10101", "09a1021e00", "a10121a2020101"])
def test_round_trip(payload: str) -> None:
    """Parsing then building reproduces the payload, status byte included."""
    assert Parameters.build(Parameters.parse(bytes.fromhex(payload))).hex() == payload
