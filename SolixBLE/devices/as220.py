"""AS220 (SOLIX S2000) portable power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

The SOLIX S2000 (model AS220) is a new-firmware Anker device. It combines the
*encrypted* negotiation + AES-GCM session layer of :class:`~SolixBLE.prime_device.PrimeDevice`
with the Gen-2 telemetry framing of the C1000 Gen 2 (fragmented ``c900``/``c421``
packets started by a ``4100`` subscribe command).

Unlike the other models, the S2000 only streams telemetry to a **client UUID that
has been bound to the device**. Binding is fully local (no Anker account): call
:meth:`AS220.bind` once and press the unit's Power button to confirm. After that a
normal :meth:`~SolixBLE.device.SolixBLEDevice.connect` with the same ``client_uuid``
streams telemetry. The device is single-owner, so binding a new UUID replaces the
previous one (including the phone app's).
"""

import asyncio
import logging
import time
import uuid as _uuid

from Crypto.Cipher import AES
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePublicKey,
    generate_private_key,
)

from ..const import (
    DEFAULT_METADATA_INT,
    DEFAULT_METADATA_STRING,
    UUID_COMMAND,
)
from ..prime_device import (
    AAD,
    NEGOTIATION_KEY,
    NEGOTIATION_NONCE,
    NEGOTIATION_PATTERN,
    PrimeDevice,
)

_LOGGER = logging.getLogger(__name__)

#: Command sent after auth to start the telemetry stream (same as the Gen-2 C1000).
CMD_SUBSCRIBE = "4100"
SUBSCRIBE_PAYLOAD = "a10121a2020401"

#: POSIX TZ string placed in the 0x22 command. The device does not validate it.
DEFAULT_TIMEZONE = "GMT0"


