# Anker Prime chargers, charging station and power bank

The Prime chargers and charging station share one session protocol: a snapshot request `0200` answered by `0a00`, a realtime trigger `020b` that buys a burst of `0303` pushes, `02xx` setters and `03xx` pushes. The A1340 Prime Power Bank uses a different command set on channel `0x11`. Discovery and GATT are in [discovery-and-gatt.md](discovery-and-gatt.md), framing in [framing.md](framing.md), negotiation in [negotiation.md](negotiation.md) and authorization in [authorization.md](authorization.md); this file starts where a session is authorized.

Each claim names the models or builds it holds for. Placeholders are those in [README.md](README.md); this file adds the A2687 serial `ASHDJV00000000001` (17 B) and MAC `aabbccddee05`. Every `fe` epoch below is `00b95569`.

## Models

| | A2345 | A91B2 | A2687 | A1340 |
|---|---|---|---|---|
| product | Prime Charger 250 W | Prime Charging Station 240 W | Prime Charger 160 W | Prime Power Bank 27 650 mAh, 250 W |
| productType | `b402` | `b401` | `b405` | — |
| advertised capability | `04` | `00` | — | `04` |
| advertised service / GATT family | `ff09` / `8c85` | `ff09` / `8c85` | `ff09` / `8c85` | `2215` / `2215` |
| comms chip | ESP32-C3 module | ESP32-class module | `"Charging"` chip | Telink TLSR8253 |
| device firmware | v2.1.1.6 (`a2` = 2116) | v1.1.2.0, v1.1.2.4 (`a2` = 1124) | — | 1.6.1, 1.6.2 |
| module firmware | v0.2.9.7 | Prime v0.2.x line (v0.2.9.7) | v0.0.5.0 | — |
| session (app) | GCM | CBC | GCM | — |
| `auth_mode` | 2 (`4027` + button) | 0 (no `4027`) | — | — |
| replies and pushes on | `03010f` | `03010f` | `030111` | channel `0x11` |
| ports | USB-C 1–4, USB-A 1–2 | AC 1–2, USB-C 1–4, USB-A 1–2 (no USB-A relay) | USB-C 1–3 | USB-C 1–2, USB-A |
| snapshot | `ca00` fragments → `4a00` | one `4a00` frame | one `4a00` frame (193 B) | `0500` → 158 B |

productType values for the other Prime models are in [discovery-and-gatt.md](discovery-and-gatt.md) "productType".

## Session frames (A2345, A91B2, A2687)

