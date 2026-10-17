"""Tests for the negotiation protocols: the outers, the session and the ECDH path.

The plaintexts were captured from a C2000 Gen 2 (A1783) on comms-module
firmware v0.3.3.0; the ``x829`` carries a synthetic serial.

.. moduleauthor:: kb1ibt
"""

from typing import ClassVar

import pytest
from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
)

from SolixBLE.const import FALLBACK_TZ
from SolixBLE.constructs import ParameterDict
from SolixBLE.protocols import (
    EcdhPath,
    EncryptedOuter,
    NegotiatedSession,
    Outer,
    Path,
    PlainOuter,
)
from SolixBLE.protocols.base import NegotiatedSessionLike, override
from tests.helpers import RECORDING_CLIENT_ID, RecordingLink

NEGOTIATION = bytes.fromhex("030001")
GRANT = bytes.fromhex("030101")

TIMESTAMP = bytes.fromhex("42ad8c69")
CLIENT_ID = RECORDING_CLIENT_ID.encode()
SERIAL = b"APCTEST0000000001"
MAC = bytes.fromhex("aabbccddeeff")

PLAIN_X801 = "00a10101"
PLAIN_X803 = "00a10102a202fd00a30144a40101a50102"
PLAIN_X829 = (
    "00a10103a2054553503332a307302e302e302e33a411" + SERIAL.hex() + "a506" + MAC.hex()
)
PLAIN_X821 = (
    "00a1405dff69533d15aae7194ccfce70978889ed3b090f0ea76c9d1b44bfcb145c80f8eb5"
    "59e5734fd9a17ea03a903eb6024786c009faa14d837031c9636c42910e490"
)
STATUS_OK = "00"
CONFIRM_30S = "09a1021e00"
CONFIRM_180S = "09a102b400"

#: ``00a10101`` sealed under the static GCM key, as the A1783 sends its ``4801``.
SEALED_X801 = "ab273ed3e27270c3f4d676ac7d69a00572793732"

#: Replies of each outer up to the key exchange, as (cmd, plaintext).
PLAIN_FLOW = (
    ("0801", PLAIN_X801),
    ("0803", PLAIN_X803),
    ("0829", PLAIN_X829),
    ("0805", STATUS_OK),
    ("0821", PLAIN_X821),
)
ENCRYPTED_FLOW = (
    ("4801", PLAIN_X801),
    ("4803", PLAIN_X803),
    ("4829", PLAIN_X829),
    ("4805", STATUS_OK),
    ("4821", PLAIN_X821),
)

PLAIN_X005 = {
    "a1": TIMESTAMP,
    "a2": CLIENT_ID,
    "a3": b"\x20",
    "a4": bytes.fromhex("00f0"),
    "a5": b"\x40",
}
ENCRYPTED_X005 = {
    "a1": TIMESTAMP,
    "a3": b"\x20",
    "a4": bytes.fromhex("fd00"),
    "a5": b"\x44",
    "a6": b"\x02",
}
X022_TAGS = {"a1": TIMESTAMP, "a3": bytes(4), "a5": FALLBACK_TZ.encode()}

#: Public point of RecordingLink's key, as main's recorded ``0021`` carries it.
CLIENT_PUBLIC_KEY = bytes.fromhex(
    "060ea168f232aedb37fb2d120c49180329ac72ab5ec3eb8fd30a2f252dc5e151"
    "dabccd9b1dc1e288704ca760a0d8c918e5c94823a1f609a4bf07fb4c33ee2190",
)

#: What ``PLAIN_X803`` declares.
DEVICE_MTU = 0xFD
BASE_AES = 0x02
ENCRYPT_ECDH = 0x44
AUTH_MODE = 0x02

