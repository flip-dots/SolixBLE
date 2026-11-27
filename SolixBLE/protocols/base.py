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
    Int8ul,
    Int16ul,
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
    "Announcement",
    "Keys",
    "Link",
    "NegotiatedSessionLike",
    "Outer",
    "Path",
    "Session",
    "UnsupportedNegotiation",
    "client_parameters",
    "override",
]

#: The client's ``a3`` in ``NEGOTIATE_CAPABILITY`` and ``SET_CAPABILITY``; the
#: device logs it and ignores it.
CLIENT_ENCRYPT = 0x20
#: The client's MTU ceiling in ``NEGOTIATE_CAPABILITY`` and the plain outer's
#: ``SET_CAPABILITY`` (61 440 = no limit).
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


#: Fields of the ``NEGOTIATE_CAPABILITY`` reply, by tag. Negotiation tags carry
#: no type byte, so each parses the tag's whole value.
CAPABILITY_FIELDS = {
    "a1": Struct("base_method" / Int8ul),
    "a2": Struct("mtu" / Int16ul),
    "a3": Struct("encrypt_method" / Int8ul),
    "a5": Struct("auth_method" / Int8ul),
}

#: Fields of the ``GET_DEVICE_INFO`` reply, by tag.
DEVICE_INFO_FIELDS = {
    "a4": Struct("serial" / GreedyBytes),
    "a5": Struct("mac" / GreedyBytes),
}

#: Fields of a ``GET_AUTHENTICATION`` reply that asks for the button, by tag.
CONFIRMATION_FIELDS = {
    "a1": Struct("confirmation_window" / Int16ul),
}


class Announcement:
    """What a device declares during negotiation.

    Every field is None until the device sends it: ``mtu``, ``base_method``
    (base capability bits), ``encrypt_method`` (advanced capability bits),
    ``auth_method``, ``serial``, ``mac``, ``registration_status`` (the
    ``GET_AUTHENTICATION`` reply's status) and ``confirmation_window``
    (seconds to press the button).
    """

    def __init__(self) -> None:
        """Start with nothing declared."""
        self.mtu: int | None = None
        self.base_method: int | None = None
        self.encrypt_method: int | None = None
        self.auth_method: int | None = None
        self.serial: bytes | None = None
        self.mac: bytes | None = None
        self.registration_status: int | None = None
        self.confirmation_window: int | None = None

    def record_capability(self, parameters: ParameterDict) -> None:
        """Record the capability bits, MTU and auth method of the capability reply.

        :param parameters: The ``NEGOTIATE_CAPABILITY`` reply's parameters.
        """
        self._record(parameters, CAPABILITY_FIELDS)

    def record_device_info(self, parameters: ParameterDict) -> None:
        """Record the serial and MAC of the device-info reply.

        :param parameters: The ``GET_DEVICE_INFO`` reply's parameters.
        """
        self._record(parameters, DEVICE_INFO_FIELDS)

    def record_confirmation(self, parameters: ParameterDict) -> None:
        """Record how long the device waits for its button to be pressed.

        :param parameters: The parameters of a registration reply asking for it.
        """
        self._record(parameters, CONFIRMATION_FIELDS)

    def _record(self, parameters: ParameterDict, fields: dict[str, Struct]) -> None:
        """Set the fields each present tag parses to.

        :param parameters: A reply's parameters.
        :param fields: The reply's fields by tag.
        """
        for tag, struct in fields.items():
            if tag in parameters:
                for name, value in struct.parse(parameters[tag].value_legacy).items():
                    if not name.startswith("_"):
                        setattr(self, name, value)


class Link(Protocol):
    """What the negotiation needs from the device that owns it."""

    #: Client id in the plain outer's a2.
    _UUID_STRING: str
    #: Registered in GET_AUTHENTICATION a2; the class UUID unless the caller gives one.
    _client_token: str

    async def _send_packet(
        self,
        channel: int,
        command: Container,
        parameters: dict[str, Any],
    ) -> None:
        """Build and send one packet; lambda values are called with ``self``.

        :param channel: The channel to send on.
        :param command: The command's fields (flags, ``message``, ``response``).
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

    def x005_tags(self, announcement: Announcement) -> tuple[bytes, bytes | None]:
        """Return ``SET_CAPABILITY``'s ``a4`` and ``a6`` (or None), as the app does.

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
    announcement: Announcement

    @property
    def outer(self) -> Outer:
        """The outer protocol the session runs on."""

    async def send(
        self,
        message: int,
        parameters: dict[str, dict[str, object]],
        *,
        client_id: bool = False,
    ) -> None:
        """Send a negotiation request, flagged and wrapped for the current state.

        :param message: The request's :class:`~SolixBLE.constructs.Negotiation` message.
        :param parameters: Parameters by tag, each ``{"value": ...}``.
        :param client_id: Insert the client id as ``a2`` if the outer sends it.
        """

    async def send_clock(self) -> None:
        """Send ``GET_AES_KEY`` with the time, UTC offset and POSIX time zone."""


class Path(Protocol):
    """Key establishment and authorization after the shared opening."""

    name: ClassVar[str]
    keys: Container | None
    authorized: bool

    @classmethod
    def matches(cls, announcement: Announcement, outer: Outer) -> bool:
        """Whether this path handles what the device declared, on this outer.

        :param announcement: What the device declared in its capability reply.
        :param outer: The outer protocol the session runs on.
        """

    async def on_stage(
        self,
        session: NegotiatedSessionLike,
        message: int,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Handle one negotiation reply after the capability exchange.

        :param session: The session running this path.
        :param message: The reply's :class:`~SolixBLE.constructs.Negotiation` message.
        :param status: The reply's status byte.
        :param parameters: The reply's parameters.
        """

    def encrypt_override(
        self,
        payload: bytes,  # noqa: ARG002  # overridden by paths that use this
    ) -> bytes | None:
        """Return this path's own ciphertext for ``payload``, or None for the outer's.

        The default never overrides, so the session falls through to the
        outer's cipher. A path whose own key exchange has a fixed cipher
        independent of the outer (the legacy AES path's bootstrap request)
        returns its own ciphertext here until it is authorized, then None.

        :param payload: Plain-text bytes the session is about to send.
        """
        return None


class Session(Protocol):
    """What the device needs from its negotiation."""

    announcement: Announcement

    @property
    def authorized(self) -> bool:
        """Whether the device accepts session commands."""

    @property
    def replied(self) -> bool:
        """Whether the device answered any negotiation request."""

    @property
    def encrypts(self) -> bool:
        """Whether frames sent now carry the encrypted flag."""

    @property
    def outer(self) -> Outer:
        """The outer protocol this session runs on."""

    async def open(self) -> None:
        """Send the opening request."""

    async def on_reply(self, packet: Container, payload: bytes) -> None:
        """Handle one negotiation frame as received.

        :param packet: The parsed frame.
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

    def __init__(self, announcement: Announcement, detail: str = "") -> None:
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
