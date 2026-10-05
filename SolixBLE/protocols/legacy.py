"""Legacy AES key establishment, on the plain outer.

The older module builds answer ``0803`` with AES (``a1 02``) and no ECDH auth
method. The client opens CBC under its client id and the device serial, and
the device hands out the session key in ``4822``.

.. moduleauthor:: kb1ibt
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Bytes,
    Container,
    Int8ul,
    Int16ul,
)

from .base import (
    CLIENT_ENCRYPT,
    CLIENT_MTU,
    Keys,
    NegotiatedSessionLike,
    Outer,
    Path,
    UnsupportedNegotiation,
    client_parameters,
    override,
    record_identity,
    send_clock,
)
from .outer import PlainOuter

if TYPE_CHECKING:
    from SolixBLE.constructs import ParameterDict

_LOGGER = logging.getLogger(__name__)

#: Base capability bit that means AES (x803 a1).
AES_METHOD = 0x02
#: Status byte of an accepted reply.
STATUS_OK = 0x00
#: Length of the AES-128 key and IV.
KEY_LENGTH = 16
#: The first ``KEY_LENGTH`` bytes of a key source (client id, serial, ``4822 a1``).
KEY_PREFIX = Bytes(KEY_LENGTH)


class LegacyAesPath(Path):
    """AES-CBC keyed on the client id and serial, then on the key the device sends."""

    name: ClassVar[str] = "legacy_aes"

    def __init__(self) -> None:
        """Start with no keys and no authorization."""
        self.keys: Container | None = None
        self.authorized = False

    @classmethod
    @override
    def matches(cls, announcement: Container, outer: Outer) -> bool:
        """Whether ``x803`` offers AES (``a1 & 0x02``) on the plain outer.

        The device installs the legacy key only on a port opened with ``0001``.

        :param announcement: What the device declared in ``x803``.
        :param outer: The outer protocol the session runs on.
        """
        return isinstance(outer, PlainOuter) and bool(
            (announcement.base_method or 0) & AES_METHOD,
        )

    @override
    async def on_stage(
        self,
        session: NegotiatedSessionLike,
        msgtype: int,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Run ``0829`` to ``4823``: method, the initial key, the device key, bind.

        :param session: The session running this path.
        :param msgtype: The reply's 12-bit message type.
        :param status: The reply's status byte.
        :param parameters: The reply's parameters.
        :raises UnsupportedNegotiation: If the device rejects the method or key.
        """
        announcement = session.announcement
        match msgtype:
            case 0x829:
                record_identity(announcement, parameters)
                await session.send(
                    0x005,
                    client_parameters(
                        a1=lambda self: self._timestamp(),
                        a3=Int8ul.build(CLIENT_ENCRYPT),
                        a4=Int16ul.build(CLIENT_MTU),
                        a5=Int8ul.build(AES_METHOD),
                    ),
                    client_id=True,
                )
            case 0x805:
                if status != STATUS_OK:
                    raise UnsupportedNegotiation(
                        announcement,
                        f"x805 status {status:02x}",
                    )
                self.keys = Keys.parse(
                    self._client_id(session) + self._iv(announcement),
                )
                await send_clock(session)
            case 0x822:
                if status != STATUS_OK or "a1" not in parameters:
                    raise UnsupportedNegotiation(announcement, "x822 without a key")
                self.keys = Keys.parse(
                    KEY_PREFIX.parse(parameters["a1"].value_legacy)
                    + self._iv(announcement),
                )
                self.authorized = True
                await session.send(
                    0x023,
                    client_parameters(
                        a1=lambda self: self._timestamp(),
                        a3=announcement.serial,
                    ),
                    client_id=True,
                )
            case 0x823:
                _LOGGER.debug("Client bind status %02x", status)

    def _client_id(self, session: NegotiatedSessionLike) -> bytes:
        """Return the initial key: the client id's first 16 bytes."""
        key: bytes = KEY_PREFIX.parse(session.link._UUID_STRING.encode())  # noqa: SLF001
        return key

    def _iv(self, announcement: Container) -> bytes:
        """Return the IV: the device serial's first 16 bytes.

        :raises UnsupportedNegotiation: If ``x829`` carried no serial.
        """
        if announcement.serial is None:
            raise UnsupportedNegotiation(announcement, "x829 without a serial")
        iv: bytes = KEY_PREFIX.parse(announcement.serial)
        return iv
