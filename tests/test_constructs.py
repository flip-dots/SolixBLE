"""Tests for the payload constructs.

.. moduleauthor:: kb1ibt
"""

import pytest
from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    ConstError,
)

from SolixBLE.constructs import (
    PORT_FAULTS,
    PORT_READING,
    PORT_RECORD,
    SCHEDULE_TRIGGER,
    SCHEDULE_UNSET,
    TIMER_SETTING,
    Channel,
    Composer,
    DecimalVersion,
    Negotiation,
    Packet,
    PacketCommand,
    PacketPattern,
    Parameters,
    WeekdayMask,
)

#: A WiFi provisioning channel, which has no enum member.
WIFI_CHANNEL = 0x13

#: Message type of the capability reply.
CAPABILITY_REPLY = 0x803


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
        ("030001", Composer.REPLY, Channel.NEGOTIATION),
        ("030101", Composer.SEND, Channel.NEGOTIATION),
        ("03000f", Composer.REPLY, Channel.SESSION),
        ("03010f", Composer.SEND, Channel.SESSION),
        ("030111", Composer.SEND, Channel.APP),
    ],
)
def test_packet_pattern(pattern: str, composer: Composer, channel: Channel) -> None:
    """The pattern decodes to family, composer and dispatch channel, as enums."""
    parsed = PacketPattern.parse(bytes.fromhex(pattern))
    assert (parsed.family, parsed.composer, parsed.channel) == (0x03, composer, channel)
    assert type(parsed.composer) is Composer
    assert type(parsed.channel) is Channel


def test_packet_pattern_unknown_channel_is_an_int() -> None:
    """A channel without an enum member decodes to the plain integer."""
    parsed = PacketPattern.parse(bytes.fromhex("030013"))
    assert parsed.channel == WIFI_CHANNEL
    assert type(parsed.channel) is int


def test_packet_pattern_family_is_checked() -> None:
    """A pattern whose family isn't ``03`` doesn't parse."""
    with pytest.raises(ConstError):
        PacketPattern.parse(bytes.fromhex("040001"))


@pytest.mark.parametrize(
    ("cmd", "fragmented", "encrypted", "response", "message", "msgtype"),
    [
        ("0001", False, False, False, 0x001, 0x001),
        ("0803", False, False, True, 0x003, 0x803),
        ("4827", False, True, True, 0x027, 0x827),
        ("c402", True, True, False, 0x402, 0x402),
        ("c900", True, True, True, 0x100, 0x900),
        ("4a00", False, True, True, 0x200, 0xA00),
    ],
)
def test_packet_command(  # noqa: PLR0913, PLR0917
    cmd: str,
    fragmented: bool,  # noqa: FBT001
    encrypted: bool,  # noqa: FBT001
    response: bool,  # noqa: FBT001
    message: int,
    msgtype: int,
) -> None:
    """The command decodes to its link flags, response bit, message and msgtype."""
    parsed = PacketCommand.parse(bytes.fromhex(cmd))
    assert (
        parsed.fragmented,
        parsed.encrypted,
        parsed.response,
        parsed.message,
        parsed.msgtype,
    ) == (fragmented, encrypted, response, message, msgtype)


@pytest.mark.parametrize(
    ("fields", "cmd"),
    [
        pytest.param({"message": 0x001}, "0001", id="message"),
        pytest.param({"encrypted": True, "message": 0x005}, "4005", id="encrypted"),
        pytest.param(
            {"encrypted": True, "response": True, "message": 0x027},
            "4827",
            id="response",
        ),
        pytest.param(
            {"fragmented": True, "encrypted": True, "msgtype": 0x900},
            "c900",
            id="msgtype",
        ),
    ],
)
def test_packet_command_build(fields: dict, cmd: str) -> None:
    """A command builds from its message and response bit, or from its msgtype."""
    assert PacketCommand.build(fields).hex() == cmd


def test_packet_fields() -> None:
    """A packet decodes its header to fields; a negotiation message to its enum."""
    packet = Packet.parse(
        bytes.fromhex("ff091b00030001080300a10102a202fd00a30144a40101a50100fd"),
    )
    assert packet.composer is Composer.REPLY
    assert packet.channel is Channel.NEGOTIATION
    assert (packet.fragmented, packet.encrypted, packet.response) == (
        False,
        False,
        True,
    )
    assert packet.message is Negotiation.NEGOTIATE_CAPABILITY
    assert packet.msgtype == CAPABILITY_REPLY
    assert packet.payload_bytes.hex() == "00a10102a202fd00a30144a40101a50100"


