"""The negotiated session: shared opening, the key exchange, cipher delegation.

.. moduleauthor:: kb1ibt
"""

# The Link's members are the owning device's own private hooks.
# ruff: noqa: SLF001

from __future__ import annotations

import logging

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Int8ul,
    Int16ul,
)

from SolixBLE.const import NEGOTIATION_PATTERN
from SolixBLE.constructs import PacketCommand, ParameterDict, Parameters

from .base import (
    CLIENT_ENCRYPT,
    CLIENT_MTU,
    Link,
    NegotiatedSessionLike,
    Outer,
    Path,
    Session,
    UnsupportedNegotiation,
    client_parameters,
    new_announcement,
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
        self.announcement = new_announcement()
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

    @override
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
        if client_id and self.outer.sends_client_id:
            a2: dict[str, object] = {"value": self.link._UUID_STRING.encode()}
            parameters = {"a1": parameters["a1"], "a2": a2} | {
                tag: value for tag, value in parameters.items() if tag != "a1"
            }
        keyed = self.path is not None and self.path.keys is not None
        encrypted = bool(self.outer.open_flag or keyed)
        cmd = PacketCommand.build(
            {
                "fragmented": False,
                "encrypted": encrypted,
                "reserved": 0,
                "msgtype": msgtype,
            },
        ).hex()
        await self.link._send_packet(
            pattern=NEGOTIATION_PATTERN,
            cmd=cmd,
            parameters=parameters,
        )

    @override
    async def open(self) -> None:
        """Send the outer's opening ``x001``."""
        await self.send(
            0x001,
            client_parameters(a1=lambda self: self._timestamp()),
            client_id=True,
        )

    @override
    async def on_reply(self, pattern: bytes, cmd: bytes, payload: bytes) -> None:
        """Handle one negotiation frame, decrypting it if its ``0x40`` flag is set.

        Clear ``08xx`` replies on the plain outer, static-GCM ``48xx`` before
        keys, CBC or GCM once keys are installed.

        :param pattern: The frame's pattern.
        :param cmd: The frame's command.
        :param payload: The frame's reassembled payload.
        """
        encrypted = PacketCommand.parse(cmd).encrypted
        await self.on_plaintext(
            pattern,
            cmd,
            self.decrypt(payload) if encrypted else payload,
        )

    async def on_plaintext(
        self,
        pattern: bytes,  # noqa: ARG002  # kept for device-initiated frames
        cmd: bytes,
        plaintext: bytes,
    ) -> None:
        """Handle one decrypted negotiation reply (also the test entry point).

        The status byte is ``Parameters``' prefix; ``pattern`` is kept for
        device-initiated frames such as the ``030101`` grant.

        :param pattern: The frame's pattern.
        :param cmd: The frame's command.
        :param plaintext: The decrypted payload.
        """
        self._replied = True
        parameters = Parameters.parse(plaintext)
        status = parameters.status if parameters.status is not None else STATUS_EMPTY
        msgtype = PacketCommand.parse(cmd).msgtype
        match msgtype:
            case 0x801:
                await self.send(
                    0x003,
                    client_parameters(
                        a1=lambda self: self._timestamp(),
                        a3=Int8ul.build(CLIENT_ENCRYPT),
                        a4=Int16ul.build(CLIENT_MTU),
                    ),
                    client_id=True,
                )
            case 0x803:
                self._record_capability(parameters)
                self.path = self._choose_path()
                await self.send(
                    0x029,
                    client_parameters(a1=lambda self: self._timestamp()),
                    client_id=True,
                )
            case _ if self.path is not None:
                await self.path.on_stage(self, msgtype, status, parameters)
            case _:
                _LOGGER.warning(
                    "Negotiation reply %03x before the capability exchange",
                    msgtype,
                )

    def _record_capability(self, parameters: ParameterDict) -> None:
        """Record the capability bits, MTU and auth method of ``x803``."""
        self.announcement.base_method = (
            Int8ul.parse(parameters["a1"].value_legacy) if "a1" in parameters else None
        )
        self.announcement.mtu = Int16ul.parse(parameters["a2"].value_legacy)
        self.announcement.encrypt_method = Int8ul.parse(parameters["a3"].value_legacy)
        self.announcement.auth_method = (
            Int8ul.parse(parameters["a5"].value_legacy) if "a5" in parameters else None
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
        """Seal a payload with the outer, under the path's keys if installed.

        :param payload: Plain-text bytes.
        """
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
