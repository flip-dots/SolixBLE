"""Solarbank 2 power station model.

Two variants live in this module:

* :class:`Solarbank2` — uses the **legacy** base ``SolixBLEDevice`` handshake
  (00xx/08xx negotiation, AES-CBC for session traffic). Does **not** require
  a cloud-tied user-id, so it can connect to any SB2 that accepts the
  base handshake.

* :class:`Solarbank2Prime` — uses the **Anker-Prime-style** handshake
  (40xx/48xx negotiation across 8 stages, AES-GCM for session traffic).
  Requires an Anker user-id.

Both variants share telemetry property accessors, the 0x405e schedule write
builder, and the wall-clock-timestamp ``_send_command`` override via the
:class:`_Solarbank2Common` base.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
"""

import logging
import os
import time
from enum import Enum

from bleak.backends.device import BLEDevice
from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePublicKey,
    generate_private_key,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ..const import (
    DEFAULT_METADATA_BOOL,
    DEFAULT_METADATA_FLOAT,
    DEFAULT_METADATA_STRING,
    UUID_COMMAND,
)
from ..device import SolixBLEDevice
from ..prime_device import (
    AAD,
    NEGOTIATION_KEY,
    NEGOTIATION_NONCE,
    NEGOTIATION_PATTERN,
    TELEMETRY_PATTERN,
    PrimeDevice,
)
from ..states import GridStatus, LightMode, SBPowerCutoff, SBUsageMode, TemperatureUnit

_LOGGER = logging.getLogger(__name__)


class MaxLoadSB2(Enum):
    """
    Maximum output power of the Solarbank 2 in watts.

    Only specific values are allowed.
    """

    #: The maximum load is unknown.
    UNKNOWN = -1

    #: 350 watts.
    W350 = 350

    #: 600 watts.
    W600 = 600

    #: 800 watts.
    W800 = 800

    #: 1000 watts.
    W1000 = 1000


#: One of the command codes for setting a schedule on an SB2.
CMD_SB2_SET_SCHEDULE = "405e"

#: TLV header introducing a 4-byte LE timestamp (tag ``a1``, length ``04``).
#: Recurs across handshake stage plaintexts and post-handshake payloads.
TLV_TIMESTAMP_HEADER = "a104"

#: TLV for an empty ``a2`` field (tag ``a2``, length ``00``, no value).
#: Appears as a fixed marker in several handshake plaintexts.
TLV_A2_EMPTY = "a200"

#: Environment variable for the Anker user ID required by Solarbank2Prime.
#: Value should be the ASCII-hex string (40 hex chars, no dashes).
#: The device validates this token against its
#: account-bound whitelist during the Prime-style handshak.
ENV_SB2_ANKER_USER_ID = "SB2_ANKER_USER_ID"


