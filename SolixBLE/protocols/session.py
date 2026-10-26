"""The negotiated session: shared opening, the key exchange, cipher delegation.

.. moduleauthor:: kb1ibt
"""

# The Link's members are the owning device's own private hooks.
# ruff: noqa: SLF001

from __future__ import annotations

import logging

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
    Int8ul,
    Int16ul,
)

from SolixBLE.constructs import Channel, Negotiation, Parameters

from .base import (
    CLIENT_ENCRYPT,
    CLIENT_MTU,
    Announcement,
    Link,
    NegotiatedSessionLike,
    Outer,
    Path,
    Session,
    UnsupportedNegotiation,
    client_parameters,
    override,
)
from .ecdh import EcdhPath
from .legacy import LegacyAesPath

_LOGGER = logging.getLogger(__name__)

#: Status recorded for a reply without a status byte (never a device status byte).
STATUS_EMPTY = 0xFF

#: Key establishment paths, tried in order against the capability reply.
PATHS: tuple[type[Path], ...] = (EcdhPath, LegacyAesPath)


class NegotiatedSession(NegotiatedSessionLike, Session):
    """One negotiation on one connection: an outer and the path that follows."""

    def __init__(self, outer: Outer, link: Link) -> None:
        """Start a negotiation on an outer protocol for the device behind ``link``.

        :param outer: The outer protocol to open with.
        :param link: The device that sends the frames.
        """
        self._outer = outer
        self.link = link
        self.announcement = Announcement()
        self.path: Path | None = None
        self._replied = False
        self._pushed = False

    @property
    @override
    def authorized(self) -> bool:
        """Whether a session push arrived or the path authorized."""
        return self._pushed or (self.path is not None and self.path.authorized)

    @property
    @override
    def replied(self) -> bool:
        """Whether the device answered any negotiation request."""
        return self._replied

    @property
    @override
    def outer(self) -> Outer:
        """The outer protocol this session runs on."""
        return self._outer

    @property
    @override
    def encrypts(self) -> bool:
        """Whether frames sent now carry the encrypted flag.

        Always on the encrypted outer; on the plain outer once a path has
        installed keys.
        """
        keyed = self.path is not None and self.path.keys is not None
        return bool(self.outer.open_flag or keyed)

    @override
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
        if client_id and self.outer.sends_client_id:
            a2: dict[str, object] = {"value": self.link._UUID_STRING.encode()}
            parameters = {"a1": parameters["a1"], "a2": a2} | {
                tag: value for tag, value in parameters.items() if tag != "a1"
            }
        await self.link._send_packet(
            channel=Channel.NEGOTIATION,
            command=Container(encrypted=self.encrypts, message=message),
            parameters=parameters,
        )

    @override
    async def send_clock(self) -> None:
        """Send ``GET_AES_KEY``: the time, UTC offset and POSIX time zone.

        The UTC offset is int32 LE seconds west; the outer adds the client id
        as ``a2`` where the app sends it.
        """
        await self.send(
            Negotiation.GET_AES_KEY,
            client_parameters(
                a1=lambda self: self._timestamp(),
                a3=self.link._timezone_offset(),
                a5=self.link._posix_timezone().encode(),
            ),
            client_id=True,
        )

    @override
    async def open(self) -> None:
        """Send the outer's opening ``CONNECT``."""
        await self.send(
            Negotiation.CONNECT,
            client_parameters(a1=lambda self: self._timestamp()),
            client_id=True,
        )

    @override
    async def on_reply(self, packet: Container, payload: bytes) -> None:
        """Handle one negotiation frame, decrypting it if its encrypted flag is set.

        Clear replies on the plain outer, static-GCM ones before keys on the
        encrypted outer, CBC or GCM once keys are installed.

        :param packet: The parsed frame.
        :param payload: The frame's reassembled payload.
        """
        await self.on_plaintext(
            packet,
            self.decrypt(payload) if packet.encrypted else payload,
        )

    async def on_plaintext(self, packet: Container, plaintext: bytes) -> None:
        """Handle one decrypted negotiation reply (also the test entry point).

        The status byte is ``Parameters``' prefix. A device-initiated frame,
        such as the grant after a button press, arrives the same way.

        :param packet: The parsed frame.
        :param plaintext: The decrypted payload.
        """
        self._replied = True
        if not packet.response:
            _LOGGER.debug("Ignoring negotiation request %03x", packet.msgtype)
            return
        parameters = Parameters.parse(plaintext)
        status = parameters.status if parameters.status is not None else STATUS_EMPTY
        match packet.message:
            case Negotiation.CONNECT:
                await self.send(
                    Negotiation.NEGOTIATE_CAPABILITY,
                    client_parameters(
                        a1=lambda self: self._timestamp(),
                        a3=Int8ul.build(CLIENT_ENCRYPT),
                        a4=Int16ul.build(CLIENT_MTU),
                    ),
                    client_id=True,
                )
            case Negotiation.NEGOTIATE_CAPABILITY:
                self.announcement.record_capability(parameters)
                self.path = self._choose_path()
                await self.send(
                    Negotiation.GET_DEVICE_INFO,
                    client_parameters(a1=lambda self: self._timestamp()),
                    client_id=True,
                )
            case _ if self.path is not None:
                await self.path.on_stage(self, packet.message, status, parameters)
            case _:
                _LOGGER.warning(
                    "Negotiation reply %03x before the capability exchange",
                    packet.msgtype,
                )

    def _choose_path(self) -> Path:
        """Return the first registered path that handles the capability reply.

        :raises UnsupportedNegotiation: If no registered path handles it.
        """
        for path_class in PATHS:
            if path_class.matches(self.announcement, self.outer):
                return path_class()
        raise UnsupportedNegotiation(
            self.announcement,
            f"no path for the {self.outer.name} outer",
        )

    @override
    def on_session_push(self) -> None:
        """Record a session push, which proves authorization."""
        self._pushed = True

    @override
    def encrypt(self, payload: bytes) -> bytes:
        """Seal a payload with the path's own cipher if it overrides, else the outer's.

        :param payload: Plain-text bytes.
        """
        if self.path is not None:
            override = self.path.encrypt_override(payload)
            if override is not None:
                return override
        return self.outer.encrypt(
            payload,
            self.path.keys if self.path is not None else None,
        )

    @override
    def decrypt(self, payload: bytes) -> bytes:
        """Open a payload with the outer, under the path's keys if installed.

        :param payload: Cipher-text bytes.
        """
        return self.outer.decrypt(
            payload,
            self.path.keys if self.path is not None else None,
        )