- Pattern `03000f`; payload `a1 01 21 <fields> fe 05 03 <u32 LE epoch>`.
- Command id: `cmd = 0x4000 | request id` (the app's `02XX` → BLE `42XX`). On BLE requests carry flag `0x40` (`42xx`), replies `4axx`, pushes `43xx`, plus `0x80` when fragmented (`ca00`). MQTT carries the same ids with neither flag (`02xx`, `0axx`, `03xx`) and `a1 22`, so one parser serves both.
- TLV entries are `tag, length, type, value`; type `01` u8, `02` u16, `03` 4 bytes, `04` raw. Byte offsets `x[n]` below count from the first byte after the type byte.
- Ack: `<status> a1 01 31`: `00` applied, `04` rejected (valid opcode, wrong payload or mode). The reply marker is `0x30 |` the request marker's low nibble, so a BLE `a1 21` gets `31` and an MQTT `a1 22` gets `34` (`32` is sent as `34`).
- **Port block** (A2345, A91B2, A2687): `08 04 <status u8> <V u16 mV> <I u16 mA> <P u16 cW>`. On a loaded port V × I / 10 000 ≈ P. An unloaded port reads a floor of I 20 mA whatever its state (status 0 ports show it too), so a live but idle port can read V 19 776, I 20, P 10, where the product doesn't hold.
- Opcode meanings are per device: `4201` factory-resets the A2345 (it acks `00 a1 01 31`, drops the link, and wipes pairing and settings) but is a harmless display flag on the A91B2. Never send `4201` to an A2345.
- anker-solix-api maps the A91B2 with the A2345's `0a00` / `0303` maps; the A91B2's layout differs (below), so decode it with the A91B2 tables.

### Realtime trigger `420b` (A2345, A91B2)

A `420b` buys exactly 10 `4303` pushes, about 1 s apart (about 10 s); the payload is ignored and the count is fixed. The app re-sends it every 9 s. The A2345 holds the burst back while an OTA is armed. Payloads seen: A2345 `a2 0a 04 010003150101000000` (ignored), A91B2 none (`a1 01 21 fe 05 03 <ts>`). The C-series counterpart is `4057`.

### Daily window `0072` / `005d` (A2345, A91B2)

`a2` enable, `a3` / `a4` = window start / end in minutes of day (u32). The device picks a random minute inside the window (−1 when off) and, once its clock is set and 60 s have passed since the last `420b`, reports to its module at that minute once a day. The A2345 acks before parsing, so an MQTT-sourced request always gets `0872` `00 a1 01 34`. The cloud sends `0072` to the A2345 as an MQTT pass-through frame; the app never does.

### `0300` stats push (A2345, A91B2)

Every 10 min, on MQTT `state_info`, only while the cloud link is up:

```
a1 01 32                                   marker (MQTT)
a2 0e 04 | 0b | bc07 0a00 0000 0a00 0000 0000
           active-port bitmap 0b = ports 1, 2, 4
           6 × u16 LE port power, 0.1 W: 198.0, 1.0, 0, 1.0, 0, 0
a3 03 02 d007                              total 200.0 W (0.1 W)
a4 02 01 00                                s8 UTC offset, hours (0 here)
fe 05 03 00b95569                          RTC epoch
```

The module adds a JSON status `{version, battery, rssi, ssid, bssid, ip}` on the same topic.

## A2345

### Snapshot `4a00` (`ca00` fragments on BLE, `0a00` on MQTT)

Request `4200` (`a1 01 21 fe 05 03 <ts>`).

| tag | value bytes | content | setter / report |
|---|---|---|---|
| `a2` | u16 | firmware version, digit-packed: `n` → `v{n//1000}.{n//100%10}.{n//10%10}.{n%10}` (2116 → v2.1.1.6) | — |
| `a3` | u16 | port fault bitmap (bits below) | push `4304` |
| `a4`–`a7` | 7 | USB-C 1–4 port block | — |
| `a8`–`a9` | 7 | USB-A 1–2 port block | — |
| `aa`–`ae` | 19 | per port (USB-C 1–4, USB-A): schedule, countdown, priority (below) | `4208`, `4209`, `420c` |
| `af` | 5 | `af[0]` = theme index `& 0x3f` (0–2 preset, 3 network, 5 custom) \| `0x80` clock on \| `0x40` holiday; then theme id u32 | `4205`; report `430b` |
| `b0` | 1 | screen timeout: 0 always, 1 30 s, 2 1 min, 3 5 min, 4 30 min | `4203`; report `4309` |
| `b1` | 1 | charging mode 1–4 (below) | `4206`; report `430d` |
| `b2` | 2 | `[0]` OTA busy (1 while an upgrade is armed; holds back `4303`), `[1]` OTA progress % | — |
| `b3` | 1 | brightness 0–100 % | `4204`; report `430a` |
| `b4` | 1 | knob direction: 0 forward, 1 backward | `420e`; report `4310` |
| `b5` | 1 | clock: 0 12 h, 1 24 h | `4210` |
| `b6` | 1 | constant `01` | — |
| `b7` | 2 | `ff`, then 6 when the USB-PD controllers report PD revision ≥ 4 (device identity supported), else 2; v1.9.0.4 sent `ff 00` | — |
| `b8` | 7 | custom charge profile: profile number, auto-exit switch, per-port power limits | `4206 a2=5 a3` |
| `b9` | 5 | screensaver active hours `[startH, startM, endH, endM, weekmask]` | `4213` |
| `ba` | 12 | 4 × `{custom USB protocol set, 0, 0}` | — |
| `bb` | 1 | compatibility switch | `4214` |
| `bc` | 1 | constant `01` | — |
| `bd` | 16 | 4 × `{u16 VID, u16 PID}` per USB-C port: the connected device's USB-PD Discover Identity; `{fffa, fffb}` no device, `{0, 0}` identity not read | — |
| `be` | 16 | 4 × `{u16 class, u16 code}` per USB-C port: the device identity resolved from `bd` (below); `ffff` none | — |
| `bf` | 1 | device-identification switch | `4223` |
| `fe` | u32 | RTC epoch | — |

The wire order puts `bf` before `bd`.

| `a3` bit | source |
|---|---|
| 0 | over-temperature: either of two NTCs above 125 °C for 60 passes, held until both are below 95 °C (a first stage at 88 °C clears below 78 °C) |
| 1–4 | USB-C 1–4 fault from the port's PD controller, on after 5 non-zero reads, off after 10 zero reads |
| 5 | either USB-A port's fault |

Worked frame (v2.1.1.6, reassembled from `ca00`):

```
00a10131a203024408a303020000a4080400000014000000a5080401404d14000a00a6080401801314000a00a7080400000014000000
a8080400000000000000a9080400000000000000aa140401ff0c0000ff0c000000580200000000000000ab140401ff0c0000ff0c0000
00580200000000000000ac140401ff0c0000ff0c000000580200000000000000ad140401ff0c0000ff0c000000580200000000000000
ae140401ff0c0000ff0c000000580200000000000000af060483d4f89e1db0020102b1020101b203040000b302013cb4020100b50201
01b6020101b70302ff02b80804010046412d2d18b90604000000007fba0d043b00003b00003b00003b0000bb020101bc020101bf0201
01bd1104fafffbffb40465f600000000fafffbffbe1104fffffffffffffffffffffffffffffffffe050300b95569

00 a1 01 31                          status 00, marker 31 (BLE)
a2 03 02 44 08                       version 2116 = v2.1.1.6
a3 03 02 00 00                       fault bitmap 0
a4 08 04 00 00 00 14 00 00 00        USB-C 1: status 0, V 0, I 20, P 0
a5 08 04 01 40 4d 14 00 0a 00        USB-C 2: status 1, V 19 776 mV, I 20 mA, P 10 cW
a6 08 04 01 80 13 14 00 0a 00        USB-C 3: status 1, V 4 992 mV, I 20 mA, P 10 cW
a7 08 04 00 00 00 14 00 00 00        USB-C 4: status 0
a8 / a9 08 04 00 00 00 00 00 00 00   USB-A 1 / 2: idle
aa … ae 14 04 01 ff 0c 00 00 ff 0c 00 00 00 58 02 00 00 00 00 00 00 00
                                     every port: switch on, no schedule, countdown off (600 s set, 0 left), priority unset
af 06 04 83 d4 f8 9e 1d              clock on, network theme (index 3), theme id 496957652
b0 02 01 02                          screen timeout 1 min
b1 02 01 01                          charging mode 1 (AI Power)
b2 03 04 00 00                       no OTA
b3 02 01 3c                          brightness 60 %
b4 02 01 00                          knob forward
b5 02 01 01                          24 h clock
b6 02 01 01                          constant
b7 03 02 ff 02                       PD revision < 4 on every port
b8 08 04 01 00 46 41 2d 2d 18        custom charge profile
b9 06 04 00 00 00 00 7f              screensaver hours 00:00–00:00, every day
ba 0d 04 3b 00 00 ×4                 custom USB protocol set 0x3b on each USB-C
bb 02 01 01                          compatibility switch on
bc 02 01 01                          constant
bf 02 01 01                          device identification on
bd 11 04 fa ff fb ff  b4 04 65 f6  00 00 00 00  fa ff fb ff
                                     C1 no device, C2 VID 04b4 PID f665, C3 not read, C4 no device
be 11 04 ff ff ff ff ×4              no identity resolved
fe 05 03 00 b9 55 69                 RTC epoch
```

**Per-port block `aa`–`ae`:**

| offset | field | notes |
|---|---|---|
| `[0]` | switch | 0 off, 1 on |
| `[1]` / `[5]` | on-time / off-time enable | 0 / 1; `ff` = never set |
| `[2]` `[3]` / `[6]` `[7]` | on-time / off-time hour, minute | |
| `[4]` / `[8]` | on-time / off-time weekdays | bit 0 Mon … bit 6 Sun (`1f` Mon–Fri, `7f` all) |
| `[9]` | countdown enable | |
| `[10:14]` | countdown seconds, u32 LE | |
| `[14:18]` | countdown remaining, u32 LE | |
| `[18]` | priority | `00` unset (outside Port Priority mode), `01` normal, `02` designated |

An unset schedule half keeps `0c 00` (12:00) behind its `ff`, and a disarmed countdown keeps its 600 s default, so gate on the enable bytes, not the values.

### Device identity (`bd` / `be`)

Each USB-C port reports the connected device's USB-PD Discover Identity VID and PID in `bd`, read while the port is active. The charger resolves them into `be` `{class, code}`: the class from the VID, the code from the PID, and a display name from a built-in table. `be` is filled whether or not the cloud identity setting is on, and a port drawing power can still read `{ffff, ffff}`.

| class | vendor | VID |
|---|---|---|
| 1 | Apple | `05ac` |
| 2 | Samsung | `04e8` |
| 3 | Xiaomi | `2717` |
| 4 | Huawei | `12d1` |
| 10 | Anker | `291a` |
| 11 | — | `339b` |
| 12 | HP | `03f0` |
| 13 | Dell | `413c` |
| 14 | Lenovo | `17ef` |
| 15 | Microsoft | `045e` |
| 16 | — | `2a7e` |
| 17 | ASUS | `0b05` |
| 18 | MSI | `0db0` |
| 19 | Razer | `1532` |

Example: `bd` C1 `{05ac, 7311}`, C2 `{05ac, 7117}` → `be` C1 `{1, ffff}`, C2 `{1, 0036}` = Apple "iPad Pro M4".

Named records (class, code → name; * = the stored name ends in a space). Class 10 holds the Anker Prime products themselves; the app shows the same names as its accessory device-type labels.

| class | code | name |
|---|---|---|
| 1 | 1 | iPhone 12 * |
| 1 | 2 | iPhone 12 mini |
| 1 | 3 | iPhone 12 |
| 1 | 4 | iPhone 12 Pro |
| 1 | 5 | iPhone 12 Pro Max |
| 1 | 6 | iPhone SE 3 |
| 1 | 7 | iPhone 13 * |
| 1 | 8 | iPhone 13 mini |
| 1 | 9 | iPhone 13 |
| 1 | 10 | iPhone 13 Pro |
| 1 | 11 | iPhone 13 Pro Max |
| 1 | 12 | iPhone 14 * |
| 1 | 13 | iPhone 14 |
| 1 | 14 | iPhone 14 Pro |
| 1 | 15 | iPhone 14 Plus |
| 1 | 16 | iPhone 14 Pro Max |
| 1 | 17 | iPhone 15 |
| 1 | 18 | iPhone 15 Plus |
| 1 | 19 | iPhone 15 Pro |
| 1 | 20 | iPhone 15 Pro Max |
| 1 | 21 | iPhone 16 * |
| 1 | 22 | iPhone 16 |
| 1 | 23 | iPhone 16 Plus |
| 1 | 24 | iPhone 16E |
| 1 | 25 | iPhone 16 * |
| 1 | 26 | iPhone 16 Pro |
| 1 | 27 | iPhone 16 Pro Max |
| 1 | 28 | iPhone 17 * |
| 1 | 29 | iPhone 17 |
| 1 | 30 | iPhone Air |
| 1 | 31 | iPhone 17 * |
| 1 | 32 | iPhone 17 Pro |
| 1 | 33 | iPhone 17 Pro Max |
| 1 | 34 | iPad 9 (2021) |
| 1 | 35 | iPad 10 (2022) |
| 1 | 36 | iPad 11 (2025) |
| 1 | 37 | iPad Air 4 (2020) |
| 1 | 38 | iPad Air 5 (2022) |
| 1 | 39 | iPad Air 11" (2024) |
| 1 | 40 | iPad Air 13" (2024) |
| 1 | 41 | iPad Air 11" (2025) |
| 1 | 42 | iPad Air 13" (2025) |
| 1 | 43 | iPad mini 6 (2021) |
| 1 | 44 | iPad mini 7 (2024) |
| 1 | 45 | iPad Pro 2020 * |
| 1 | 46 | iPad Pro 11" (2020) |
| 1 | 47 | iPad Pro 12.9" (2020) |
| 1 | 48 | iPad Pro M1 * |
| 1 | 49 | iPad Pro 11" M1 |
| 1 | 50 | iPad Pro 12.9" M1 |
| 1 | 51 | iPad Pro M2 * |
| 1 | 52 | iPad Pro 11" M2 |
| 1 | 53 | iPad Pro 12.9" M2 |
| 1 | 54 | iPad Pro M4 * |
| 1 | 55 | iPad Pro 11" M4 |
| 1 | 56 | iPad Pro 13" M4 |
| 1 | 57 | iPad Pro M5 * |
| 1 | 58 | iPad Pro 11" M5 |
| 1 | 59 | iPad Pro 13" M5 |
| 1 | 60 | MacBook Air 13" (2020) |
| 1 | 61 | MacBook Air 13" M1 |
| 1 | 62 | MacBook Pro 13.4" (2020) |
| 1 | 63 | MacBook Pro 13.4" M1 |
| 1 | 64 | MacBook Air 13" M2 |
| 1 | 65 | MacBook Air 13" M3 |
| 1 | 66 | MacBook Air 13" M4 |
| 1 | 67 | MacBook Air 15" (2023) |
| 1 | 68 | MacBook Air 15" M3 |
| 1 | 69 | MacBook Air 15" M4 |
| 1 | 70 | MacBook Pro 13" M2 |
| 1 | 71 | MacBook Pro 14" M1 Pro |
| 1 | 72 | MacBook Pro 14" M2 Pro |
| 1 | 73 | MacBook Pro 14" M3 |
| 1 | 74 | MacBook Pro 14" 2024 * |
| 1 | 75 | MacBook Pro 14" M4 Pro |
| 1 | 76 | MacBook Pro 14" M4 Max |
| 1 | 77 | MacBook Pro 14" M5 |
| 1 | 78 | MacBook Pro 16" M1 Max |
| 1 | 79 | MacBook Pro 16" M2 Pro |
| 1 | 80 | MacBook Pro 16" M3 Pro |
| 1 | 81 | MacBook Pro 16" 2024 * |
| 1 | 82 | MacBook Pro 16" M4 Pro |
| 1 | 83 | MacBook Pro 16" M4 Max |
| 1 | 84 | HomePod Mini |
| 10 | 1 | Power Bank 26K |
| 10 | 2 | Power Bank 20K |
| 10 | 3 | (empty) |
| 10 | 4 | Power Bank 5K |
| 10 | 5 | Power Bank 10K |
| 10 | 6 | Charging Base 150W |
| 10 | 7 | (empty) |
| 10 | 8 | Power Bank 27K |
| 10 | 9 | Wireless Charger 35W |
| 10 | 10 | Charger 160W |
| 10 | 11 | Charger 250W |
| 10 | 12 | Charging Station 240W |
| 10 | 13 | Power Bank 20K |
| 14 | 1 | ThinkBook 16 (2025) |
| 14 | 2 | ThinkPad X1Carbon (2025) |
| 14 | 3 | YOGA Air 14c |
| 14 | 4 | YOGA Pro 14s |
| 14 | 5 | YOGA Air 15s (2025) |

Classes 1, 10 and 14 are looked up in this table; other classes display as the vendor name followed by " ?".

### Realtime stream `4303`

During a `420b` burst: port blocks USB-C 1–4 at `a2`–`a5`, USB-A at `a6` / `a7`, `a8` = `bd`, `a9` = `be`, `fe`. Builds before v2.1.1.6 send no `a9`.

```
a10131a2080400000014000000a3080401384d14000a00a4080401801314000a00a5080400000014000000a6080400000000000000
a7080400000000000000a81104fafffbffb40465f600000000fafffbffa91104ffffffffffffffffffffffffffffffff fe050300b95569

a1 01 31                             marker
a2 08 04 00 00 00 14 00 00 00        USB-C 1 idle
a3 08 04 01 38 4d 14 00 0a 00        USB-C 2: on, 19 768 mV, 20 mA, 10 cW
a4 08 04 01 80 13 14 00 0a 00        USB-C 3: on, 4 992 mV, 20 mA, 10 cW
a5 08 04 00 00 00 14 00 00 00        USB-C 4 idle
a6 / a7                              USB-A 1 / 2 idle
a8 11 04 …                           bd, as in the snapshot
a9 11 04 ff ×16                      be: none
fe 05 03 00 b9 55 69
```

SolixBLE names the stream's fields `usb_port_c1` … `c4`, `usb_c1_voltage` / `_current` / `_power` …, and `usb_port_a1` / `a2` likewise.

### Setters and requests

All payloads follow `a1 01 21`; the reply is the `0x0800` response with `<status> a1 01 31`.

| cmd | app name | payload | effect |
|---|---|---|---|
| `4200` | `getAllDeviceInfo` | — | snapshot |
| `4201` | — | any | **factory reset** |
| `4202` | `getScreensaver` | — | `4a02`: `a2` = bit 7 clock on, bit 6 holiday (only with bit 7), low 6 bits theme index · `a3` theme id u32 · `a4` path / url · `a6` port-widgets flag · `fe` |
| `4203` | `setScreenTimeout` | `a2 02 01 <enum>` (as `b0`) | sets `b0` |
| `4204` | `setScreenBrightness` | `a2 02 01 <0–100>` | sets `b3` |
| `4205` | `setScreenSaverSwitchAndTheme` | `a2` = `0x80` \| theme index (bit 7 clear = clock off). Preset `80` / `81` / `82` + `a6` asset path; network `83` / custom `85` + `a3 05 03 <theme id>` `a4 05 03 <image crc32>` `a5 05 03 <text colour, ffffffff default>` + url in `a7` (else `a6`). The app fills an unused `a6` with the ASCII `1234567890123456` | downloads the image itself when not cached |
| `4206` | `setChargingMode` | `a2 02 01 <mode 1–4>`; mode 5 (custom) adds `a3 08 …` (7 B → `b8`) and `a4 0d …` (12 B, per-port 3-byte records) | every port renegotiates: all drop to 0 W for about 8 s. `a2 = 0` is acked and ignored |
| `4207` | `setDCRelaySwitch` | `a2 02 01 <index> a3 02 01 <0 / 1>`; each field exactly type + 1 byte, else `04` | port on / off: index 0–3 = USB-C 1–4, 4 = both USB-A outlets (one switch), the same index as `aa`–`ae`. An index ≥ 5 or a state ≥ 2 is acked and ignored. Reply `a2` index, `fe`. In custom mode 5 a port with a 0 W limit stays at the profile's setting |
| `4208` | (`setACPortTimedTaskRes`) | `a2 02 01 <port> a3 02 01 <1 on-time / 0 off-time> a4 05 03 <en><hour><min><weekmask>` | writes the on-time quad (`[1..4]`) or the off-time quad (`[5..8]`); answered `4a08`, then a `4308` push |
| `4209` | `setDCPortCountdownTask` | `a2 02 01 <port> a3 06 04 <en><u32 LE s>` (5 min = `2c010000`) | starts the port countdown |
| `420a` | (setter) | `a2 03 02 <2 ASCII country>` `a3 29 04 <owner, 40 B>` | stores country and owner (below) |
| `420b` | realtime trigger | ignored | 10 × `4303` |
| `420c` | — | `a2 02 01 <bitmask, bit 0 C1 … bit 3 C4>` | designates ports and enters Port Priority mode |
| `420d` | — | `a2` (any value) | display shows "Activate New Secret Features"; push `4305 a2=00` |
| `420e` | `setButtonRotateDirection` | `a2 02 01 <0 / 1>` | sets `b4`; reply `4a0e` |
| `420f` | — | `a2 02 01 <0 / 1>` | holiday switch; the app refuses to enable it over BLE |
| `4210` | `setTimeFormat` | `a2 02 01 <0 12 h / 1 24 h>` | sets `b5` |
| `4211` | `setCustomChargeModeSwitch` | `a2 02 01 <0 / 1>` | 0 restores the previous mode |
| `4212` | — | `a2` theme id u32, `a3` / `a4` u32, `a5` / `a6` 7-byte datetimes, `a7` url; `a2 = 0` clears | scheduled holiday theme |
| `4213` | — | `a2 06 04 <startH><startM><endH><endM><weekmask>` | screensaver window: inside it a timeout shows the screensaver, outside it the screen goes black |
| `4214` | (compatibility switch) | `a2 02 01 <0 / 1>` | sets `bb` |
| `4215`–`4217`, `4219`–`421f` | — | — | ignored (the cloud sends `421d a2 04 7a00×4`) |
| `4218` | — | — | `a2` 8 B: two status bytes per USB-C port |
| `4220` | `prepareSendScreensaver` | `a2 <kind: 0 JPEG / 2>` `a3 05 03 <theme id>` `a4 05 03 <crc32>` `a5 05 03 <size>` `a6 <window>` `a7 03 02 <chunk 192>` `a8 03 02 <count>` `a9 11 04 <url>` | opens the image upload |
| `4221` | `sendScreensaverData` | `a2 <u16 index> a3 <JPEG chunk>` | status `00` window ack, `10` done, `11` CRC error, `12` resend from index |
| `4222` | — | `a2 02 01 <0 / 1>` | shows or hides the per-port icons and values on the port display page; read back as `4202 a6` |
| `4223` | (device identification switch) | `a2 02 01 <0 / 1>` | sets `bf` |

**`420a`.** `a2` is a type byte plus two ASCII characters (uppercased; the type byte is ignored, so `03 02 'US'` and `03 04 'US'` are equal). `a3` is the owner: 40 bytes (the app's account id) or 36 (a UUID). Only a changed owner has effects: it raises an owner-change event, leaves custom charging mode, and resets the theme to preset; an identical re-send (the app sends it every 1–2 s) is acked and does nothing. A missing or short `a2`, or a bad `a3`, answers `04`.

**Other requests.**

| request | channel | payload | reply |
|---|---|---|---|
| `4030` | 0x0f | — | `4830`: `a1` module fw · `a2` device fw · `a3` model · `a4` `A2345_mcu` · `a5` `A2345_esp32` |
| `4023` | 0x01 | `a2` owner (required, else `04`), optional `a4` flag byte | `01` unless the device's bound check passes; changes no key and authorizes nothing |
| WiFi scan | 0x02 op `0x30`, or 0x0f / 0x13 op `0x22` | `a3` country | `a1 01 <n>`, the number of de-duplicated SSIDs seen |
| `4024` | 0x0f | `a1` ts · `a2` owner uid · `a3` SSID · `a4 00` · `a5 00` · `a6` password (no `fe`) | WiFi association only; the cloud bind is separate |

### Charging mode (`b1`)

| value | mode | behaviour |
|---|---|---|
| 1 | AI Power | identifies connected devices |
| 2 | Port Priority | up to two designated USB-C ports get precedence |
| 3 | Dual-Laptop | two laptops first, detected automatically; all priority bytes `00` |
| 4 | Low Current | reduced output |

- Push `430d` on every mode change: `a1 01 31 a2 02 01 <mode> a3 08 04 <b8 profile> a4 02 01 <designated-port bitmask> fe`.
- Entering Port Priority also pushes `430f`, whose `a3` is the designated-port bitmask (bit 0 C1 … bit 3 C4). Designating a port from the Dual-Laptop screen switches to mode 2. USB-A never takes part in priority.

| `430f a3` | priority bytes `aa`–`ad` | designated |
|---|---|---|
| `00` | `01 01 01 01` | none |
| `02` | `01 02 01 01` | C2 |
| `04` | `01 01 02 01` | C3 |
| `06` | `01 02 02 01` | C2 + C3 |
| `08` | `01 01 01 02` | C4 |
| `0c` | `01 01 02 02` | C3 + C4 |

### Pushes

| push | when | payload |
|---|---|---|
| `4300` | every 10 min (MQTT `state_info`) | "`0300` stats push", above |
| `4303` | during a `420b` burst | realtime stream (above) |
| `4304` | any plug / unplug | `a2 03 <u16 LE port bitmask>` `fe`; sent twice when cloud-bound (`a1 64`, then `44`) |
| `4305` | Secret Features | `a2` `00` prompt, `01` Feature Expert, `04` / `05` Expression |
| `4308` | after `4208` | the schedule record |
| `4309` / `430a` / `430b` / `4310` | a setting changed on the unit | screen reports: `a1 01 31 a2 02 01 <value> [a3 05 04 <field>] fe` for `b0` / `b3` / `af[0]` / `b4` |
| `430d` / `430f` | mode change | charging mode / designated ports |

Sending a `43xx` back is acked (`4b0a`) but not applied; the setters are the `42xx`. A cloud-bound unit's pushes carry `a1 64` / `44` (the cloud lanes) instead of `31`.

The A2345 also pushes `0312` on `state_info`, every 60 s while the holiday switch is on, the cloud link is up and a country is set: `a1 01 32 a2 03 04 <2 ASCII country> a3 05 03 <int32 LE UTC offset, hours> fe`.

**Markers.** A reply carries `0x30 |` the request's low nibble: BLE `21` → `31`, MQTT `22` → `34` (the snapshot answers MQTT with `64`). Pushes pick theirs from the link state: `31` with only BLE up; with the cloud link up `0300` / `0312` carry `32` (state topic), `4303` / `4306` `34`, `4304` is sent twice (`64`, then `44`), and the other pushes `64` (`param_info`). `0300`, `0306` and `0312` go out only with the cloud link up.

### Themes

| kind | `4205` | image delivery |
|---|---|---|
| preset | `a2` `80` / `81` / `82` (Theme 1 / 2 / 3), `a6` the app's asset path | built in |
| network | `a2` `83`, `a3` theme id, `a4` image CRC32 | `4205`, then `4220` and `4221` × count; the device can also fetch the url itself |
| custom | `a2` `85` | `4205`, `4220`, then `4221` × count (192-byte chunks, raw JPEG) |

Network theme ids: Celestial 948897111, Robotic 236632206, Lunar 938963984, Galactic 819158638, Meteorite 95294588, Floral Waltz 130254227, Rhythmic Hue 496957652 (image CRC32 `f9abd0b5`).

### Secret Features

| feature | kind | unlock | BLE signature |
|---|---|---|---|
| Feature 1 | Expression | main screen switched 20× in 10 s | `4305 a2=04` when shown |
| Feature 2 | Expression | the same USB-C port plugged 10× in 60 s | port status in `a4`–`a9`; `4305 a2=05` |
| Power Expert | Achievement | 3 high-power laptops at once | — |
| Feature Expert | Achievement | port priority toggled 10× | ten `430f`; `4305 a2=01` on unlock |
| Device Expert | Achievement | all six ports in use | — |

The counters live on the device. No charging-mode change sends `4305`.

### BLE OTA

| op | app | payload / reply |
|---|---|---|
| `4263` | begin | `a2` u32 total length, `a3` u8 window, `a4` u16 chunk size, `a5` u16 chunk count |
| `4264` | chunk | `a2` u16 sequence, `a3` data; reply `<status> a1 01 31 a2 03 02 <seq>`: `00` window ack, `12` resend from seq, `10` done and verified, `11` image CRC mismatch |
| `4265` | capabilities | reply `a3` `0x800`, `a4` 250, `a5` `0x832` (each u32) |
| `4266` | read back | `a2` index → `a2` index, `a3` u16 250, `a4` 250 bytes of the staged image |
| `4267` | state | `a2` 1 armed, `0x61` apply; the app also sends it for the on-screen progress |

- The chunk size is the client's (the app uses 200); `4265` reports the 250-byte ceiling.
- A sequence that doesn't match is answered `12` at a window boundary and dropped elsewhere. Each full window is written to flash and acked `00`.
- After the first window the device checks the 256-byte image header (`Anker` / `A2345` / `V1` magic, payload length at +0x34, CRC32 at +0x38) and strips it. Only when the chunk count reaches `4263 a5` does it compare the image CRC32: `10` and apply on a match, `11` otherwise.
- Example: a 461 280-byte image, window 10, chunk 200 → 2 307 chunks (`4263` `a2 e0090700 a3 0a a4 c800 a5 0309`).

## A91B2

### Snapshot `4a00` (one frame on BLE, `0a00` on MQTT)

| tag | value bytes | content |
|---|---|---|
| `a2` | u16 | firmware version, digit-packed (1124 → v1.1.2.4) |
| `a3` | u16 | port fault bitmap (bits below) |
| `a4`–`a7` | 7 | USB-C 1–4 port block |
| `a8`–`a9` | 7 | USB-A 1–2 port block |
| `aa`–`ab` | 18 | AC 1–2: switch · on-time `{en (ff unset), hh, mm, mask}` · off-time (same) · countdown enable · set u32 LE · remaining u32 LE |
| `ac` | 1 | bit 7 clock display; bits 6:0 theme index |
| `ad` | 1 | high nibble brightness, low nibble screen timeout (same enum as the A2345's `b0`) |
| `ae` | 2 | charging mode `<byte0><byte1>` |
| `af` | 2 | `[0]` OTA busy (holds back `4303`), `[1]` OTA progress % |
| `b0`–`b3` | 18 | USB-C 1–4 schedule / countdown, same record as `aa` |
| `b4` | 1 | clock format: 1 24 h, 0 12 h |
| `b5` | 1 | AC LED: 0 Normal, 1 Sleep |
| `fe` | u32 | RTC epoch |

| `a3` bit | source |
|---|---|
| 0 | NTC over-temperature: set when the 8-sample average reaches 117 °C, cleared at 75 °C |
| 1–4 | USB-C 1–4 PD-controller fault, latched after 2 non-zero reads, cleared after 5 zero reads |
| 5 | a USB-A rail below 4.0 V for 20 passes |

The A91B2 resets itself when its input voltage averages below 25.0 V on four consecutive checks.

Worked frame (v1.1.2.4):

```
00a10131a203026404a303020000a4080400000000000000a5080400000000000000a6080400000000000000a70804019813db006900
a8080400e11303000000a9080400e11300000000aa130401ff0c0000ff0c000000302a0000302a0000ab130401ff0c0000ff0c000000
5802000058020000ac020181ad020100ae03040000af03040000b01304010001007f00170004005802000000000000b1130401ff0c00
00ff0c000000100e000000000000b2130401ff0c0000ff0c000000201c000000000000b3130401ff0c0000ff0c000000580200000000
0000b4020101b5020100fe050300b95569

00 a1 01 31                          status 00, marker 31
a2 03 02 64 04                       version 1124 = v1.1.2.4
a3 03 02 00 00                       fault bitmap 0
a4 / a5 / a6 08 04 00 …              USB-C 1–3 idle
a7 08 04 01 98 13 db 00 69 00        USB-C 4: on, 5 016 mV, 219 mA, 105 cW
a8 08 04 00 e1 13 03 00 00 00        USB-A 1: 5 089 mV, 3 mA, 0 cW
a9 08 04 00 e1 13 00 00 00 00        USB-A 2: 5 089 mV, idle
aa 13 04 01 | ff 0c 00 00 | ff 0c 00 00 | 00 | 30 2a 00 00 | 30 2a 00 00
                                     AC 1: on, no schedule, countdown off, set 10 800 s, remaining 10 800 s
ab 13 04 01 | ff 0c 00 00 | ff 0c 00 00 | 00 | 58 02 00 00 | 58 02 00 00
                                     AC 2: on, no schedule, countdown off, 600 s
ac 02 01 81                          clock display on, theme 1
ad 02 01 00                          brightness 0, timeout always on
ae 03 04 00 00                       charging mode Smart Dynamic
af 03 04 00 00                       no OTA
b0 13 04 01 | 00 01 00 7f | 00 17 00 04 | 00 | 58 02 00 00 | 00 00 00 00
                                     USB-C 1: on; on-time disabled 01:00 daily; off-time disabled 23:00 Wed; countdown off
b1 … 10 0e 00 00 | 00 00 00 00       USB-C 2: countdown set 3 600 s, off
b2 … 20 1c 00 00 | 00 00 00 00       USB-C 3: countdown set 7 200 s, off
b3 … 58 02 00 00 | 00 00 00 00       USB-C 4: countdown set 600 s, off
b4 02 01 01                          24 h clock
b5 02 01 00                          AC LED normal
fe 05 03 00 b9 55 69                 RTC epoch
```

A disarmed countdown keeps its `set` and `remaining`; gate on the enable byte.

### Realtime stream `4303`

USB-C 1–4 at `a2`–`a5`, USB-A at `a6` / `a7`:

```
a10131a2080400000000000000a3080400000000000000a4080400000000000000a508040198138a004100a6080400e11303000000
a7080400e11300000000fe050300b95569

a2 / a3 / a4                         USB-C 1–3 idle
a5 08 04 01 98 13 8a 00 41 00        USB-C 4: on, 5 016 mV, 138 mA, 65 cW
a6 08 04 00 e1 13 03 00 00 00        USB-A 1
a7 08 04 00 e1 13 00 00 00 00        USB-A 2
```

### Setters and requests

| cmd | payload | effect |
|---|---|---|
| `4200` | — | snapshot |
| `4201` | — | display flag; harmless |
| `4202` | — | `a2` = flag << 7 \| level, `fe` |
| `4203` | `a2` 0 always / 1 30 s / 2 1 min / 3 5 min / 4 30 min | `ad` low nibble |
| `4204` | `a2` (u8) | `ad` high nibble, brightness; the app offers 0–2 and the device doesn't clamp |
| `4205` | `a2` = bit 7 clock display on \| low nibble theme 0 / 1 / 2 | `ac` |
| `4206` | `a2 03 02 <byte0><byte1>`: byte0 0 Smart Dynamic / 1 High-Power; byte1 sub-mode 0 / 1 / 2 when byte0 = 1 | `ae`; the type byte isn't checked, so `a2 03 03 …` applies the same mode |
| `4207` | `a2` port (0 AC 1, 1 AC 2, 2–5 USB-C 1–4), `a3` 0 / 1 | output on / off; reply `a1 a2 fe`; push `4302`. USB-A has no relay |
| `4208` | `a2` port, `a3` 1 on-time / 0 off-time, `a4 05 03 <en><hour><min><days>` (bit 0 Mon … bit 6 Sun; `7f` daily, `00` once) | schedule; a colliding other slot is disabled and pushed as `4308` |
| `4209` | `a2` port, `a3 06 04 <en><u32 LE s>` | countdown; `en = 0` disarms and keeps the seconds; push `4307` |
| `420a` | — | display page |
| `420b` | `a1 01 21 fe 05 03 <ts>` | 10 × `4303` |
| `4210` | `a2` 1 24 h / 0 12 h | `b4` |
| `4214` | `a2` 0 Normal / 1 Sleep | `b5`, the AC LED (`setAcLightMode`) |
| `4218` | — | `a2` 8 B: two status bytes per USB-C port |
| `421b` | `a2 05 04 <u32 total length>` | OTA begin: chunks = ceil(length / 128) |
| `421c` | `a2 <u16 index> a3 <128-byte chunk>` | OTA chunk. Chunk 0 is the header (expected CRC32 at +0x39), chunk 1 is acked and skipped, chunks ≥ 2 are written and verified; after the last chunk, a matching CRC32 installs the image and resets the device. A missing `a2` answers `01`, a wrong index or failed read-back is NACKed, and every accepted chunk is ACKed, the last one included, so a CRC32 mismatch is acked and the image is simply not installed |
| `420c`–`420f`, `4211`–`4213`, `4215`–`4217`, `4219`, `421a` | — | ignored, no reply |

### Pushes

| push | payload |
|---|---|
| `4302` | output state after `4207`: `a2` port, `a3` state |
| `4303` | port blocks during a `420b` burst |
| `4304` | port fault bitmap on change: `a2` u16 (the snapshot's `a3`), `fe`; sent again with marker `44` when cloud-bound |
| `4306` | OTA progress: `a2` kind, `a3` percent |
| `4307` | countdown state: `a2` port, `a3` 10 bytes `{en u8, set u32 LE, remaining u32 LE}` |
| `4308` | a schedule slot the device has just disabled: `a2` port, `a3` slot (1 on-time, 0 off-time), `a4 05 04 <en 00><hour><min><days>` = that slot's stored record. Sent after a `4208` that collides with the other slot of the same port (both enabled, the unset `ff` counting as enabled, at the same hour:minute with overlapping days: the other slot is disabled), and when a once slot fires or its date has passed. Repeating slots switch with no push |

`4308` example: request `4208` `a1 01 21 · a2 02 01 02 · a3 02 01 01 · a4 05 03 01 0c 00 00` (port 2, on-time, enabled, 12:00, once) → push `4308` `a1 01 31 · a2 02 01 02 · a3 02 01 00 · a4 05 04 00 0c 00 00 · fe 05 03 00b95569` (port 2, off-time slot, disabled, 12:00, once).

The `0300` stats push has the A2345's layout:

```
a1 01 32
a2 0e 04 | 04 | 0000 0000 c800 0000 0000 0000   bitmap 04 = port 3; port 3 = 20.0 W
a3 03 02 c800                                    total 20.0 W
a4 02 01 00                                      UTC offset, hours
fe 05 03 00b95569                                RTC epoch
```

### Session

- The app runs cleartext ECDH and an AES-128-CBC session (`key = ss[:16]`, `iv = ss[16:32]`, PKCS7). Session frames are single-packet (the largest, `4a00`, is 250 bytes).
- The unit runs `auth_mode 0`: `0027` disconnects it. It authorizes at `0821` on the cleartext outer, or through the legacy confer on either outer ([authorization.md](authorization.md)).
- The bind is `4023` with `a2 28 <account>` and `a3 10 <serial>` → `00 a1 10 <serial>`; without `a2` it answers `04`, and the unit streams either way.
- The MCU does no session cryptography; the comms module decrypts and relays cleartext.

## A2687

Prime Charger 160 W, three USB-C ports. Advert name `Charging`; serials start `ASHD`. Its comms chip identifies itself as `"Charging"` v0.0.5.0 in `0829`, not as the ESP32 module ([negotiation.md](negotiation.md) "Device answers by family"):

```
0803 ←  00 | a1 01 02 | a2 02 2901 | a3 01 44 | a4 01 01 | a5 01 02     MTU 297, ECDH capable, authMethod 2
0829 ←  00 | a1 01 03 | a2 08 "Charging" | a3 08 "v0.0.5.0" | a4 11 "ASHDJV00000000001" | a5 11 aabbccddee05 "00000000001"
           a5 = the 6-byte MAC followed by the serial's last 11 characters
```

The app negotiates encrypted ECDH (GCM session); a client on the cleartext outer completes the negotiation too and gets `4a00`.

### Session

- Requests on `03000f`; every reply and push on `030111` (channel `0x11`).
- Acks `00 a1 01 31`, as on the A2345 (seen for `4205`, `4206`, `4207`, `420a`).
- The device pushes `4300`.

| cmd | payload | effect |
|---|---|---|
| `4200` | `a1 01 21 fe 05 03 <ts>` | `4a00`, 193 B (below) |
| `4205` / `4206` | not captured | ack |
| `4207` | `a2 02 01 <port 0–2 = USB-C 1–3> a3 02 01 <0 / 1>` | port on / off (SolixBLE `turn_usb_c1_on` …) |
| `4209` | `a2 02 01 <port> a3 05 04 <u32 LE s>` | port timer (SolixBLE `set_timer_usb_c1` …); SolixBLE sends no enable byte, unlike the A2345's `a3 06 04 <en><u32>` |
| `420a` | a 40-character account token | `4a0a` = `00 a1 01 31 a2 02 01 00 fe 05 03 00000000` |

### Snapshot `4a00`

All three ports charging:

```
00 a1 01 31                          status 00, marker 31
a2 03 02 e805                        u16 1512 (the A2345 and A91B2 carry their controller's digit-packed firmware version here: read that way, v1.5.1.2; the comms chip reports its own v0.0.5.0 in `0829`)
a3 03 02 0000                        u16 0 (the A2345 and A91B2 carry the port fault bitmap here)
a4 02 01 00                          (not mapped)
a5 08 04 01 e013 7400 3700           USB-C 1: status 1, 5 088 mV, 116 mA, 55 cW
a6 08 04 01 0823 6c03 0b03           USB-C 2: status 1, 8 968 mV, 876 mA, 779 cW
a7 08 04 01 d813 6400 3200           USB-C 3: status 1, 5 080 mV, 100 mA, 50 cW
a8 02 01 03 · a9 02 01 50 · aa 02 01 00                    (not mapped: 3, 80, 0)
ab 09 04 00 00 0f 0f 0f 00 00 00                           (not mapped)
ac 0d 04 01 00 2c010000 2c010000 00 00                     USB-C 1 record (not mapped; carries 300 twice)
ad 0d 04 01 00 2c010000 2c010000 02 03                     USB-C 2 record
ae 0d 04 01 00 2c010000 2c010000 00 00                     USB-C 3 record
af 02 01 00 · b0 02 01 00 · b1 02 01 01 · b2 02 01 01 · b3 02 01 01      (not mapped)
b4 0d 04 00000000 e8040000 00000000                        3 × {u16, u16}: C2 {04e8, 0000}, C1 / C3 {0, 0}
b5 0d 04 ff ×12                                            3 × {ffff, ffff}
e0 05 04 08000000                                          (not mapped)
e1 0b 04 80034b53 00000000 0000                            (not mapped)
fe 05 03 00000000                                          RTC epoch
```

- The three port blocks have the A2345's port-block layout: V × I / 10 000 matches P on each port (59 ≈ 55, 786 ≈ 779, 51 ≈ 50 cW). SolixBLE names them `usb_port_c1` … `c3` with `usb_c1_voltage` / `_current` / `_power` ….
- At idle each port block reads status 0 and zeros, `b4` reads `{fffa, fffb}` on all three ports and the `ac`–`ae` records end `03 00`. `b4` / `b5` use the A2345's `bd` / `be` sentinels (`{fffa, fffb}` no device, `{0, 0}` identity not read, `ffff` none), on three ports instead of four.
- `e1` reads all zeros in another unit's snapshot.

## A1340

Prime Power Bank, 27 650 mAh, 250 W: two USB-C ports and one USB-A, plus a 5-pad base connector (UART 9 600 baud and 100 W charging). This section describes firmware 1.6.1 and 1.6.2, the public images (2025); later builds may differ.

### Hardware

| part | role |
|---|---|
| GD32F303 | main MCU: status, configuration, pushes, OTA |
| Telink TLSR8253 | BLE chip: advertising, negotiation and session encryption; linked to the MCU over UART at 115 200 baud |
| ST7789 240 × 240 LCD | display, on SPI |
| 8 MB SPI NOR flash | LCD images from `0x000000`; OTA staging at `0x700000`–`0x7FFFFF` |

### Transport and negotiation

- Service `2215`: `22150001-4002-81c5-b46e-cf057c562025`, write `…0002`, notify `…0003` ([discovery-and-gatt.md](discovery-and-gatt.md)); the `ff09` framing as on the other families.
- The BLE chip holds the cryptography: the static key derived as on the ESP32 modules, ECDH on `0021` (capability mode 4), and the legacy confer on `0022` (modes 1 and 2). There is no `0003` → `0803` exchange; `0005 a5` sets the mode (`02` legacy, `44` ECDH). 1.6.1's BLE chip carries neither the static-key constants nor P-256; it has AES-CBC. Details: [negotiation.md](negotiation.md).
- The MCU handles channel `0x01`'s session ops `0x01 0x02 0x03 0x05 0x23 0x24 0x29 0x2a 0x2b 0x2f 0x30 0x25 0x26 0x1f`, the A2345 module's channel-1 set in the same order; the BLE chip keeps connect, `0x21` and `0x22`.
- `0829` device info: `a3` firmware version, `a4` serial, `a5` MAC.

### Channel `0x11` commands

| op | function | request | reply |
|---|---|---|---|
| `0x500` | status read | `a1 01` (full status) | 158 B: `[0]` result, then `a1 01 31` and the status TLVs (below) |
| `0x504` | theme | `a1 01`, `a2 01 <theme>` (theme selector at payload +6) | 4-byte ack |
| `0x501`–`0x509`, `0x50c`, `0x50d`, `0x510`–`0x512`, `0x514`–`0x516`, `0x518`, `0x520`, `0x521`, `0x524`, `0x550`, `0x089`, `0x08a`, `0x08c` | status and configuration | — | — |

Pushes, periodic, on channel `0x11`: `0x50e` live power and `0x522` temperature.

Tags are per-opcode ordinals, so the same datum has a different tag in each frame:

| datum | `0x500` status | `0x50e` live power | `0x522` temperature |
|---|---|---|---|
| per-port block: `[2]` mode (0 off, 1 in, 2 out), `[3:5]` u16 LE V ÷ 10, `[5:7]` u16 LE I ÷ 10; ≥ 12 B | USB-C 1 `a4`, USB-C 2 `a5`, USB-A `a6` | USB-C 1 `a2`, USB-C 2 `a3`, USB-A `a4` | — |
| totals: `[1:3]` u16 LE out ÷ 10 W, `[3:5]` in ÷ 10 W | `ae` | `a6` | — |
| battery: `[8]`.`[9]` = integer . fraction % | `a2` | `a8` | — |
| temperature: `[1]` °C, `[2]` °F | `b3` | — | `a2` |

The other `0x500` tags (`a3`, `a7`–`ad`, `af`–`b2`, `b4`, `b5`) carry no confirmed field. The app's A1340 parser (app code) also reads, per port, the connected device's manufacturer, product and charge protocol, and at device level the battery charge state, charge / discharge time, SoH, cycle count, buzzer switch and time, and charge and discharge switch states; their tags aren't located.

### OTA

- 1.6.1 accepts an image on a CRC32 check alone.
- 1.6.2 first verifies an ECDSA P-256 signature (a 64-byte signature over a 32-byte hash, against a public key in the MCU firmware) and fails with `OTA_---error8_ECDSA` before the CRC32 check.
- The image is staged in SPI flash at `0x700000`.