class _Solarbank2Common(SolixBLEDevice):
    """Shared base for both SB2 handshake variants.

    Holds everything that does not depend on the negotiation/crypto variant:

    * Telemetry property accessors (parse fields out of ``self._data`` populated
      by the parent's ``_process_telemetry``).
    * ``set_schedule`` / ``_build_set_schedule_payload`` for the 0x405e write.
    * ``_send_command`` override that uses a real wall-clock unix timestamp
      in the ``fe 05 03 <ts>`` trailer (the SolixBLEDevice base would use
      ``BASE_TIMESTAMP + elapsed_seconds`` which is fine for Prime but the SB2
      validates the timestamp against a sane recent-time window).

    The concrete subclasses :class:`Solarbank2` (legacy CBC) and
    :class:`Solarbank2Prime` (Prime-style GCM) pick the handshake/crypto
    behavior by their second base class.
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 253

    # ───────────────────────────────────────────────────────────────────────
    # Post-handshake command path
    # ───────────────────────────────────────────────────────────────────────

    async def _send_command(self, cmd: bytes, payload: bytes) -> None:
        """Send a post-handshake command with a wall-clock ``fe 05 03 <ts>`` trailer.

        Overrides the base/Prime schemes that derive the timestamp from a
        hardcoded ``BASE_TIMESTAMP`` constant. The SB2 expects a current Unix
        timestamp.

        Uses ``self._encrypt_payload`` and ``self._build_packet`` polymorphically:
        for :class:`Solarbank2` (legacy) ``_encrypt_payload`` resolves to the
        SolixBLEDevice CBC variant; for :class:`Solarbank2Prime` it resolves
        to the PrimeDevice GCM variant.

        :param cmd: 2-byte command identifier.
        :param payload: Plaintext payload (without the ``fe 05 03 <ts>`` trailer).
        :raises ConnectionError: If not connected/negotiated to device.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        ts = int(time.time()).to_bytes(4, "little")
        full_payload = payload + bytes.fromhex("fe0503") + ts

        encrypted = self._encrypt_payload(full_payload)
        packet = self._build_packet(
            pattern=bytes.fromhex(TELEMETRY_PATTERN),
            cmd=cmd,
            payload=encrypted,
        )
        _LOGGER.debug(f"SB2 _send_command cmd={cmd.hex()} packet={packet.hex()}")
        await self._client.write_gatt_char(UUID_COMMAND, packet)

    # ───────────────────────────────────────────────────────────────────────
    # 0x405e set-schedule
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_set_schedule_payload(power_w: int) -> bytes:
        """Build the plaintext payload for cmd 0x405e (set schedule).

        Produces a uniform 7-day schedule (Mon-Sun, all identical) with the
        same time range (00:00-24:00) and the requested output power.

        The caller's session timestamp is appended automatically by
        ``_send_command`` as the ``fe 05 03 <4-byte LE>`` trailer, so this
        function returns the payload *without* that trailer.

        :param power_w: Output wattage (0 = charge-only).
        """
        if not (0 <= power_w <= 800):
            raise ValueError(f"power_w must be 0-800 W, got {power_w}")

        # 8-byte schedule struct (byte layout shared with SB1, but the trailing
        # 2 bytes are an unknown constant on SB2 — SB1 calls that slot SOC but
        # on SB2 we've only ever seen 0x0050 LE regardless of user settings).
        #   bytes [0:2]  start_min u16 LE
        #   bytes [2:4]  end_min   u16 LE
        #   bytes [4:6]  power_W   u16 LE
        #   bytes [6:8]  unknown constant, always 0x0050 LE in captures
        # 00:00-24:00 → start=0, end=1440.
        sched_struct = (
            (0).to_bytes(2, "little")
            + (1440).to_bytes(2, "little")
            + power_w.to_bytes(2, "little")
            + bytes.fromhex("5000")
        )

        pt = bytearray()
        # Header
        pt += bytes.fromhex("a10121")
        pt += bytes.fromhex("a2020101")

        # 7 fully-symmetric day blocks (Mon-Sun). Each day uses 4 tags starting
        # at base = (a3 + 4*day):
        #   aX     02 01 01           enable/include flag for this day (always 1)
        #   aX+1   09 04 <8B struct>  the schedule struct itself
        #   aX+2   02 01 00           per-day flag (always 0 in captures)
        #   aX+3   01 04              1-byte trailer (always value 0x04)
        for day in range(7):
            base = 0xa3 + 4 * day
            pt += bytes([base    ]) + bytes.fromhex("020101")
            pt += bytes([base + 1]) + bytes.fromhex("0904") + sched_struct
            pt += bytes([base + 2]) + bytes.fromhex("020100")
            pt += bytes([base + 3]) + bytes.fromhex("0104")

        # `fd` trailer: 4 fresh random bytes generated per write. The Anker app
        # uses a different value every time (confirmed by a 3-write
        # capture); reusing a value the device has already seen in this session
        # leaves the device in an "abnormal state" where the schedule storage
        # gets updated but the inverter target doesn't change, and only a
        # subsequent write with a fresh value clears it.
        pt += bytes.fromhex("fd0503") + os.urandom(4)

        return bytes(pt)

    async def set_schedule(self, power_w: int) -> None:
        """Set a uniform 7-day charge/discharge schedule on the SB2.

        Sends cmd 405e with a payload that configures every day of the week
        identically: output `power_w` Watts from 00:00 to 24:00.

        :param power_w: Output wattage (0 = charge-only).
        :raises ConnectionError: If not connected/negotiated to the device.
        :raises ValueError: For out-of-range power_w.
        """
        payload = self._build_set_schedule_payload(power_w)
        await self._send_command(cmd=bytes.fromhex(CMD_SB2_SET_SCHEDULE), payload=payload)

    # ───────────────────────────────────────────────────────────────────────
    # Telemetry property accessors
    # ───────────────────────────────────────────────────────────────────────

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("a2", begin=1)

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a3", begin=1)

    @property
    def software_version(self) -> str:
        """Main software version.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a6", begin=1))])

    @property
    def software_version_controller(self) -> str:
        """Software version of the controller.

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a7", begin=1))])

    @property
    def software_version_expansion(self) -> str:
        """Software version of any expansion batteries.

        If there is no expansion battery then it will be "0".

        :returns: Firmware version or default str value.
        """
        if self._data is None:
            return DEFAULT_METADATA_STRING

        return ".".join([digit for digit in str(self._parse_int("a8", begin=1))])

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("aa", begin=1, signed=True)

    @property
    def solar_power_in(self) -> float:
        """Total Solar Power In.

        :returns: Total solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ab", begin=1) / 10.0

    @property
    def ac_power_out(self) -> float:
        """AC Power Out.

        :returns: Total AC power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ac", begin=1) / 10.0

    @property
    def battery_percentage_aggregate(self) -> int:
        """Battery Percentage average across all batteries.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("ad", begin=1)

    @property
    def battery_charge_power(self) -> float:
        """Battery charging power.

        :returns: Total battery power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b0", begin=1) / 100.0

    @property
    def pv_yield(self) -> float:
        """Solar energy generated in kWh.

        :returns: Total solar energy generated or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b1", begin=1) / 10000.0

    @property
    def charged_energy(self) -> float:
        """Total accumulated energy that passed through the battery in kWh

        :returns: The amount of energy or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        # The / 100 000 is correct despite all other divisors being 10 000.
        # This is the "Storage" stats field in the Anker app
        return self._parse_int("b2", begin=1) / 100000.0

    @property
    def output_energy(self) -> float:
        """Output energy in kWh.

        :returns: Total energy output or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b3", begin=1) / 10000.0

    @property
    def battery_discharge_power(self) -> float:
        """Battery discharging power.

        :returns: Total battery power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("b7", begin=1) / 100.0

    @property
    def grid_to_home_power(self) -> float:
        """Grid to home power.

        :returns: Power from grid to home or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bc", begin=1) / 10.0

    @property
    def pv_to_grid_power(self) -> float:
        """PV to grid power.

        :returns: Power from PV to grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bd", begin=1) / 10.0

    @property
    def grid_import_energy(self) -> float:
        """Grid import energy.

        :returns: Total energy imported from grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("be", begin=1) / 10000.0

    @property
    def grid_export_energy(self) -> float:
        """Grid export energy.

        :returns: Total energy exported to grid or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("bf", begin=1) / 10000.0

    @property
    def house_demand(self) -> float:
        """House demand power.

        :returns: Power used by house or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c4", begin=1) / 10.0

    @property
    def ac_power_out_sockets(self) -> float:
        """AC Power Out to sockets.

        :returns: AC power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c8", begin=1) / 10.0

    @property
    def consumed_energy(self) -> float:
        """Consumed energy by house.

        :returns: Total energy consumed by house or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("c9", begin=1) / 10000.0

    @property
    def solar_pv_1_power_in(self) -> float:
        """Solar Power In for port 1.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("ca", begin=1) / 10.0

    @property
    def solar_pv_2_power_in(self) -> float:
        """Solar Power In for port 2.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cb", begin=1) / 10.0

    @property
    def solar_pv_3_power_in(self) -> float:
        """Solar Power In for port 3.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cc", begin=1) / 10.0

    @property
    def solar_pv_4_power_in(self) -> float:
        """Solar Power In for port 4.

        :returns: Solar power in or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("cd", begin=1) / 10.0

    @property
    def power_out(self) -> float:
        """Total Power Out.

        :returns: Total power out or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return self._parse_int("d3", begin=1) / 10.0

    @property
    def error_code(self) -> int:
        """Device error code.

        :returns: Error code or default int value.
        """
        return self._parse_int("a5", begin=1)

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """Temperature unit setting.

        :returns: Temperature unit (Celsius or Fahrenheit).
        """
        return TemperatureUnit(self._parse_int("a9", begin=1))

    @property
    def output_cutoff_data(self) -> SBPowerCutoff:
        """
        Output cutoff threshold in %.

        Minimum battery SOC to maintain.

        :returns: Output cutoff battery SOC threshold.
        """
        return SBPowerCutoff(self._parse_int("b4", begin=1))

    @property
    def lowpower_input_data(self) -> int:
        """Low power input data.

        :returns: Low power input data or default int value.
        """
        return self._parse_int("b5", begin=1)

    @property
    def input_cutoff_data(self) -> SBPowerCutoff:
        """Input cutoff threshold in %.

        :returns: Input cutoff battery SOC threshold.
        """
        return SBPowerCutoff(self._parse_int("b6", begin=1))

    @property
    def max_load(self) -> MaxLoadSB2:
        """
        Maximum output power in watts.

        Maximum legal value depends on country of operation.

        :returns: Maximum load as a MaxLoadSB2 enum value.
        """
        return MaxLoadSB2(self._parse_int("c2", begin=1))

    @property
    def usage_mode(self) -> SBUsageMode:
        """Usage mode.

        :returns: Usage mode as a SBUsageMode enum value.
        """
        return SBUsageMode(self._parse_int("c6", begin=1))

    @property
    def home_load_preset(self) -> int:
        """Home load preset in watts.

        :returns: Home load preset in watts or default int value.
        """
        return self._parse_int("c7", begin=1)

    @property
    def light_mode(self) -> LightMode:
        """Light mode. Normal or Mood.

        :returns: Light mode.
        """
        return LightMode(self._parse_int("d2", begin=1))

    @property
    def grid_status(self) -> GridStatus:
        """Grid connection status.

        :returns: Grid status.
        """
        return GridStatus(self._parse_int("e0", begin=1))

    @property
    def light_on(self) -> bool | None:
        """Whether the light is switched on.
        Original value is inverted because it is called "light_off_switch"

        :returns: True if light is on, False if off.
        """
        return (
            not bool(self._parse_int("e1", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )

    @property
    def battery_heating(self) -> bool | None:
        """Whether the battery is currently heating.

        :returns: True if heating, False if not heating.
        """
        return (
            bool(self._parse_int("e8", begin=1))
            if self._data is not None
            else DEFAULT_METADATA_BOOL
        )


class Solarbank2(_Solarbank2Common):
    """SolarBank 2 power station with the **legacy** base handshake.

    Uses the SolixBLEDevice 00xx/08xx negotiation and AES-CBC for session
    traffic. Does **not** require a user-id.

    This is the **recommended default** for end users — no cloud-side
    user-id capture needed. Use :class:`Solarbank2Prime` only if you need
    to mimic the Anker app's exact handshake (e.g. for protocol research).
    """

    async def _initiate_negotiations(self) -> None:
        """Start the legacy base SolixBLEDevice handshake."""
        _LOGGER.info(
            "SB2: starting legacy base handshake (00xx/08xx, AES-CBC)"
        )
        await super()._initiate_negotiations()


class Solarbank2Prime(_Solarbank2Common, PrimeDevice):
    """SolarBank 2 power station with the **Anker-Prime-style** handshake.

    Uses 40xx/48xx negotiation across 8 stages and AES-GCM for session
    traffic. Requires an Anker user-id - SB2 firmware whitelists user-ids
    rejects unknown values with RX 4827 = ``09 a1 02 b4 00``.

    Differences from Anker Prime power stations:

    * Per-session random ECDH private key (Prime uses a hardcoded one).
    * Different stage-0 through stage-4 plaintexts (live timestamps, extra
      TLVs).
    * Stage-6 sets the timezone (TX 4022); stage-7 re-sends the user-id
      (TX 4027) session-encrypted.
    * Post-stage-5 payloads use the ``fe 05 03 <ts>`` trailer rather than
      Prime's ``fe 04 <ts>``.

    .. note::
       The Anker app sends TX 4001 (stage 0) and TX 4040 (stage 8) **twice**
       each. We send each once because it seems to work.
    """

    # ───────────────────────────────────────────────────────────────────────
    # Per-session state for the SB2 handshake
    # ───────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        ble_device: BLEDevice,
        anker_user_id: bytes | str | None = None,
    ) -> None:
        """Initialize SB2 device with per-instance ECDH key and Anker user ID.

        :param ble_device: The discovered BLE device handle.
        :param anker_user_id: Cloud-registered Anker user ID for the user's
            Anker account. If ``None``, reads from the
            ``SB2_ANKER_USER_ID`` environment variable. If neither is set,
            raises ``ValueError``.
        :raises ValueError: If no Anker user ID is available via either
            source.
        """
        super().__init__(ble_device)
        # Per-session random ECDH private key (regenerated on each connect via
        # ``_initiate_negotiations``). SB2 does NOT use Prime's hardcoded key.
        self._ecdh_private_key = generate_private_key(SECP256R1())
        # Negotiation-stage timestamp baked into stage-0..4 TX plaintexts as the
        # 4-byte LE int after the a1 tag. Same value across all of stages 0-4.
        self._neg_ts_bytes: bytes | None = None
        # Anker user ID resolution: explicit arg > env var > error.
        # The SB2 firmware whitelists Anker user IDs.
        if anker_user_id is None:
            env_val = os.environ.get(ENV_SB2_ANKER_USER_ID)
            if not env_val:
                raise ValueError(
                    f"Solarbank2Prime requires the Anker cloud-side userId. "
                    f"Either pass anker_user_id=<bytes|str> to the constructor "
                    f"or set the {ENV_SB2_ANKER_USER_ID} environment variable. "
                    f"Alternatively, use the Solarbank2 (legacy CBC) class — "
                    f"it does not require an Anker user ID."
                )
            anker_user_id = env_val
        if isinstance(anker_user_id, str):
            anker_user_id = anker_user_id.encode("ascii")
        self._anker_user_id: bytes = anker_user_id

    # ───────────────────────────────────────────────────────────────────────
    # Encryption helpers
    # ───────────────────────────────────────────────────────────────────────

    def _encrypt_with_static_key(self, plaintext: bytes) -> bytes:
        """AES-GCM encrypt with the static negotiation key (stages 0-4)."""
        cipher = AES.new(
            bytes.fromhex(NEGOTIATION_KEY),
            AES.MODE_GCM,
            nonce=bytes.fromhex(NEGOTIATION_NONCE),
        )
        cipher.update(bytes.fromhex(AAD))
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return ciphertext + tag

    def _build_static_packet(self, cmd_hex: str, plaintext: bytes) -> bytes:
        """Build a stage-0..4 packet: encrypt with static key, then frame."""
        return self._build_packet(
            pattern=bytes.fromhex(NEGOTIATION_PATTERN),
            cmd=bytes.fromhex(cmd_hex),
            payload=self._encrypt_with_static_key(plaintext),
        )

    def _build_session_packet(self, cmd_hex: str, plaintext: bytes) -> bytes:
        """Build a stage-5+ packet: encrypt with session key, then frame."""
        return self._build_packet(
            pattern=bytes.fromhex(NEGOTIATION_PATTERN),
            cmd=bytes.fromhex(cmd_hex),
            payload=self._encrypt_payload(plaintext),
        )

    # ───────────────────────────────────────────────────────────────────────
    # Handshake
    # ───────────────────────────────────────────────────────────────────────

    async def _initiate_negotiations(self) -> None:
        """SB2 stage 0: send TX 4001 with ``a1 04 <ts> a2 00``."""
        _LOGGER.info(
            "SB2: starting Prime-style handshake (40xx/48xx, AES-GCM, with Anker user ID)"
        )
        # Fresh ECDH key + negotiation timestamp on every (re-)connect.
        self._ecdh_private_key = generate_private_key(SECP256R1())
        self._neg_ts_bytes = int(time.time()).to_bytes(4, "little")

        plaintext = bytes.fromhex(TLV_TIMESTAMP_HEADER) + self._neg_ts_bytes + bytes.fromhex(TLV_A2_EMPTY)
        packet = self._build_static_packet("4001", plaintext)
        _LOGGER.debug(f"SB2 stage 0 TX 4001 packet: {packet.hex()}")
        await self._client.write_gatt_char(UUID_COMMAND, packet)

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """SB2 handshake state machine (overrides PrimeDevice's variant)."""

        # Decrypt for logging; _decrypt_payload picks static vs session key
        # automatically based on whether _shared_secret has been set.
        try:
            decrypted = self._decrypt_payload(payload)
            _LOGGER.debug(
                f"SB2 stage cmd={cmd.hex()} decrypted plaintext={decrypted.hex()}"
            )
        except Exception:
            _LOGGER.exception(f"SB2 failed to decrypt stage cmd={cmd.hex()}")
            decrypted = b""

        match cmd.hex():

            # Stage 1 — RX 4801 → TX 4003 (a1 04 <ts> a2 00 a3 01 20 a4 02 00 f0)
            case "4801":
                pt = (
                    bytes.fromhex(TLV_TIMESTAMP_HEADER) + self._neg_ts_bytes +
                    bytes.fromhex(TLV_A2_EMPTY) +
                    bytes.fromhex("a30120") +
                    bytes.fromhex("a40200f0")
                )
                packet = self._build_static_packet("4003", pt)
                _LOGGER.debug(f"SB2 stage 2 TX 4003 packet: {packet.hex()}")
                return await self._client.write_gatt_char(UUID_COMMAND, packet)

            # Stage 2 — RX 4803 → TX 4029 (a1 04 <ts> a2 <len> <user-id>)
            case "4803":
                pt = (
                    bytes.fromhex(TLV_TIMESTAMP_HEADER) + self._neg_ts_bytes +
                    bytes.fromhex("a2") + bytes([len(self._anker_user_id)]) + self._anker_user_id
                )
                packet = self._build_static_packet("4029", pt)
                _LOGGER.debug(f"SB2 stage 3 TX 4029 packet: {packet.hex()}")
                return await self._client.write_gatt_char(UUID_COMMAND, packet)

            # Stage 3 — RX 4829 → TX 4005
            case "4829":
                pt = (
                    bytes.fromhex(TLV_TIMESTAMP_HEADER) + self._neg_ts_bytes +
                    bytes.fromhex(TLV_A2_EMPTY) +
                    bytes.fromhex("a30120") +
                    bytes.fromhex("a40200f0") +
                    bytes.fromhex("a50140") +
                    bytes.fromhex("a60102")
                )
                packet = self._build_static_packet("4005", pt)
                _LOGGER.debug(f"SB2 stage 4 TX 4005 packet: {packet.hex()}")
                return await self._client.write_gatt_char(UUID_COMMAND, packet)

            # Stage 4 — RX 4805 → TX 4021 (phone ECDH pubkey, raw X||Y)
            case "4805":
                phone_pub_xy = self._ecdh_private_key.public_key().public_bytes(
                    Encoding.X962, PublicFormat.UncompressedPoint
                )[1:]  # strip 0x04 prefix → 64 B X||Y
                pt = bytes.fromhex("a140") + phone_pub_xy
                packet = self._build_static_packet("4021", pt)
                _LOGGER.debug(f"SB2 stage 5 TX 4021 packet: {packet.hex()}")
                return await self._client.write_gatt_char(UUID_COMMAND, packet)

            # Stage 5 — RX 4821 → derive shared secret, then TX 4022 (timezone)
            case "4821":
                # Parse plaintext: <status 1B> <TLV a1 40 <device pubkey 64B>>
                parameters = self._parse_payload(decrypted[1:])
                device_pub_xy = parameters["a1"]
                device_pubkey = EllipticCurvePublicKey.from_encoded_point(
                    SECP256R1(), bytes.fromhex("04") + device_pub_xy
                )
                self._shared_secret = self._ecdh_private_key.exchange(
                    ECDH(), device_pubkey
                )
                self._negotiation_timestamp = time.time()
                _LOGGER.debug(
                    f"SB2 ECDH shared secret derived: {self._shared_secret.hex()}"
                )

                # TX 4022 — set timezone. Plaintext layout:
                #   a1 04 <session-ts>  a2 00  a3 04 <tz_offset_seconds_LE>
                #   a5 <len> <POSIX TZ string>
                # The tz_offset is signed LE seconds; CEST in capture was -7200
                # (= -2h). We hardcode that for now — proper localtime detection
                # is a TODO.
                tz_str = b"CET-1CEST,M3.5.0,M10.5.0/3"
                tz_offset = (-7200).to_bytes(4, "little", signed=True)
                pt = (
                    bytes.fromhex(TLV_TIMESTAMP_HEADER) + int(time.time()).to_bytes(4, "little") +
                    bytes.fromhex(TLV_A2_EMPTY) +
                    bytes.fromhex("a304") + tz_offset +
                    bytes([0xa5, len(tz_str)]) + tz_str
                )
                packet = self._build_session_packet("4022", pt)
                _LOGGER.debug(f"SB2 stage 6 TX 4022 packet: {packet.hex()}")
                return await self._client.write_gatt_char(UUID_COMMAND, packet)

            # Stage 6 — RX 4822 → TX 4027 (re-send user-id, session-encrypted)
            case "4822":
                pt = (
                    bytes.fromhex(TLV_TIMESTAMP_HEADER) + int(time.time()).to_bytes(4, "little") +
                    bytes.fromhex("a2") + bytes([len(self._anker_user_id)]) + self._anker_user_id
                )
                packet = self._build_session_packet("4027", pt)
                _LOGGER.debug(f"SB2 stage 7 TX 4027 packet: {packet.hex()}")
                return await self._client.write_gatt_char(UUID_COMMAND, packet)

            # Stage 7 — RX 4827 → TX 4040 (start telemetry stream)
            case "4827":
                # _send_command handles the fe0503 timestamp trailer + 03000f
                # pattern.
                _LOGGER.debug("SB2 stage 8 — sending TX 4040 to start telemetry")
                return await self._send_command(
                    cmd=bytes.fromhex("4040"), payload=bytes.fromhex("a10121")
                )

            case _:
                _LOGGER.warning(
                    f"SB2 unexpected negotiation cmd: {cmd.hex()} "
                    f"plaintext={decrypted.hex()}"
                )

    # ───────────────────────────────────────────────────────────────────────
    # Telemetry
    # ───────────────────────────────────────────────────────────────────────

    async def _process_telemetry_packet(
        self, payload: bytes, cmd: bytes = None
    ) -> None:
        """Handle SB2 multi-fragment telemetry (cmd c405 + c840, pattern 03010f).

        PrimeDevice's variant assumes single-packet telemetry, but SB2 splits
        large telemetry across multiple ``03010f`` packets with a per-packet
        ``<index/total>`` nibble byte after CMD. Delegate to the base
        SolixBLEDevice implementation, which already implements reassembly.
        After reassembly it calls ``self._decrypt_payload``, which on this
        class is PrimeDevice's AES-GCM variant.
        """
        return await SolixBLEDevice._process_telemetry_packet(self, payload, cmd)