class AS220(PrimeDevice):
    """SOLIX S2000 Portable Power Station (model AS220).

    :param ble_device: the bleak ``BLEDevice`` to connect to.
    :param client_uuid: a client UUID bound to this device (see :meth:`bind`). If
        omitted a random one is generated; you must then :meth:`bind` it once.
    :param timezone: POSIX TZ string sent in the 0x22 command (cosmetic).
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    #: The S2000 pushes telemetry on the same command codes as the Gen-2 C1000.
    _TELEMETRY_COMMANDS: tuple[str, ...] = ("c900", "c421")

    def __init__(self, ble_device, client_uuid: str | None = None,
                 timezone: str = DEFAULT_TIMEZONE) -> None:
        super().__init__(ble_device)
        self._client_uuid = (client_uuid or str(_uuid.uuid4())).encode("ascii")
        self._timezone = timezone.encode("ascii")
        self._ecdh_priv = None
        self._session_ts: bytes | None = None
        self._authed: bool = False
        self._bind_mode: bool = False
        self._device_serial: bytes | None = None  # learned from the 4829 response

    @property
    def client_uuid(self) -> str:
        """The client UUID this instance authenticates with."""
        return self._client_uuid.decode("ascii")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _now_ts() -> bytes:
        """Current unix time as little-endian 4 bytes (the ``a1`` timestamp)."""
        return int(time.time()).to_bytes(4, "little")

    def _gcm(self, key: bytes, nonce: bytes, payload: bytes) -> bytes:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        cipher.update(bytes.fromhex(AAD))
        ct, mac = cipher.encrypt_and_digest(payload)
        return ct + mac

    def _gcm_open(self, key: bytes, nonce: bytes, payload: bytes) -> bytes:
        cipher = AES.new(key, AES.MODE_GCM, nonce)
        cipher.update(bytes.fromhex(AAD))
        return cipher.decrypt_and_verify(payload[:-16], payload[-16:])

    def _enc_nego(self, payload: bytes) -> bytes:
        """Encrypt a pre-ECDH negotiation payload with the static key/nonce."""
        return self._gcm(bytes.fromhex(NEGOTIATION_KEY),
                         bytes.fromhex(NEGOTIATION_NONCE), payload)

    def _dec_nego(self, payload: bytes) -> bytes:
        return self._gcm_open(bytes.fromhex(NEGOTIATION_KEY),
                              bytes.fromhex(NEGOTIATION_NONCE), payload)

    async def _write(self, cmd_hex: str, ct: bytes) -> None:
        pkt = self._build_packet(
            pattern=bytes.fromhex(NEGOTIATION_PATTERN),
            cmd=bytes.fromhex(cmd_hex),
            payload=ct,
        )
        await self._client.write_gatt_char(UUID_COMMAND, pkt)

    # --------------------------------------------------------------- negotiated

    @property
    def negotiated(self) -> bool:
        """Session is only usable once the multi-step auth (through 0x23) is done."""
        return self.connected and self._shared_secret is not None and self._authed

    @property
    def device_serial(self) -> str:
        """Device serial learned during negotiation (or default)."""
        return (self._device_serial.decode("ascii")
                if self._device_serial else DEFAULT_METADATA_STRING)

    # ---------------------------------------------------------------- binding

    async def bind(self, timeout: float = 60.0) -> bool:
        """Register this client's UUID with the device (one-time, local, no account).

        Runs the device-registration handshake, then the **user must press the
        Power button once on the S2000** to confirm (a physical proximity check;
        the press opens a short pairing window). Once confirmed the UUID is stored
        on the device and normal :meth:`connect` calls stream telemetry.

        The S2000 is single-owner: binding a new UUID replaces the previous one.

        :param timeout: seconds to wait for the user to press Power.
        :returns: True if the binding was confirmed (telemetry started).
        """
        self._bind_mode = True
        try:
            if not await self.connect(run_callbacks=False):
                return False
            _LOGGER.info(
                "Bind request sent for %s. Press the Power button on the S2000 "
                "once to confirm.", self.client_uuid)
            # Telemetry only begins once the owner confirms with the button. Re-send
            # the subscribe each second so the stream starts right after the press.
            for _ in range(int(timeout)):
                await asyncio.sleep(1)
                if self.available:
                    _LOGGER.info("Binding confirmed for %s.", self.client_uuid)
                    return True
                try:
                    await self._post_connect()
                except Exception:  # noqa: BLE001 - best-effort re-subscribe
                    pass
            _LOGGER.warning(
                "Binding not confirmed within %ss (Power button not pressed?).",
                timeout)
            return False
        finally:
            self._bind_mode = False

    # -------------------------------------------------------------- negotiation

    async def _initiate_negotiations(self) -> None:
        """Kick off the handshake: fresh keypair + timestamp, then send stage 0x01."""
        self._ecdh_priv = generate_private_key(SECP256R1())
        self._session_ts = self._now_ts()
        self._authed = False
        await self._write("4001", self._enc_nego(b"\xa1\x04" + self._session_ts))

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        t = self._session_ts

        # Once auth is done, ignore repeat auth-stage confirmations. In bind mode the
        # device sends a fresh 4827 after the Power-button press; re-sending 0x23 there
        # would re-arm the confirmation and swallow the press.
        if self._authed and cmd.hex() in ("4822", "4827"):
            return

        match cmd.hex():

            # Static-key negotiation stages (device -> us) ----------------------
            case "4801":  # -> stage 0x03
                await self._write(
                    "4003", self._enc_nego(b"\xa1\x04" + t + bytes.fromhex("a30120a40200f0")))

            case "4803":  # -> stage 0x29
                await self._write("4029", self._enc_nego(b"\xa1\x04" + t))

            case "4829":  # device info (serial in a4) -> stage 0x05
                try:
                    info = self._parse_payload(self._dec_nego(payload)[1:])
                    if "a4" in info:
                        self._device_serial = info["a4"]
                except Exception:  # noqa: BLE001
                    pass
                await self._write(
                    "4005",
                    self._enc_nego(b"\xa1\x04" + t + bytes.fromhex("a30120a402fd00a50144a60102")))

            case "4805":  # -> stage 0x21: send our ECDH public key
                pub = self._ecdh_priv.public_key().public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint,
                )[1:]  # strip 0x04 prefix -> raw X||Y (64 bytes)
                await self._write("4021", self._enc_nego(b"\xa1\x40" + pub))

            case "4821":  # device public key -> compute shared secret, start auth
                dec = self._dec_nego(payload)          # 00 a1 40 <devpub>
                params = self._parse_payload(dec[1:])   # skip status byte
                dev_pub = EllipticCurvePublicKey.from_encoded_point(
                    SECP256R1(), b"\x04" + params["a1"])
                self._shared_secret = self._ecdh_priv.exchange(ECDH(), dev_pub)
                self._negotiation_timestamp = time.time()
                _LOGGER.debug("Shared secret: %s", self._shared_secret.hex())

                # 0x22: timestamp + flags + timezone. In bind mode we also include
                # our UUID (a2), matching the app's device-registration flow.
                pt = b"\xa1\x04" + t
                if self._bind_mode:
                    pt += b"\xa2\x24" + self._client_uuid
                pt += (bytes.fromhex("a30440380000")
                       + b"\xa5" + bytes([len(self._timezone)]) + self._timezone)
                await self._write("4022", self._encrypt_payload(pt))

            # Session-key auth stages ------------------------------------------
            case "4822":  # -> 0x27: our client UUID
                pt = b"\xa1\x04" + t + b"\xa2\x24" + self._client_uuid
                await self._write("4027", self._encrypt_payload(pt))

            case "4827":  # -> 0x23: final auth (or device-registration in bind mode)
                if self._bind_mode and self._device_serial:
                    # Register our UUID against this device serial; the device then
                    # waits for the user to press the Power button to confirm.
                    pt = (b"\xa1\x04" + t + b"\xa2\x24" + self._client_uuid
                          + b"\xa3" + bytes([len(self._device_serial)]) + self._device_serial
                          + bytes.fromhex("a40100"))
                else:
                    pt = bytes.fromhex("a10121a2020401") + b"\xfe\x04" + t
                await self._write("4023", self._encrypt_payload(pt))

            case "4823":  # device acknowledged auth -> session established
                self._authed = True
                # The 4823 payload also carries the device serial (a1); capture it.
                try:
                    p = self._parse_payload(self._decrypt_payload(payload)[1:])
                    if "a1" in p and len(p["a1"]) >= 10:
                        self._device_serial = p["a1"]
                except Exception:  # noqa: BLE001
                    pass
                _LOGGER.debug("S2000 auth complete.")

            case _:
                _LOGGER.warning("Unexpected negotiation cmd from S2000: %s", cmd.hex())

    # ----------------------------------------------------------- post-connect

    async def _post_connect(self) -> None:
        """Subscribe to telemetry; the S2000 streams nothing until it gets this."""
        await self._send_command(
            cmd=bytes.fromhex(CMD_SUBSCRIBE),
            payload=bytes.fromhex(SUBSCRIBE_PAYLOAD),
        )

    async def _send_command(self, cmd: bytes, payload: bytes) -> None:
        """Send a session command with the fe04+current-timestamp trailer.

        Overrides PrimeDevice (which uses a hardcoded Prime base timestamp); the
        S2000 accepts the current unix time.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")
        await self._send_encrypted_packet(
            cmd, payload + bytes.fromhex("fe04") + self._now_ts())

    # ------------------------------------------------- fragmented telemetry

    async def _process_telemetry_packet(self, payload: bytes, cmd: bytes = None) -> None:
        """S2000 splits telemetry across packets (hi-nibble=index, lo=total)."""
        fi = (payload[0] >> 4) & 0x0F
        ft = payload[0] & 0x0F
        if ft > 1:
            key = bytes(cmd)
            if key not in self._fragment_buffers or fi == 1:
                self._fragment_buffers[key] = {}
                self._fragment_totals[key] = ft
            self._fragment_buffers[key][fi] = payload[1:]
            if len(self._fragment_buffers[key]) < ft:
                return
            body = b"".join(self._fragment_buffers[key][i]
                            for i in sorted(self._fragment_buffers[key]))
            del self._fragment_buffers[key]
            del self._fragment_totals[key]
        else:
            body = payload[1:]
        decrypted = self._decrypt_payload(body)
        _LOGGER.debug("Decrypted telemetry: %s", decrypted.hex())
        return await self._process_telemetry(self._parse_payload(decrypted))

    # ---------------------------------------------------------- telemetry props
    # Confirmed on the S2000: a2=serial/model, a5=temp/battery%, a6=power/AC-in,
    # a7=AC out, a8=solar in, d9=battery limits. The S2000 omits some TLVs the
    # C1000G2 reports (e.g. b2/DC, per-USB-port) so parsing is made defensive.
    # Other TLVs (a3/a4/aa/dc..fe) hold more data whose offsets still need mapping.

    def _parse_int(self, key, begin=None, end=None, signed=False):
        """Defensive int parse: return default if the S2000 omits this TLV."""
        if self._data is None or key not in self._data:
            return DEFAULT_METADATA_INT
        return super()._parse_int(key, begin=begin, end=end, signed=signed)

    def _parse_string(self, key, begin=None, end=None):
        if self._data is None or key not in self._data:
            return DEFAULT_METADATA_STRING
        return super()._parse_string(key, begin=begin, end=end)

    @property
    def serial_number(self) -> str:
        return self._parse_string("a2", begin=3, end=20)

    @property
    def model(self) -> str:
        return self._parse_string("a2", begin=22, end=27)

    @property
    def temperature(self) -> int:
        """Unit temperature (deg C)."""
        return self._parse_int("a5", begin=1, end=2, signed=True)

    @property
    def battery_percentage(self) -> int:
        return self._parse_int("a5", begin=3, end=4)

    @property
    def power_out(self) -> int:
        """Total power out (watts)."""
        return self._parse_int("a6", begin=1, end=3)

    @property
    def ac_power_in(self) -> int:
        return self._parse_int("a6", begin=3, end=5)

    @property
    def ac_power_out(self) -> int:
        return self._parse_int("a7", begin=2, end=4)

    @property
    def solar_power_in(self) -> int:
        return self._parse_int("a8", begin=2)

    @property
    def max_battery_percentage(self) -> int:
        return self._parse_int("d9", begin=4, end=5)

    @property
    def min_battery_percentage(self) -> int:
        return self._parse_int("d9", begin=5, end=6)
