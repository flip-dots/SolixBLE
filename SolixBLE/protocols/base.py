"""Interfaces of the negotiation: the link, outer protocols, paths and the session.

.. moduleauthor:: kb1ibt
"""

import sys
from typing import Any, ClassVar, Protocol

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Bytes,
    Computed,
    Container,
    GreedyBytes,
    Struct,
)
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

from SolixBLE.constructs import ParameterDict

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

__all__ = [
    "CLIENT_ENCRYPT",
    "CLIENT_MTU",
    "Keys",
    "Link",
    "NegotiatedSessionLike",
    "Outer",
    "Path",
    "Session",
    "UnsupportedNegotiation",
    "client_parameters",
    "new_announcement",
    "override",
]

#: The client's ``a3`` in ``x003`` and ``x005``; the device logs it and ignores it.
CLIENT_ENCRYPT = 0x20
#: The client's MTU ceiling in ``x003`` and the plain ``0005`` (61 440 = no limit).
CLIENT_MTU = 0xF000

Keys = Struct(
    "key" / Bytes(16),
    "iv" / GreedyBytes,
    "nonce" / Computed(lambda this: this.iv[:12]),
)
"""
Session key material: a 16-byte key, then the IV.

ECDH parses the 32-byte shared secret (a 16-byte IV); the static key is the key
followed by its 12-byte nonce. GCM uses ``nonce``, CBC the whole ``iv``.

Usage:
    .. code-block:: python
       :linenos:

        keys = Keys.parse(shared_secret)
        print(f"key: {keys.key.hex()}, nonce: {keys.nonce.hex()}")

"""


def new_announcement() -> Container:
    """
    Return an empty record of what a device declares during negotiation.

    Fields, all None until the device sends them: ``mtu``, ``base_method``
    (``x803 a1``, base capability bits), ``encrypt_method`` (``x803 a3``,
    advanced capability bits), ``auth_method``, ``serial``, ``mac``,
    ``registration_status`` (``x827`` status) and ``confirmation_window``
    (seconds, from ``09``'s ``a1``).
    """
    return Container(
        mtu=None,
        base_method=None,
        encrypt_method=None,
        auth_method=None,
        serial=None,
        mac=None,
        registration_status=None,
        confirmation_window=None,
    )


class Link(Protocol):
    """What the negotiation needs from the device that owns it."""

    #: Client id in the plain outer's a2.
    _UUID_STRING: str
    #: Registered in 4027 a2; the class UUID unless the caller gives one.
    _client_token: str

    async def _send_packet(
        self,
        pattern: str,
        cmd: str,
        parameters: dict[str, Any],
    ) -> None:
        """Build and send one packet; lambda values are called with ``self``.

        :param pattern: Pattern of the packet as hex.
        :param cmd: Command of the packet as hex.
        :param parameters: Parameters by tag, each ``{"value": ...}``.
        """

    def _timestamp(self) -> bytes:
        """Return the current time as the 4-byte timestamp tag value."""

    def _timezone_offset(self) -> bytes:
        """Return the local UTC offset as int32 LE seconds west."""

    def _posix_timezone(self) -> str:
        """Return the local POSIX time zone string."""

    def _generate_private_key(self) -> EllipticCurvePrivateKey:
        """Return a fresh P-256 private key for one negotiation."""


class Outer(Protocol):
    """How the negotiation travels and which cipher the session uses."""

    name: ClassVar[str]
    open_flag: ClassVar[int]
    sends_client_id: ClassVar[bool]
    authorizes_at_key_exchange: ClassVar[bool]

    def x005_tags(self, announcement: Container) -> tuple[bytes, bytes | None]:
        """Return ``x005``'s ``a4`` and ``a6`` (or None) as the app sends them here.

        :param announcement: What the device declared so far.
        """

    def encrypt(self, payload: bytes, keys: Container | None) -> bytes:
        """Seal a payload under the installed keys, or the pre-key wrapper.

        :param payload: Plain-text bytes.
        :param keys: Keys a path installed, or None before the key exchange.
        """

    def decrypt(self, payload: bytes, keys: Container | None) -> bytes:
        """Open a payload under the installed keys, or the pre-key wrapper.

        :param payload: Cipher-text bytes.
        :param keys: Keys a path installed, or None before the key exchange.
        """


class NegotiatedSessionLike(Protocol):
    """What a path may use of the session that runs it."""

    link: Link
    announcement: Container

    @property
    def outer(self) -> Outer:
        """The outer protocol the session runs on."""

    async def send(
        self,
        msgtype: int,
        parameters: dict[str, dict[str, object]],
        *,
        client_id: bool = False,
    ) -> None:
        """Send a negotiation request, flagged and wrapped for the current state.

        :param msgtype: The 12-bit message type.
        :param parameters: Parameters by tag, each ``{"value": ...}``.
        :param client_id: Insert the client id as ``a2`` if the outer sends it.
        """


class Path(Protocol):
    """Key establishment and authorization after the shared opening."""

    name: ClassVar[str]
    keys: Container | None
    authorized: bool

    async def on_stage(
        self,
        session: NegotiatedSessionLike,
        msgtype: int,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Handle one negotiation reply after the capability exchange.

        :param session: The session running this path.
        :param msgtype: The reply's 12-bit message type.
        :param status: The reply's status byte.
        :param parameters: The reply's parameters.
        """


class Session(Protocol):
    """What the device needs from its negotiation."""

    announcement: Container

    @property
    def authorized(self) -> bool:
        """Whether the device accepts session commands."""

    @property
    def replied(self) -> bool:
        """Whether the device answered any negotiation request."""

    @property
    def outer(self) -> Outer:
        """The outer protocol this session runs on."""

    async def open(self) -> None:
        """Send the opening request."""

    async def on_reply(self, pattern: bytes, cmd: bytes, payload: bytes) -> None:
        """Handle one negotiation frame as received.

        :param pattern: The frame's pattern.
        :param cmd: The frame's command.
        :param payload: The frame's reassembled payload, decrypted here if flagged.
        """

    def on_session_push(self) -> None:
        """Record that the device pushed session data, which proves authorization."""

    def encrypt(self, payload: bytes) -> bytes:
        """Seal a payload for the current negotiation state.

        :param payload: Plain-text bytes.
        """

    def decrypt(self, payload: bytes) -> bytes:
        """Open a payload for the current negotiation state.

        :param payload: Cipher-text bytes.
        """


class UnsupportedNegotiation(Exception):  # noqa: N818
    """The device announced, or rejected, something no registered path handles."""

    def __init__(self, announcement: Container, detail: str = "") -> None:
        """Name what the device announced.

        :param announcement: What the device declared.
        :param detail: The stage or reason, if any.
        """
        method = announcement.encrypt_method
        base = announcement.base_method
        super().__init__(
            "Unsupported negotiation: "
            f"base_method={'None' if base is None else f'{base:#04x}'}, "
            f"encrypt_method={'None' if method is None else f'{method:#04x}'}, "
            f"auth_method={announcement.auth_method}, mtu={announcement.mtu}"
            + (f" ({detail})" if detail else ""),
        )
        self.announcement = announcement


def client_parameters(**tags: object) -> dict[str, dict[str, object]]:
    """Build a negotiation parameter dict for ``_send_packet`` from tag=value pairs."""
    return {tag: {"value": value} for tag, value in tags.items()}
