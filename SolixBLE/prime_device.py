"""Base Anker Prime device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import logging
import time

from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePublicKey,
    derive_private_key,
)

from SolixBLE.const import FALLBACK_TZ, NEGOTIATION_PATTERN
from SolixBLE.constructs import Parameters
from SolixBLE.device import SolixBLEDevice
from SolixBLE.utilities import get_posix_tz

_LOGGER = logging.getLogger(__name__)

#: The pattern used in telemetry packets from Anker Prime and Solix devices
TELEMETRY_PATTERN = "03000f"

#: Anker Prime devices encrypt the negotiation using a static key
NEGOTIATION_KEY = "b8ff7422955d4eb6d554a2c470280559"

#: Anker Prime devices encrypt the negotiation using a static nonce
NEGOTIATION_NONCE = "6ba3e3f2f3a60f2971ce5d1f"

#: Additional Authenticated Data bytes used by protocol
AAD = "3322110077665544bbaa9988ffeeddcc"

#: The private key this program uses to perform the ECDH negotiation to
#: get a shared secret which is then used as an AES key for encrypting
#: communications between the program and the power station. Yes I know it
#: is bad security practice to hardcode keys but its a freaking power station
#: talking over Bluetooth with a range of like 10m... I don't care.
PRIVATE_KEY = "754744d72984c378bc4fa77d7fcdf6bbb6d9df119fa9be4948eb8a3b4cd6071f"

#: The UUID sent to the device during negotiation
UUID_STRING = "79ebed35-dc9c-4904-b40c-72c4e863aa10"



class PrimeDevice(SolixBLEDevice):
    """
    This is a base class based upon SolixBLEDevice which contains logic
    unique to Anker Prime devices that is designed to be overridden for
    specific implementations, e.g 160w, 250w, etc.
    """

    ###########################
    # Encryption / Decryption #
    ###########################

    def _encrypt_payload(self, payload: bytes) -> bytes:
        """
        Encrypt the payload of a session message (e.g telemetry, commands, etc).

        Anker Prime devices use AES GCM with the first 16 bytes of the shared
        secret as the AES key and next 12 bytes as the nonce. The MAC tag is
        16 bytes and appended to the end of the payload.
        """
        key = (
            self._shared_secret[:16]
            if self._shared_secret is not None
            else bytes.fromhex(NEGOTIATION_KEY)
        )
        nonce = (
            self._shared_secret[16:28]
            if self._shared_secret is not None
            else bytes.fromhex(NEGOTIATION_NONCE)
        )
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        cipher.update(bytes.fromhex(AAD))
        encrypted_payload, mac_bytes = cipher.encrypt_and_digest(payload)
        return encrypted_payload + mac_bytes

    def _decrypt_payload(self, payload: bytes) -> bytes:
        """
        Decrypt the payload of a message (e.g telemetry, commands, etc).

        If the shared secret has not been established then the static
        negotiation key and nonce will be used.

        Anker Prime devices use AES GCM with the first 16 bytes of the shared
        secret as the AES key and next 12 bytes as the nonce. The last 16 bytes
        of the payload are a MAC used to ensure the message has not been tampered
        with.
        """
        mac = payload[-16:]
        encrypted_payload = payload[:-16]
        key = (
            self._shared_secret[:16]
            if self._shared_secret is not None
            else bytes.fromhex(NEGOTIATION_KEY)
        )
        nonce = (
            self._shared_secret[16:28]
            if self._shared_secret is not None
            else bytes.fromhex(NEGOTIATION_NONCE)
        )

        # Try to decrypt and verify data
        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce)
            cipher.update(bytes.fromhex(AAD))
            return cipher.decrypt_and_verify(encrypted_payload, mac)

        # If validation fails decrypt anyway
        except ValueError:
            _LOGGER.exception(
                "Failed to validate authenticity of payload, decoding anyway..."
            )
            cipher = AES.new(key, AES.MODE_GCM, nonce)
            return cipher.decrypt(encrypted_payload)

    ###############
    # Negotiation #
    ###############

    async def _initiate_negotiations(self) -> None:
        """Send the negotiation initiation command."""
        await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="4001",
            parameters={ "a1": {
                "key": bytes.fromhex("a1"),
                "type": None,
                "value": lambda self: self._timestamp(),
            }},
        )

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """Negotiate encryption with the device."""

        decrypted_payload = self._decrypt_payload(payload)
        _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
        parameters = Parameters.parse(decrypted_payload).to_legacy()
        _LOGGER.debug(
            f"Parameters: {self._parameters_to_str(parameters, types=True)}",
        )

        match cmd.hex():

            # There is a "stage 0" in which we automatically send a negotiation
            # request as soon as we establish the initial connection. That
            # should lead to the power station sending a response landing us
            # in stage 1.

            # Negotiations at this point are encrypted using the static key and nonce

            # Negotiation stage 1
            case "4801":
                _LOGGER.debug(
                    "Entered negotiation stage 1 due to response from device!",
                )
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="4003",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
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
            case "4803":
                _LOGGER.debug(
                    "Entered negotiation stage 2 due to response from device!",
                )
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="4029",
                    parameters={ "a1": {
                        "key": bytes.fromhex("a1"),
                        "type": None,
                        "value": lambda self: self._timestamp(),
                    }},
                )

            # Negotiation stage 3
            case "4829":
                _LOGGER.debug(
                    "Entered negotiation stage 3 due to response from device!",
                )
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="4005",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
                        }, "a3": {
                            "key": bytes.fromhex("a3"),
                            "type": None,
                            "value": bytes.fromhex("20"),
                        }, "a4": {
                            "key": bytes.fromhex("a4"),
                            "type": None,
                            "value": bytes.fromhex("2901"),
                        }, "a5": {
                            "key": bytes.fromhex("a5"),
                            "type": None,
                            "value": bytes.fromhex("44"),
                        }, "a6": {
                            "key": bytes.fromhex("a6"),
                            "type": None,
                            "value": bytes.fromhex("02"),
                        },
                    },
                )

            # Negotiation stage 4
            case "4805":
                _LOGGER.debug(
                    "Entered negotiation stage 4 due to response from device!",
                )
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="4021",
                    parameters={ "a1": {
                        "key": bytes.fromhex("a1"),
                        "type": None,
                        "value": bytes.fromhex("d5e3020a220079c96517fd47d6023df4f5530914cc6843aaad76cf888537c4cd7db4c879056ea7d5ff83696f0f32bd7034b251396bf0b1bb1f37a7446857d1a6"),
                    }},
                )

            # Negotiation stage 5
            case "4821":
                _LOGGER.debug(
                    "Entered negotiation stage 5 due to response from device!",
                )
                self._negotiation_timestamp = time.time()

                # Extract public key of device from payload
                device_public_key_bytes = bytes.fromhex("04") + parameters["a1"]
                _LOGGER.debug(f"Public key of device: {device_public_key_bytes.hex()}")
                device_public_key = EllipticCurvePublicKey.from_encoded_point(
                    SECP256R1(), device_public_key_bytes,
                )

                # Calculate the shared secret
                # The first half of the shared secret is the encryption key
                # and the 12 bytes after that is the nonce
                private_value = int.from_bytes(
                    bytes.fromhex(PRIVATE_KEY),
                    byteorder="big",
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
                        }, "a3": {
                            "key": bytes.fromhex("a3"),
                            "type": None,
                            "value": bytes.fromhex("00000000"),
                        }, "a5": {
                            "key": bytes.fromhex("a5"),
                            "type": None,
                            "value": (get_posix_tz() or FALLBACK_TZ).encode(),
                        },
                    },
                )

            # Negotiations past this point are encrypted using the shared secret

            # Negotiation stage 6
            case "4822":
                _LOGGER.debug(
                    "Entered negotiation stage 6 due to response from device!"
                )
                await self._send_packet(pattern=NEGOTIATION_PATTERN, cmd="4027",
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

            # Negotiation stage 7
            case "4827":
                _LOGGER.debug(
                    "Entered negotiation stage 7 due to response from device!",
                )
                await self._send_packet(pattern=TELEMETRY_PATTERN, cmd="4200",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": bytes.fromhex("21"),
                        }, "fe": {
                            "key": bytes.fromhex("fe"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
                        },
                    },
                )
                await self._send_packet(pattern=TELEMETRY_PATTERN, cmd="420a",
                    parameters={
                        "a1": {
                            "key": bytes.fromhex("a1"),
                            "type": None,
                            "value": bytes.fromhex("21"),
                        }, "a2": {
                            "key": bytes.fromhex("a2"),
                            "type": None,
                            "value": bytes.fromhex("044742"),
                        }, "a3": {
                            "key": bytes.fromhex("a3"),
                            "type": 4,
                            "value": UUID_STRING.encode(),
                        }, "a5": {
                            "key": bytes.fromhex("a5"),
                            "type": None,
                            "value": bytes.fromhex("0101"),
                        }, "fe": {
                            "key": bytes.fromhex("fe"),
                            "type": None,
                            "value": lambda self: self._timestamp(),
                        },
                    },
                )

            case _:
                _LOGGER.warning(
                    f"Received unexpected negotiation request response from device! cmd: '{cmd}', parameters: '{self._parameters_to_str(parameters, types=True)}'"
                )

    #####################
    # Packet processing #
    #####################

    async def _send_command(self, cmd: str, parameters: dict, **kwargs: dict) -> None:
        """Send a command to the device.

        Parameter values may use lambda functions which will be executed at
        this point, where variables may be passed in as keyword arguments.

        :param cmd: The command type (e.g 4200, 0001, etc).
        :param parameters: Parameters of the command.
        :raises ConnectionError: If not connected/negotiated to device.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        await self._send_packet(
            pattern="03000f",
            cmd=cmd,
            parameters=parameters | { "fe": {
                "key": bytes.fromhex("fe"),
                "type": None,
                "value": lambda self: self._timestamp(),
            }},
            **kwargs,
        )
