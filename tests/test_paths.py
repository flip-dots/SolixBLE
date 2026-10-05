"""Tests for choosing the negotiation path from the device's capability reply.

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE.const import FALLBACK_TZ
from SolixBLE.protocols import (
    EcdhPath,
    EncryptedOuter,
    LegacyAesPath,
    NegotiatedSession,
    Outer,
    PlainOuter,
    UnsupportedNegotiation,
    new_announcement,
)
from tests.helpers import RECORDING_CLIENT_ID, RecordingLink, feed_negotiation

TIMESTAMP = bytes.fromhex("42ad8c69")
CLIENT_ID = RECORDING_CLIENT_ID.encode()
SERIAL = b"APCTEST0000000001"
MAC = bytes.fromhex("aabbccddeeff")

#: Capability replies: current ECDH builds, the older legacy shape (no a5), and
#: one with neither an AES bit in a1 nor an ECDH bit in a3.
ECDH_X803 = "00a10102a202fd00a30144a40101a50102"
LEGACY_X803 = "00a10102a202fd00a30104a40101"
UNKNOWN_X803 = "00a10100a202fd00a30110a40101a50102"

X829 = (
    "00a10103a2054553503332a307302e302e302e33a411" + SERIAL.hex() + "a506" + MAC.hex()
)

#: Key the legacy device hands out in 4822 (synthetic).
LEGACY_NEW_KEY = bytes.fromhex("00112233445566778899aabbccddeeff")


def test_unsupported_names_the_announcement() -> None:
    """The error names what the device announced and where it stopped."""
    announcement = new_announcement()
    announcement.update({"base_method": 0x00, "encrypt_method": 0x10, "mtu": 253})
    error = UnsupportedNegotiation(announcement, "no path for the plain outer")
    assert str(error) == (
        "Unsupported negotiation: base_method=0x00, encrypt_method=0x10, "
        "auth_method=None, mtu=253 (no path for the plain outer)"
    )
    assert error.announcement is announcement


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer", "x803", "path"),
    [
        pytest.param(PlainOuter(), ECDH_X803, EcdhPath, id="ecdh_plain"),
        pytest.param(EncryptedOuter(), ECDH_X803, EcdhPath, id="ecdh_encrypted"),
        pytest.param(PlainOuter(), LEGACY_X803, LegacyAesPath, id="legacy_plain"),
    ],
)
async def test_capability_reply_chooses_the_path(
    outer: Outer,
    x803: str,
    path: type,
) -> None:
    """``x803`` picks ECDH when it offers it, else legacy AES on the plain outer."""
    session = NegotiatedSession(outer, RecordingLink())
    await feed_negotiation(session, [("0803", x803)])
    assert type(session.path) is path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer", "x803", "detail", "encrypt_method"),
    [
        pytest.param(
            PlainOuter(),
            UNKNOWN_X803,
            "encrypt_method=0x10.*no path for the plain outer",
            0x10,
            id="unknown_capabilities",
        ),
        pytest.param(
            EncryptedOuter(),
            LEGACY_X803,
            "no path for the encrypted outer",
            0x04,
            id="legacy_needs_the_plain_outer",
        ),
    ],
)
async def test_unknown_path_is_reported(
    outer: Outer,
    x803: str,
    detail: str,
    encrypt_method: int,
) -> None:
    """A capability reply no registered path handles raises naming its values."""
    session = NegotiatedSession(outer, RecordingLink())
    with pytest.raises(UnsupportedNegotiation, match=detail) as error:
        await feed_negotiation(session, [("0803", x803)])
    assert error.value.announcement.encrypt_method == encrypt_method


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("replies", "detail"),
    [
        pytest.param(
            [("0803", ECDH_X803), ("0829", X829), ("0805", "01")],
            "x805 status 01",
            id="ecdh_x805_refused",
        ),
        pytest.param(
            [("0803", ECDH_X803), ("0829", X829), ("0805", "00"), ("0821", "00")],
            "x821 without a device key",
            id="ecdh_x821_empty",
        ),
        pytest.param(
            [("0803", LEGACY_X803), ("0829", X829), ("0805", "01")],
            "x805 status 01",
            id="legacy_x805_refused",
        ),
    ],
)
async def test_path_rejections_are_reported(
    replies: list[tuple[str, str]],
    detail: str,
) -> None:
    """A device that rejects the path's method raises naming the stage."""
    session = NegotiatedSession(PlainOuter(), RecordingLink())
    with pytest.raises(UnsupportedNegotiation, match=detail):
        await feed_negotiation(session, replies)


@pytest.mark.asyncio
async def test_legacy_aes_path() -> None:
    """The legacy path states AES, keys on the client id and serial, then rekeys."""
    link = RecordingLink()
    session = NegotiatedSession(PlainOuter(), link)

    await feed_negotiation(session, [("0803", LEGACY_X803), ("0829", X829)])
    assert link.sent[-1][1:] == (
        "0005",
        {
            "a1": TIMESTAMP,
            "a2": CLIENT_ID,
            "a3": b"\x20",
            "a4": bytes.fromhex("00f0"),
            "a5": b"\x02",
        },
    )

    await feed_negotiation(session, [("0805", "00")])
    assert session.path is not None
    assert session.path.keys is not None
    assert (session.path.keys.key, session.path.keys.iv) == (
        CLIENT_ID[:16],
        SERIAL[:16],
    )
    assert not session.authorized
    assert link.sent[-1][1:] == (
        "4022",
        {
            "a1": TIMESTAMP,
            "a2": CLIENT_ID,
            "a3": bytes(4),
            "a5": FALLBACK_TZ.encode(),
        },
    )

    await feed_negotiation(session, [("0822", "00a110" + LEGACY_NEW_KEY.hex())])
    assert session.path.keys is not None
    assert (session.path.keys.key, session.path.keys.iv) == (
        LEGACY_NEW_KEY,
        SERIAL[:16],
    )
    assert session.authorized
    assert link.sent[-1][1:] == (
        "4023",
        {"a1": TIMESTAMP, "a2": CLIENT_ID, "a3": SERIAL},
    )
