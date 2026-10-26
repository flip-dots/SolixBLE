"""ECDH key establishment, on either outer protocol.

.. moduleauthor:: kb1ibt
"""

# The Link's members are the owning device's own private hooks.
# ruff: noqa: SLF001

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
    Int8ul,
)

from SolixBLE.constructs import Negotiation
from SolixBLE.utilities import ecdh_public_bytes, ecdh_shared_secret

from .base import (
    CLIENT_ENCRYPT,
    Announcement,
    Keys,
    NegotiatedSessionLike,
    Outer,
    Path,
    UnsupportedNegotiation,
    client_parameters,
    override,
)

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

    from SolixBLE.constructs import ParameterDict

_LOGGER = logging.getLogger(__name__)

#: Advanced capability bits that mean ECDH (capability reply a3; either bit suffices).
ECDH_METHODS = 0x44
#: The method this path tells the device it will use (SET_CAPABILITY a5), per
#: outer, as the app sends it: 0x40 on the plain outer, 0x44 on the encrypted
#: one. The firmware tests a5 & 0x44, so both select ECDH.
ECDH_METHOD = {"plain": 0x40, "encrypted": 0x44}
#: Status byte of an accepted reply.
STATUS_OK = 0x00
#: Registration status: the device waits for its button to confirm this client.
STATUS_CONFIRM = 0x09


class EcdhPath(Path):
    """P-256 ECDH, a fresh key per negotiation; the outer decides CBC or GCM."""

    name: ClassVar[str] = "ecdh"

    def __init__(self) -> None:
        """Start with no keys and no authorization."""
        self.keys: Container | None = None
        self.authorized = False
        self._key: EllipticCurvePrivateKey | None = None

    @classmethod
    @override
    def matches(cls, announcement: Announcement, outer: Outer) -> bool:  # noqa: ARG003  # the protocol's signature
        """Whether the capability reply offers ECDH (``a3 & 0x44``) and an auth method.

        :param announcement: What the device declared in its capability reply.
        :param outer: The outer protocol; ECDH runs on either.
        """
        return (
            bool((announcement.encrypt_method or 0) & ECDH_METHODS)
            and announcement.auth_method is not None
        )

    @override
    async def on_stage(
        self,
        session: NegotiatedSessionLike,
        message: int,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Run the device-info reply to registration: method, keys, clock, register.

        :param session: The session running this path.
        :param message: The reply's :class:`~SolixBLE.constructs.Negotiation` message.
        :param status: The reply's status byte.
        :param parameters: The reply's parameters.
        :raises RuntimeError: If the key exchange reply arrives before the client key.
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
                self._key = session.link._generate_private_key()
                await session.send(
                    Negotiation.GET_PUBLIC_KEY,
                    client_parameters(a1=ecdh_public_bytes(self._key)),
                )
            case Negotiation.GET_PUBLIC_KEY:
                self._exchange_keys(announcement, session.outer, parameters)
                await session.send_clock()
            case Negotiation.GET_AES_KEY:
                if not self.authorized:
                    await session.send(
                        Negotiation.GET_AUTHENTICATION,
                        client_parameters(
                            a1=lambda self: self._timestamp(),
                            a2=session.link._client_token.encode(),
                        ),
                    )
            case Negotiation.GET_AUTHENTICATION:
                self._register(announcement, status, parameters)

    def _exchange_keys(
        self,
        announcement: Announcement,
        outer: Outer,
        parameters: ParameterDict,
    ) -> None:
        """Derive the session keys from the device's public point.

        :param announcement: What the device declared so far.
        :param outer: The outer protocol the session runs on.
        :param parameters: The ``GET_PUBLIC_KEY`` reply's parameters.
        :raises RuntimeError: If the reply arrives before the client key exists.
        :raises UnsupportedNegotiation: If the reply carries no device key.
        """
        if self._key is None:
            msg = "GET_PUBLIC_KEY reply before the client key was generated"
            raise RuntimeError(msg)
        if "a1" not in parameters:
            raise UnsupportedNegotiation(
                announcement,
                "GET_PUBLIC_KEY reply without a device key",
            )
        self.keys = Keys.parse(
            ecdh_shared_secret(self._key, parameters["a1"].value_legacy),
        )
        if outer.authorizes_at_key_exchange:
            self.authorized = True

    def _register(
        self,
        announcement: Announcement,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Record a registration reply; ``00`` authorizes, ``09`` asks for the button.

        The reply to ``GET_AUTHENTICATION`` and the grant the device pushes
        after a button press are the same message; either authorizes.
        """
        announcement.registration_status = status
        if status == STATUS_OK:
            self.authorized = True
            return
        if status == STATUS_CONFIRM:
            announcement.record_confirmation(parameters)
        _LOGGER.info("Client registration status %02x; not authorized", status)

    def _choose_method(
        self,
        session: NegotiatedSessionLike,
    ) -> dict[str, dict[str, object]]:
        """Tell the device this path's method in ``SET_CAPABILITY``: ECDH.

        ECDH sets the device's mode 4 and opens ``GET_PUBLIC_KEY``. The outer
        supplies ``a4`` and ``a6`` the way the app sends them on it.
        """
        a4, a6 = session.outer.x005_tags(session.announcement)
        tags = client_parameters(
            a1=lambda self: self._timestamp(),
            a3=Int8ul.build(CLIENT_ENCRYPT),
            a4=a4,
            a5=Int8ul.build(ECDH_METHOD[session.outer.name]),
        )
        if a6 is not None:
            tags["a6"] = {"value": a6}
        return tags
