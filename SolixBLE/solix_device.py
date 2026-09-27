"""Anker Solix device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import logging
import time

from bleak.backends.device import BLEDevice
from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePublicKey,
    derive_private_key,
)
from cryptography.hazmat.primitives.padding import PKCS7

from SolixBLE.constructs import Parameters
from SolixBLE.device import AnkerBLEDevice
from SolixBLE.utilities import get_posix_tz

from .const import (
    FALLBACK_TZ,
    NEGOTIATION_PATTERN,
    PRIVATE_KEY,
)

_LOGGER = logging.getLogger(__name__)

#: The UUID sent to the device during negotiation
UUID_STRING = "b2dc0b17-b75d-4abf-ba6e-ec7c997c23e7"


class SolixBLEDevice(AnkerBLEDevice):
    """Solix BLE device object."""

    #: Command codes (hex) that carry telemetry for this device. Subclasses can
    #: override this if their model uses different telemetry command codes
    #: (e.g the C1000 Gen 2 uses ``c421``/``c900`` instead of ``c402``/``c405``).
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("c402", "4300", "c405")

    #: The maximum packet size an Anker device is able to send
    _mtu = 253

    async def _initiate_negotiations(self) -> None:
        """Send the negotiation initiation command."""
        await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="0001",
            parameters={
                "a1": {
                    "key": bytes.fromhex("a1"),
                    "type": None,
                    "value": lambda self: self._timestamp(),
                }, "a2": {
                    "key": bytes.fromhex("a2"),
                    "type": None,
                    "value": UUID_STRING.encode(),
                },
            },
        )

    def _decrypt_payload(self, payload: bytes) -> bytes:
        """Decrypt payload using negotiated shared secret and IV if available."""

        if self._shared_secret is None:
            _LOGGER.debug("Skipping decryption as key not negotiated...")
            return payload

        cipher = AES.new(
            self._shared_secret[:16], AES.MODE_CBC, iv=self._shared_secret[16:],
        )
        decrypted = cipher.decrypt(payload)
        unpadder = PKCS7(128).unpadder()
        unpadded_data = unpadder.update(decrypted)
        return unpadded_data + unpadder.finalize()

    def _encrypt_payload(self, payload: bytes) -> bytes:
        """Encrypt payload using negotiated shared secret if available."""

        if self._shared_secret is None:
            _LOGGER.debug("Skipping encryption as key not negotiated...")
            return payload

        # Pad and encrypt payload
        padder = PKCS7(128).padder()
        padded_data = padder.update(payload)
        padded_data += padder.finalize()
        cipher = AES.new(
            self._shared_secret[:16], AES.MODE_CBC, iv=self._shared_secret[16:]
        )
        return cipher.encrypt(padded_data)

    def _timestamp(self) -> bytes:
        """Unix timestamp in byte form (4B)."""
        return int(time.time()).to_bytes(length=4, byteorder="little", signed=False)

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """Negotiate encryption with the device."""

        plain_text_payload = self._decrypt_payload(payload)
        _LOGGER.debug(f"Plain-text payload: {plain_text_payload.hex()}")
        parameters = Parameters.parse(plain_text_payload)
        _LOGGER.debug(f"Parameters: {parameters.to_str(verbose=True, types=False)}")

        match cmd.hex():

            # There is a "stage 0" in which we automatically send a negotiation
            # request as soon as we establish the initial connection. That
            # should lead to the power station sending a response landing us
            # in stage 1.

            # Negotiation stage 1
            case "0801":
                _LOGGER.debug(
                    "Entered negotiation stage 1 due to response from device!",
                )
                _LOGGER.debug("Sending stage 1 response message...")
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="0003",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
                        }, "a2": {
                            "key": bytes.fromhex("a2"),
                            "type": None,
                            "value": UUID_STRING.encode(),
                        }, "a3": {
                            "key": bytes.fromhex("a3"),
                            "type": None,
                            "value": bytes.fromhex("20"),
                        }, "a4": {
                            "key": bytes.fromhex("a4"),
                            "type": None,
                            "value": bytes.fromhex("00f0"),
                        },
                    },
                )

            # Negotiation stage 2
            case "0803":
                _LOGGER.debug(
                    "Entered negotiation stage 2 due to response from device!",
                )
                self._mtu = int.from_bytes(parameters["a2"].value_legacy, byteorder="little")
                _LOGGER.debug(f"MTU of device: {self._mtu}")

                _LOGGER.debug("Sending stage 2 response message...")
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="0029",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
                        }, "a2": {
                            "key": bytes.fromhex("a2"),
                            "type": None,
                            "value": UUID_STRING.encode(),
                        },
                    },
                )

            # Negotiation stage 3
            case "0829":
                _LOGGER.debug(
                    "Entered negotiation stage 3 due to response from device!",
                )
                self._negotiation_timestamp = time.time()
                _LOGGER.debug("Sending stage 3 response message...")
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="0005",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
                        }, "a2": {
                            "key": bytes.fromhex("a2"),
                            "type": None,
                            "value": UUID_STRING.encode(),
                        }, "a3": {
                            "key": bytes.fromhex("a3"),
                            "type": None,
                            "value": bytes.fromhex("20"),
                        }, "a4": {
                            "key": bytes.fromhex("a4"),
                            "type": None,
                            "value": bytes.fromhex("00f0"),
                        }, "a5": {
                            "key": bytes.fromhex("a5"),
                            "type": None,
                            "value": bytes.fromhex("40"),
                        },
                    },
                )

            # Negotiation stage 4
            case "0805":
                _LOGGER.debug(
                    "Entered negotiation stage 4 due to response from device!",
                )
                _LOGGER.debug("Sending stage 4 response message...")
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="0021",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": bytes.fromhex("060ea168f232aedb37fb2d120c49180329ac72ab5ec3eb8fd30a2f252dc5e151dabccd9b1dc1e288704ca760a0d8c918e5c94823a1f609a4bf07fb4c33ee2190"),
                        },
                    },
                )

            # Negotiation stage 5
            case "0821":
                _LOGGER.debug(
                    "Entered negotiation stage 5 due to response from device!",
                )

                # Extract public key of device from payload
                device_public_key_bytes = bytes.fromhex("04") + parameters["a1"].value_legacy
                _LOGGER.debug(f"Public key of device: {device_public_key_bytes.hex()}")
                device_public_key = EllipticCurvePublicKey.from_encoded_point(
                    SECP256R1(), device_public_key_bytes,
                )

                # Calculate the shared secret
                # The first half of the shared secret is the encryption key
                # and the second half is the IV
                private_value = int.from_bytes(
                    bytes.fromhex(PRIVATE_KEY), byteorder="big",
                )
                private_key = derive_private_key(private_value, SECP256R1())
                self._shared_secret = private_key.exchange(ECDH(), device_public_key)
                _LOGGER.debug(f"Shared secret: {self._shared_secret.hex()}")

                _LOGGER.debug("Sending stage 5 response message...")
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="4022",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
                        }, "a2": {
                            "key": bytes.fromhex("a2"),
                            "type": None,
                            "value": UUID_STRING.encode(),
                        }, "a3": {
                            "key": bytes.fromhex("a3"),
                            "type": None,
                            "value": bytes.fromhex("20"),
                        }, "a4": {
                            "key": bytes.fromhex("a4"),
                            "type": None,
                            "value": bytes.fromhex("00000000"),
                        }, "a5": {
                            "key": bytes.fromhex("a5"),
                            "type": None,
                            "value": (get_posix_tz() or FALLBACK_TZ).encode(),
                        },
                    },
                )

            # Negotiation stage 6 (Optional)
            # Some devices (e.g C300X) sometimes send an extra message after
            # stage 5 but others (e.g C1000) do not. No response is needed
            # but it does not hurt to decrypt it anyway.
            case "4822":
                _LOGGER.debug(
                    "Entered negotiation stage 6 (optional) due to response from device!"
                )

            case _:
                parameters = Parameters.parse(payload)
                _LOGGER.warning(
                    f"Received unexpected negotiation request response from device! cmd: '{cmd}', parameters: '{parameters}'"
                )
