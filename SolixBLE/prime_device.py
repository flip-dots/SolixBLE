"""Base Anker Prime device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
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

#: Account owner_user_id bound into the 4027 registration (``a228``). Hardened
#: (SolixBLE #22) firmware rejects a plain ``a224<uuid>`` registration (ack status
#: ``09``) and only arms telemetry once the registration carries the account that
#: owns the device. Account-specific -- MUST be sourced from config, never hard-coded
#: upstream. ``None`` falls back to the legacy ``a224<uuid>`` payload.
OWNER_USER_ID: str | None = None

#: The cmd to put in the response to receiving 6th negotiation message
NEGOTIATION_COMMAND_6_CMD = "4027"

#: The payload to put in the response to receiving 6th negotiation message
NEGOTIATION_COMMAND_6_PAYLOAD = "a104f079b569a22437396562656433352d646339632d343930342d623430632d373263346538363361613130"

#: Stage 7a starts the telemetry stream; its body matches the C1000 Gen 2
#: subscribe (a10121). Sent via _send_command so the current session timestamp is
#: appended: the device rejects a stale timestamp as a replay and then never
#: streams, so this body must NOT carry a hard-coded fe04<timestamp> trailer.
NEGOTIATION_COMMAND_7_CMD = "4200"
NEGOTIATION_COMMAND_7_PAYLOAD = "a10121"

#: Stage 7b is the getter (region only). Also sent via _send_command, so likewise no
#: hard-coded timestamp trailer. The a3<app-uuid> field the app also sends is dropped:
#: the device binds its own serial via the 4027 registration, so the stale author UUID
#: is unnecessary (and a foreign one risks the device dropping the link).
NEGOTIATION_COMMAND_8_CMD = "420a"
NEGOTIATION_COMMAND_8_PAYLOAD = "a10121a203044742a5020101"

#: Stage 7c is the realtime trigger (REALTIME_TRIGGER, 020b) that starts the ~1/s
#: per-port telemetry stream. The ``a20a`` block is the enable payload the app sends
#: (``04 01 0003 15 01 01 00 00 00``); a bare ``a10121`` trigger does nothing. Sent
#: via _send_command so it carries the live session timestamp trailer.
NEGOTIATION_COMMAND_9_CMD = "420b"
NEGOTIATION_COMMAND_9_PAYLOAD = "a10121a20a04010003150101000000"

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

    #: Prime devices stream ~1/s after a 420b trigger, but the realtime window
    #: lapses after ~10s -- so re-arm 420b (with the default bare a10121 payload +
    #: live session timestamp) a little under that. See SolixBLEDevice._keepalive_loop.
    _KEEPALIVE_CMD = "420b"

    ###########################
    # Encryption / Decryption #
    ###########################

    def _encrypt_payload(self, payload: bytes) -> bytes:
        """
        Encrypt the payload of a session message (e.g telemetry, commands, etc).

        Anker Prime devices use AES GCM with the first 16 bytes of the shared
        secret as the AES key and next 12 bytes as the nonce. The MAC tag is
        16 bytes and appended to the end of the payload. Before the shared secret
        is established the static negotiation key and nonce are used instead (so the
        early ``40xx`` stages can be built live rather than replayed).
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

        # If validation fails decrypt anyway (Anker tolerates a MAC mismatch, and
        # control-response acks are not meant to decrypt at all) -- this is expected
        # and non-fatal, so log at DEBUG rather than an ERROR traceback per frame.
        except ValueError:
            _LOGGER.debug(
                "Failed to validate authenticity of payload, decoding anyway...",
            )
            cipher = AES.new(key, AES.MODE_GCM, nonce)
            return cipher.decrypt(encrypted_payload)

    ###############
    # Negotiation #
    ###############

    def _live_negotiation_packet(self, cmd: str, extra: str = "") -> bytes:
        """Build an encrypted 40xx negotiation frame carrying a live timestamp.

        ``_encrypt_payload`` selects the key: the static ``NEGOTIATION_KEY``/nonce
        before the ECDH secret exists (stages 0-4), the negotiated secret after (the
        4022 confer and 4027 registration). This replaces the frozen constants so
        every frame shares one live clock -- newer firmware rejects a stale or
        internally-inconsistent timestamp (the device acks but never streams).
        """
        payload = bytes.fromhex("a104" + self._ts() + extra)
        return self._build_packet(
            bytes.fromhex(NEGOTIATION_PATTERN),
            bytes.fromhex(cmd),
            self._encrypt_payload(payload),
        )

    async def _initiate_negotiations(self) -> None:
        """Send the negotiation initiation command with a live timestamp."""
        await self._client.write_gatt_char(
            UUID_COMMAND,
            self._live_negotiation_packet("4001"),
            response=True,
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
                    "Entered negotiation stage 1 due to response from device!",
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}",
                )

                _LOGGER.debug("Sending stage 1 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    self._live_negotiation_packet("4003", "a30120a40200f0"),
                )

            # Negotiation stage 2
            case "4803":
                _LOGGER.debug(
                    "Entered negotiation stage 2 due to response from device!",
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}",
                )

                _LOGGER.debug("Sending stage 2 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    self._live_negotiation_packet("4029"),
                )

            # Negotiation stage 3
            case "4829":
                _LOGGER.debug(
                    "Entered negotiation stage 3 due to response from device!",
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                # Device identity (chip, BLE firmware, serial, MAC) is sent only
                # in this stage-3 message, never in telemetry, so persist it for
                # the identity properties to read.
                self._device_info = parameters
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}",
                )

                _LOGGER.debug("Sending stage 3 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    self._live_negotiation_packet("4005", "a30120a4022901a50144a60102"),
                )

            # Negotiation stage 4
            case "4805":
                _LOGGER.debug(
                    "Entered negotiation stage 4 due to response from device!",
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}",
                )

                # Log parameters we will send if debugging (makes handshake easier to see in logs)
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    new_parameters = self._parse_payload(
                        self._decrypt_payload(
                            self._split_packet(bytes.fromhex(NEGOTIATION_COMMAND_4))[2],
                        ),
                    )
                    _LOGGER.debug(
                        f"Stage 4 response message parameters: {self._parameters_to_str(new_parameters, types=True)}",
                    )

                _LOGGER.debug("Sending stage 4 response message...")
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    bytes.fromhex(NEGOTIATION_COMMAND_4),
                )

            # Negotiation stage 5
            case "4821":
                _LOGGER.debug(
                    "Entered negotiation stage 5 due to response from device!",
                )
                decrypted_payload = self._decrypt_payload(payload)
                _LOGGER.debug(f"Decrypted payload: {decrypted_payload.hex()}")
                parameters = self._parse_payload(decrypted_payload)
                _LOGGER.debug(
                    f"Parameters: {self._parameters_to_str(parameters, types=True)}",
                )

                self._negotiation_timestamp = time.time()

                # Extract public key of device from payload
                device_public_key_bytes = bytes.fromhex("04") + parameters["a1"]
                _LOGGER.debug(f"Public key of device: {device_public_key_bytes.hex()}")
                device_public_key = EllipticCurvePublicKey.from_encoded_point(
                    SECP256R1(),
                    device_public_key_bytes,
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
                # Build the 4022 confer live (a1 timestamp + local timezone), encrypted
                # with the just-derived secret, instead of replaying the frozen payload.
                _LOGGER.debug("Sending stage 5 (confer) response message...")
                tz = self._local_posix_tz().encode()
                confer = "a30400000000a5" + f"{len(tz):02x}" + tz.hex()
                return await self._client.write_gatt_char(
                    UUID_COMMAND,
                    self._live_negotiation_packet(NEGOTIATION_COMMAND_5_CMD, confer),
                )

            # The ECDH handshake is complete after stage 5; the device's trailing
            # "stage 6/7" messages (4822/4827) are just acks. The registration and
            # telemetry subscribe are post-connect commands, not responses to
            # these -- they are sent from _post_connect once the handshake settles.
            case "4822" | "4827":
                _LOGGER.debug(
                    "Received post-ECDH ack %s; registration/subscribe run in "
                    "_post_connect",
                    cmd.hex(),
                )
                return None

            case _:
                _LOGGER.warning(
                    "Received unexpected negotiation response from device! cmd: %s",
                    cmd.hex(),
                )

    async def _post_connect(self) -> None:
        """Register the client and start the realtime telemetry stream.

        The Prime stream is armed post-connect (not as responses to the device's
        trailing 4822/4827 acks):

        1. **Registration** -- ``4027`` carries ``a224<app-uuid>``. The device acks
           it (``4827``) and stays connected. (Binding the device's own serial via
           ``a3<len><serial>`` -- the 240W station's ``4023`` shape -- is *rejected*
           on the genuine-Prime ``4027`` and drops the link.)
        2. **The realtime trigger** -- ``420b`` (REALTIME_TRIGGER) is the enable that
           starts the ``ca00`` stream. A plain ``4200`` subscribe streams on some
           firmware, but the hardened units stay silent until ``420b`` is sent.

        All session bodies carry the live session timestamp (via ``_send_command`` /
        ``_live_negotiation_packet``) since a stale one is rejected as a replay.
        Overridden by models whose sequence differs (e.g. the 240W station).
        """
        await asyncio.sleep(1)
        # 4027 registration (live timestamp, shares the session clock with the commands
        # below). Hardened firmware (SolixBLE #22) only arms telemetry when the
        # registration binds the account owner_user_id (a228); without it the device
        # withholds telemetry (a224<uuid> is rejected with ack 09; the cloud-free
        # a310<serial> is acked 04 but still never streams). Falls back to the legacy
        # a224<uuid> payload when no owner_user_id is configured.
        if OWNER_USER_ID is not None:
            extra = "a228" + OWNER_USER_ID.encode().hex()
        else:
            extra = NEGOTIATION_COMMAND_6_PAYLOAD[12:]
        registration = self._live_negotiation_packet(NEGOTIATION_COMMAND_6_CMD, extra)
        await self._client.write_gatt_char(UUID_COMMAND, registration)
        # Space each command (like the 240W station) so the device isn't overrun.
        await asyncio.sleep(0.4)
        # 4200 status request, 420a getter, then 420b realtime trigger -- the enable
        # that actually starts the ca00 stream.
        await self._send_command(
            bytes.fromhex(NEGOTIATION_COMMAND_7_CMD),
            bytes.fromhex(NEGOTIATION_COMMAND_7_PAYLOAD),
        )
        await asyncio.sleep(0.4)
        await self._send_command(
            bytes.fromhex(NEGOTIATION_COMMAND_8_CMD),
            bytes.fromhex(NEGOTIATION_COMMAND_8_PAYLOAD),
        )
        await asyncio.sleep(0.4)
        await self._send_command(
            bytes.fromhex(NEGOTIATION_COMMAND_9_CMD),
            bytes.fromhex(NEGOTIATION_COMMAND_9_PAYLOAD),
        )

    #####################
    # Packet processing #
    #####################

    async def _send_command(self, cmd: bytes, payload: bytes) -> None:
        """Send a command to the device.

        :param cmd: 2 bytes containing command type.
        :param payload: Variable number of bytes containing arguments.
        :raises ConnectionError: If not connected/negotiated to device.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        # Commands carry a live timestamp in the payload to prevent replay attacks;
        # newer firmware rejects a stale one, which blocks the stream.
        new_payload = payload + bytes.fromhex("fe04") + bytes.fromhex(self._ts())
        await self._send_encrypted_packet(cmd, new_payload)
