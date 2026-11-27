# Anker BLE protocol: deep documentation

A byte-level reference for the BLE protocol of Anker's SOLIX power stations, Solarbank, Prime chargers and Prime power banks. It goes below the [Protocols](../source/protocols.rst) page, which introduces the transports, packet layout, channels and advertisement record SolixBLE implements: this set gives the wire format, the negotiation and encryption state machine, the authorization policy, and each family's session commands and telemetry, with real frames decoded field by field.

Each statement names the products, firmware builds or app versions it was established on. Where families differ, the tables give each one; where nothing is known for a family, the table says "not identified" rather than assuming the common case.

## Files

| file | contents |
|---|---|
| [discovery-and-gatt.md](discovery-and-gatt.md) | transport families and their GATT UUIDs, the advertisement record, `productType` values, the GATT table, write type, MTU and fragmentation |
| [framing.md](framing.md) | the `ff09` frame: pattern and channels, cmd and msgtype, status byte, TLV payloads, the routing marker, MQTT |
| [negotiation.md](negotiation.md) | the negotiation generations, which product runs which, the static key, ECDH, legacy confer, worked examples, field reference |
| [authorization.md](authorization.md) | `auth_mode`, `0027` and the button grant, the authorize timer, the forwarding gate, per-build enforcement, binding, a client checklist |
| [c-series.md](c-series.md) | the C-series power stations: status, `c421` / `c490` telemetry, control |
| [prime.md](prime.md) | the Prime chargers, charging station and power banks: snapshot, realtime stream, setters, pushes, OTA |
| [f-series.md](f-series.md) | the F-series power stations (F1200, F2000, F2600, F3800): commands, telemetry, F3800 expansion and power-panel frames |
| [solarbank.md](solarbank.md) | Solarbank 1, 2 and 3, the smart plug and the smart meter: commands, telemetry, usage modes |
| [other-devices.md](other-devices.md) | the V1 smart EV charger, the X1 home energy system (attribute ids and JSON, not TLV) and the EverFrost coolers (names only) |

## Architecture

Most of these products split the work between two chips:

- **A comms chip** handles BLE, the negotiation and encryption, authorization, WiFi provisioning, the cloud link and its own OTA. On the C-series, the S2000, Solarbank 2, the A2345 and the A91B2 it is an ESP32 (`0829 a2` = `"ESP32"`) running Anker's module firmware, an ESP32-C3 on the C-series Gen 2, A2345 and A91B2; on the A1340 power bank it is a Telink TLSR8253; the A2687 reports a different chip (`"Charging"`, v0.0.5.0).
- **The device controller** (an MCU) owns telemetry and control. The comms chip forwards it every session frame with an opcode ≥ `0x40` and relays its replies and pushes back.

Both speak the same `ff09` frames to each other over UART, and the cloud carries the same frames over MQTT.

## Products and firmware

| product | model | comms firmware | controller firmware |
|---|---|---|---|
| SOLIX C2000 Gen 2 | A1783 | ESP32-C3 module v0.3.0.6, v0.3.3.0 | v1.2.1.1, v1.2.1.6 |
| SOLIX C1000 Gen 2 | A1763 | the A1783's controller build | |
| SOLIX C1000 | A1761 | ESP32 module v0.2.3.1 | v1.5.9 |
| SOLIX C300 | A1722 | ESP32 module v0.2.9.8 | v1.0.5.7 |
| SOLIX S2000 | AS220 | ESP32 module v0.3.3.0 | v1.0.2.9 |
| SOLIX F3800 / F3800 Plus | A1790 / A1790P | not identified | not identified |
| Solarbank 2 E1600 Pro | A17C1 | ESP32 module | not identified |
| Prime Charger 250 W | A2345 | ESP32-C3 module v0.2.3.3 (2024), v0.2.8.8, v0.2.9.7 | v2.1.1.6 |
| Prime Charging Station 240 W | A91B2 | ESP32-C3 module v0.2.9.7 | v1.1.2.0, v1.1.2.4 |
| Prime Charger 160 W | A2687 | `"Charging"` v0.0.5.0 | not identified |
| Prime Power Bank 27 650 mAh | A1340 | TLSR8253 1.6.1, 1.6.2 | GD32F303 1.6.1, 1.6.2 |
| 767 PowerHouse / F2000 | A1780 | legacy `1780` transport | |

## Conventions

- Hex bytes are written in wire order; multi-byte integers are little-endian unless stated.
- `→` is client to device, `←` device to client.
- An opcode is written with its link-flag nibble as it appears on the wire (`4100`, `c900`); the message it names is the msgtype without the flags ([framing.md](framing.md)).
- Field names: app names are Anker's own (from the app's parser and logs); `anker-solix-api` names are that library's; SolixBLE names are SolixBLE's. Each is cited as such.

Placeholders used throughout:

| item | placeholder |
|---|---|
| serials | `APCDKKE0000000001` (A1783, 17 B), `APCDK960000000001` (A1763), `APCDKJM0000000001` (C-series Gen 2 expansion battery), `APC9FE0000000001` (A1761), `AZVSBJ0000000001` (A1722), `ASHQJB0000000001` (A2345, 16 B), `AFYJTB0000000001` (A91B2, 16 B), `ASHDJV00000000001` (A2687, 17 B), `AZV3NM0000000001` (A1781), `APCGQ80000000001` (A17C1) |
| MACs | `aabbccddee01` (A1783), `aabbccddee02` (A2345), `aabbccddee03` (A91B2), `aabbccddee04` (A1340), `aabbccddee05` (A2687) |
| timestamps | `00b95569` (u32 LE, 1767225600); millisecond transaction ids `1767225600000` |
| account and owner ids | 40 ASCII `0`s |
| session keys, ECDH points and secrets | `<…>` |