STATUS_ACCEPTED = 0x00
STATUS_CONFIRM = 0x09
WINDOW_30S = 30
WINDOW_180S = 180


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer", "cmd", "parameters"),
    [
        pytest.param(
            PlainOuter(),
            "0001",
            {"a1": TIMESTAMP, "a2": CLIENT_ID},
            id="plain",
        ),
        pytest.param(EncryptedOuter(), "4001", {"a1": TIMESTAMP}, id="encrypted"),
    ],
)
async def test_open(outer: Outer, cmd: str, parameters: dict[str, bytes]) -> None:
    """The plain outer opens with ``0001`` and the client id; encrypted, ``4001``."""
    link = RecordingLink()
    await NegotiatedSession(outer, link).open()
    assert link.sent == [("030001", cmd, parameters)]
    assert list(link.sent[0][2]) == list(parameters)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer", "reply", "cmd", "parameters"),
    [
        pytest.param(
            PlainOuter(),
            "0801",
            "0003",
            {
                "a1": TIMESTAMP,
                "a2": CLIENT_ID,
                "a3": b"\x20",
                "a4": bytes.fromhex("00f0"),
            },
            id="plain",
        ),
        pytest.param(
            EncryptedOuter(),
            "4801",
            "4003",
            {"a1": TIMESTAMP, "a3": b"\x20", "a4": bytes.fromhex("00f0")},
            id="encrypted",
        ),
    ],
)
async def test_x801_asks_for_capabilities(
    outer: Outer,
    reply: str,
    cmd: str,
    parameters: dict[str, bytes],
) -> None:
    """The ``x801`` reply is answered with the outer's ``x003``."""
    link = RecordingLink()
    session = NegotiatedSession(outer, link)
    await session.on_plaintext(
        NEGOTIATION,
        bytes.fromhex(reply),
        bytes.fromhex(PLAIN_X801),
    )
    assert link.sent == [("030001", cmd, parameters)]
    assert list(link.sent[0][2]) == list(parameters)


def test_encrypted_outer_seals_with_static_key() -> None:
    """Before keys the encrypted outer uses the static GCM key, as the A1783 does."""
    session = NegotiatedSession(EncryptedOuter(), RecordingLink())
    assert session.encrypt(bytes.fromhex(PLAIN_X801)).hex() == SEALED_X801
    assert session.decrypt(bytes.fromhex(SEALED_X801)).hex() == PLAIN_X801


def test_plain_outer_is_clear_before_keys() -> None:
    """Before keys the plain outer leaves payloads in clear."""
    session = NegotiatedSession(PlainOuter(), RecordingLink())
    payload = bytes.fromhex(PLAIN_X801)
    assert session.encrypt(payload) == payload
    assert session.decrypt(payload) == payload


@pytest.mark.asyncio
async def test_on_reply_decrypts_flagged_frames() -> None:
    """A ``0x40`` reply is decrypted before it is handled."""
    link = RecordingLink()
    session = NegotiatedSession(EncryptedOuter(), link)
    await session.on_reply(
        NEGOTIATION,
        bytes.fromhex("4801"),
        bytes.fromhex(SEALED_X801),
    )
    assert session.replied
    assert [cmd for _, cmd, _ in link.sent] == ["4003"]


