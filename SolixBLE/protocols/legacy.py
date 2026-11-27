"""Legacy AES key establishment, on either outer protocol.

Older module builds answer the capability negotiation with AES (``a1 02``)
and no ECDH auth method: the F3800 (#63) and the 2024 A2345 module builds.
The A91B2 takes it too, and on the encrypted outer it is the only path that
device accepts.

The exchange, after the shared opening and the device-info reply:

1. ``SET_CAPABILITY`` with ``a5 02`` chooses legacy AES.
2. ``GET_AES_KEY`` (the clock) goes out CBC-sealed under a bootstrap key: the
   client id and the device serial on the plain outer, the static key and IV
   on the encrypted outer, which never sends a client id.
3. Its reply carries a 16-byte session key, CBC-encrypted under the bootstrap
   key. Everything after uses the session key, with the same IV.
4. ``BIND_USER`` binds the client to the device serial, as the app does.

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

from SolixBLE.constructs import Negotiation
from SolixBLE.utilities import cbc_encrypt

from .base import (
    CLIENT_ENCRYPT,
    Announcement,
    Keys,
    Link,
    NegotiatedSessionLike,
    Outer,
    Path,
    UnsupportedNegotiation,
    client_parameters,
    override,
)
from .outer import STATIC_KEYS

if TYPE_CHECKING:
    from SolixBLE.constructs import ParameterDict

_LOGGER = logging.getLogger(__name__)

#: Base capability bit that means AES (capability reply a1).
AES_METHOD = 0x02
#: Status byte of an accepted reply.
STATUS_OK = 0x00
#: Length of the AES-128 key and IV.
KEY_LENGTH = 16
#: The first ``KEY_LENGTH`` bytes of a key source (client id, serial, session key).
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
        announcement: Announcement,
        outer: Outer,  # noqa: ARG003  # the protocol's signature; legacy runs on either
    ) -> bool:
        """Whether the capability reply offers AES (``a1 & 0x02``), on either outer.

        :param announcement: What the device declared in its capability reply.
        :param outer: The outer protocol; legacy AES runs on either.
        """
        return bool((announcement.base_method or 0) & AES_METHOD)

    @override
    def encrypt_override(self, payload: bytes) -> bytes | None:
        """CBC-seal requests under the bootstrap key until the session key arrives.

        The device answers ``GET_AES_KEY`` only when it is CBC-sealed under
        the bootstrap key, on either outer. The plain outer seals it that way
        on its own; this override exists for the encrypted outer, whose own
        cipher is GCM. Once the session key authorizes the path it returns
        None, and everything goes through the outer's cipher again.

        :param payload: Plain-text bytes.
        """
        if self.authorized or self.keys is None:
            return None
        return cbc_encrypt(self.keys.key, self.keys.iv, payload)

    @override
    async def on_stage(
        self,
        session: NegotiatedSessionLike,
        message: int,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Run the device-info reply to the bind: method, both keys, then the bind.

        :param session: The session running this path.
        :param message: The reply's :class:`~SolixBLE.constructs.Negotiation` message.
        :param status: The reply's status byte.
        :param parameters: The reply's parameters.
        :raises UnsupportedNegotiation: If the device rejects the method or key.
        """
        announcement = session.announcement
        match message:
            case Negotiation.GET_DEVICE_INFO:
                announcement.record_device_info(parameters)
                await session.send(
                    Negotiation.SET_CAPABILITY,
                    self._choose_method(session),
                    client_id=True,
                )
            case Negotiation.SET_CAPABILITY:
                if status != STATUS_OK:
                    raise UnsupportedNegotiation(
                        announcement,
                        f"SET_CAPABILITY status {status:02x}",
                    )
                self.keys = self._bootstrap_keys(
                    session.outer,
                    session.link,
                    announcement,
                )
                await session.send_clock()
            case Negotiation.GET_AES_KEY:
                if status != STATUS_OK or "a1" not in parameters:
                    raise UnsupportedNegotiation(
                        announcement,
                        "GET_AES_KEY reply without a key",
                    )
                self.keys = Keys.parse(
                    KEY_PREFIX.parse(parameters["a1"].value_legacy)
                    + self._ongoing_iv(session.outer, announcement),
                )
                self.authorized = True
                await session.send(
                    Negotiation.BIND_USER,
                    client_parameters(
                        a1=lambda self: self._timestamp(),
                        a3=announcement.serial,
                    ),
                    client_id=True,
                )
            case Negotiation.BIND_USER:
                _LOGGER.debug("Client bind status %02x", status)

    def _choose_method(
        self,
        session: NegotiatedSessionLike,
    ) -> dict[str, dict[str, object]]:
        """Tell the device this path's method in ``SET_CAPABILITY``: legacy AES.

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
        announcement: Announcement,
    ) -> Container:
        """Return the bootstrap key, used until the session key arrives.

        The encrypted outer's static key and IV, else the client id this
        session opened with and the device serial.

        :param outer: The outer protocol the session runs on.
        :param link: The device sending the frames.
        :param announcement: What the device declared in its device-info reply.
        """
        if not outer.sends_client_id:
            return STATIC_KEYS
        client_id: bytes = KEY_PREFIX.parse(link._UUID_STRING.encode())  # noqa: SLF001
        return Keys.parse(client_id + self._iv(announcement))

    def _ongoing_iv(self, outer: Outer, announcement: Announcement) -> bytes:
        """Return the IV/nonce source for traffic once the session key arrives.

        The static IV on the encrypted outer, the serial on the plain one.

        :param outer: The outer protocol the session runs on.
        :param announcement: What the device declared in its device-info reply.
        """
        if not outer.sends_client_id:
            iv: bytes = STATIC_KEYS.iv
            return iv
        return self._iv(announcement)

    def _iv(self, announcement: Announcement) -> bytes:
        """Return the IV: the device serial's first 16 bytes.

        :raises UnsupportedNegotiation: If the device-info reply carried no serial.
        """
        if announcement.serial is None:
            raise UnsupportedNegotiation(
                announcement,
                "GET_DEVICE_INFO reply without a serial",
            )
        iv: bytes = KEY_PREFIX.parse(announcement.serial)
        return iv