def test_packet_session_message_is_an_int() -> None:
    """Off the negotiation channel the message stays an integer."""
    frame = Packet.build(
        {
            "composer": Composer.SEND,
            "channel": Channel.SESSION,
            "fragmented": True,
            "encrypted": True,
            "msgtype": 0x900,
            "payload_bytes": b"\x11",
        },
    )
    assert frame.hex() == "ff090b0003010fc9001128"
    packet = Packet.parse(frame)
    assert (packet.message, packet.msgtype) == (0x100, 0x900)
    assert type(packet.message) is int


def test_packet_build_round_trip() -> None:
    """A packet built from its fields parses back to them."""
    frame = Packet.build(
        {
            "channel": Channel.NEGOTIATION,
            "response": True,
            "message": Negotiation.NEGOTIATE_CAPABILITY,
            "payload_bytes": bytes.fromhex("00a10102a202fd00a30144a40101a50100"),
        },
    )
    assert frame.hex() == "ff091b00030001080300a10102a202fd00a30144a40101a50100fd"


@pytest.mark.parametrize(
    ("mask", "days"),
    [
        pytest.param("24", frozenset({2, 5}), id="wed_and_sat"),
        pytest.param("7f", frozenset(range(7)), id="every_day"),
        pytest.param("00", frozenset(), id="no_days"),
        pytest.param("1f", frozenset(range(5)), id="weekdays_only"),
    ],
)
def test_weekday_mask(mask: str, days: frozenset[int]) -> None:
    """A weekday bitmask decodes to the set bits, bit 0 Monday to bit 6 Sunday."""
    assert WeekdayMask.parse(bytes.fromhex(mask)) == days
    assert WeekdayMask.build(days).hex() == mask


@pytest.mark.parametrize(
    ("value", "version"),
    [
        pytest.param("4408", "2.1.1.6", id="a2345_v2116"),
        pytest.param("6004", "1.1.2.0", id="a91b2_v1120"),
        pytest.param("6404", "1.1.2.4", id="a91b2_v1124"),
        pytest.param("2901", "0.2.9.7", id="below_1000_keeps_four_parts"),
    ],
)
def test_decimal_version(value: str, version: str) -> None:
    """A snapshot's ``a2`` value decodes digit by digit (prime-a2345-a91b2.md)."""
    assert DecimalVersion.parse(bytes.fromhex(value)) == version
    assert DecimalVersion.build(version).hex() == value


def test_port_faults_shared_bits() -> None:
    """The fault bitmap is the same layout on the A2345 and the A91B2."""
    faults = PORT_FAULTS.parse(bytes.fromhex("1100"))
    assert faults.over_temperature
    assert faults.usb_c4
    assert not faults.usb_c1


def test_schedule_trigger_unset_half() -> None:
    """An unset schedule half reads a stale default time behind its enable byte."""
    trigger = SCHEDULE_TRIGGER.parse(bytes.fromhex("ff0c0000"))
    assert trigger.enabled == SCHEDULE_UNSET
    assert (trigger.hour, trigger.minute) == (12, 0)
    assert trigger.weekdays == frozenset()


def test_timer_setting_round_trip() -> None:
    """A countdown timer parses and rebuilds enable, seconds and remaining."""
    timer_bytes = bytes.fromhex("0158020000 2c010000".replace(" ", ""))
    timer = TIMER_SETTING.parse(timer_bytes)
    assert (timer.enabled, timer.seconds, timer.remaining) == (1, 600, 300)
    assert TIMER_SETTING.build(timer) == timer_bytes


@pytest.mark.parametrize(
    ("record_hex", "priority"),
    [
        pytest.param(
            "01ff0c0000ff0c0000005802000000000000" + "00",
            0,
            id="a2345_19_bytes",
        ),
        pytest.param(
            "01ff0c0000ff0c00000058020000" + "58020000",
            None,
            id="a91b2_18_bytes",
        ),
    ],
)
def test_port_record_with_and_without_priority(
    record_hex: str,
    priority: int | None,
) -> None:
    """The A2345's 19-byte record and the A91B2's 18-byte record both parse."""
    record = PORT_RECORD.parse(bytes.fromhex(record_hex))
    assert record.switch is True
    assert record.priority == priority
    assert PORT_RECORD.build(record) == bytes.fromhex(record_hex)


def test_port_reading_matches_a_real_frame() -> None:
    """A USB-C port reading decodes a real captured 4303-stream record."""
    reading = PORT_READING.parse(bytes.fromhex("01004db301140 3".replace(" ", "")))
    assert (reading.status, reading.voltage, reading.current, reading.power) == (
        1,
        19712,
        435,
        788,
    )