@pytest.mark.asyncio
async def test_status_byte_reaches_the_path() -> None:
    """The path receives the reply's status byte apart from its parameters."""
    received: list[tuple[str, int, int, dict[str, str]]] = []

    class Probe(Path):
        name: ClassVar[str] = "probe"

        def __init__(self) -> None:
            self.keys: Container | None = None
            self.authorized = False

        @classmethod
        @override
        def matches(cls, announcement: Container, outer: Outer) -> bool:  # noqa: ARG003  # the protocol's signature
            return True

        @override
        async def on_stage(
            self,
            session: NegotiatedSessionLike,
            msgtype: int,
            status: int,
            parameters: ParameterDict,
        ) -> None:
            received.append(
                (
                    session.outer.name,
                    msgtype,
                    status,
                    {tag: p.value_legacy.hex() for tag, p in parameters.items()},
                ),
            )

    session = NegotiatedSession(EncryptedOuter(), RecordingLink())
    session.path = Probe()
    await session.on_plaintext(
        NEGOTIATION,
        bytes.fromhex("4827"),
        bytes.fromhex(CONFIRM_30S),
    )
    assert received == [("encrypted", 0x827, STATUS_CONFIRM, {"a1": "1e00"})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer", "flow", "x029"),
    [
        pytest.param(
            PlainOuter(),
            PLAIN_FLOW,
            ("030001", "0029", {"a1": TIMESTAMP, "a2": CLIENT_ID}),
            id="plain",
        ),
        pytest.param(
            EncryptedOuter(),
            ENCRYPTED_FLOW,
            ("030001", "4029", {"a1": TIMESTAMP}),
            id="encrypted",
        ),
    ],
)
async def test_capability_exchange_chooses_ecdh(
    outer: Outer,
    flow: tuple[tuple[str, str], ...],
    x029: tuple[str, str, dict[str, bytes]],
) -> None:
    """After ``x803`` the session runs ECDH; ``x829`` records the serial and MAC."""
    link = RecordingLink()
    session = NegotiatedSession(outer, link)
    for cmd, plaintext in flow[:3]:
        await session.on_plaintext(
            NEGOTIATION,
            bytes.fromhex(cmd),
            bytes.fromhex(plaintext),
        )
    assert isinstance(session.path, EcdhPath)
    assert link.sent[1] == x029
    assert session.announcement.mtu == DEVICE_MTU
    assert session.announcement.base_method == BASE_AES
    assert session.announcement.encrypt_method == ENCRYPT_ECDH
    assert session.announcement.auth_method == AUTH_MODE
    assert session.announcement.serial == SERIAL
    assert session.announcement.mac == MAC


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["44", "40", "04"])
@pytest.mark.parametrize(
    ("outer", "flow", "x005"),
    [
        pytest.param(
            PlainOuter(),
            PLAIN_FLOW,
            ("030001", "0005", PLAIN_X005),
            id="plain",
        ),
        pytest.param(
            EncryptedOuter(),
            ENCRYPTED_FLOW,
            ("030001", "4005", ENCRYPTED_X005),
            id="encrypted",
        ),
    ],
)
async def test_x005_states_the_method_per_outer(
    outer: Outer,
    flow: tuple[tuple[str, str], ...],
    x005: tuple[str, str, dict[str, bytes]],
    method: str,
) -> None:
    """``x005`` carries the app's method for the outer, whatever ``x803 a3`` was."""
    link = RecordingLink()
    session = NegotiatedSession(outer, link)
    x803 = PLAIN_X803.replace("a30144", "a301" + method)
    for cmd, plaintext in (flow[0], (flow[1][0], x803), flow[2]):
        await session.on_plaintext(
            NEGOTIATION,
            bytes.fromhex(cmd),
            bytes.fromhex(plaintext),
        )
    assert link.sent[-1] == x005
    assert list(link.sent[-1][2]) == list(x005[2])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer", "flow", "x021", "x022", "authorized"),
    [
        pytest.param(
            PlainOuter(),
            PLAIN_FLOW,
            "0021",
            {"a1": TIMESTAMP, "a2": CLIENT_ID} | X022_TAGS,
            True,
            id="plain",
        ),
        pytest.param(
            EncryptedOuter(),
            ENCRYPTED_FLOW,
            "4021",
            X022_TAGS,
            False,
            id="encrypted",
        ),
    ],
)
async def test_key_exchange_sets_the_clock(
    outer: Outer,
    flow: tuple[tuple[str, str], ...],
    x021: str,
    x022: dict[str, bytes],
    authorized: bool,  # noqa: FBT001
) -> None:
    """``x821`` installs the keys and sends ``4022``; the plain outer adds ``a2``."""
    link = RecordingLink()
    session = NegotiatedSession(outer, link)
    for cmd, plaintext in flow:
        await session.on_plaintext(
            NEGOTIATION,
            bytes.fromhex(cmd),
            bytes.fromhex(plaintext),
        )
    assert link.sent[-2] == ("030001", x021, {"a1": CLIENT_PUBLIC_KEY})
    assert link.sent[-1] == ("030001", "4022", x022)
    assert list(link.sent[-1][2]) == list(x022)
    assert session.path is not None
    assert session.path.keys is not None
    assert session.authorized is authorized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outer", "flow", "registration"),
    [
        pytest.param(PlainOuter(), PLAIN_FLOW, [], id="plain"),
        pytest.param(
            EncryptedOuter(),
            ENCRYPTED_FLOW,
            [("030001", "4027", {"a1": TIMESTAMP, "a2": CLIENT_ID})],
            id="encrypted",
        ),
    ],
)
async def test_x822_registers_an_unauthorized_client(
    outer: Outer,
    flow: tuple[tuple[str, str], ...],
    registration: list[tuple[str, str, dict[str, bytes]]],
) -> None:
    """``x822`` is followed by ``4027`` with the client token unless authorized."""
    link = RecordingLink()
    session = NegotiatedSession(outer, link)
    for cmd, plaintext in flow:
        await session.on_plaintext(
            NEGOTIATION,
            bytes.fromhex(cmd),
            bytes.fromhex(plaintext),
        )
    sent = len(link.sent)
    await session.on_plaintext(
        NEGOTIATION,
        bytes.fromhex("4822"),
        bytes.fromhex(STATUS_OK),
    )
    assert link.sent[sent:] == registration


