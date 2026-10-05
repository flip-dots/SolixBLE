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
    Int16ul,
)

from SolixBLE.utilities import ecdh_public_bytes, ecdh_shared_secret

from .base import (
    CLIENT_ENCRYPT,
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

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

    from SolixBLE.constructs import ParameterDict

_LOGGER = logging.getLogger(__name__)

#: Advanced capability bits that mean ECDH (x803 a3; either bit suffices).
ECDH_METHODS = 0x44
#: The method this path tells the device it will use (x005 a5), per outer, as
#: the app sends it: 0x40 on the plain outer, 0x44 on the encrypted one. The
#: firmware tests a5 & 0x44, so both select ECDH.
ECDH_METHOD = {"plain": 0x40, "encrypted": 0x44}
#: Status byte of an accepted reply.
STATUS_OK = 0x00
#: x827 status: the device waits for its button to confirm this client.
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
    def matches(cls, announcement: Container, outer: Outer) -> bool:  # noqa: ARG003  # the protocol's signature
        """Whether ``x803`` offers ECDH (``a3 & 0x44``) and an auth method (``a5``).

        :param announcement: What the device declared in ``x803``.
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
        msgtype: int,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Run ``x829`` to ``x827``: method, key exchange, clock and registration.

        :param session: The session running this path.
        :param msgtype: The reply's 12-bit message type.
        :param status: The reply's status byte.
        :param parameters: The reply's parameters.
        :raises RuntimeError: If ``x821`` arrives before the client key exists.
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
                self._key = session.link._generate_private_key()
                await session.send(
                    0x021,
                    client_parameters(a1=ecdh_public_bytes(self._key)),
                )
            case 0x821:
                self._exchange_keys(announcement, session.outer, parameters)
                await send_clock(session)
            case 0x822:
                if not self.authorized:
                    await session.send(
                        0x027,
                        client_parameters(
                            a1=lambda self: self._timestamp(),
                            a2=session.link._client_token.encode(),
                        ),
                    )
            case 0x827:
                self._register(announcement, status, parameters)

    def _exchange_keys(
        self,
        announcement: Container,
        outer: Outer,
        parameters: ParameterDict,
    ) -> None:
        """Derive the session keys from the device's ``x821`` public point.

        :param announcement: What the device declared so far.
        :param outer: The outer protocol the session runs on.
        :param parameters: The ``x821`` reply's parameters.
        :raises RuntimeError: If ``x821`` arrives before the client key exists.
        :raises UnsupportedNegotiation: If ``x821`` carries no device key.
        """
        if self._key is None:
            msg = "x821 before the client key was generated"
            raise RuntimeError(msg)
        if "a1" not in parameters:
            raise UnsupportedNegotiation(announcement, "x821 without a device key")
        self.keys = Keys.parse(
            ecdh_shared_secret(self._key, parameters["a1"].value_legacy),
        )
        if outer.authorizes_at_key_exchange:
            self.authorized = True

    def _register(
        self,
        announcement: Container,
        status: int,
        parameters: ParameterDict,
    ) -> None:
        """Record an ``x827``; ``00`` authorizes, ``09`` opens a confirmation window.

        The reply to ``4027`` and the grant pushed on ``030101`` after a button
        press are the same message; either authorizes.
        """
        announcement.registration_status = status
        if status == STATUS_OK:
            self.authorized = True
            return
        if status == STATUS_CONFIRM and "a1" in parameters:
            announcement.confirmation_window = Int16ul.parse(
                parameters["a1"].value_legacy,
            )
        _LOGGER.info("Client registration status %02x; not authorized", status)

    def _choose_method(
        self,
        session: NegotiatedSessionLike,
    ) -> dict[str, dict[str, object]]:
        """Tell the device this path's method in x005: ECDH.

        ECDH sets the device's mode 4 and opens ``x021``. The outer supplies
        ``a4`` and ``a6`` the way the app sends them on it.
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
