"""Legacy AES key establishment, on either outer protocol.

The older module builds answer ``0803`` with AES (``a1 02``) and no ECDH auth
method. On the plain outer the client opens CBC under the client id it
connected with and the device serial; on the encrypted outer, which never
sends a client id, it opens CBC under the outer's own static key instead.
Either way the device hands out the session key in ``4822``.

.. moduleauthor:: kb1ibt
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Bytes,
    Container,
    Int8ul,
)

from SolixBLE.utilities import cbc_encrypt

from .base import (
    CLIENT_ENCRYPT,
    Keys,
    Link,
    NegotiatedSessionLike,
    Outer,
    Path,
    UnsupportedNegotiation,
    client_parameters,
    override,
    record_identity,
    send_clock,
)
from .outer import STATIC_KEYS

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
    """AES-CBC keyed on the bootstrap material, then on the key the device sends."""

    name: ClassVar[str] = "legacy_aes"

    def __init__(self) -> None:
        """Start with no keys and no authorization."""
        self.keys: Container | None = None
        self.authorized = False

    @classmethod
    @override
    def matches(
        cls,
        announcement: Container,
        outer: Outer,  # noqa: ARG003  # the protocol's signature; legacy runs on either
    ) -> bool:
        """Whether ``x803`` offers AES (``a1 & 0x02``), on either outer.

        :param announcement: What the device declared in ``x803``.
        :param outer: The outer protocol; legacy AES runs on either.
        """
        return bool((announcement.base_method or 0) & AES_METHOD)

    @override
    def encrypt_override(self, payload: bytes) -> bytes | None:
        """CBC-seal the bootstrap exchange under the current keys.

        The device answers the ``0022``/``4822`` key request in CBC under
        whatever keys this path just installed (the client id and serial on
        the plain outer, the outer's own static key on the encrypted one),
        regardless of the outer's own cipher: ``EncryptedOuter`` can only
        produce GCM on its own. Once the device's key authorizes the path,
        traffic resumes under the outer's normal cipher with that key.

        :param payload: Plain-text bytes.
        """
        if self.authorized or self.keys is None:
            return None
        return cbc_encrypt(self.keys.key, self.keys.iv, payload)

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
                await session.send(0x005, self._choose_method(session), client_id=True)
            case 0x805:
                if status != STATUS_OK:
                    raise UnsupportedNegotiation(
                        announcement,
                        f"x805 status {status:02x}",
                    )
                self.keys = self._bootstrap_keys(
                    session.outer,
                    session.link,
                    announcement,
                )
                await send_clock(session)
            case 0x822:
                if status != STATUS_OK or "a1" not in parameters:
                    raise UnsupportedNegotiation(announcement, "x822 without a key")
                self.keys = Keys.parse(
                    KEY_PREFIX.parse(parameters["a1"].value_legacy)
                    + self._ongoing_iv(session.outer, announcement),
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

    def _choose_method(
        self,
        session: NegotiatedSessionLike,
    ) -> dict[str, dict[str, object]]:
        """Tell the device this path's method in x005: legacy AES.

        The outer supplies ``a4`` and ``a6`` the way the app sends them on it.
        """
        a4, a6 = session.outer.x005_tags(session.announcement)
        tags = client_parameters(
            a1=lambda self: self._timestamp(),
            a3=Int8ul.build(CLIENT_ENCRYPT),
            a4=a4,
            a5=Int8ul.build(AES_METHOD),
        )
        if a6 is not None:
            tags["a6"] = {"value": a6}
        return tags

    def _bootstrap_keys(
        self,
        outer: Outer,
        link: Link,
        announcement: Container,
    ) -> Container:
        """Return the pre-``0822`` key.

        The static key on the encrypted outer, else the client id this
        session opened with and the device serial.

        :param outer: The outer protocol the session runs on.
        :param link: The device sending the frames.
        :param announcement: What the device declared in ``x829``.
        """
        if not outer.sends_client_id:
            return STATIC_KEYS
        client_id: bytes = KEY_PREFIX.parse(link._UUID_STRING.encode())  # noqa: SLF001
        return Keys.parse(client_id + self._iv(announcement))

    def _ongoing_iv(self, outer: Outer, announcement: Container) -> bytes:
        """Return the IV/nonce source for traffic once the device's key arrives.

        The static nonce on the encrypted outer, the serial on the plain one.

        :param outer: The outer protocol the session runs on.
        :param announcement: What the device declared in ``x829``.
        """
        if not outer.sends_client_id:
            iv: bytes = STATIC_KEYS.iv
            return iv
        return self._iv(announcement)

    def _iv(self, announcement: Container) -> bytes:
        """Return the IV: the device serial's first 16 bytes.

        :raises UnsupportedNegotiation: If ``x829`` carried no serial.
        """
        if announcement.serial is None:
            raise UnsupportedNegotiation(announcement, "x829 without a serial")
        iv: bytes = KEY_PREFIX.parse(announcement.serial)
        return iv