@pytest.mark.asyncio
async def test_registration_accepted_authorizes() -> None:
    """``4827 00`` authorizes the encrypted outer."""
    session = NegotiatedSession(EncryptedOuter(), RecordingLink())
    for cmd, plaintext in ENCRYPTED_FLOW:
        await session.on_plaintext(
            NEGOTIATION,
            bytes.fromhex(cmd),
            bytes.fromhex(plaintext),
        )
    assert not session.authorized
    await session.on_plaintext(
        NEGOTIATION,
        bytes.fromhex("4827"),
        bytes.fromhex(STATUS_OK),
    )
    assert session.announcement.registration_status == STATUS_ACCEPTED
    assert session.authorized


@pytest.mark.asyncio
async def test_confirmation_required_until_a_session_push() -> None:
    """``4827 09`` leaves the client unauthorized; a session push then authorizes."""
    session = NegotiatedSession(EncryptedOuter(), RecordingLink())
    for cmd, plaintext in ENCRYPTED_FLOW:
        await session.on_plaintext(
            NEGOTIATION,
            bytes.fromhex(cmd),
            bytes.fromhex(plaintext),
        )
    await session.on_plaintext(
        NEGOTIATION,
        bytes.fromhex("4827"),
        bytes.fromhex(CONFIRM_180S),
    )
    assert session.announcement.registration_status == STATUS_CONFIRM
    assert session.announcement.confirmation_window == WINDOW_180S
    assert not session.authorized
    session.on_session_push()
    assert session.authorized


@pytest.mark.asyncio
async def test_grant_after_confirmation_authorizes() -> None:
    """``4827 09`` records its window; a later ``4827 00`` on ``030101`` authorizes."""
    session = NegotiatedSession(EncryptedOuter(), RecordingLink())
    for cmd, plaintext in ENCRYPTED_FLOW:
        await session.on_plaintext(
            NEGOTIATION,
            bytes.fromhex(cmd),
            bytes.fromhex(plaintext),
        )
    await session.on_plaintext(
        NEGOTIATION,
        bytes.fromhex("4827"),
        bytes.fromhex(CONFIRM_30S),
    )
    assert session.announcement.registration_status == STATUS_CONFIRM
    assert session.announcement.confirmation_window == WINDOW_30S
    assert not session.authorized
    await session.on_plaintext(GRANT, bytes.fromhex("4827"), bytes.fromhex(STATUS_OK))
    assert session.announcement.registration_status == STATUS_ACCEPTED
    assert session.authorized
