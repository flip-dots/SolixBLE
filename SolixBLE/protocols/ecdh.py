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
    Path,
    client_parameters,
    override,
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
        """
        announcement = session.announcement
        match msgtype:
            case 0x829:
                self._record_identity(announcement, parameters)
                await session.send(0x005, self._choose_method(session), client_id=True)
            case 0x805:
                self._key = session.link._generate_private_key()
                await session.send(
                    0x021,
                    client_parameters(a1=ecdh_public_bytes(self._key)),
                )
            case 0x821:
                if self._key is None:
                    msg = "x821 before the client key was generated"
                    raise RuntimeError(msg)
                self.keys = Keys.parse(
                    ecdh_shared_secret(self._key, parameters["a1"].value_legacy),
                )
                if session.outer.authorizes_at_key_exchange:
                    self.authorized = True
                # The outer adds a2 (the app sends it on the plain outer only).
                await session.send(
                    0x022,
                    client_parameters(
                        a1=lambda self: self._timestamp(),
                        a3=session.link._timezone_offset(),
                        a5=session.link._posix_timezone().encode(),
                    ),
                    client_id=True,
                )
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

    def _record_identity(
        self,
        announcement: Container,
        parameters: ParameterDict,
    ) -> None:
        """Record the serial (``a4``) and MAC (``a5``) the device sent in ``x829``."""
        if "a4" in parameters:
            announcement.serial = parameters["a4"].value_legacy
        if "a5" in parameters:
            announcement.mac = parameters["a5"].value_legacy

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
