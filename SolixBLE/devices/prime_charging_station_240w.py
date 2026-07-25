"""Anker Prime Charging Station (240W / A91B2) model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
import time

from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePublicKey,
    derive_private_key,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    UUID_COMMAND,
)
from ..device import SolixBLEDevice
from ..prime_device import PRIVATE_KEY
from .prime_usb_charger import PrimeUsbCharger

_LOGGER = logging.getLogger(__name__)

#: Cleartext-negotiation / confer packet pattern (``0xxx`` and ``4022``/``4023``).
_NEGOTIATION_PATTERN = b"\x03\x00\x01"
#: Encrypted session (data command) packet pattern.
_SESSION_PATTERN = b"\x03\x00\x0f"


class PrimeChargingStation240w(PrimeUsbCharger):
    """Anker Prime Charging Station (240W / A91B2), an 8-in-1 charging station.

    Despite sharing the Prime USB-charger telemetry layout, the station is **not**
    a Prime/GCM device -- it is a base/**CBC**-lineage device (like the C1000 Gen 2):
    it negotiates *in the clear* (``0xxx``) rather than with the encrypted ``4xxx``
    handshake, and encrypts the session with AES-CBC (key ``ss[:16]``, IV ``ss[16:]``).
    Talking GCM to it (as :class:`PrimeDevice` does) leaves every session command
    silently un-decryptable, so this class overrides the crypto and negotiation while
    inheriting the port decode from :class:`PrimeUsbCharger`.

    Two telemetry frames with **different tag layouts** are handled separately:

    * ``4a00`` (msgtype ``0a00``) -- full snapshot: ``a4``-``a9`` = the six USB ports
      (decoded by the inherited properties) plus ``aa``/``ab`` = the two AC-outlet
      switch states. Requested with ``4200``; refreshed by re-running the confer.
    * ``4303`` (msgtype ``0303``) -- ~1/s stream: the same six ports, one tag earlier
      (``a2``-``a7``). Remapped onto the snapshot tags and merged into :attr:`_data`,
      so the one inherited ``usb_c*``/``usb_a*`` property set reflects either frame.
      Started with ``420b`` (realtime trigger).

    No cloud/account data is needed: the confer is self-contained, and the device
    serial (which it binds) comes from the negotiation itself (``0829`` stage,
    ``a4``). Verified on hardware -- the station streams with no owner user_id.
    """

    #: The station is a base/CBC device -- use the base session crypto, not
    #: :class:`PrimeDevice`'s AES-GCM.
    _encrypt_payload = SolixBLEDevice._encrypt_payload
    _decrypt_payload = SolixBLEDevice._decrypt_payload

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _ts() -> str:
        """Current unix time as a 4-byte little-endian hex string."""
        return int(time.time()).to_bytes(4, "little").hex()

    async def _send_packet(self, pattern: bytes, cmd: str, plaintext: bytes) -> None:
        """Encrypt (CBC) and send a session/confer command, no response awaited."""
        packet = self._build_packet(
            pattern,
            bytes.fromhex(cmd),
            self._encrypt_payload(plaintext),
        )
        await self._client.write_gatt_char(UUID_COMMAND, packet, response=True)

    async def _exchange(
        self,
        cmd: str,
        payload_hex: str,
        resp_cmd: str,
        timeout: int = 6,
    ) -> bytes | None:
        """Send a cleartext ``0xxx`` negotiation frame and await its ``08xx`` reply."""
        future = asyncio.get_running_loop().create_future()
        resp = bytes.fromhex(resp_cmd)
        self._register_future(future, _NEGOTIATION_PATTERN, resp)
        try:
            packet = self._build_packet(
                _NEGOTIATION_PATTERN,
                bytes.fromhex(cmd),
                bytes.fromhex(payload_hex),
            )
            await self._client.write_gatt_char(UUID_COMMAND, packet, response=True)
            return await asyncio.wait_for(future, timeout)
        except (TimeoutError, asyncio.CancelledError):
            return None
        finally:
            self._deregister_future(future, _NEGOTIATION_PATTERN, resp)

    # ------------------------------------------------------------- negotiation

    async def _initiate_negotiations(self) -> None:
        """Run the whole cleartext (``0xxx``) handshake and derive the CBC session key.

        Base :meth:`connect` calls this and then waits on :attr:`negotiated`
        (``_shared_secret is not None``); doing the full handshake here lets us reuse
        the base connect/reconnect machinery while replacing only the negotiation.
        """
        private_key = derive_private_key(int(PRIVATE_KEY, 16), SECP256R1())
        public_key = private_key.public_key().public_bytes(
            Encoding.X962,
            PublicFormat.UncompressedPoint,
        )[1:]

        stages = (
            ("0001", "a104" + self._ts(), "0801"),
            ("0003", "a104" + self._ts() + "a30120a40200f0", "0803"),
            ("0029", "a104" + self._ts(), "0829"),
            ("0005", "a104" + self._ts() + "a30120a40200f0a50140", "0805"),
        )
        for cmd, payload, resp_cmd in stages:
            response = await self._exchange(cmd, payload, resp_cmd)
            if response is None:
                _LOGGER.warning(
                    "A91B2 '%s' negotiation stalled awaiting %s",
                    self.name,
                    resp_cmd,
                )
                return
            # Stage 3 (0829) carries the device identity: a4 = serial, a5 = MAC.
            if cmd == "0029":
                self._device_info = self._parse_payload(response)

        response = await self._exchange("0021", "a140" + public_key.hex(), "0821")
        if response is None:
            _LOGGER.warning("A91B2 '%s' no device public key (0821)", self.name)
            return
        device_public_key = EllipticCurvePublicKey.from_encoded_point(
            SECP256R1(),
            b"\x04" + self._parse_payload(response)["a1"],
        )
        self._shared_secret = private_key.exchange(ECDH(), device_public_key)
        self._negotiation_timestamp = time.time()
        _LOGGER.debug(
            "A91B2 '%s' negotiated (serial=%s)",
            self.name,
            self.serial_number,
        )

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """No-op: the station negotiates in the clear in :meth:`_initiate_negotiations`.

        The base ``030001`` handler drives :class:`PrimeDevice`'s encrypted ``4xxx``
        reactor, which must never run here; stray ``030001`` frames (e.g. a confer ack
        not consumed by a future) are simply logged.
        """
        _LOGGER.debug(
            "A91B2 '%s' ignoring unsolicited 030001 cmd %s",
            self.name,
            cmd.hex(),
        )

    async def _post_connect(self) -> None:
        """Send the CBC confer, request the full snapshot, and start the stream.

        Runs on every (re)connection once the session is negotiated. Fire-and-forget:
        ``4822``/``4823`` confer acks are harmless (see :meth:`_process_negotiation`),
        and ``4a00``/``4303`` responses flow through the telemetry path.
        """
        serial = (self._device_info or {}).get("a4", b"")
        timezone = self._local_posix_tz().encode()

        # 4022 -- timezone; 4023 -- bind device serial (both AES-CBC, 030001).
        await self._send_packet(
            _NEGOTIATION_PATTERN,
            "4022",
            bytes.fromhex(
                "a104"
                + self._ts()
                + "a30440380000a5"
                + f"{len(timezone):02x}"
                + timezone.hex()
            ),
        )
        await asyncio.sleep(0.4)
        await self._send_packet(
            _NEGOTIATION_PATTERN,
            "4023",
            bytes.fromhex("a104" + self._ts() + "a310") + serial,
        )
        await asyncio.sleep(0.4)
        # 4200 -- status request (-> 4a00 snapshot); 420b -- realtime trigger (-> 4303).
        await self._send_packet(
            _SESSION_PATTERN,
            "4200",
            bytes.fromhex("a10121fe0503" + self._ts()),
        )
        await asyncio.sleep(0.4)
        await self._send_packet(
            _SESSION_PATTERN,
            "420b",
            bytes.fromhex("a10121fe0503" + self._ts()),
        )

    async def _keepalive_loop(self) -> None:
        """Re-arm the realtime stream on a timer -- the app's ~9s 420b heartbeat.

        Overrides the base loop, which sends via ``_send_command`` (``fe04`` timestamp,
        write-without-response). This CBC station's realtime trigger is ``420b`` with
        ``a10121fe0503<ts>`` at ``response=True`` (the same framing its ``_post_connect``
        uses), so it must go through :meth:`_send_packet`. Started by base ``connect()``
        via the inherited ``_KEEPALIVE_CMD``; the interval (``_KEEPALIVE_INTERVAL``, 1s
        under the device's ~10s realtime window) and disconnect-cancel come from the base.
        """
        try:
            while True:
                await asyncio.sleep(self._KEEPALIVE_INTERVAL)
                await self._send_packet(
                    _SESSION_PATTERN,
                    "420b",
                    bytes.fromhex("a10121fe0503" + self._ts()),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.debug(
                "A91B2 '%s' realtime keep-alive stopped", self.name, exc_info=True
            )

    # ------------------------------------------------- 4a00 snapshot additions

    @property
    def ac_1_switch(self) -> bool:
        """AC outlet 1 switch state (from the ``4a00`` snapshot).

        :returns: True if on, else False (or default bool if no data).
        """
        if not self._data or "aa" not in self._data:
            return DEFAULT_METADATA_BOOL
        return bool(self._parse_int("aa", begin=1, end=2))

    @property
    def ac_2_switch(self) -> bool:
        """AC outlet 2 switch state (from the ``4a00`` snapshot).

        :returns: True if on, else False (or default bool if no data).
        """
        if not self._data or "ab" not in self._data:
            return DEFAULT_METADATA_BOOL
        return bool(self._parse_int("ab", begin=1, end=2))

    @property
    def usb_total_power_out(self) -> float:
        """Total output power over the six USB ports (W), from either frame."""
        if self._data is None:
            return DEFAULT_METADATA_FLOAT
        return round(
            self.usb_c1_power
            + self.usb_c2_power
            + self.usb_c3_power
            + self.usb_c4_power
            + self.usb_a1_power
            + self.usb_a2_power,
            2,
        )
