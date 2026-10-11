"""Tests for the payload constructs.

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE.constructs import PacketCommand, PacketPattern, Parameters


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


@pytest.mark.parametrize(
    ("pattern", "composer", "channel"),
    [
        ("030001", 0x00, 0x01),
        ("030101", 0x01, 0x01),
        ("03000f", 0x00, 0x0F),
        ("03010f", 0x01, 0x0F),
        ("030111", 0x01, 0x11),
    ],
)
def test_packet_pattern(pattern: str, composer: int, channel: int) -> None:
    """The pattern decodes to family, composer and dispatch channel."""
    parsed = PacketPattern.parse(bytes.fromhex(pattern))
    assert (parsed.family, parsed.composer, parsed.channel) == (0x03, composer, channel)


@pytest.mark.parametrize(
    ("cmd", "fragmented", "encrypted", "msgtype", "response"),
    [
        ("0001", False, False, 0x001, False),
        ("0803", False, False, 0x803, True),
        ("4827", False, True, 0x827, True),
        ("c402", True, True, 0x402, False),
        ("c900", True, True, 0x900, True),
        ("4a00", False, True, 0xA00, True),
    ],
)
def test_packet_command(
    cmd: str,
    fragmented: bool,  # noqa: FBT001
    encrypted: bool,  # noqa: FBT001
    msgtype: int,
    response: bool,  # noqa: FBT001
) -> None:
    """The command decodes to its link flags and 12-bit message type."""
    parsed = PacketCommand.parse(bytes.fromhex(cmd))
    assert (parsed.fragmented, parsed.encrypted, parsed.msgtype, parsed.response) == (
        fragmented,
        encrypted,
        msgtype,
        response,
    )


@pytest.mark.parametrize(
    ("encrypted", "msgtype", "cmd"),
    [(False, 0x001, "0001"), (True, 0x005, "4005"), (True, 0x027, "4027")],
)
def test_packet_command_build(
    encrypted: bool,  # noqa: FBT001
    msgtype: int,
    cmd: str,
) -> None:
    """A command builds from its flags and message type."""
    built = PacketCommand.build(
        {"fragmented": False, "encrypted": encrypted, "msgtype": msgtype},
    )
    assert built.hex() == cmd
