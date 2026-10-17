"""Outer negotiation protocols: how the negotiation travels and the session cipher.

The port cipher follows the connect frame: ``0001`` gives CBC, ``4001`` GCM.

.. moduleauthor:: kb1ibt
"""

from __future__ import annotations

from typing import ClassVar

from construct import (  # type: ignore[import-untyped]  # construct ships no type stubs
    Container,
    Int8ul,
    Int16ul,
)

from SolixBLE.const import NEGOTIATION_AAD, NEGOTIATION_KEY, NEGOTIATION_NONCE
from SolixBLE.utilities import cbc_decrypt, cbc_encrypt, gcm_decrypt, gcm_encrypt

from .base import CLIENT_MTU, Keys, Outer, override

#: Static key material of the encrypted outer before a path installs keys.
STATIC_KEYS = Keys.parse(bytes.fromhex(NEGOTIATION_KEY + NEGOTIATION_NONCE))
AAD = bytes.fromhex(NEGOTIATION_AAD)


class PlainOuter(Outer):
    """``0xxx`` negotiation in clear; AES-CBC once a path installs keys."""

    name: ClassVar[str] = "plain"
    open_flag: ClassVar[int] = 0x00
    sends_client_id: ClassVar[bool] = True
    authorizes_at_key_exchange: ClassVar[bool] = True

    @override
    def x005_tags(self, announcement: Container) -> tuple[bytes, bytes | None]:  # noqa: ARG002  # the protocol's signature
        """Return the app's plain-outer ``0005`` tags: its MTU ceiling, no ``a6``.

        The app sends these whatever the device declared.

        :param announcement: What the device declared so far.
        """
        return Int16ul.build(CLIENT_MTU), None

    @override
    def encrypt(self, payload: bytes, keys: Container | None) -> bytes:
        """Leave the payload clear before keys, AES-CBC under them.

        :param payload: Plain-text bytes.
        :param keys: Keys a path installed, or None before the key exchange.
        """
        return payload if keys is None else cbc_encrypt(keys.key, keys.iv, payload)

    @override
    def decrypt(self, payload: bytes, keys: Container | None) -> bytes:
        """Return the payload as is before keys, AES-CBC decrypted under them.

        :param payload: Cipher-text bytes.
        :param keys: Keys a path installed, or None before the key exchange.
        """
        return payload if keys is None else cbc_decrypt(keys.key, keys.iv, payload)


class EncryptedOuter(Outer):
    """``4xxx`` negotiation under the static GCM key.

    AES-GCM under the path's keys once it installs them.
    """

    name: ClassVar[str] = "encrypted"
    open_flag: ClassVar[int] = 0x40
    sends_client_id: ClassVar[bool] = False
    authorizes_at_key_exchange: ClassVar[bool] = False

    @override
    def x005_tags(self, announcement: Container) -> tuple[bytes, bytes | None]:
        """Return the app's encrypted-outer ``4005`` tags: device MTU and auth mode.

        :param announcement: What the device declared in ``x803``.
        """
        mtu = Int16ul.build(announcement.mtu or CLIENT_MTU)
        auth = (
            Int8ul.build(announcement.auth_method)
            if announcement.auth_method is not None
            else None
        )
        return mtu, auth

    @override
    def encrypt(self, payload: bytes, keys: Container | None) -> bytes:
        """AES-GCM seal under the path's keys, or the static key before them.

        :param payload: Plain-text bytes.
        :param keys: Keys a path installed, or None before the key exchange.
        """
        k = keys or STATIC_KEYS
        return gcm_encrypt(k.key, k.nonce, AAD, payload)

    @override
    def decrypt(self, payload: bytes, keys: Container | None) -> bytes:
        """AES-GCM open under the path's keys, or the static key before them.

        :param payload: Cipher-text bytes.
        :param keys: Keys a path installed, or None before the key exchange.
        """
        k = keys or STATIC_KEYS
        return gcm_decrypt(k.key, k.nonce, AAD, payload)
