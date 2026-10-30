# SOLIX C-series power stations

The C-series portable power stations speak the `ff09` protocol in two generations. The first (C300, C800, C1000) has one opcode per setting and flat telemetry tags; the second (C1000 Gen 2, C2000 Gen 2) groups its settings into three commands, carries structured telemetry blocks, and adds a protobuf statistics frame. Framing, the TLV encoding, negotiation and authorization are in [framing.md](framing.md), [negotiation.md](negotiation.md) and [authorization.md](authorization.md); this file starts where a session is authorized.

Each claim names the models or builds it holds for. Worked examples come from a C2000 Gen 2 (A1783), a C1000 Gen 2 (A1763), a C1000 (A1761) and a C300 (A1722).

## Models

| model | name | generation | status poll | telemetry push |
|---|---|---|---|---|
| A1722 / A1723 | SOLIX C300 / C300X | 1 | `4040` → `c840` | `c402` (BLE), `0405` (MQTT) |
| A1753 / A1754 / A1755 | SOLIX C800 / C800 Plus / C800X | 1 | `4040` → `c840` | `c402`, `0405` |
| A1761 | SOLIX C1000(X) | 1 | `4040` → `c840` | `c402`, `0405` |
| A1763 | SOLIX C1000 Gen 2 (productType `b118`) | 2 | `4100` → `c900` | `c421` (BLE), `0421` (MQTT), `c490` |
| A1765 | SOLIX C1000X Gen 2 / C1000 Plus (`b119`) | 2 | `4100` → `c900` | `c421`, `0421`, `c490` |
| A1783 | SOLIX C2000 Gen 2 (`b11a`) | 2 | `4100` → `c900` | `c421`, `0421`, `c490` |
| A1785 | SOLIX C2000X Gen 2 (`b11b`) | 2 | `4100` → `c900` | `c421`, `0421`, `c490` |

