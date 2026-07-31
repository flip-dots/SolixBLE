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

from SolixBLE.const import UUID_COMMAND
from SolixBLE.device import SolixBLEDevice

_LOGGER = logging.getLogger(__name__)

#: Command used to initiate negotiations
NEGOTIATION_COMMAND_0 = (
    "ff09200003000140010a82d0ab535303e3aa9f0c2f9c868465bc8476f556fb7d"
)

#: Response to receiving 1st negotiation message
NEGOTIATION_COMMAND_1 = (
    "ff09270003000140030a82d0ab53538ab3de100ac9bb87a0b8e36c1dd8167a9c25a9839d9a14d5"
)

#: Response to receiving 2nd negotiation message
NEGOTIATION_COMMAND_2 = (
    "ff09200003000140290a82d0ab535303e3aa9f0c2f9c868465bc8476f556fb55"
)

#: Response to receiving 3rd negotiation message
NEGOTIATION_COMMAND_3 = "ff092d0003000140050a82d0ab53538ab3de100ae04aca6791257881a90164eac7460450e0c82f2c03de4f9604"

#: Response to receiving 4th negotiation message
NEGOTIATION_COMMAND_4 = "ff095c0003000140210ac6ea31e4300bb2877d6ddeb628b0d7be8d768333f00ceab5454d20fbd97e091457b1f3b6efb6511eb9e98ac2b2c46eee211ae359ad246e1ae9886b4a29e41eddd5a5064d8b9ffdbfb43eb6b8e307fcde9de7"

#: The cmd to put in the response to receiving 5th negotiation message
NEGOTIATION_COMMAND_5_CMD = "4022"

#: The payload to put in the response to receiving 5th negotiation message
NEGOTIATION_COMMAND_5_PAYLOAD = (
    "a104f079b569a30400000000a518474d54304253542c4d332e352e302f312c4d31302e352e30"
)

#: The cmd to put in the response to receiving 6th negotiation message
NEGOTIATION_COMMAND_6_CMD = "4027"

#: The payload to put in the response to receiving 6th negotiation message
NEGOTIATION_COMMAND_6_PAYLOAD = "a104f079b569a22437396562656433352d646339632d343930342d623430632d373263346538363361613130"

#: The cmd to put in the first response to receiving 7th negotiation message
NEGOTIATION_COMMAND_7_CMD = "4200"

#: The payload to put in the first response to receiving 7th negotiation message
NEGOTIATION_COMMAND_7_PAYLOAD = "a10121fe04f079b569"

#: The cmd to put in the second response to receiving 7th negotiation message
NEGOTIATION_COMMAND_8_CMD = "420a"

#: The payload to put in the second response to receiving 7th negotiation message
NEGOTIATION_COMMAND_8_PAYLOAD = "a10121a203044742a3250437396562656433352d646339632d343930342d623430632d373263346538363361613130a5020101fe04f079b569"

#: Anker Prime devices encrypt the negotiation using a static key
NEGOTIATION_KEY = "b8ff7422955d4eb6d554a2c470280559"

#: Anker Prime devices encrypt the negotiation using a static nonce
NEGOTIATION_NONCE = "6ba3e3f2f3a60f2971ce5d1f"

#: The pattern used in negotiation packets from Anker Prime devices
NEGOTIATION_PATTERN = "030001"

#: The pattern used in telemetry packets from Anker Prime and Solix devices
TELEMETRY_PATTERN = "03000f"

#: Additional Authenticated Data bytes used by protocol
AAD = "3322110077665544bbaa9988ffeeddcc"

#: The private key this program uses to perform the ECDH negotiation to
#: get a shared secret which is then used as an AES key for encrypting
#: communications between the program and the power station. Yes I know it
#: is bad security practice to hardcode keys but its a freaking power station
#: talking over Bluetooth with a range of like 10m... I don't care.
PRIVATE_KEY = "754744d72984c378bc4fa77d7fcdf6bbb6d9df119fa9be4948eb8a3b4cd6071f"

