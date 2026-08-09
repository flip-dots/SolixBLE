"""Solarbank 3 power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import logging
import struct
import time

from bleak.backends.device import BLEDevice
from cryptography.hazmat.primitives.asymmetric import ec

from ..const import DEFAULT_METADATA_FLOAT, DEFAULT_METADATA_STRING, UUID_COMMAND
from ..prime_device import PrimeDevice
from ..sb3_protocol import (
    SB3_4001,
    SB3_4003,
    SB3_4005,
    SB3_4029,
    SB3_4822_SUCCESS_PLAINTEXT,
    SB3_SCHEDULE_MODE_CHARGE,
    SB3_SCHEDULE_MODE_DISCHARGE,
    SB3_SET_MAX_LOAD_COMMAND,
    SB3_SET_SCHEDULE_COMMAND,
    aes_gcm_decrypt,
    build_account_auth_packet,
    build_firmware_request_packet,
    build_max_load_plaintext,
    build_public_key_packet,
    build_schedule_plaintext,
    build_security_auth_packet,
    build_telemetry_request_packet,
    decode_public_key,
    validate_account_id,
)

_LOGGER = logging.getLogger(__name__)


class Solarbank3(PrimeDevice):
    """
    SolarBank 3 Power Station.

    Use this class to connect and monitor a Solarbank 3 power station.
    This model is also known as the A17C5.

    The implementation has been tested against an Anker Solarbank 3 E2700 Pro
    (A17C5) running firmware 1.0.7.1.  The account identifier is passed to the
    constructor because the device validates it during local BLE authentication.

    .. note::
        It should be possible to add more sensors. I think devices with lots of
        telemetry values split them up into multiple messages but I have not
        played around with this yet. That and I am being a bit conservative with
        these initial implementations, if you want more sensors and are willing
        to help with testing feel free to raise a GitHub issue.

    """

    _TELEMETRY_COMMANDS: tuple[str, ...] = (
        "c405",
        "c840",
        "4409",
        "4830",
        "485e",
    )
    _EXPECTED_TELEMETRY_LENGTH: int = 253

    def __init__(self, ble_device: BLEDevice, anker_user_id: str) -> None:
        """Initialise an A17C5 device with its Anker account identifier."""
        super().__init__(ble_device)
        self._anker_user_id = validate_account_id(anker_user_id)
        self._sb3_session_ready = False
        self._sb3_private_key = ec.generate_private_key(ec.SECP256R1())
        self._sb3_raw_fragments: dict[str, dict[int, bytes]] = {}
        self._sb3_battery_metadata: bytes | None = None
        self._sb3_firmware_metadata: dict[str, str] = {}
        self._schedule_mode = SB3_SCHEDULE_MODE_DISCHARGE

    @property
    def negotiated(self) -> bool:
        """Return True only after the SB3 authentication sequence is complete."""
        return self.connected and self._sb3_session_ready

    def _reset_session(self, reset_data: bool = True) -> None:
        """Reset the inherited session and the SB3-specific authentication state."""
        super()._reset_session(reset_data)
        self._sb3_session_ready = False
        self._sb3_raw_fragments = {}

    @property
    def schedule_mode(self) -> str:
        """Return the direction used by the next all-day schedule write."""
        return self._schedule_mode

    def set_schedule_mode(self, mode: str) -> None:
        """Choose whether a custom schedule charges or discharges the bank."""
        if mode not in (SB3_SCHEDULE_MODE_DISCHARGE, SB3_SCHEDULE_MODE_CHARGE):
            raise ValueError("mode must be 'discharge' or 'charge'")
        self._schedule_mode = mode

    def _decrypt_payload(self, payload: bytes) -> bytes:
        """Authenticate and decrypt an A17C5 session payload without fallback."""
        if self._shared_secret is None:
            raise ConnectionError("Solarbank 3 session key is not available")
        return aes_gcm_decrypt(
            self._shared_secret[:16],
            self._shared_secret[16:28],
            payload,
        )

    @staticmethod
    def _is_complete_tlv_payload(payload: bytes) -> bool:
        """Return whether an A17C5 payload is a complete telemetry TLV list."""
        if not payload:
            return False
        index = 1 if payload[0] == 0 else 0
        if index == len(payload):
            return False
        while index < len(payload):
            if len(payload) - index < 2:
                return False
            value_length = payload[index + 1]
            index += 2
            if len(payload) - index < value_length:
                return False
            index += value_length
        return True

    @staticmethod
    def _parse_firmware_metadata(payload: bytes) -> dict[str, str]:
        """Decode the compact ASCII TLV body returned by authenticated 4830."""
        index = 1 if payload[:1] in (b"\x00", b"\x04") else 0
        metadata: dict[str, str] = {}
        while index + 2 <= len(payload):
            parameter_id, value_length = payload[index : index + 2]
            index += 2
            value = payload[index : index + value_length]
            if len(value) != value_length:
                return {}
            try:
                metadata[f"{parameter_id:02x}"] = value.decode("ascii")
            except UnicodeDecodeError:
                pass
            index += value_length
        return metadata if index == len(payload) else {}

    async def _process_telemetry_packet(
        self, payload: bytes, cmd: bytes = None
    ) -> None:
        """Handle A17C5 GCM frames without losing a valid first byte.

        A17C5 uses ``0x12``/``0x22`` only for actual two-part packets.  A
        single encrypted packet can legitimately begin with ``0x11``; treating
        that byte as a fragment marker drops data and makes AES-GCM validation
        fail after reconnects.
        """
        if cmd is None:
            return
        command = cmd.hex()
        complete_payload = bytes(payload)
        if payload:
            fragment_index = (payload[0] >> 4) & 0x0F
            fragment_total = payload[0] & 0x0F
            if 1 <= fragment_index <= fragment_total and 2 <= fragment_total <= 4:
                fragments = self._sb3_raw_fragments.setdefault(command, {})
                if fragment_index == 1:
                    fragments.clear()
                fragments[fragment_index] = bytes(payload[1:])
                if len(fragments) < fragment_total:
                    return
                complete_payload = b"".join(
                    fragments[index] for index in range(1, fragment_total + 1)
                )
                self._sb3_raw_fragments.pop(command, None)

        plaintext = self._decrypt_payload(complete_payload)
        if len(plaintext) == 4 and plaintext[:3] == b"\x01\xa1\x01":
            _LOGGER.debug("Solarbank 3 command acknowledgement: %s", plaintext[-1:])
            return
        if command == "4409":
            self._sb3_battery_metadata = plaintext
            return
        if command == "4830":
            self._sb3_firmware_metadata = self._parse_firmware_metadata(plaintext)
            return
        if not self._is_complete_tlv_payload(plaintext):
            _LOGGER.debug(
                "Ignoring authenticated non-telemetry A17C5 packet %s", command
            )
            return
        await self._process_telemetry(self._parse_payload(plaintext))

    async def _process_telemetry(self, parameters: dict[str, bytes]) -> None:
        """Merge partial A17C5 updates instead of clearing known fields."""
        if self._data is not None:
            parameters = {**self._data, **parameters}
        await super()._process_telemetry(parameters)

    async def _initiate_negotiations(self) -> None:
        """Start the A17C5 secure-conference handshake."""
        self._sb3_private_key = ec.generate_private_key(ec.SECP256R1())
        await self._client.write_gatt_char(UUID_COMMAND, SB3_4001, response=False)

    async def _process_negotiation(self, cmd: bytes, payload: bytes) -> None:
        """Advance the A17C5 handshake and start encrypted telemetry."""
        command = cmd.hex()
        if command == "4801":
            reply = SB3_4003
        elif command == "4803":
            reply = SB3_4029
        elif command == "4829":
            reply = SB3_4005
        elif command == "4805":
            reply = build_public_key_packet(self._sb3_private_key.public_key())
        elif command == "4821":
            encrypted = aes_gcm_decrypt(
                bytes.fromhex("b8ff7422955d4eb6d554a2c470280559"),
                bytes.fromhex("6ba3e3f2f3a60f2971ce5d1f"),
                payload,
            )
            if not encrypted.startswith(b"\x00\xa1\x40"):
                raise ValueError("unexpected Solarbank 3 4821 public-key payload")
            device_public_key = decode_public_key(encrypted[3:])
            self._shared_secret = self._sb3_private_key.exchange(
                ec.ECDH(), device_public_key
            )
            self._negotiation_timestamp = time.time()
            reply = build_account_auth_packet(
                self._anker_user_id,
                self._shared_secret[:16],
                self._shared_secret[16:28],
            )
        elif command == "4822":
            plaintext = self._decrypt_payload(payload)
            if plaintext != SB3_4822_SUCCESS_PLAINTEXT:
                raise ValueError(
                    f"Solarbank 3 identity authentication failed: {plaintext.hex()}"
                )
            reply = build_security_auth_packet(
                self._anker_user_id,
                self._shared_secret[:16],
                self._shared_secret[16:28],
            )
        elif command == "4827":
            plaintext = self._decrypt_payload(payload)
            if plaintext != b"\x00":
                raise ValueError(
                    "Solarbank 3 client-security authentication failed: "
                    f"{plaintext.hex()}"
                )
            self._sb3_session_ready = True
            reply = build_telemetry_request_packet(
                self._shared_secret[:16],
                self._shared_secret[16:28],
                int.from_bytes(bytes.fromhex("ef79b569"), "little")
                + int(time.time() - self._negotiation_timestamp),
            )
        else:
            _LOGGER.warning("Unexpected Solarbank 3 negotiation command: %s", command)
            return

        await self._client.write_gatt_char(UUID_COMMAND, reply, response=False)

    async def _post_connect(self) -> None:
        """Re-arm status telemetry and request read-only firmware metadata."""
        if self._sb3_session_ready:
            timestamp = int.from_bytes(bytes.fromhex("ef79b569"), "little") + int(
                time.time() - self._negotiation_timestamp
            )
            await self._client.write_gatt_char(
                UUID_COMMAND,
                build_telemetry_request_packet(
                    self._shared_secret[:16],
                    self._shared_secret[16:28],
                    timestamp,
                ),
                response=False,
            )
            await self._client.write_gatt_char(
                UUID_COMMAND,
                build_firmware_request_packet(
                    self._shared_secret[:16],
                    self._shared_secret[16:28],
                    timestamp + 1,
                ),
                response=False,
            )

    async def set_schedule(
        self,
        power_w: int,
        *,
        start_minutes: int = 0,
        end_minutes: int = 1440,
        mode: str | None = None,
    ) -> None:
        """Set a uniform seven-day output schedule using command 405e."""
        await self._send_command(
            SB3_SET_SCHEDULE_COMMAND,
            build_schedule_plaintext(
                power_w,
                start_minutes=start_minutes,
                end_minutes=end_minutes,
                mode=self._schedule_mode if mode is None else mode,
            ),
        )

    async def set_max_load(self, max_load_w: int) -> None:
        """Set the device maximum output/load limit using command 4080."""
        await self._send_command(
            SB3_SET_MAX_LOAD_COMMAND,
            build_max_load_plaintext(max_load_w),
        )

    def _parse_sb3_float(self, key: str) -> float:
        """Parse an A17C5 typed float, retaining compatibility with integer data."""
        if self._data is None or key not in self._data:
            return DEFAULT_METADATA_FLOAT
        value = self._data[key]
        if value and value[0] == 0x05 and len(value) >= 5:
            return struct.unpack("<f", value[1:5])[0]
        return float(self._parse_int(key, begin=1))

    @property
    def serial_number(self) -> str:
        """Device serial number.

        :returns: Device serial number or default str value.
        """
        return self._parse_string("a2", begin=1)

    @property
    def software_version(self) -> str:
        """Return the primary Solarbank firmware reported by ``4830``."""
        return self._sb3_firmware_metadata.get("a2", DEFAULT_METADATA_STRING)

    @property
    def firmware_versions(self) -> str:
        """Return all verified bank-side firmware and component strings."""
        labels = (
            ("Solarbank", "a2"),
            ("Internal MCU", "a1"),
            ("MCU component", "a4"),
            ("ESP32 component", "a5"),
        )
        values = [
            f"{label}: {value}"
            for label, key in labels
            if (value := self._sb3_firmware_metadata.get(key))
        ]
        return " | ".join(values) if values else DEFAULT_METADATA_STRING

    @property
    def battery_percentage_aggregate(self) -> float:
        """Battery Percentage average across all batteries.

        :returns: Percentage charge of battery or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        percentages = [self._parse_int("a3", begin=1)]
        for slot in range(1, 6):
            percentage = self._expansion_battery(slot)[1]
            if percentage is not None:
                percentages.append(percentage)
        return float(sum(percentages) // len(percentages))

    @property
    def battery_health(self) -> float:
        """Battery health as a percentage.

        :returns: Percentage of battery health or default float value.
        """
        if self._data is None:
            return DEFAULT_METADATA_FLOAT

        return float(self._parse_int("a6", begin=1))

    @property
    def battery_percentage(self) -> int:
        """Battery Percentage.

        :returns: Percentage charge of battery or default int value.
        """
        return self._parse_int("a3", begin=1)

    @property
    def solar_power_in(self) -> int:
        """Total Solar Power In.

        :returns: Total solar power in or default int value.
        """
        return round(self._parse_sb3_float("ab"))

    @property
    def pv_yield(self) -> int:
        """Solar power generated.

        :returns: Total solar power generated or default int value.
        """
        return max(0.0, self._parse_sb3_float("ac"))

    @property
    def house_demand(self) -> int:
        """House demand power.

        :returns: Power used by house or default int value.
        """
        return round(self._parse_sb3_float("b1"))

    @property
    def house_consumption(self) -> int:
        """House consumption power.

        Don't ask me how this differs from house demand, I have no idea.

        :returns: Power used by house or default int value.
        """
        return round(self._parse_sb3_float("b2"))

    @property
    def battery_power(self) -> int:
        """Battery power in and out.

        I don't know what direction is which.

        :returns: Power in/out of battery or default int value.
        """
        return self._parse_int("b6", begin=1, signed=True)

    @property
    def schedule_power(self) -> int:
        """Return the active schedule output target reported in field b9."""
        return self._parse_int("b9", begin=1)

    @property
    def charged_energy(self) -> int:
        """Energy into battery?

        :returns: Energy into battery or default int value.
        """
        return self._parse_int("b7", begin=1)

    @property
    def discharged_energy(self) -> int:
        """Energy out of battery?

        :returns: Energy out of battery or default int value.
        """
        return self._parse_int("b8", begin=1)

    @property
    def grid_power(self) -> int:
        """Grid power in and out.

        I don't know what direction is which.

        :returns: Power in/out of grid or default int value.
        """
        return round(self._parse_sb3_float("bd"))

    @property
    def grid_import_energy(self) -> int:
        """Grid import energy.

        :returns: Total energy imported from grid or default int value.
        """
        return self._parse_int("be", begin=1)

    @property
    def grid_export_energy(self) -> int:
        """Grid export energy.

        :returns: Total energy exported to grid or default int value.
        """
        return round(self._parse_sb3_float("bf"))

    @property
    def solar_pv_1_power_in(self) -> int:
        """Solar Power In for port 1.

        :returns: Solar power in or default int value.
        """
        return self._solar_pv_port_power_in("c6")

    def _solar_pv_port_power_in(self, key: str) -> int:
        """Return a non-stale individual MPPT value from c6 through c9."""
        value = max(0.0, self._parse_sb3_float(key))
        if self.solar_power_in <= 0 and value > 0:
            return 0
        return round(value)

    @property
    def solar_pv_2_power_in(self) -> int:
        """Solar Power In for port 2.

        :returns: Solar power in or default int value.
        """
        return self._solar_pv_port_power_in("c7")

    @property
    def solar_pv_3_power_in(self) -> int:
        """Solar Power In for port 3.

        :returns: Solar power in or default int value.
        """
        return self._solar_pv_port_power_in("c8")

    @property
    def solar_pv_4_power_in(self) -> int:
        """Solar Power In for port 4.

        :returns: Solar power in or default int value.
        """
        return self._solar_pv_port_power_in("c9")

    @property
    def temperature(self) -> int:
        """Temperature of the unit (C).

        :returns: Temperature of the unit in degrees C.
        """
        return self._parse_int("a5", begin=1, signed=True)

    def _expansion_battery(
        self, slot: int
    ) -> tuple[str | None, int | None, int | None]:
        """Decode one inserted BP1600/BP2700 record from ``4409`` metadata.

        Firmware through 1.0.7.3 uses either ``63 01`` or ``6a 01`` as the
        record marker.  The 16 ASCII bytes directly ahead of that marker are
        the battery serial; SoC and temperature use the verified positions in
        the compact record.  Unknown layouts remain unavailable rather than
        being guessed.
        """
        payload = getattr(self, "_sb3_battery_metadata", None)
        if payload is None:
            return None, None, None
        for marker_start in (0x63, 0x6A):
            marker = bytes((marker_start, 0x01, slot))
            start = 0
            while (index := payload.find(marker, start)) >= 16:
                if index + 7 > len(payload):
                    start = index + 1
                    continue
                try:
                    serial = payload[index - 16 : index].decode("ascii")
                except UnicodeDecodeError:
                    start = index + 1
                    continue
                return serial, payload[index + 5], payload[index + 3]
        return None, None, None

    @property
    def num_expansion(self) -> int:
        """Return the number of detected expansion batteries."""
        return sum(self._expansion_battery(slot)[0] is not None for slot in range(1, 6))

    @property
    def expansion_battery_1_serial_number(self) -> str | None:
        """Return the first expansion serial, when present."""
        return self._expansion_battery(2)[0]

    @property
    def expansion_battery_1_percentage(self) -> int | None:
        """Return the first expansion state of charge, when present."""
        return self._expansion_battery(2)[1]

    @property
    def expansion_battery_1_temperature(self) -> int | None:
        """Return the first expansion temperature, when present."""
        return self._expansion_battery(2)[2]

    @property
    def expansion_battery_2_serial_number(self) -> str | None:
        """Return the second expansion serial, when present."""
        return self._expansion_battery(3)[0]

    @property
    def expansion_battery_2_percentage(self) -> int | None:
        """Return the second expansion state of charge, when present."""
        return self._expansion_battery(3)[1]

    @property
    def expansion_battery_2_temperature(self) -> int | None:
        """Return the second expansion temperature, when present."""
        return self._expansion_battery(3)[2]

    @property
    def expansion_battery_3_serial_number(self) -> str | None:
        """Return the third expansion serial, when present."""
        return self._expansion_battery(4)[0]

    @property
    def expansion_battery_3_percentage(self) -> int | None:
        """Return the third expansion state of charge, when present."""
        return self._expansion_battery(4)[1]

    @property
    def expansion_battery_3_temperature(self) -> int | None:
        """Return the third expansion temperature, when present."""
        return self._expansion_battery(4)[2]

    @property
    def power_out(self) -> int:
        """Total Power Out.

        :returns: Total power out or default int value.
        """
        return round(self._parse_sb3_float("ad"))

    @property
    def power_in(self) -> int:
        """Return live battery charging power from verified field ``bc``."""
        return round(self._parse_sb3_float("bc"))

    @property
    def grid_to_home_power(self) -> int:
        """Grid to home power.

        :returns: Power from grid to home or default int value.
        """
        return self._parse_int("d5", begin=1)