Model names are anker-solix-api's. The C800 models share the C1000's telemetry layout (anker-solix-api, verified on the A1753 and A1755; the A1754 isn't validated). The C800 and C300 have no expansion battery.

## Conventions

- **Names.** Each field name says whose it is: SolixBLE (Harvey's), anker-solix-api (Thom's), or the Anker app (Anker's). Where SolixBLE has a name, it is used as is.
- **Offsets.** `x[n]` counts from the first byte after the TLV type byte: `a5[2]` is the third value byte of tag `a5`. SolixBLE's `_parse_int(tag, begin=…)` counts the type byte as index 0, so its `begin` is one higher (`battery_percentage` on the C1000 Gen 2 reads `a5` `begin=3` = `a5[2]` here). anker-solix-api's `BYTES` keys use this file's convention.
- **Placeholders** are those in [README.md](README.md). This file adds the serials `APCDK960000000001` (A1763, 17 B), `APC9FE0000000001` (A1761, 16 B), `AZVSBJ0000000001` (A1722, 16 B) and expansion `APCDKJM0000000001`, and the transaction id `"1767225600000"` (the `00b95569` instant in ms).

## Session frames (both generations)

| item | value |
|---|---|
| pattern | requests on `03000f`; replies relayed from the device MCU and all pushes on `03010f`; replies the comms module answers itself on `03000f` |
| command | BLE requests carry flag `0x40` (`40xx` / `41xx`); replies `48xx` / `49xx`, plus `0x80` when fragmented (`c402`, `c840`, `c900`, `c421`); MQTT carries the same message types with neither flag |
| payload | `a1 01 21 <fields>`, then the trailer `fe 05 03 <u32 LE epoch>`. Gen 2 also accepts `fd 0e 00 <13 ASCII digits>` (ms epoch, the app's transaction id; anker-solix-api `msg_timestamp`) |
| field encoding | `<tag> <len> <type> <value>`, `len` counting the type byte. Types: `00` string, `01` u8, `02` u16, `03` 4-byte, `04` raw bytes; Gen 2's `a2` identity block uses `06`. Switch `a2 02 01 <00\|01>`; timer `a2 05 03 <u32 LE s>`; u16 `a2 03 02 <LE>` |
| reply | response = request `\| 0x0800`. Setters answer `00 a1 01 31` only; read the effect from the next telemetry frame |
| routing byte | `a1`: a BLE client sends `21`, the app over MQTT `22`. Replies carry `30 \|` the request's low nibble (`31` for a BLE request); telemetry pushes carry `31` on BLE and `34` on MQTT |

An ack frame (Gen 2, MQTT form, flag nibble 0; checksum = XOR of every preceding byte):

```
ff09 0e00 03010f 0857 00 a1 01 32 38
     len 14, pattern 03010f, cmd 0857 (reply to 0057), status 00, a1 32 (MQTT request), checksum 38
```

An ack proves only that the frame was parsed. Confirm a setter by its effect in telemetry.

## First generation: C300, C800, C1000

### Negotiation

The C300 and C1000 negotiate cleartext ECDH; their `0803` and `0829` answers are byte-identical and listed in [negotiation.md](negotiation.md) "Device answers by family". `0829 a4` is the 16-character serial.

### Commands

All carry `a1 01 21`, then the field, then `fe`. Opcodes as sent on BLE (`40xx`); on MQTT the same with flag nibble 0 (`00xx`).

| BLE | function | payload | models | name (SolixBLE / anker-solix-api) |
|---|---|---|---|---|
| `4040` | status request | — | all | `get_status_update()`; reply `c840` |
| `4042` | AC output timer | `a2 05 03 <u32 LE s>`, 0–86 400 in steps of 300, 0 off | C800, C1000 | `ac_output_timeout_seconds` |
| `4043` | DC output timer | `a2 05 03 <u32 LE s>`, as `4042` | C800, C1000 | `dc_output_timeout_seconds` |
| `4044` | AC charge limit | `a2 03 02 <u16 LE W>` | all | `ac_input_limit` |
| `4045` | device timeout | `a2 03 02 <u16 LE min>`: 0 (never), 30, 60, 120, 240, 360, 720, 1440 | C800, C1000 | `device_timeout_minutes` |
| `4046` | display timeout | `a2 03 02 <u16 LE s>`: 20, 30, 60, 300, 1800 | all (SolixBLE) | `set_display_timeout(DisplayTimeout)` / `display_timeout_seconds` |
| `404a` | AC output | `a2 02 01 <00\|01>` | all | `turn_ac_on()` / `turn_ac_off()` |
| `404b` | DC (12 V socket) output | `a2 02 01 <00\|01>` | all | `turn_dc_on()` / `turn_dc_off()` |
| `404c` | display brightness | `a2 02 01 <1 low / 2 medium / 3 high>`; the C1000 also takes 0 (off) | all | `set_display_mode(LightStatus)` / `display_mode` |
| `404f` | LED light | `a2 02 01 <0 off / 1 low / 2 medium / 3 high / 4 SOS blink>` | all | `set_light_mode(LightStatus)` / `light_mode` |
| `4050` | temperature unit | `a2 02 01 <0 °C / 1 °F>` | C800, C1000 | `temp_unit_fahrenheit` |
| `4052` | display on / off | `a2 02 01 <00\|01>` | all | `turn_display_on()` / `turn_display_off()` |
| `4057` | realtime trigger | `a2 02 01 <00\|01>`, optional `a3` timeout s | all | `realtime_trigger` |
| `405e` | ultrafast AC charge | `a2 02 01 <00\|01>` | C800, C1000 | `ac_fast_charge_switch` |
| `4076` | 12 V output mode | `a2 02 01 <mode>` | C800, C1000 | `dc_12v_output_mode` |
| `4077` | AC output mode | `a2 02 01 <mode>` | C800, C1000 | `ac_output_mode` |

- `4076` / `4077` encode the mode differently per model: the C800 takes Normal 0 / Smart 1, the C1000 Normal 1 / Smart 0. Both report the state as Normal 1 / Smart 2 (`f8[0]` / `f8[1]`, below).
- `4044` options (anker-solix-api): C300 100 / 200 / 300 / 330 W; C800 200–750 W (200, 300, 400, 500, 600, 700, 750); C1000 100–1000 W in steps of 100.
- The C300's cloud map lists `0044`, `004a`, `004b`, `004f`, `0052` and `0057`; SolixBLE also drives `404c` and `4046` on it.

Requests as SolixBLE builds them (C1000):

```
404a  a1 01 21 | a2 02 01 01           AC output on
4046  a1 01 21 | a2 03 02 1400         display timeout 20 s
4046  a1 01 21 | a2 03 02 0807         display timeout 1800 s
404f  a1 01 21 | a2 02 01 04           light SOS
4040  a1 01 21                         status request
```

App command names for the first-generation command class with no device-verified map (app code): `004d` `setAcFrequency`, `0075` `setPullLightWaitTime` (u16), `0079` `setMomenryPortSwitch` (port memory).

### Telemetry (`c402` / `0405`)

The device pushes `c402` on BLE; MQTT carries the same TLV as `0405` on `param_info`, with `a1 34` in place of `a1 31`. The C1000 and C300 frames are 240 B, one BLE frame. The BLE frames seen carry tags `a2` to `d0` (C1000: and `e5`); anker-solix-api's `0405` maps add settings tags past them (`d1`–`de`, `f8`, `fd` on the C800 and C1000). `4057 a2 01` starts the stream (anker-solix-api: every 3–5 s while it runs).

#### C1000 and C800 tags

| tag | type | field | SolixBLE | anker-solix-api |
|---|---|---|---|---|
| `a2` | u32 | AC output timer remaining, s | `ac_timer_remaining` | `ac_output_timeout_seconds` |
| `a3` | u32 | DC output timer remaining, s | — | `dc_output_timeout_seconds` |
| `a4` | u16 | time to full or empty, 0.1 h | `time_remaining` | `remaining_time_hours` |
| `a5` | u16 | AC input W | `ac_power_in` | `ac_input_power` |
| `a6` | u16 | AC output W | `ac_power_out` | `ac_output_power` |
| `a7` / `a8` | u16 | USB-C 1 / 2 W | `usb_c1_power` / `usb_c2_power` | `usbc_1_power` / `usbc_2_power` |
| `a9` / `aa` | u16 | USB-A 1 / 2 W | `usb_a1_power` / `usb_a2_power` | `usba_1_power` / `usba_2_power` |
| `ae` | u16 | DC (solar or car) input W | `solar_power_in` | `dc_input_power` |
| `af` | u16 | total input W: AC plus DC (584 with AC charging, 98 with DC charging) | `power_in` | `photovoltaic_power` |
| `b0` | u16 | total output W, the LED light included | `power_out` | `output_power_total` |
| `b2` | u16 | SolixBLE reads the 12 V socket state and power here | `dc_output` / `dc_power_out` | — |
| `b3` | u16 | firmware, decimal digits (166 = v1.6.6) | `software_version` | `sw_version` |
| `b9` | u16 | expansion firmware, 0 with none | `software_version_expansion` | `sw_expansion` |
| `ba` | u16 | controller firmware | `software_version_controller` | `sw_controller` |
| `bb` | u16 | AC output on | `ac_output` | `ac_output_status` |
| `bc` | u8 | charge source: 0 none, 1 solar, 2 AC, 3 both | — | `charging_status` |
| `bd` / `be` | u8, signed | temperature / expansion temperature, °C | `temperature` / `temperature_expansion` | `temperature` / `exp_1_temperature` |
| `bf` | u8 | battery: 0 standby, 1 discharging, 2 charging | — | `battery_status` (C800 map) |
| `c1` / `c2` | u8 | battery / expansion SoC % | `battery_percentage` / `battery_percentage_expansion` | `main_battery_soc` / `exp_1_soc` |
| `c3` / `c4` | u8 | SoH / expansion SoH %; may read 0 on the A1753 | `battery_health` / `battery_health_expansion` | `battery_soh` / `exp_1_soh` |
| `c5` | u8 | expansion count | `num_expansion` | `expansion_packs` |
| `c6` / `c7` / `c8` / `c9` | u8 | USB-C 1, USB-C 2, USB-A 1, USB-A 2 on | — | `usbc_1_status` … `usba_2_status` |
| `cc` | u8 | 12 V socket on | — | `dc_12v_1_status` |
| `d0` | string | serial | `serial_number` | `device_sn` |
| `d1` | u16 | AC charge limit W | — | `ac_input_limit` |
| `d2` / `d3` | u16 | device timeout min / display timeout s | — | `device_timeout_minutes` / `display_timeout_seconds` |
| `d7` / `d8` | u8 | AC / DC output switch | — | `ac_output_power_switch` / `dc_output_power_switch` |
| `d9` | u8 | display brightness 0–3 | — | `display_mode` |
| `da` | u8 | AC frequency, 50 / 60 Hz | — | `ac_frequency` |
| `dc` | u8 | LED light 0–3, 4 blinking | — | `light_mode` |
| `dd` / `de` | u8 | temperature unit / display on | — | `temp_unit_fahrenheit` / `display_switch` |
| `e5` | u8 | ultrafast charge | — | `ac_fast_charge_switch` |
| `f8` | raw | `[0]` 12 V output mode, `[1]` AC output mode: Normal 1, Smart 2 | — | `dc_12v_output_mode` / `ac_output_mode` |
| `fd` | — | expansion type | — | `exp_1_type` |
| `fe` | u32 | timestamp | — | `msg_timestamp` |

`ab`–`ad`, `b1`, `b4`–`b8`, `c0`, `ca`, `cb`, `cd`–`cf` carry no mapped field.

#### Worked example: C1000 `c402`, AC charging

Firmware v1.6.6, no expansion, battery 24 %, AC charging at 584 W.

```
a1 01 31                       routing: device → BLE
a2 05 03 00000000              AC timer remaining 0 s
a3 05 03 00000000              DC timer remaining 0 s
a4 03 02 0f00                  time to full 1.5 h
a5 03 02 4802                  AC input 584 W
a6 03 02 0000                  AC output 0 W
a7 03 02 0000 · a8 03 02 0000  USB-C 1 / 2: 0 W
a9 03 02 0000 · aa 03 02 0000  USB-A 1 / 2: 0 W
ab ac ad 03 02 0000            (no field)
ae 03 02 0000                  DC input 0 W
af 03 02 4802                  total input 584 W
b0 03 02 0000                  total output 0 W
b1 03 02 0000                  (no field)
b2 03 02 0100                  1 (SolixBLE dc_output)
b3 03 02 a600                  firmware 166 = v1.6.6
b4 03 02 0000 · b5 03 02 ff01 · b6 03 02 ff01 · b7 03 02 0000 · b8 03 02 9a00     (no field)
b9 03 02 0000                  expansion firmware 0: none attached
ba 03 02 a600                  controller firmware v1.6.6
bb 03 02 0000                  AC output off
bc 02 01 02                    charge source AC
bd 02 01 17                    temperature 23 °C
be 02 01 00                    expansion temperature 0
bf 02 01 02                    battery charging
c0 02 01 00                    (no field)
c1 02 01 18                    battery 24 %
c2 02 01 00                    expansion SoC 0
c3 02 01 64                    SoH 100 %
c4 02 01 00                    expansion SoH 0
c5 02 01 00                    0 expansions
c6 c7 c8 c9 02 01 00           USB-C 1–2, USB-A 1–2 off
ca cb 02 01 00                 (no field)
cc 02 01 00                    12 V socket off
cd ce cf 02 01 00              (no field)
d0 11 00 "APC9FE0000000001"    serial
e5 02 01 00                    ultrafast charge off
```

In the same unit's DC-charging frame `ae` and `af` both read 98 (`6200`), `bc` reads 1 (solar) and `a4` 9.0 h.

#### C300 tags

The C300 numbers its tags differently from the C1000:

| tag | type | field | SolixBLE | anker-solix-api |
|---|---|---|---|---|
| `a2` / `a3` | u32 | AC / DC output timer remaining, s | `ac_timer_remaining` / `dc_timer_remaining` | — |
| `a4` | u16 | time to full or empty, 0.1 h; `ffff` with no estimate | `time_remaining` | `remaining_time_hours` |
| `a5` | u16 | AC input W | `ac_power_in` | — |
| `a6` | u16 | AC output W | `ac_power_out` | — |
| `a7` / `a8` / `a9` | u16 | USB-C 1 / 2 / 3 W | `usb_c1_power` … `usb_c3_power` | `usbc_1_power` … `usbc_3_power` |
| `aa` | u16 | USB-A W | `usb_a1_power` | `usba_1_power` |
| `ab` | u16 | 12 V socket W | `dc_power_out` | — |
| `ac` | u16 | DC input W | `solar_power_in` | `dc_input_power_total` |
| `ad` | u16 | total input W, a USB-C input included (29 W charging over USB-C 2 reads 29) | `power_in` | `ac_input_power_total` |
| `ae` | u16 | total output W: the port outputs plus the LED light (2–3 W with the light on) | `power_out` | `ac_output_power_total` |
| `b0` | u16 | AC lead plugged in | — | `ac_input_plug_status` |
| `b1` | u16 | firmware, decimal digits (1051 = v1.0.5.1) | `software_version` | — |
| `b7` | u8 | AC output on | `ac_output` | `ac_output_power_switch` |
| `b8` | u8 | 2 while AC charging | — | `dc_charging_status` |
| `b9` | u8, signed | temperature °C | `temperature` | `temperature` |
| `ba` | u8 | 0 idle, 1 discharging, 2 charging | `charging_status` | `battery_status` |
| `bb` | u8 | battery SoC % | `battery_percentage` | `battery_soc` |
| `bc` | u8 | equal to `bb` in all five public frames (89–100) | — | `battery_soh` |
| `bd` / `be` / `bf` | u8 | USB-C 1 / 2 / 3: 0 off, 1 output, 2 input | `usb_port_c1` … `usb_port_c3` | — |
| `c0` | u8 | USB-A on | `usb_port_a1` | — |
| `c1` | u8 | 12 V socket on | `dc_output` | `dc_output_power_switch` |
| `c5` | string | serial | `serial_number` | `device_sn` |
| `c6` | u16 | AC charge limit W | — | `ac_input_limit` |
| `cf` | u8 | LED light 0–3 | `light` | `display_mode` |

#### Worked example: C300 `c402`, AC charging with the light on

Firmware v1.0.5.1, battery 89 %, AC charging at 403 W while powering an 84 W AC load and a 1 W USB-A load.

```
a1 01 31                       routing: device → BLE
a2 05 03 00000000              AC timer remaining 0 s
a3 05 03 00000000              DC timer remaining 0 s
a4 03 02 0100                  time to full 0.1 h
a5 03 02 9301                  AC input 403 W
a6 03 02 5400                  AC output 84 W
a7 a8 a9 03 02 0000            USB-C 1–3: 0 W
aa 03 02 0100                  USB-A 1 W
ab 03 02 0000                  12 V socket 0 W
ac 03 02 0000                  DC input 0 W
ad 03 02 9301                  total input 403 W
ae 03 02 5800                  total output 88 W (84 AC + 1 USB-A + the light)
af 03 02 0000                  (no field)
b0 03 02 0100                  AC lead plugged in
b1 03 02 1b04                  firmware 1051 = v1.0.5.1
b2 03 02 fc01 · b3 03 02 fc01 · b4 03 02 1c00 · b5 03 02 7b00 · b6 03 02 1b04     (no field)
b7 02 01 01                    AC output on
b8 02 01 02                    AC charging
b9 02 01 26                    temperature 38 °C
ba 02 01 02                    charging
bb 02 01 59                    battery 89 %
bc 02 01 59                    89
bd be bf 02 01 00              USB-C 1–3 off
c0 02 01 01                    USB-A on
c1 02 01 00                    12 V socket off
c2 c3 c4 02 01 00              (no field)
c5 11 00 "AZVSBJ0000000001"    serial
c6 03 02 4a01                  AC charge limit 330 W
c7 03 02 a005 · c8 03 02 2c01 · c9 03 02 3c00 · ca 03 02 0000                     (no field: 1440, 300, 60, 0)
cb 02 01 01 · cc 02 01 00 · cd 02 01 02 · ce 02 01 32                             (no field)
cf 02 01 03                    LED light high
d0 02 01 00 · d1 02 01 01                                                         (no field)
```

### Versions (`0830`)

`0830` (the reply to `0030`, BLE `4030` / `4830`, as on Gen 2 and the Prime) comes from the comms module: `a1` module firmware (anker-solix-api `hw_version`), `a2` device firmware (`sw_version`), then on some models the OTA type names.

```
C1000:  00 | a1 08 "v0.2.3.1" | a2 06 "v1.5.9"
C300:   00 | a1 08 "v0.2.9.8" | a2 08 "v1.0.5.7" | a3 0a "A1722_high" | a4 0e "A1722_mcu_high" | a5 10 "A1722_esp32_high"
```

The C300's names end `_high`; the A1783's end `_low`.

### Network message (`0407`)

The C1000 pushes `0407` on MQTT `state_info` (anker-solix-api): `a2` serial, `a3` WiFi network name, `a4` WiFi signal.

## Second generation: C1000 Gen 2, C2000 Gen 2

One display-board build serves the A1763, A1765, A1783 and A1785; the factory record picks the model at boot. The names, productType, PN strings and expansion pack names depend on the model; the tags, the telemetry layout and the setters don't. The C2000 Gen 2 takes a BP2000 or BP3000 expansion; the C1000 Gen 2 takes none.

Builds this section describes: display board (MainMcu) v1.2.1.1 and v1.2.1.6, comms module v0.3.0.6 and v0.3.3.0, BMS v1.9.2.2 and v1.9.3.3. Firmware behaviour holds for all four models on those builds. Facts observed on hardware are labelled with the model they were seen on; "Older builds" below lists what earlier A1763 firmware sends differently.

### Session frames

| item | value |
|---|---|
| pattern | requests on `03000f`; module-local replies on `03000f` (the decrypt-failure `01` included); replies relayed from the display board and all pushes on `03010f` |
| trailers | `fe 05 03 <u32 LE epoch>` and `fd 0e 00 <13 ASCII digits>` (ms epoch, the app's transaction id). The display board stores each trailer when present (`fd` ≤ 15 B, `fe` ≤ 4 B, independently); `fe` never sets the clock |
| reply `a1` | display-board replies carry `30 \|` the request's low nibble; the realtime-data replies and pushes carry `31`, or `34` while the unit is cloud-bound and on WiFi |

- Every request is answered by a frame with exactly one `a1`, and a request with no `a1` is still answered (`a1 30`); no handler rejects a request for its `a1`.
- `4057` needs `a1 01 21` on BLE: the MQTT form `a1 01 22` is ignored there.
- A field shorter than its declared length is still acked.
- While the unit is on WiFi talking to the cloud it may hold no BLE link at all; its telemetry and acks then travel over MQTT with `a1 34` / `a1 32` (A1783).

### Telemetry frames

The display-board MCU builds every telemetry frame; the comms module forwards them byte for byte.

| frame | transport | trigger | body |
|---|---|---|---|
| `c421` | BLE notify, `03010f` | pushed on change while the `4057` countdown runs (about one per second when values move) | work-info TLV |
| `c900` | BLE | reply to `4100` | status `00` + the same TLV as `c421`, so one byte longer |
| `4900` | BLE, `03000f` | a `4100` the comms module can't decrypt | status `01` only, 17 B with the tag; from the module, not the display board ([framing.md](framing.md#status-byte)) |
| `0421` / `0900` | MQTT `param_info`, `a1 34` | device cadence / reply to `0100` | the same TLV |
| `4425` / `0425` | BLE and MQTT | a backup-plan window start or end, or a debounced grid loss | event report ("Event report") |
| `4403` | BLE; `a1 44` to the cloud while cloud-bound and on WiFi | main SoC at 10 % or 1 %, or an output timer ran out | one event code ("Event push") |
| `c490` | BLE notify, op `0x490` | every 540 s | protobuf statistics ("c490") |

One field map serves `c421`, `c900` and `0421`. A changed setting appears in the next `c421` / `c900`; there is no separate change-report opcode. On MainMcu v1.2.1.6 a `c421` or `c900` runs to about 380 B, so it arrives in two fragments (253 B + the rest).

### Streaming (`4057`, `4100`)

```
4100 →  a1 01 21 | fe 05 03 00b95569
c900 ←  00 | <work-info TLV>                         one snapshot, normally followed by one c421 burst

4057 →  a1 01 21 | a2 02 01 01 | a3 03 02 2c01 | fe 05 03 00b95569
           a2 01 start (00 stop) · a3 u16 countdown 300 (optional; a missing a3 leaves the countdown unchanged)
4857 ←  00 | a1 01 31
```

- `4057` (anker-solix-api `realtime_trigger`; the Prime counterpart is `420b`) starts or stops `c421` pushes. Start and stop take effect within seconds: the first `c421` follows the start ack, and the stream is already silent when a stop is acked.
- The countdown is 2 × `a3` ticks of the ~1 s push timer and counts down only while no BLE client is connected. On a connected link the stream runs until a stop. `a3` is read as the low 16 bits of the value, so a type-`03` 4-byte `a3` (anker-solix-api's form) is accepted too; it isn't clamped and wraps above 32767.
- `4100` (the app's `getAllDeviceInfo`) draws one `c900`, normally followed by one `c421`. A bare `a1 01 21` works; the app sends `a2 0a 04 01 00 03 17 00 01 00 00 00`, an app-version descriptor (`03 17 00` = app 3.23.0). Bit 0 of that `a2`'s byte 5 selects `a3[10:12]` (`silentRechargePower`) = 1000, else 600.
- A `4100` sent under a session the module no longer holds gets `4900 01` on `03000f` instead (A1783, module v0.3.3.0). Seen with two clients on one relayed BLE connection: the second client's ECDH replaced the session key, the first client's polls each got the same `4900 01`, and the second client's own polls kept getting `c900` on `03010f` in between. Both replies are msgtype `0900` on channel `0x0f`, so a client has to check the status byte before taking a `0900` as its snapshot.
- The app sends `0057` with `a2 01 a3 2c01` every few minutes while it is open, mostly over MQTT.
- **`a2 = 0` stops `c421`.** After a stop, `c490` posts were absent for over an hour as well (A1783); a client that wants telemetry never sends `a2 00`, at teardown included. A plain disconnect leaves the stream running for the countdown.

### Worked example: a full `c421` (A1783)

MainMcu v1.2.1.6 with a BP2000 expansion attached; main pack 81 % discharging a 1 W load, expansion at 5 %, mains lead in with AC input disabled.

```
a1 01 31                                   routing: MCU → BLE
a2 21 06 | 20 11 "APCDKKE0000000001" 00 05 "A1783" 06 01 02 01 00 01
a3 0e 04 | 00 00 01 01 08 07 00 64 cc 00 58 02 00
a4 22 04 | 00 00 00 00 b0 04 3c 00 00 00 00 00 00 00 00 3c 00 03 00 01 00 00 01 5f 05 00 00 00 00 00 00 06 00
a5 06 04 | 15 01 51 e8 00
a6 0a 04 | 01 00 00 00 00 00 1c 0c 51
a7 07 04 | 00 00 00 02 00 00
a8 04 04 | 00 00 00
aa 04 04 | 00 00 00
ab 04 04 | 01 01 00
ac 04 04 | 00 00 00
ae 04 04 | 00 00 00
b2 04 04 | 00 00 00
c0 2c 04 | 11 "APCDKJM0000000001" 01 03 03 09 01 14 00 05 e8 01 01 00 01 00 0a "A1783_2kWh"
ce 2c 04 | 10 00×16 01 11 00×17 00 00 00 00 00 00 00
d9 1a 04 | 00 00 32 5f 05 00 | 00 00 00 00b95569 10c75569 00000000 00000000
da 18 04 | 81 00 00000000 00000000 01 ef01 3804 7f 01 01 00 3804 ef01
dc 06 04 | 00 00000000
f9 1d 04 | 06010201 06020100 00000000 06020100 03030901 03030901 00030300
fa 15 04 | 01 01 01 01 00 1f 35 00×13
fd 0e 00 | "1767225600000"
fe 05 03 | 00b95569
```

| tag | decoded |
|---|---|
| `a2` | protocol version `20`, SN length 17, serial, `00`, PN length 5, `"A1783"`, MainMcu v1.2.1.6, variant 0, `01` |
| `a3` | workStatus 0 (idle), errorCode 0, packageCount 1, packageUseCount 1, maxInputPower 1800 W, upgradeProgress 0, wifiSignalStrength 100, mtuSize 204, silentRechargePower 600, weakLightLockFlag 0 |
| `a4` | AC timer 0 (off), AC input limit 1200 W, AC frequency 60 Hz, AC power-saving off, car timer 0, DC power-saving off, device timeout 0 (never), display timeout 60 s, brightness 3 (high), `[18]` 0, temperature unit 1 (°F), fast charge off, display off, port memory on, max SoC 95, min SoC 5, language 0 (English), `[26..30]` 0, flags `06` (outage alert on; AC input disabled by the app), `[32]` 0 |
| `a5` | temperature 21 °C, charge_discharge_status 1 (discharging), battery_percentage 81, battery_health byte `e8` (SoH 1000 ‰, low byte), `00` |
| `a6` | power_out 1 W, ac_power_in 0 W, DC input 0 W, remaining time 3100 = 310.0 h, main SoC 81 |
| `a7` | ac_output 0 (off), ac_power_out 0 W, ac_input_status 2 (lead in, Battery-Only Power on), AC input 0 W |
| `a8` | solar_port 0, solar_power_in 0 W |
| `aa` / `ab` / `ac` | usb_port_c1 off 0 W · usb_port_c2 on 1 W · usb_port_c3 off 0 W |
| `ae` / `b2` | usb_port_a1 off 0 W · dc_output off 0 W |
| `c0` | expansion SN, slot 1, v1.9.3.3, 20 °C, status 0, SoC 5, health byte `e8`, blink 1, switch 1 (on), error 0, connected 1, balance 0, type `"A1783_2kWh"` |
| `ce` | no alternator charger: header `10`, empty PN, `01`, `11`, empty SN, mode 0, power 0 |
| `d9` | no active TOU period, mode Standard, reserve 50 %, max 95, min 5, 0 periods; tail: no active window, fast charging plan off, storm guard off, stored plan 1767225600 → 1767229200, no active window pair |
| `da` | screensaver on + Theme 2, no theme download, 24 h clock, period 1 08:15–18:00, every day, period 2 on, period 1 brightness 20 %, period 2 5 %, period 2 18:00–08:15 |
| `dc` | no output-memory fault |
| `f9` | MCU v1.2.1.6, DCDC v0.1.2.6, MPPT 0, ACDC v0.1.2.6, main BMS v1.9.3.3, expansion BMS v1.9.3.3, module v0.3.3.0 |
| `fa` | capability flags (below) |
| `fd` / `fe` | last app transaction id; timestamp |

### Tag reference

| tag | offset | field | notes |
|---|---|---|---|
| `a2` | 0–31 | basicData (type `06`, 32 B) | 0 protocol version `20`; 1 SN length `11`; 2–18 serial (SolixBLE `serial_number`); 19 `00`; 20 PN length `05`; 21–25 PN (SolixBLE `part_number`), the literal `A1783` on every model on v1.2.1.x; 26–29 MainMcu version, one decimal digit per byte, last digit first (`06 01 02 01` = v1.2.1.6); 30 model variant (0 base, 1 high-input variant); 31 `01` |
| `a3` | 0 | `workStatus` (anker-solix-api `working_status`) | 0 idle / 1 discharging / 2 charging / 5 upgrading; the main pack's current-based state, below. The app's enum also names 3 sleep and 4 shutdown |
| `a3` | 1 | `errorCode` | reads `0x19` for one frame on leaving upgrade mode, then 0 |
| `a3` | 2 / 3 | `packageCount` / `packageUseCount` | 1 / 1 with a BP2000 attached (A1783); 0 / 0 on an A1763 |
| `a3` | 4:6 | `maxInputPower` (anker-solix-api `ac_input_limit_max`) | u16 LE W. MainMcu v1.2.1.x: 2300 on the high-input variant, 1500 with country `JP`, else 1800 (A1783 reads 1800). An A1763 on v1.1.x reads 1200 |
| `a3` | 6 | `upgradeProgress` | firmware-update progress %, 0 outside an update |
| `a3` | 7 | `wifiSignalStrength` | `min(100, 2 × (100 + RSSI dBm))`; 100 with no WiFi link |
| `a3` | 8:10 | `mtuSize` | u16 LE: the BLE OTA packet size `(MTU − 46) & ~3`, MTU being ATT MTU − 3; 253 → 204, 266 → 220 |
| `a3` | 10:12 | `silentRechargePower` | u16 LE: 1000 or 600, set by the `4100` request's `a2` (above) |
| `a3` | 12 | `weakLightLockFlag` | |
| `a4` | 0–32 | settings (33 B; 26 B on v1.2.1.1 and earlier) | byte map in "Settings block (`a4`)" |
| `a5` | 0 | temperature (SolixBLE `temperature`) | °C, signed |
| `a5` | 1 | `charge_discharge_status` (anker-solix-api) | port-power flow: 0 / 1 discharging / 2 charging, main pack only (below) |
| `a5` | 2 | SolixBLE `battery_percentage` | main pack SoC % |
| `a5` | 3 | SolixBLE `battery_health` | the low byte of the main pack's SoH in 0.1 % (1000 ‰ reads `e8` = 232). Reads 0 on BMS builds before v1.9.3.3 |
| `a5` | 4 | — | always 0 |
| `a6` | 0:2 | SolixBLE `power_out` | u16 LE W: sum of all port outputs (AC, car socket, USB) |
| `a6` | 2:4 | SolixBLE `ac_power_in` | u16 LE W |
| `a6` | 4:6 | DC input power total | u16 LE W |
| `a6` | 6:8 | remaining time (anker-solix-api `remaining_time_hours`) | u16 LE, 0.1 h: time to full when total port input > total output, else time to empty; 10923 (1092.3 h) = no estimate on the chosen side, the BMS's `ffff` minutes scaled |
| `a6` | 8 | main battery SoC | always equal to `a5[2]` |
| `a7` | 0 | SolixBLE `ac_output` | AC output switch state |
| `a7` | 1:3 | SolixBLE `ac_power_out` | u16 LE W; 0 unless AC output is on |
| `a7` | 3 | `ac_input_status` (anker-solix-api) | mains lead present, whether or not power flows: 0 out, 1 in, 2 in with Battery-Only Power on (`4101 ab`) |
| `a7` | 4:6 | AC input power | u16 LE W |
| `a8` | 0 / 1:3 | SolixBLE `solar_port` / `solar_power_in` | the single XT-60 DC input (solar, car socket or alternator); status, u16 LE W. The app's `pv1ChargeStatus`, `pv1InputPower` and `carChargerInputPower` all name this one port |
| `aa` / `ab` / `ac` | 0 / 1:3 | SolixBLE `usb_port_c1` … `c3`, `usb_c1_power` … | USB-C status, u16 LE W |
| `ae` | 0 / 1:3 | SolixBLE `usb_port_a1` / `usb_a1_power` | USB-A |
| `b2` | 0 / 1:3 | SolixBLE `dc_output` / `dc_power_out` | 12 V car socket (`04 01 06 00` = on, 6 W) |
| `c0` | — | expansion block | "Expansion (`c0`)" |
| `ce` | — | car-alternator charger accessory | `[0]` `10`, `[1:17]` PN, `[17]` `01`, `[18]` `11`, `[19:36]` SN, `[36:40]` 0, `[40]` mode, `[41:43]` power u16 LE W |
| `d9` | — | TOU and backup plan | "TOU (`4090`)" and "Backup plan (`405e`)" |
| `da` | — | clock screen | "Clock screen (`4091`)" |
| `dc` | 0 / 1:5 | `memorySwitchErrorCode` / `memorySwitchErrorTimestamp` (app) | the BMS fault that blocks the output-memory restore: 0 none, 1 discharge over-temperature, 2 discharge low-temperature, 3 low battery, 4 BMS communication error, 5 over-current, 6 MOS over-temperature, 7 pre-discharge MOS fault, 8 main charge MOS fault, 9 main discharge MOS fault; u32 LE epoch = fault time + the configured recovery delay. Zero while no fault. Written only by the firmware; no setter |
| `f9` | — | seven versions | "Versions (`f9`)" |
| `fa` | — | capability flags | "Capability flags (`fa`)" |
| `fd` | — | transaction id | the last request `fd` (type `00`, 13 ASCII digits). Length = 1 + min(len, 15); after a display-board reset it is empty (`fd 01 00`) until the next request carrying one. Fields that change under one `fd` came from one app write |
| `fe` | 0 | timestamp (anker-solix-api `msg_timestamp`) | u32 LE: the RTC plus the stored offset |

**Example `a3`** (an app session, `silentRechargePower` 1000): `a3 0e 04 | 00 00 01 01 08 07 00 64 cc 00 e8 03 00` = workStatus 0, errorCode 0, packageCount 1, packageUseCount 1, maxInputPower 1800, upgradeProgress 0, wifiSignalStrength 100, mtuSize 204, silentRechargePower 1000, weakLightLockFlag 0.

### Older builds

An A1763 on MainMcu v1.1.2.6 and v1.1.4.3 sends the same tag set with these differences:

| field | A1763 v1.1.2.6 / v1.1.4.3 | v1.2.1.x |
|---|---|---|
| `a2[21:26]` PN | `A1763` | `A1783` on every model |
| `a2[30:32]` | `01 00` | `00 01` (A1783, A1785) |
| `a3` | 10 B on v1.1.2.6 (no `silentRechargePower`, no `weakLightLockFlag`); 13 B on v1.1.4.3 | 13 B |
| `a4` | 26 B | 26 B on v1.2.1.1, 33 B on v1.2.1.6 |

The A1763 v1.1.2.6 identity and settings blocks:

```
a2 21 06 | 20 11 "APCDK960000000001" 00 05 "A1763" 06 02 01 01 01 00
           version 20, serial, PN "A1763", MainMcu v1.1.2.6, 01, 00
a3 0b 04 | 00 00 00 00 b0 04 00 58 dc 00
           workStatus 0, errorCode 0, packageCount 0, packageUseCount 0, maxInputPower 1200, upgradeProgress 0, wifiSignalStrength 88, mtuSize 220
a4 1b 04 | 00000000 b004 32 01 00000000 00 0000 1e00 01 00 00 00 00 00 64 01 03
           AC timer 0, AC input limit 1200 W, 50 Hz, AC power-saving on, car timer 0, DC power-saving off, device timeout never,
           display timeout 30 s, brightness 1, [18] 0, °C, fast charge off, display off, port memory off, max SoC 100, min SoC 1, language 3 (German)
d9 1a 04 | 00 00 19 64 01 00 | …   no active period, Standard, reserve 25 %, max 100, min 1, no records
```

### Settings block (`a4`)

Each byte and the setter that writes it.

| byte | field (anker-solix-api) | setter |
|---|---|---|
| `[0..3]` | `ac_output_timeout_seconds`, u32 LE s | `4101 a3` |
| `[4..5]` | `ac_input_limit`, u16 LE W | `4101 a4` |
| `[6]` | `ac_frequency` (the output-frequency setting, Hz) | `4101 a5` |
| `[7]` | `ac_output_mode` (AC power-saving) | `4101 a6` |
| `[8..11]` | `dc_output_timeout_seconds`, u32 LE s | `4102 a3` |
| `[12]` | `dc_12v_output_mode` (DC power-saving) | `4102 a4` |
| `[13..14]` | `device_timeout_minutes`, u16 LE; 0 = never | `4103 a6` |
| `[15..16]` | `display_timeout_seconds`, u16 LE | `4103 a4` |
| `[17]` | `display_mode` (brightness 1 / 2 / 3) | `4103 a3` |
| `[18]` | 0 | — |
| `[19]` | `temp_unit_fahrenheit` | `4103 a5` |
| `[20]` | `ac_fast_charge_switch` | `4101 a7` |
| `[21]` | `display_switch`: 1 while the screen timer runs; also drops to 0 by itself one display timeout after a wake | `4103 a2` |
| `[22]` | `port_memory_switch` (app `memorySwitch`) | `4103 a8` |
| `[23]` | `max_soc` (SolixBLE `max_battery_percentage` reads the same value from `d9[3]`) | `4103 aa` |
| `[24]` | `min_soc` | `4103 ab` |
| `[25]` | `display_language` (app `deviceLanguage`): 0 English, 1 Chinese, 2 French, 3 German, 4 Japanese | `4103 a9` |
| `[26..30]` | 0 | — |
| `[31]` | bit 1 `outage_alert_switch` (app `outageAlertSwitch`); bits 2–3 `ac_input_disable_state`: 0 AC input accepted, 1 disabled by `4101 ab`, 2 auto-off: no mains plugged in, or the main pack at `min_soc` (either one also clears the disable); no other value | `4103 b0` / `4101 ab` |
| `[32]` | 0 | — |

Bytes 26–32 exist from MainMcu v1.2.1.6. Example sequences on `[31]` (A1783):

- `08` → `00` mains plugged in → `02` outage alert on → `06` AC input disabled (`a7[3]` 1 → 2) → `02` disable off.
- With mains in and Battery-Only Power on: `06` → `0a` as the main pack reaches `min_soc` (auto-off, `a7[3]` 2 → 1) → `02` once its SoC is back above the floor ("Battery-Only Power at the floor").

### Flow state

Two bytes report charge / discharge, from different sources:

| field | source | behaviour |
|---|---|---|
| `a5[1]` (app `chargeDischargeStatus`) | port powers | 2 if total input > total output, 0 if total output = 0, else 1; no debounce. 0 while the expansion holds the bus |
| `a3[0]` (app `workStatus`) | main pack current | 2 after 20 samples (~2 s) at ≥ +0.3 A with an external charge source present (AC or DC input), 1 after 20 at ≤ −0.3 A, back to 0 as the counters decay; forced to 5 during a firmware update |
| `c0[24]` (app `subPackageStatus`) | port powers | the `a5[1]` code while the expansion holds the bus, 0 while the main does |

| `a3[0]` | `a5[1]` | reading |
|---|---|---|
| 0 | 0 | idle |
| 0 | 1 | output on the ports, pack current under 0.3 A |
| 1 | 1 | discharging |
| 2 | 2 | charging |
| 2 | 1 or 0 | leaving charge: `a5[1]` has moved, `a3[0]` follows after its 20 samples |
| 0 or 1 | 2 | entering charge |

- `a3[0]` follows `a5[1]` by 2–3 s on the wire (A1783).
- Read `a5[1]` and `c0[24]` together: one of them carries the port-flow code, depending on which pack holds the bus, and the other reads 0. With the expansion carrying the load, `a5[1]` and `a3[0]` read 0 for a whole discharge.
- Port watts aren't pack current (standby, pass-through and pack selection sit between them), so the port power at a transition isn't a threshold.
- `workStatus 5` spans the whole update; the app's `isOTA` is derived by the app and trails it by seconds.

### Presence

| field | reports |
|---|---|
| `a7[3]` | the mains lead is plugged in, whether or not power flows (1 at 0 W); 2 = plugged in with Battery-Only Power on |
| `a8[0]` | a DC source attached; `solar_power_in` is 0 when the pack is above its cap. A 12 V car-socket adapter reads 1 at 0 W; solar follows panel voltage, so attached panels read 0 / 0 W at night and 1 by day |
| `c0[30]` | an expansion attached |

The LCD shows the same split: `--` for a disabled path, `0 W` for an enabled one drawing nothing (A1783).

### Expansion (`c0`)

C2000 Gen 2 (A1783, A1785). Emitted with or without a pack attached; gate every expansion value on `[30]`. Both length prefixes shift the later offsets, so walk them.

| offset | app name | notes |
|---|---|---|
| `[0]` | SN length | 17 attached, 16 unattached |
| `[1:18]` | `subPackageSN` | 16 zero bytes unattached |
| `[18]` | `subPackageNumber` | slot index, always 1 |
| `[19:23]` | `subPackageVersion` | one decimal digit per byte, last digit first; `0.0.0.0` unattached |
| `[23]` | `subPackageTemperature` | °C; `ef` (239) unattached |
| `[24]` | `subPackageStatus` | the port-flow code while the expansion holds the bus, 0 while the main does (Flow state) |
| `[25]` | `subPackageBatteryLevel` | expansion SoC % |
| `[26]` | `subPackageHealth` | the main pack's SoH byte, equal to `a5[3]` |
| `[27]` | `subPackageBlinkStatus` | constant 1; doesn't follow the `4104` locate blink |
| `[28]` | `subPackageSwitchStatus` | the expansion's reported output state (not the commanded one; see `4104`) |
| `[29]` | `subPackageErrorCode` | |
| `[30]` | `subPackageConnectionStatus` | 1 attached |
| `[31]` | `subPackageBalanceStatus` | |
| `[32]` | type length | 10 attached, 2 unattached |
| `[33:]` | `subPackageType` | `A1783_2kWh` (BP2000) or `A1783_3kWh` (BP3000); `A1785_*` on the A1785; two spaces unattached |

The wire block is `c0 23 04 …` (35 B) unattached and `c0 2c 04 …` (44 B) attached.

### Versions (`f9`)

Seven 4-byte versions, one decimal digit per byte, last digit first.

| slot | app name | source |
|---|---|---|
| `[0:4]` | `mcuVersion` | display board (MainMcu) |
| `[4:8]` | `subMCUVersion` | DCDC stage; reads 0 for about 1 s about once a minute while both AC paths are off and the stage sleeps, and at power-up |
| `[8:12]` | `MPPTVersion` | always 0 |
| `[12:16]` | `INVVersion` | ACDC stage; non-zero only while that stage is energised: appears within ~1 s of the mains lead going in, clears ~1 s after it comes out or ~50 s after AC output switches off |
| `[16:20]` | `BMSVersion` | main pack BMS |
| `[20:24]` | `subPackageVersion` | expansion BMS; 0 with no pack |
| `[24:28]` | `moduleVersion` | comms module |

The main pack and the BP2000 run the same BMS image, so after an update both BMS slots carry the same version. After an update the versions arrive in stages: the MCU first, then BMS, expansion and module together about 25 s later (A1783).

### Capability flags (`fa`)

20 bytes of constants; names are the app's, bits LSB first.

| byte / bit | app name | v1.2.1.1 | v1.2.1.6 |
|---|---|---|---|
| `[0]` | `supportACEnergyMode` | 1 | 1 |
| `[1]` | `supportCarChargeMode` | 1 | 1 |
| `[2]` | `supportParallelUpgrade` | 1 | 1 |
| `[3]` | `supportGetUpgradeInfo` | 1 | 1 |
| `[4]` | `stationProtocolVersion` | 0 | 0 |
| `[5]` b0–b4 | `supportTransactionId`, `supportMemorySwitch`, `supportBackupDisaster`, `supportUpgradeRecord`, `supportScreenTimePeriod` | 1 | 1 |
| `[5]` b5–b7 | `supportOutputStatus`, `supportChargingLimits`, `supportSetCountryCode` | 0 | 0 |
| `[6]` b0 | `supportPPSTOU` | 1 | 1 |
| `[6]` b1 | `memorySwitchTwo` | 1 | 0 |
| `[6]` b2 | `supportSilentRecharge` | 1 | 1 |
| `[6]` b3 | `supportOutageAlert` | 0 | 0 |
| `[6]` b4 | `supportAcInputDisable` | 0 | 1 |
| `[6]` b5 | — | 0 | 1 |
| `[7..19]` | — | 0 | 0 |

The wire shows `fa 15 04 01 01 01 01 00 1f 07 …` on v1.2.1.1 and `… 1f 35 …` on v1.2.1.6. An A1763 on v1.1.2.6 sends `… 1f 03 …`, on v1.1.4.3 `… 17 03 …`.

### Command map (channel 0x0f, opcode ≥ `0x40`)

Handled by the display board. Every request carries `a1 01 21`; examples omit the `fe` / `fd` trailers.

| BLE | function | request | reply / effect |
|---|---|---|---|
| `4051` | restore settings defaults | — | ack; the settings block (`a4`) returns to defaults |
| `4055` / `4062` | none | — | no reply, no effect |
| `4057` | realtime trigger: `c421` streaming countdown | `a2` start / stop, optional `a3` u16 countdown | `4857 00 a1 01 31` |
| `4059` | registration retry for the display board's own identity push; `a2 = 0` makes it re-push its identity up to 10 times. State-changing; a client has no use for it | `a2` | ack |
| `405e` | backup plan ("Backup Mode": Fast Charging Plan and Storm Guard) | below | `485e` ack; `d9` tail |
| `4063` / `4064` | BLE OTA start / packet | below | below |
| `4065` / `4066` | BLE log upload: size / chunk | — / u16 index at payload +6 | below |
| `4072` | daily cloud update-check window | below | `4872` ack |
| `4089` | OTA precheck (the app's `check_device_ota_status`) | ignored | below |
| `4090` | TOU plan | below | ack; `d9` |
| `4091` | clock screen (Display Plan) | `a2`–`af` | ack; `da` |
| `4092` | clock screen read | — | `da` bytes + theme name |
| `4100` | all device info (subscribe) | `a2` optional | `c900` |
| `4101` | AC group (cloud `action_set_ac_params`) | below | `4901` ack |
| `4102` | DC / car-socket group (`action_set_car_charger_params`) | below | `4902` ack |
| `4103` | system / display group (`action_set_system_params`) | below | `4903` ack |
| `4104` | expansion switch and locate (`action_set_bms_params`) | below | ack |

- Gen 2 has no per-setting opcodes: the first generation's `4052` display switch, `404c` brightness and `4046` display timeout don't apply; settings go by tag inside the group commands.
- The app's send flags `ble=true, mqtt=true` name the transports a command may use: with BLE connected a setting goes over BLE only. Polls such as `0057` are flagged MQTT-only.
- Cloud action names multiplex opcodes: `action_set_system_params {chargingLimitValue}` → `4103`, `{timestamp}` → `4089`, `{temperatureUnit}` → `4103 a5`.

### AC, DC and system groups (`4101`–`4103`)

| tag | `4101` AC | `4102` DC | `4103` system |
|---|---|---|---|
| `a2` | AC output on / off (`a7[0]`) | 12 V car socket on / off (`b2[0]`) | display on / off, app `screenSwitch` (`a4[21]`) |
| `a3` | AC timer, u32 s, 0 disables (`a4[0..3]`) | car timer, u32 s (`a4[8..11]`) | brightness 1 / 2 / 3 (`a4[17]`) |
| `a4` | AC input limit, u16 W, app `acRechargePower` (`a4[4..5]`) | DC power-saving (`a4[12]`) | display timeout, u16 s (`a4[15..16]`) |
| `a5` | AC frequency (`a4[6]`) | — | temperature unit (`a4[19]`) |
| `a6` | AC power-saving (`a4[7]`) | — | device timeout, u16 min, 0 = never (`a4[13..14]`) |
| `a7` | fast charge; applied only while no TOU period is active (`a4[20]`) | — | ambient light: accepted, no effect |
| `a8` | — | — | port memory, app `memorySwitch` (`a4[22]`) |
| `a9` | — | — | language (`a4[25]`) |
| `aa` | — | — | max SoC (`a4[23]`, `d9[3]`); lowers the TOU reserve to it |
| `ab` | AC input disable, u16, app `acInputDisableSwitch` ("Battery-Only Power") | — | min SoC (`a4[24]`, `d9[4]`); raises the TOU reserve to min + 5 |
| `b0` | — | — | AC off-grid (outage) alert, `a4[31]` bit 1; applied only when a value follows the type byte (the length byte > 1) |

SolixBLE's `turn_ac_on` / `turn_ac_off` send `4101 a2 02 01 01` / `00`, and `turn_dc_on` / `turn_dc_off` send `4102 a2`.

Requests as the app sends them (BLE form):

```
4101  a1 01 21 | a2 02 01 01                           AC output on
4101  a1 01 21 | a3 05 03 b0040000                      AC timer 1200 s
4101  a1 01 21 | a4 03 02 b004 | ab 03 02 0000          AC input limit 1200 W, AC input enabled
4102  a1 01 21 | a3 05 03 201c0000                      car timer 7200 s
4103  a1 01 21 | a2 02 01 00 | fd 0e 00 "1767225600000" display off
4103  a1 01 21 | aa 02 01 5f | ab 02 01 05              max SoC 95, min SoC 5
4103  a1 01 21 | a9 02 01 04                           language: Japanese
```

- `4101 a2` and `4103 a2` act only when the value differs from the current state.
- The app pairs `4101 a4` with `ab 03 02 0000`: the maximum AC input with AC input enabled.
- `4101 ab`: 1 = AC input off and fast charge off ("Battery-Only Power": loads draw from the battery only, grid charging and TOU can't run); 0 = AC input on. The disable is held in RAM: the firmware clears it when the main pack reaches `min_soc` ("Battery-Only Power at the floor"), when mains is unplugged, and on a restart.
- `4102 a2`: switching the car socket on or off, by command or by the button, triggers a USB-PD renegotiation on the USB-C ports, so a `b2[0]` edge explains a USB-C port-power drop and a recharge burst (A1783).
- The app's AC and car invoke parameters are named `acInputStatus` / `carChargerInputStatus`, but the UI actions are `setACOutputSwitch` / `setDCOutputSwitch`: they are the output toggles. The app's property names for the real output states are `acOutputStatus` / `carCharge1OutputStatus`.
- App picker values on the A1783 (examples, not the accepted range): `4101 a3` 300 / 7200 s; `4101 a4` 500–1800 W; `4102 a3` 0 / 600 / 3600 / 7200 / 40500 s; `4103 a4` 10 / 20 / 30 / 60 / 300 / 1800 s; `4103 a6` 0 / 360 / 720 min. anker-solix-api offers 0 (never), 10, 20, 30, 60, 300 and 1800 s for `4103 a4` and 0, 30, 60, 120, 240, 360, 720 and 1440 min for `4103 a6`.

**Display.** `4103 a2` on / off, `a3` 1 low / 2 medium / 3 high, `a4` timeout seconds (`3c00` 60, `2c01` 300, `0807` 1800).

**SoC limits** (`4103 aa` / `ab`): `aa` = the charge cap (app picker 80 / 85 / 90 / 95 / 100), `ab` = the discharge floor (1 / 5 / 10 / 15 / 20).

- The BMS clamps: max ≤ min → 100 / 1; max > 100 or < 2 → 100; min 0 → 1. An off-picker value inside those bounds (e.g. 98) is applied and held.
- The BLE write alone is sufficient and durable. anker-solix-api maps it as `CMD_SOC_LIMITS_V2`.
- Read the cap from `a4[23]`; `d9[3]` / `[4]` track cap and floor.
- `min_soc` also selects which pack holds the bus on the C2000 Gen 2 ("Pack selection").

**C1000 Gen 2 (A1763), on hardware.** `4103 aa` / `ab` apply at once, each sent alone, and `d9` follows; `4101 a4` takes 100–1200 W in steps of 100 and `a4[4..5]` follows within ~1 s; `4101 a7` sets `a4[20]`; `4090` is stored and reflected in `d9`.

### Backup plan (`405e`)

The app's "Backup Mode" screen, with two toggles: "Fast Charging Plan" (the manual plan: charge at a set time) and "Storm Guard" (the automatic plan). On the first generation `405e` is a 1-byte ultrafast-charge switch (anker-solix-api `CMD_AC_FAST_CHARGE_SWITCH`); on Gen 2 it is this group (`CMD_BACKUP_*_V2`), and a 1-byte decoder is wrong here.

```
a1 01 21                                routing
a3 02 01 03                             group selector, must be 3
a4 02 01 00                             backupMode: 0 manual (Fast Charging Plan), 1 auto (Storm Guard), 2 clear all
a5 02 01 01                             manualBackupSwitch: 1 on, 0 off
a6 02 01 01                             plan count (≤ 3)
a7 0b 04 64 00 00b95569 ffffffff        one plan, 10 B: u8 100, u8 00, u32 LE start 1767225600, u32 LE end (ffffffff = no end)
fd 0e 00 "1767225600000"
```

- A plan is 10 bytes after the type byte: `+1` u8 (anker-solix-api `max_soc`), `+2` u8 (anker-solix-api `min_soc`; not read by the firmware), `+3` u32 start, `+7` u32 end.
- `aa 02 01 01` cancels the running plan.
- A switch alone sends `a3` / `a4` / `a5` with no `a6` / `a7`. Clear all is `a3 02 01 03 · a4 02 01 02` with no `a5`.
- The app always sends one plan (`a6 01`).
- The cloud action for the same write is `action_set_backup_mode {manualBackupSwitch, backupMode, backupStartTime, backupEndTime}`.

The `d9` tail (19 B after the TOU records) reports it:

| field | anker-solix-api name |
|---|---|
| active window type, u8 | `backup_status` |
| manual plan (Fast Charging Plan) enabled, u8 | `backup_switch` |
| auto plan (Storm Guard) enabled, u8 | `storm_guard_switch` |
| manual plan start / end, u32 LE each | `backup_start_timestamp` / `backup_end_timestamp` |
| the running window's start / end, u32 LE each, 0 when none runs | `auto_backup_start_timestamp` / `auto_backup_end_timestamp` (despite the name, whichever plan is running) |

- While a plan window runs it overrides the AC charge limit (`a4[4:6]` reads 1200 W) and the max SoC (`d9[3]` reads 95), and charging moves to the main pack until it is full, then back to the expansion (A1783).
- A scheduled window starts on its own at its start time, with a `4425` event `0a`.

### TOU (`4090`)

`4090` stores the plan; activation follows the rules below.

| tag | field |
|---|---|
| `a2` | u8 mode: 1 TOU, 0 Standard (other values are stored and never match) |
| `a5` | u8 reserve SoC % |
| `a6` | u8 record count |
| `a7` | records, 3 B each `{type, start hour, end hour}`: type 1 Peak, 2 Mid-Peak, 3 Off-Peak; whole hours 0–24, start ≤ hour < end, no wrap past midnight |

- `a3` / `a4` are ignored. Nothing is checked: the count isn't compared with the records, and an `a7` longer than 18 data bytes overruns the handler's buffer. Send at most 6 records.
- Example: the plan "00:00–23:00 Off-Peak, 23:00–24:00 Peak" reads back as `d9[5..11]` = `02 · 03 00 17 · 01 17 18`.

`d9` (touData, 6 + 3n + 19 B):

| byte | field | setter |
|---|---|---|
| `[0]` | the active record's type, 0 = none | — |
| `[1]` | mode: 0 Standard, 1 Time-of-Use | `4090 a2` |
| `[2]` | reserve SoC % (anker-solix-api `backup_soc`, app `TOUReservePower`) | `4090 a5` |
| `[3]` | max SoC (SolixBLE `max_battery_percentage`; anker-solix-api `backup_charge_soc`) | `4103 aa` |
| `[4]` | min SoC (SolixBLE `min_battery_percentage`; anker-solix-api `backup_discharge_soc`) | `4103 ab` |
| `[5]` | record count n | `4090 a6` |
| `[6 .. 6+3n−1]` | records | `4090 a7` |
| then 19 B | backup-plan tail | `405e` |

Later offsets move with the record count. Example: `d9 1a 04 00 00 41 5f 05 00 …` = none active, Standard, reserve 65, max 95, min 5, no records.

A period is active (`d9[0]` ≠ 0) only while all of these hold, in this order:

| # | condition |
|---|---|
| 1 | mode = 1 |
| 2 | the unit itself cloud-bound **and** on WiFi; a BLE-only unit never activates TOU, while a plan written over BLE to a bound unit does |
| 3 | AC input present as the power stage reports it (input power available, no fault) |
| 4 | no car-alternator charger attached |
| 5 | AC input disable (`4101 ab`) off (v1.2.1.6) |
| 6 | the hour is inside a record, by the device clock |

What an active period does:

| effect | where it shows |
|---|---|
| Peak (1) and Mid-Peak (2) hold off AC (grid) charging while SoC ≥ max(reserve, min + 5 %), 0.3 % higher while already charging; Off-Peak (3) charges as usual. Bench: a Peak period at 95 % SoC, reserve 50 %, held AC input at 0 W and charging resumed at ~1 290 W within 13 s of the period ending; an Off-Peak period kept charging at ~1 280 W | `a7` AC input power |
| the AC output has no tariff gate | `a7` |
| the main pack's charge current is capped at 40.0 A (normally 58.0 A) | charge power |
| `4101 a7` fast charge = 1 is ignored | `a4[20]` |
| status bit `0x80` = period active and no backup plan running | `c490 .14.30` |
| the reserve SoC is held between min and max | `d9[2]` |
| the energy and time totals accumulate | `0503`, `c490 .18` |

It never switches AC input off. On an A1763 a `4090` plan was stored and reflected in `d9` while AC input stayed on and no period activated, the result of an unmet condition 2, 3 or 6.

**Clock.** The device clock holds local time and is set only from the comms module: from the `0022` a client sends during negotiation (`a1` UTC, `a3` offset, int32 seconds west of UTC; [negotiation.md](negotiation.md)) and from SNTP over WiFi. The `fe` on each request is stored and never sets the clock, so a client that sends a wrong `0022 a3` shifts every TOU hour.

### Clock screen (`4091` → `da`, `4092`)

`4091` writes only the tags present; the app sends only what changed. `da` changes only on a write.

| tag | width | `da` | field (app name) |
|---|---|---|---|
| `a2` | 1 | `[0]` | bit 7 screensaver (`screenSaverSwitch`); bits 0–3 clock theme (`lcdTheme`), "Theme N" stored as N − 1: 0 digital, 1 flip clock, 2 stacked hours over minutes, 3 the downloaded network theme (the digital clock over its background); 4–15 show Theme 1. Bits 4–6 are stored and echoed, never read |
| — | — | `[1]` | theme download state: 1 downloading, 0 idle or done, 2 failed |
| `a3` | 4 | `[2:6]` | network theme id; a change while bound and on WiFi starts a theme download |
| `a4` | u32 | `[6:10]` | network theme CRC; compared only for a change; same download rule |
| `a5` | string | — | theme name (returned by `4092 a3`) |
| `a6` | string | — | theme download URL (`http`/`https`, ≤ 255 B, sent NUL-terminated) |
| `a7` | 1 | `[10]` | clock format: 1 = 24 h, 0 = 12 h (`lcdTimeFormat`) |
| `a8` | u16 LE | `[11:13]` | period 1 start, minutes from midnight (`lcdStartTime`) |
| `a9` | u16 LE | `[13:15]` | period 1 end (`lcdEndTime`) |
| `aa` | 1 | `[15]` | weekday mask, bit 0 Monday … bit 6 Sunday; `7f` every day (`lcdRepeatCycle`) |
| `ab` | 1 | `[16]` | period 2 active, "distinguish day from night" (`dayNightSwitch`) |
| `ac` | 1 | `[17]` | period 1 brightness: 0 = 5 %, 1 = 20 % (`dayBrightnessLevel`) |
| `ad` | 1 | `[18]` | period 2 brightness: 0 = 5 %, 1 = 20 % (`nightBrightnessLevel`) |
| `ae` | u16 LE | `[19:21]` | period 2 start |
| `af` | u16 LE | `[21:23]` | period 2 end |

- Turning period 2 off zeroes `[16]` and `[18:23]` and moves the period-1 end to the old period-2 end; turning it on restores both windows.
- Turning the screensaver off clears only `[0]` bit 7; the screen timeout `a4[15..16]` doesn't move.
- Gen 2's `0091` is this setter, not the app's `setLocale` of other models.

```
4091  a1 01 21 | a2 02 01 82                                                      screensaver on, Theme 3
4091  a1 01 21 | a8 03 02 e001 | a9 03 02 3804 | ab 02 01 01 | ac 02 01 00 | ad 02 01 00 | ae 03 02 3804 | af 03 02 6405
          period 1 08:00–18:00, period 2 on, both at 5 %, period 2 18:00–23:00
4091  a1 01 21 | aa 02 01 24                                                      Wednesday and Saturday

4092  a1 01 21
4892  00 | a1 01 31 | a2 11 04 82 00 00000000 00000000 01 e001 3804 00 | a3 01 04
          da[0..15]: screensaver on + Theme 3, no download, theme id 0, size 0, 24 h, period 1 08:00–18:00, no days;
          a3 01 04 = no theme name
```

The app sends `4092` when its device settings page opens.

### Expansion switch and locate (`4104`)

C2000 Gen 2.

```
4104  a1 01 21 | a2 02 01 01 | a3 12 00 "APCDKJM0000000001" | a5 02 01 01      locate blink
4104  a1 01 21 | a2 02 01 01 | a3 12 00 "APCDKJM0000000001" | a4 02 01 00      expansion output off
```

- `a3` the expansion serial (type `00`), `a4` the expansion output switch (1 on, 0 off), `a5` a one-shot locate blink that stops by itself after 5–10 s.
- **An "off" doesn't latch:** the expansion's contactor logic re-closes it about 2 s later, so `c0[28]` reads 0 for one or two frames and returns to 1 (A1783 with a BP2000).

### OTA precheck (`4089`) and its push (`0489`)

```
4089  a1 01 21
4889  00 | a1 01 31 | a2 02 01 01 | a3 02 01 00 | a4 02 01 28 | a5 02 01 0f | a6 02 01 0f | fd 10 00 "1767225600000" 00 00
          a2 otaEnable 1 · a3 reason 0 · a4 rebootTime 40 s · a5 wifiOTATimeOut 15 min · a6 bleOTATimeOut 15 min ·
          fd the last request fd (15-byte buffer: type, 13 digits, 2 NUL)

0489  a1 01 34 | a2 02 01 01 | a3 02 01 00 | a4 02 01 2d | a5 02 01 0f | a6 02 01 0f      unsolicited, a4 45
```

| state | `a2` / `a3` |
|---|---|
| in upgrade mode | 1 / 0 |
| main SoC < 6 %, or an attached expansion's SoC < 6 % | 0 / 2 |
| BMS in boot mode (SoC unreadable): mains lead in | 1 / 0 |
| BMS in boot mode: mains lead out | 0 / 4 ("connect AC") |
| otherwise | 1 / 0 |

- The app refuses the upgrade when `a2` = 0.
- The device pushes `0489` whenever the pair changes (A1783: in the second the charging expansion's SoC went 5 → 6 %).
- anker-solix-api maps an A1763 `0889` (on MQTT about every 300 s) with `a4`–`a6` unnamed: they are this reply's `rebootTime` and the two timeouts.

### Daily update-check window (`4072`)

Once a day, at a random minute between `a3` and `a4` (minutes of the day), the unit asks the cloud over MQTT whether a firmware update is available. The handler reads fixed offsets, so send the fields in this order and width:

```
4072  a1 01 21 | a2 02 01 <state> | a3 05 03 <u32 LE start minute> | a4 05 03 <u32 LE end minute>
4872  00 | a1 01 31
```

- `a2 00` turns the daily check off.
- The check runs only while the module is connected, main SoC > 5 %, the expansion is absent or > 5 %, and no update is running.
- The app's setting: `a2 00, a3 180, a4 240` (03:00–04:00).

### BLE OTA (`4063`, `4064`)

The app's BLE firmware path (`WifiBleParallelOtaLogic`) sends the image in 204-byte chunks.

```
4063  a1 01 21 | a2 05 03 69ae1b00 | a3 02 01 0a | a4 03 02 cc00 | a5 03 02 bd22 | a6 02 01 01 | a8 02 01 01 | fe 05 03 00b95569
          a2 total size 1 814 121 · a3 10 · a4 chunk 204 · a5 8893 chunks · a6 flag bits · a8 01
4863  00 | a1 01 31 | a2 03 02 cc00                     packet size 204
4064  a2 u16 index · a3 data
4864  <status> | a1 01 31 | a2 03 02 <u16 next index>   every 8 packets and on the last
0864  12 …                                               receive timeout: resend from the index
```

| status | meaning |
|---|---|
| `00` | continue |
| `10` | complete |
| `11` | flash info wrong (the image failed its final check) |
| `12` | resend from the index; sent on a 1500-tick receive timeout up to 10 times, then the display board resets |

- **`4063` enters upgrade mode** outside it, even with no fields: `a3[0]` reads 5, `c490` stops, the display stays on and USB-C 2 output is off. **After 15 min without OTA data the display board resets.** Inside upgrade mode `4063` only replies. Treat `4063`–`4065` as state-changing.
- On first entry a blocking 64 KB flash erase precedes the reply, so the first `4063` may draw no reply within 5 s.
- Packet size = (MTU − 46) & ~3, MTU being ATT MTU − 3: 253 → 204 (`a3[8:10]`).
- `4064` before a `4063` draws nothing.
- Telemetry continues during the transfer, so it isn't evidence that the update applied. The app reports a BLE OTA as failed even when it applies: the link drops for the reboot about 43 s after the 100 % result, and the app then logs an OTA error and a decryption failure on the reconnect (A1783).
- The device pushes `0406` (OTA progress: `a3` percent 10 → 100, `a4[0]` result; app `transferProgress`).

### Log upload (`4065`, `4066`)

```
4865  00 | a1 01 31 | a3 05 03 <u32 total bytes> | a4 05 03 <u16 chunk size fa00> 00 00 | a5 05 03 <u32 chunk count>
4066  <u16 chunk index at payload offset 6>
4866  … | a2 03 02 <index> | a3 03 02 <length> | a4 <length+1> 04 <data>      chunk 0 = CSV header
```

### Event report (`4425` / `0425`)

Device-initiated (app `ReportPpsEventInfo`), on BLE as `4425` and on MQTT as `0425`. Body: `a1 01 <routing>` (`12` while cloud-bound, else `31`; sent on BLE either way), `a2 02 01 <event>`, then up to three `<tag> <len> 04 <data>` fields.

| event | trigger | `a3` | `a4` |
|---|---|---|---|
| `07` | Storm Guard (auto) window started | window start, u32 LE | window end, u32 LE |
| `08` | Storm Guard window ended | 0 | 0 |
| `0a` | Fast Charging Plan (manual) window started | window start | window end; `ffffffff` = no end |
| `0b` | Fast Charging Plan window ended | 0 | 0 |
| `59` | AC grid loss, debounced over 4 polls | SoC %, 1 B | — |

```
4425  a1 01 31 | a2 02 01 07 | a3 05 04 00b95569 | a4 05 04 10c75569     Storm Guard window 1767225600 → 1767229200
4425  a1 01 31 | a2 02 01 0b | a3 05 04 00000000 | a4 05 04 00000000     Fast Charging Plan window ended
0425  a1 01 12 | a2 02 01 0a | a3 05 04 00b95569 | a4 05 04 ffffffff     Fast Charging Plan on, no end (MQTT)
```

Start vs end compares the newly active window type with the stored one; the epochs are the running window's (the `d9` tail's last pair).

### Event push (`4403`)

Device-initiated (op `0x403`), one frame per event: `a1 01 <routing>`, `a2 02 01 <code>`. Routing is `31` (sent on BLE), or `44` to the cloud while the unit is cloud-bound and on WiFi.

| code | trigger |
|---|---|
| `50` | main SoC ≤ 1 % for 3 BMS updates; re-arms once SoC is above 1 % |
| `52` | main SoC ≤ 10 % for 3 BMS updates; re-arms once SoC is above 10 % |
| `55` | the AC output timer (`4101 a3`) ran out |
| `56` | the car-socket timer (`4102 a3`) ran out |

```
4403  a1 01 31 | a2 02 01 52     main SoC reached 10 % (A1783: in the c421 where a5[2] went 11 → 10)
```

### Module-owned session ops (channel 0x0f, opcode < `0x40`)

Answered by the comms module itself, on `03000f`. Comms module v0.3.0.6 and v0.3.3.0.

| op | function | request | reply |
|---|---|---|---|
| `0x20` | diagnostics | — | `a1`–`a6`, below |
| `0x27` | device auth state | — | `a1` 1 when the module reports bound, else 0; `a2` 0 |
| `0x28` | bind / ready status | — | `a1` ready status (bound and ready) |
| `0x2d` | module OTA status | `a3` optional, unused | none: the module builds `a1` (OTA state 1 running, 2 committed, 3 failed) and never sends it, whatever the request; read progress from the `0x2f` replies |
| `0x2e` | module OTA start / stop | `a3` OTA type string, `a4` app type, `a5` 1 start / 0 stop, `a6` u32 size, `a7` u32 CRC-32, `a8` response interval | `a1` u16 chunk size `(mtu − 33) & ~3`; `01` when `a3` is missing or matches neither OTA type |
| `0x2f` | module OTA data | `a1` u16 index, then `a2` u16 length + chunk | statuses below |
| `0x30` | firmware versions | — | below |
| `0x35` | exit cloud bind | — | `00`; **not read-only**, below |
| `0x36` | fast-pair list | `a3` u8 count, then per entry a PN (≤ 8 B) and a 6-byte MAC on consecutive tags from `a4`; the stored list is cleared first | none when well-formed; `04` when the count is ≥ 11 or a pair is missing |
| `0x38` | server-connect config | — | `04` on a bare request |

Bare requests (`a1 01 21` only) and their replies:

```
4827  00 | a1 01 00 | a2 01 00
4828  00 | a1 01 00
482e  01
482f  04
4835  00                 and the cloud bind is exited (below)
4836  04
402d  (no reply)
```

**`0x20` diagnostics:**

```
4820  00 | a1 01 03 | a2 01 03 | a3 04 00000000 | a4 04 02000000 | a5 04 16020000 | a6 04 00000000
```

| tag | width | field (module log name) | example |
|---|---|---|---|
| `a1` | u8 | `sys_reboot_code`: the ESP-IDF reset reason (`3` = software reset) | 3 |
| `a2` | u8 | `sdk_reset_code`: the vendor SDK reboot reason | 3 |
| `a3` | u32 LE | `http_err_code` (cloud bind HTTP result) | 0 |
| `a4` | u32 LE | `wifi_err_code`: the last station disconnect reason (ESP-IDF `wifi_err_reason_t`: `ca` = 202 AUTH_FAIL, `02` AUTH_EXPIRE; 0 once connected) | 2 AUTH_EXPIRE |
| `a5` | u32 LE | `ble_distconnect_code`: `0x200` + the HCI reason (`213` remote user terminated, `216` local host terminated) | `216` |
| `a6` | u32 LE | `mqtt_err_code` | 0 |

`a1` / `a2` are captured at boot and read `ff` after the first request; `a3`–`a6` are current on every request.

**`0x2f` module OTA statuses:**

| status | meaning |
|---|---|
| `00` + `a1` u16 next index | continue; sent every `a8` packets (every packet when `a8` < 2) |
| `01` | no OTA buffer (no `0x2e` start) |
| `04` | `a2` missing after `a1` (a bare request) |
| `10` | module image accepted (last packet of a module self-update) |
| `11` | module image failed to finalize: validation failed or the boot-partition switch failed |
| `12` + `a1` expected index | an index ahead of the expected one: resend from `a1` |
| `14` + `a1` index | the chunk write failed |

- A well-formed packet with no `0x2e` start running is dropped with no reply; an index behind the expected one is dropped too.
- `0x2e` with `a5 1` and a matching type erases the OTA partition and puts the display board into upgrade mode, as `4063` does; `a5 0` aborts a running update.

**`0x30` versions** (A1783):

```
4830  00 | a1 08 "v0.3.3.0" | a2 08 "v1.2.1.6" | a3 09 "A1783_low" | a4 0d "A1783_mcu_low" | a5 0f "A1783_esp32_low"
          a1 module fw · a2 MCU fw · a3 main OTA type · a4 MCU OTA type · a5 ESP32 OTA type
```

The module's own replies use untyped tags (`tag len value`, no type byte).

**`0x35` exit bind.** Reads no payload and checks no authorization. While the WiFi station is connected it publishes a cloud unbind request; while it isn't, it **erases the stored WiFi SSID and password from flash**. Either way the local bind flag goes to 0 (the cloud re-affirms it on its next sync unless it actions the unbind). The BLE authorization is untouched. Don't send it as a probe.

### WiFi provisioning (channels 0x02 / 0x13)

| channel 0x02 op | channel 0x13 op | action | request | reply |
|---|---|---|---|---|
| `0x30` | `0x22` | start scan | `a3` scan parameter | status (`00 a1 01 09` seen) |
| `0x31` | `0x23` | scan list | — | the list |
| `0x32` | `0x24` | connect | `a3` SSID ≤ 32 B, `a6` password ≤ 64 B, both required | status; `04` when either is missing |
| `0x33` | `0x25` | cloud bind / activate | `a2` account, `a3` domain, `a4` time zone (all required); `a6` app id, `a8` time id, `ab` app token | status; `04` missing, `01` no serial |

The channel-0x13 set also answers on channel 0x0f. A WiFi re-provision (connect + bind) also refreshes the cloud flag that gates `c490` ("When c490 posts").

### c490

A protobuf statistics frame, every 540 s, inside a TLV wrapper. The display-board build writes the same layout on all four models; the pack values come from each pack's BMS.

```
a1 01 31
a2 <u16 LE length> 04 <protobuf>          the length is 2 bytes: a2 55 02 = 0x0255 = 597 (type byte + protobuf)
a3 1c 04 "charging_pps_series_c_0009" 00  schema name, NUL-terminated
```

Split `a2` on its declared length before walking the protobuf. On the wire it arrives as `ff09` fragments of up to 253 B: `_0005` in two, `_0009` in three (253 + 253 + 174). `c490` never appears on MQTT `param_info`.

| schema (`a3`) | display-board build | frame |
|---|---|---|
| `charging_pps_series_c_0002` | v1.0.4.3 | no `.23` block |
| `_0005` | v1.2.1.1 | 371–382 B; carries `.1` = `"A1763"` (a literal on every model) and an empty `.2` |
| `_0009` | v1.2.1.6 | 626–638 B; adds `.14.15`–`.14.32`; no `.1` / `.2` |

Select the field map by `a3`. In `_0005` frames the expansion slot `.14#1.2`–`.6` repeats the main pack's values with an expansion attached, and `.14.2`, `.14.5`, `.14.6` read 0. Paths below are protobuf field numbers; `#1` is the second occurrence of a repeated field (slot 0 main, slot `#1` expansion).

#### When c490 posts

The display board posts `c490` only while all of these hold:

- a BLE client is connected, or the unit is bound and on WiFi; bound and on WiFi it posts to the cloud instead (op `0x401`, `a1 1a`), with no BLE notify;
- the cloud's device-point flag is on;
- the unit isn't in upgrade mode.

The device-point flag:

| property | behaviour |
|---|---|
| storage | display-board RAM, 0 after every reset, never saved |
| source | the comms module, from a cloud fetch: the cloud's value on success, 0 on a cloud error |
| fetch triggers | module boot with WiFi up, a successful WiFi bind, and a 30-minute timer while bound and on WiFi |
| offline | no fetch; the flag stays as it is |
| BLE | no path sets it |

| event | c490 (A1783) |
|---|---|
| display-board reset | stops until the next successful cloud fetch |
| the module joins WiFi while a BLE client is connected and the cloud fetch fails (e.g. WiFi without internet) | stops within 0–7 min; `a3[7]` leaves 100 during the attempt |
| `4057 a2 00` | stops (over an hour seen) |
| a WiFi re-provision from the app (channel 0x02 / 0x13 connect + bind) | back within seconds |
| the next successful 30-minute fetch | back |
| `4057 a2 01` re-sends, new BLE sessions | no effect |

With a BLE client connected the module still joins WiFi for about 30 s every 20–40 min, and sometimes stays joined for hours (`a3[7]` < 100) (A1783).

#### Worked example: `.23` and slot summary (`_0009`, A1783)

Same session as the `c421` example above (main 81 % discharging 1 W, expansion 5 %, AC input disabled):

| path | value | reading |
|---|---|---|
| `.23.1` / `.23.1#1` | 81 / 5 | main / expansion SoC % |
| `.23.2` / `.23.3` | 0 / 0 | output total / AC output, W |
| `.23.4` / `.23.5` / `.23.6` | 0 / 0 / 43 | input total / DC input W / DC input voltage 0.43 V |
| `.23.7` | 0 | workStatus |
| `.23.8` | 3100 | remaining time 310.0 h |
| `.23.9` / `.23.10` | 1216 / 330 | MCU v1.2.1.6 / module v0.3.3.0, packed decimal |
| `.14.18` / `.14#1.18` | 818 / 56 | displayed SoC 81.8 % / 5.6 % |
| `.14.3` / `.14.4` | 8212 / 6716 | main cumulative charge / discharge, 821.2 / 671.6 Ah |
| `.14.5` / `.14.6` | 1000 / 20 | main SoH 100.0 %, 20 cycles |
| `.14.22` / `.14#1.22` | 367 / 392 | learned capacity 36.7 / 39.2 Ah |
| `.14.30` | 18 = `0x12` | USB-C on + AC input reported |
| `.15.3` / `.15.4` | 532 / 532 | main terminal / bus voltage, 53.2 V |
| `.15.5` / `.15.6` | 8 / 9 | main on the bus |
| `.15#1.3` / `.15#1.5` / `.15#1.6` | 473 / 3 / 3 | expansion 47.3 V, off the bus |
| `.15#1.8` / `.15#1.9` | 8192 / 8192 | `0x2000`: expansion at `min_soc` |
| `.22` | 50504 | 540 s intervals powered |
| `.6.7` / `.6.8` | 2103 / 13 | time with AC input lost while the inverter runs / count of those losses |

#### `.23`: live values

| path | field | unit |
|---|---|---|
| `.23.1` / `.23.1#1` | main / expansion SoC | %; floor(`.14.18` / 10), lagging or leading by 1 at a whole-percent boundary |
| `.23.2` | output power total | W |
| `.23.3` | AC output power | W; DC and USB out = `.23.2` − `.23.3` |
| `.23.4` | input power total | W |
| `.23.5` | DC input power | W; AC in = `.23.4` − `.23.5` |
| `.23.6` | DC input voltage | 0.01 V |
| `.23.7` | the on-bus pack's flow state | 0 / 1 / 2, both packs, ±0.3 A for 20 samples; never 5; the expansion's charging 2 reads 0 here |
| `.23.8` | remaining time | 0.1 h, to full or to empty |
| `.23.9` / `.23.10` | MCU firmware (the app's `otaVer`) / module firmware | packed decimal |

There is no per-port breakdown.

#### Counters

| | AC | DC |
|---|---|---|
| discharge path active (540 s units) | `.19.1` | `.19.5` |
| charge path active | `.19.2` | `.19.6` |
| charge energy | `.19.3` | `.19.7` |
| discharge energy | `.19.4` | `.19.8` |

- Energy counters are 0.9 Wh per count: each port's power in W is sampled every 9 s and the sum published / 360. A load that bursts between samples moves the effective Wh per count away from 0.9.
- "Active" counts a path being energised, not energy flowing; delta × 540 s = active seconds.
- `.19.7` meters the DC input port, `.19.8` the DC output.
- `.14.3` / `.14.4` are per-pack 0.1 Ah coulomb counters (charge / discharge); each advances only while its pack is active.
- `.22` counts 540 s intervals while powered; a shortfall against elapsed time bounds the time the unit was off.
- `.24.1` = the settings-session number; a session closes on every orderly power-off or auto-off and on each upgrade-mode entry, not on sleep or a hard power cut.
- `.18` (TOU bin) moves only while a TOU period is active; `.20` / `.21` (the two backup-plan bins) are lifetime totals that move only while a backup-plan window runs.
- The counters live on the device, so a gap in reception costs resolution, not totals: difference the posts on either side.

| kind | fields | read as |
|---|---|---|
| one reading at post time | `.23.1`–`.23.4`, `.14.30`–`.14.32`, `.15.3`, `.15.4`; `.14.29` a running mean over seconds | a single point: it aliases a duty-cycled load |
| energies | `.18`–`.21`, `.19.3` / `.4` / `.7` / `.8`, `.14.3` / `.14.4` | delta ÷ 540 s = mean power (mean current for the Ah counters) |
| on-times | `.19.1` / `.2` / `.5` / `.6` | delta × 540 s = active seconds |

`c421` port powers are pushed on change and carry a load's shape; the `c490` counters carry its average.

#### `.14`: per-pack BMS

`.14` is the main pack, `.14#1` the expansion. The second block is always present, keeping its last or boot content when nothing is attached: gate on `c0[30]`.

| path | meaning |
|---|---|
| `.14.1` | 32-byte pack status array (below) |
| `.14.2` | second SoC value, 0.1 % |
| `.14.3` / `.14.4` | cumulative charge / discharge, 0.1 Ah |
| `.14.5` | SoH, 0.1 %, from learned capacity ÷ 40 Ah: ≤ 70 % equal to the ratio, 70 → 85 % mapped linearly to 70 → 100 %, ≥ 85 % = 100 % |
| `.14.6` | cycle count = floor(`.14.3` / 400) |
| `.14.15` | 16 × u16 LE cell voltages, mV (LiFePO4 16S, 2.5–3.65 V window) |
| `.14.16` | 4 × u16 LE temperatures, 0.1 K (3009 = 27.8 °C) |
| `.14.18` | displayed SoC, 0.1 % (what the app shows) |
| `.14.19` | the SoC estimator's output, 0.1 % |
| `.14.20` / `.14.21` | max-cell / min-cell OCV integrals, 0.1 % |
| `.14.22` | learned capacity, 0.1 Ah |
| `.14.23` | cell-balancing bitmap |
| `.14.24` | unusable-capacity reserve, 0.1 %: at rest about 34.9 − 1.02 × the pack's minimum temperature in °C; falls while the pack warms under charge |
| `.14.25` / `.14.26` | page 0–3 / whole hours of four per-pack counters (below) |
| `.14.27` | 1 while capacity learning is armed (minimum cell < 3251 mV for ≥ 5 s at rest); cleared 36 h later or when a learn completes |
| `.14.28` | 32 zero bytes |
| `.14.29` | net pack current, 10 mA, zigzag-encoded signed varint (even raw = positive): positive charging, negative discharging |
| `.14.30` | port-status bits (below), the same in both blocks |
| `.14.31` / `.14.32` | input / output power, W |

- **SoC.** `.14.18` is what the app shows; `.14.2` and `.14.19`–`.21` are the raw cluster. At rest with a cell below 3251 mV the BMS resets its SoC integrals to the OCV-table value (18.0 % at 3250 mV), so the expansion's raw values can sit tens of points from `.14.18`, and `.14#1.2` can read 0 for 10+ h while `.14#1.18` reads 6–13 % (A1783).
- An idle pack's displayed SoC can settle by a few points with no discharge; check `.14.4` before reading a falling idle SoC as consumption.

**`.14.30` bits:**

| bit | meaning |
|---|---|
| `0x01` | PV / DC input present (2 s debounce) |
| `0x02` | AC input as the power stage reports it (follows `a7[3]` into the next post) |
| `0x04` | 12 V car output on |
| `0x08` | AC inverter on |
| `0x10` | USB-C on |
| `0x20` | USB-A on |
| `0x40` | unused |
| `0x80` | a TOU period is active and no backup plan runs |

Seen: `0x1a` USB-C + inverter + AC in; `0x12` / `0x10` USB-C (+ AC in); `0x32` / `0x30` USB-A + USB-C (+ AC in).

**`.14.25` / `.14.26` pages.** The page advances every 360 s, so 540 s posts land 1.5 pages apart. Each counter counts seconds, including slept time.

| page | reads as |
|---|---|
| 0 | hours since the last charge ended |
| 1 | hours since last full |
| 2 | hours since the last OCV recalibration |
| 3 | hours since boot |

**`.14.1` status array**, bytes a client can use (`<byte>.<bit>`, bit 0 = LSB):

| byte | meaning |
|---|---|
| 4 | `4.6` discharge < 1.0 A, `4.7` discharge > 2.0 A: `75` at rest, charging, or discharging under 1 A; `35` discharging 1–2 A; `b5` over 2 A |
| 9 | `9.3` = 1 on the main unit, 0 on the expansion (confirms the slot order) |
| 12 | alarm flags; reads `52` or `1e` |
| 13 | the pack-selection byte of that node: low nibble active pack (1 main, 2 expansion), high nibble direction (1 charge, 2 discharge); the expansion's own copy stays `01` |
| 18 | `18.4` = the link to the display board is alive |
| 30 | 1 when the BMS's cell-monitor I2C bus has failed 250 recoveries in a row |
| 3, 10, 11, 19, 25–27 | always 0 |

The two slots differ by node role (`9.3`, `6.0`, `6.2`), so compare slot against slot before comparing over time.

#### `.15`: bus and pack selection

| path | meaning |
|---|---|
| `.15.1` | that pack's BMS firmware, packed decimal (1933 = v1.9.3.3) |
| `.15.3` | that pack's terminal voltage, 0.1 V |
| `.15.4` | the bus voltage, 0.1 V (one node, read by both slots) |
| `.15.5` | that pack's stage-A state: `8` inside floor-to-cap and at the floor; `3` at or above `max_soc`; `13` on the expansion slot at the cap while quiet |
| `.15.6` | that pack's stage-B state: `9` on the bus, `3` off |
| `.15#1.8` / `.9` | `0x2000` while the expansion sits at `min_soc` |

- The off-bus slot reads `.15.5` / `.15.6` = 3 / 3. `.15.5` isn't a charge / discharge indicator (it reads 8 charging at 1.2 kW and discharging at 73 W).
- At the cap, 8 means current is flowing; 3 and 13 hold only while quiet. A pack-side discharge ≥ 0.3 A for 2 s lifts the expansion from 13 to 8.
- `.15.4` identifies the driving pack only under load: in states 3 and 13 the bus reads 0.4–0.6 V below the on-bus terminal; at 8 the two agree within 0.1 V.

### Pack selection

C2000 Gen 2 with a BP2000 attached (A1783). The packs are switched onto one bus, never paralleled.

| policy | behaviour |
|---|---|
| charge | main first to `max_soc`, then the expansion. A charge start moves the bus to the pack that will take charge |
| discharge | expansion first to `min_soc`, then the main |
| last pack at the floor | output stops; a pack already below `min_soc` is not brought back |
| losing eligibility | the pack is dropped after 3 s, mid-discharge, with no break in output |
| main → expansion for discharge | needs 100 discharge steps plus a ≥ 1.0 % SoC drop on the main, and > 2 s since the last switch |
| `min_soc` | a slot-selection lever, not checked against a pack's current SoC |

- The charge-side handover is a live step down in bus voltage (e.g. 54.9 → 51.3 V as charge moves from a 98 % main to a 6 % expansion); a discharge handover keeps the load continuous.
- With main 100 %, expansion 56 % and the unit idle, `4103 aa 02 01 64 · ab 02 01 3c` (floor 60) makes the expansion ineligible: the next `c490` shows the main on the bus. There is no rejection or warning; the expansion's charge is stranded until the floor is lowered, and even then the main keeps the bus until its own SoC has dropped ≥ 1.0 %.

### Battery-Only Power at the floor

With Battery-Only Power on (`4101 ab`) and mains plugged in, the packs discharge as if off-grid. When the main pack reaches `min_soc`, the firmware drops the mode and charges from mains. It fires when the main pack's SoC falls below `min_soc` + 0.9 % (or, as a separate backstop, a cell below 1.8 V), and releases once SoC is back above `min_soc` + 0.9 %; each change holds for two BMS updates first. A1783, `min_soc` 5, the expansion already at its floor:

| t | event |
|---|---|
| 0 | main 6 → 5 % |
| +54 s | `dc` = 3 (low battery) with its epoch; `a4[31]` `06` → `0a` (auto-off); `a7[3]` 2 → 1; `a5[1]` 1 → 0; output (`a6[0:2]`) → 0 W |
| +58 – 63 s | AC input 96 → 609 → 1 227 W; `a3[0]` → 2 |
| +98 s | main 5 → 6 % |
| +99 s | `dc` cleared; `a4[31]` → `02` |
| +102 s | output back |

- Output stays off for the whole span `dc` reads 3 (here 45 s), however much mains charge flows; it returns once the main pack's SoC is above `min_soc`.
- The mode stays off afterwards (`a4[31]` `02`): the unit then charges from mains like a normal grid-connected unit, main first to `max_soc`, then the expansion ("Pack selection").
- The `4403` code `52` arrives earlier, at 10 % ("Event push").

### Firmware updates

| path | behaviour |
|---|---|
| WiFi (cloud) | the app sends one MQTT command carrying only the serial and account; the device fetches its own manifest and reports `{progress, mcuResult, bmsResult}` every ~2 s. Reboot wait 40 s, timeouts 15 min |
| BLE (app) | the image in 204-byte chunks on `4063` / `4064` (above); 1 814 121 B take about 8 min 20 s at MTU 253 (A1783). Telemetry continues throughout |
| module self-update | channel 0x0f `0x2e` / `0x2f` (above) |

- `workStatus 5` spans the whole update, MCU, BMS and module included.
- The OTA manifest labels expansion children `A1783_2kWh` (BP2000) and `A1783_3kWh` (BP3000); the device picks the child by the attached pack type.
- The DCDC and ACDC slots of `f9` report v0.1.2.6 across updates; the version labels arrive in stages after an update (`f9`, above).

Firmware sets seen together on the A1783:

| MCU | BMS | expansion BMS | module | c490 schema |
|---|---|---|---|---|
| v1.0.4.3 | v1.1.3.3 | — | v0.2.7.5 | `_0002` |
| v1.2.1.1 | v1.9.2.2 | v1.1.3.3 (the BP2000 as shipped) | v0.3.0.6 | `_0005` |
| v1.2.1.1 | v1.9.2.2 | v1.9.2.2 | v0.3.0.6 | `_0005` |
| v1.2.1.6 | v1.9.3.3 | v1.9.3.3 | v0.3.3.0 | `_0009` |

### Cloud-side frames (MQTT)

The same TLV frames travel over MQTT with flag nibble 0, base64-encoded in a JSON envelope (`payload.data`). Topics use the model's PN (`A1763`, `A1783`, …).

| topic | content |
|---|---|
| `dt/anker_power/<PN>/<sn>/param_info` | `0421` telemetry, `a1 34`, `head.cmd = 16`; the same tag set as `c421` |
| `dt/anker_power/<PN>/<sn>/state_info` | `0413` OTA upgrade state, `0425` events, `0503` energy totals, the command acks (`0857`, `085e`, `0872`, `0890`, `0891`, `0901`–`0903`: `00 a1 01 32`), and the module's JSON heartbeat `{version, battery, rssi, ssid, bssid, ip}` |
| `cmd/anker_power/<PN>/<sn>/req` | cloud → device commands |

**`0413` OTA upgrade state** (app `postUpgradeStateReq`), after an expansion update (A1783):

```
a1 01 12
a2 1c 06 | 11 "APCDKKE0000000001" | bb04 bb04 | 3201 3201 | 01       main unit: u16 pairs 1211 → 1211, 306 → 306 (unchanged), 01
a3 02 01 01
a4 22 06 | 11 "APCDKJM0000000001" | 6d04 8207 | 0a "A1783_2kWh"     expansion: u16 1133 → 1922 (v1.1.3.3 → v1.9.2.2), OTA type
a5 04 04 04 04 04                                                  per-component result bytes
```

**`0503` energy and TOU-time totals**, sent only while cloud-bound (never on BLE):

```
a1 01 12
a2 19 04 | u32 [0] | u32 [4] | u32 [8] | u32 [12] | u32 [16] | u32 [20]
a3 05 03 | u32 Time Save
```

| `a2` offset | name | unit | accumulates every 10 s while a TOU period is active |
|---|---|---|---|
| `[0]` | SolarToBatt | Wh | min(DC input, pack charge power) while charging |
| `[4]` | GridToBatt | Wh | pack charge power − DC input, while charging with DC input below it |
| `[8]` | BattToLoad | Wh | pack power while not charging |
| `[12]` / `[16]` / `[20]` | Peak / OffPeak / SuperOffPeak | s | +10 in the active period type 1 / 2 / 3 |

They are lifetime totals, persisted to flash every 2 h, and stay flat while Time-of-Use is off. `a3` Time Save = the clock at the last persist.