#: The unix timestamp that is agreed upon in the negotiations. This is used
#: by Anker to protect against replay attacks as commands must contain the
#: current encrypted time.
BASE_TIMESTAMP = "ef79b569"


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
        cipher = AES.new(
            self._shared_secret[:16], AES.MODE_GCM, nonce=self._shared_secret[16:28]
        )
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
        """
        Send the negotiation initiation command.
        """

        # Log parameters we will send if debugging (makes handshake easier to see in logs)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            new_parameters = self._parse_payload(
                self._decrypt_payload(
                    self._split_packet(bytes.fromhex(NEGOTIATION_COMMAND_0))[2]
                )
            )
            _LOGGER.debug(
                f"Stage 0 message parameters: {self._parameters_to_str(new_parameters, types=True)}"
            )

        await self._client.write_gatt_char(
            UUID_COMMAND, bytes.fromhex(NEGOTIATION_COMMAND_0)
        )

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """
        Negotiate encryption with the device.
        """

        match cmd.hex():

            # There is a "stage 0" in which we automatically send a negotiation
            # request as soon as we establish the initial connection. That
            # should lead to the power station sending a response landing us
            # in stage 1.

            # Negotiations at this point are encrypted using the static key and nonce

            # Negotiation stage 1
            case "4801":
                _LOGGER.debug(
                    "Entered negotiation stage 1 due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                )

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        self._decrypt_payload(
                            self._split_packet(bytes.fromhex(NEGOTIATION_COMMAND_1))[2]
                        )
                    )
                    _LOGGER.debug(
                        f"Stage 1 response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                _LOGGER.debug("Sending stage 1 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    bytes.fromhex(NEGOTIATION_COMMAND_1),
                )

            # Negotiation stage 2
            case "4803":
                _LOGGER.debug(
                    "Entered negotiation stage 2 due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                )

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        self._decrypt_payload(
                            self._split_packet(bytes.fromhex(NEGOTIATION_COMMAND_2))[2]
                        )
                    )
                    _LOGGER.debug(
                        f"Stage 2 response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                _LOGGER.debug("Sending stage 2 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    bytes.fromhex(NEGOTIATION_COMMAND_2),
                )

            # Negotiation stage 3
            case "4829":
                _LOGGER.debug(
                    "Entered negotiation stage 3 due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                )

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        self._decrypt_payload(
                            self._split_packet(bytes.fromhex(NEGOTIATION_COMMAND_3))[2]
                        )
                    )
                    _LOGGER.debug(
                        f"Stage 3 response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                _LOGGER.debug("Sending stage 3 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    bytes.fromhex(NEGOTIATION_COMMAND_3),
                )

            # Negotiation stage 4
            case "4805":
                _LOGGER.debug(
                    "Entered negotiation stage 4 due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                )

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        self._decrypt_payload(
                            self._split_packet(bytes.fromhex(NEGOTIATION_COMMAND_4))[2]
                        )
                    )
                    _LOGGER.debug(
                        f"Stage 4 response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                _LOGGER.debug("Sending stage 4 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    bytes.fromhex(NEGOTIATION_COMMAND_4),
                )

            # Negotiation stage 5
            case "4821":
                _LOGGER.debug(
                    "Entered negotiation stage 5 due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                )

                self._negotiation_timestamp = time.time()

                # Extract public key of device from payload
                device_public_key_bytes = bytes.fromhex("04") + parameters["a1"]
                _LOGGER.debug(f"Public key of device: {device_public_key_bytes.hex()}")
                device_public_key = EllipticCurvePublicKey.from_encoded_point(
                    SECP256R1(), device_public_key_bytes
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

                # All negotiation packets past this point use the
                # shared secret for encryption rather than the static key.
                # This means we need to build these messages instead of using
                # pre-defined ones.
                _LOGGER.debug("Sending stage 5 response message...")

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        bytes.fromhex(NEGOTIATION_COMMAND_5_PAYLOAD)
                    )
                    _LOGGER.debug(
                        f"Stage 5 response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                new_payload = self._encrypt_payload(
                    bytes.fromhex(NEGOTIATION_COMMAND_5_PAYLOAD)
                )
                new_packet = self._build_packet(
                    pattern=bytes.fromhex(NEGOTIATION_PATTERN),
                    cmd=bytes.fromhex(NEGOTIATION_COMMAND_5_CMD),
                    payload=new_payload,
                )
                _LOGGER.debug(f"Built stage 5 response packet: {new_packet.hex()}")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    new_packet,
                )

            # Negotiations past this point are encrypted using the shared secret

            # Negotiation stage 6
            case "4822":
                _LOGGER.debug(
                    "Entered negotiation stage 6 due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                )

                _LOGGER.debug("Sending stage 6 response message...")

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        bytes.fromhex(NEGOTIATION_COMMAND_6_PAYLOAD)
                    )
                    _LOGGER.debug(
                        f"Stage 6 response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                new_payload = self._encrypt_payload(
                    bytes.fromhex(NEGOTIATION_COMMAND_6_PAYLOAD)
                )
                new_packet = self._build_packet(
                    pattern=bytes.fromhex(NEGOTIATION_PATTERN),
                    cmd=bytes.fromhex(NEGOTIATION_COMMAND_6_CMD),
                    payload=new_payload,
                )
                _LOGGER.debug(f"Built stage 6 response packet: {new_packet.hex()}")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    new_packet,
                )

            # Negotiation stage 7
            case "4827":
                _LOGGER.debug(
                    "Entered negotiation stage 7 due to response from device!"
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}"
                )

                _LOGGER.debug("Sending stage 7 response messages...")

                # Packet A
                new_payload_a = self._encrypt_payload(
                    bytes.fromhex(NEGOTIATION_COMMAND_7_PAYLOAD)
                )
                new_packet_a = self._build_packet(
                    pattern=bytes.fromhex(TELEMETRY_PATTERN),
                    cmd=bytes.fromhex(NEGOTIATION_COMMAND_7_CMD),
                    payload=new_payload_a,
                )
                _LOGGER.debug(f"Built stage 7a response packet: {new_packet_a.hex()}")
                await self._client.write_gatt_char(
                    UUID_COMMAND,
                    new_packet_a,
                )

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        bytes.fromhex(NEGOTIATION_COMMAND_7_PAYLOAD)
                    )
                    _LOGGER.debug(
                        f"Stage 7a response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                # Packet B
                new_payload_b = self._encrypt_payload(
                    bytes.fromhex(NEGOTIATION_COMMAND_8_PAYLOAD)
                )
                new_packet_b = self._build_packet(
                    pattern=bytes.fromhex(TELEMETRY_PATTERN),
                    cmd=bytes.fromhex(NEGOTIATION_COMMAND_8_CMD),
                    payload=new_payload_b,
                )
                _LOGGER.debug(f"Built stage 7b response packet: {new_packet_b.hex()}")
                await self._client.write_gatt_char(
                    UUID_COMMAND,
                    new_packet_b,
                )

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        bytes.fromhex(NEGOTIATION_COMMAND_8_PAYLOAD)
                    )
                    _LOGGER.debug(
                        f"Stage 7b response message parameters: {self._parameters_to_str(new_parameters, types=True)}"
                    )

                return

            case _:
                _LOGGER.warning(
                    f"Received unexpected negotiation request response from device! cmd: '{cmd}', parameters: '{self._parameters_to_str(parameters, types=True)}'"
                )

    #####################
    # Packet processing #
    #####################

    async def _process_telemetry_packet(
        self, payload: bytes, cmd: bytes = None
    ) -> None:
        """
        Process a telemetry packet from an Anker Prime device.

        Anker Prime devices pack all telemetry data into a single packet
        requiring no special logic to handle.
        """
        decrypted_payload = self._decrypt_payload(payload)
        _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
        parameters = self._parse_payload(decrypted_payload)
        return await self._process_telemetry(parameters)

    async def _send_command(self, cmd: bytes, payload: bytes) -> None:
        """Send a command to the device.

        :param cmd: 2 bytes containing command type.
        :param payload: Variable number of bytes containing arguments.
        :raises ConnectionError: If not connected/negotiated to device.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        # Commands include a timestamp in the payload to prevent replay attacks
        # and that timestamp is set during negotiations
        time_passed = int(time.time() - self._negotiation_timestamp)
        base_timestamp = int.from_bytes(
            bytes.fromhex(BASE_TIMESTAMP), byteorder="little"
        )
        new_timestamp = (base_timestamp + time_passed).to_bytes(
            length=4, byteorder="little"
        )
        new_payload = payload + bytes.fromhex("fe04") + new_timestamp
        await self._send_encrypted_packet(cmd, new_payload)
