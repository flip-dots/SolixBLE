# SOLIX Solarbank, smart plug and smart meter

The Solarbank balcony and home storage systems, the A17X8 smart plug and the A17X7 smart meter use the first-generation command style: one `00xx` opcode per function, a `0057` realtime trigger, and telemetry pushed as `0405` (BLE `c405`). Framing and negotiation are in [framing.md](framing.md) and [negotiation.md](negotiation.md).

No unit of these families has been captured for this documentation. Every table names its basis: a SolixBLE test frame (Harvey's), the anker-solix-api map (Thom's, built from MQTT captures), or the Anker app's code. Placeholders are those in [README.md](README.md); this file adds the Solarbank 2 serial `APCGQ80000000001` (16 B).

## ⚠ Hazard: `005e` schedules on the Solarbank 2

A Solarbank 2 accepts the legacy confer with no account check, and a Solarbank 1 schedule (`405e`) sent to it after that confer factory-resets it. Never send `005e` schedule frames to a Solarbank 2, and treat the legacy confer on it as destructive. The app drives schedules and usage modes through the cloud; anker-solix-api keeps its `005e` description for decoding only.

## Models

| model | name | basis |
|---|---|---|
| A17C0 | Solarbank E1600 (Solarbank 1) | anker-solix-api, app code |
| A17C1 | Solarbank 2 E1600 Pro | SolixBLE test frame, anker-solix-api, app code |
| A17C2 | Solarbank 2 E1600 AC | anker-solix-api, app code |
| A17C3 | Solarbank 2 E1600 Plus | anker-solix-api |
| A17C5 | Solarbank 3 E2700 Pro | anker-solix-api; SolixBLE (from anker-solix-api data, untested) |
| A17X8 | smart plug | anker-solix-api, a third-party device test, app code |
| A17X7 / A17X7US | smart meter / US smart meter | anker-solix-api, app code |

Model names are anker-solix-api's. The app runs the Solarbank 3 on its Solarbank 2 controller class (app code).

## Solarbank 2 (A17C1)

### Session

- 2026 firmware negotiates cleartext ECDH, the C1000's shape (`0803 a3 44 · a4 01 · a5 02`; `0829` `"ESP32"`), then an AES-128-CBC session (key `ss[:16]`, IV `ss[16:32]`, PKCS7).
- 2025 firmware sent cleartext telemetry: `8405` fragments and `0409`, with no encryption flag.
- Telemetry arrives as `c405` in three fragments: frames of 253, 253 and 39 B, each fragment's first payload byte `(index << 4) | count` = `13`, `23`, `33`. Reassemble the ciphertext first, then decrypt: 511 B of cleartext.
- The device also pushes `4409` = `a1 01 31 · a2 02 01 00 · a3 02 01 2f`.

### Telemetry (`c405`)

On this firmware the BLE `c405` differs from anker-solix-api's `0405` map in seven tags (`a5`, `a7`, `b6`, `c2`, `c9`, `ca`, `cb`: type or length), so SolixBLE's `Solarbank2` map is the one to use on BLE. Both names are given; scales are SolixBLE's.

| tag | type | field | SolixBLE | anker-solix-api |
|---|---|---|---|---|
| `a2` | string | serial | `serial_number` | `device_sn` |
| `a3` | u8 | SoC % (this unit's battery) | `battery_percentage` | `main_battery_soc` |
| `a5` | u16 | error code | `error_code` | `error_code` |
| `a6` / `a7` / `a8` | 4 B | firmware / controller / expansion versions; `a8` 0 with no expansion | `software_version` / `_controller` / `_expansion` | `sw_version` / `sw_controller` / `sw_expansion` |
| `a9` | u8 | temperature unit, 0 °C / 1 °F | `temperature_unit` | `temp_unit_fahrenheit` |
| `aa` | u8, signed | temperature °C | `temperature` | `temperature` |
| `ab` | u32 | solar input, 0.1 W | `solar_power_in` | `photovoltaic_power` |
| `ac` | u32 | AC output, 0.1 W | `ac_power_out` | `ac_output_power` |
| `ad` | u8 | SoC %, expansions included | `battery_percentage_aggregate` | `battery_soc` |
| `b0` | u32 | battery charge power, 0.01 W | `battery_charge_power` | `bat_charge_power` |
| `b1` | u32 | solar yield, 0.0001 kWh | `pv_yield` | `pv_yield` |
| `b2` | u32 | charged energy, 0.00001 kWh | `charged_energy` | `charged_energy` |
| `b3` | u32 | output energy, 0.0001 kWh | `output_energy` | `output_energy` |
| `b4` | u8 | output cut-off SoC % | `output_cutoff_data` | `min_soc` |
| `b5` | u8 | low-power input threshold | `lowpower_input_data` | `lowpower_input_data` |
| `b6` | u8 | input cut-off SoC % | `input_cutoff_data` | `active_charge_soc` |
| `b7` | u32 | battery discharge power, 0.01 W | `battery_discharge_power` | `bat_discharge_power` |
| `bc` / `bd` | u32 | grid → home / PV → grid, 0.1 W | `grid_to_home_power` / `pv_to_grid_power` | same |
| `be` / `bf` | u32 | grid import / export energy, 0.0001 kWh | `grid_import_energy` / `grid_export_energy` | same |
| `c2` | u16 | maximum load: 350 / 600 / 800 / 1000 W | `max_load` | `max_load` |
| `c4` | u32 | house demand, 0.1 W | `house_demand` | `home_demand` |
| `c6` | u8 | usage mode (below) | `usage_mode` | `usage_mode` |
| `c7` | u16 | home load preset, W; 0 = "0 W" mode | `home_load_preset` | `home_load_preset` |
| `c8` | u32 | AC sockets, 0.1 W | `ac_power_out_sockets` | `ac_socket_power` |
| `c9` | u32 | consumed energy, 0.0001 kWh | `consumed_energy` | `consumed_energy` |
| `ca`–`cd` | u32 | PV inputs 1–4, 0.1 W | `solar_pv_1_power_in` … `_4_` | `pv_1_power` … `pv_4_power` |
| `d2` | u8 | light mode: 0 normal, 1 mood | `light_mode` | `light_mode` |
| `d3` | u32 | output power, 0.1 W | `power_out` | `output_power` |
| `e0` | u8 | grid status | `grid_status` | `grid_status` (1 OK, 3 connecting, 6 no grid) |
| `e1` | u8 | light off switch: 1 off, 0 on | `light_on` = not `e1` | `light_off_switch` |
| `e8` | u8 | battery heating | `battery_heating` | `battery_heating` (1 not heating, 3 heating) |
| `eb` | u8 | maximum SoC % | — | `max_soc` |
| `fb` | u32 | `[0]` bit 0: grid export disabled | — | `grid_export_disabled` |
| `fe` | u32 | clock | — | `msg_timestamp` |

- `c7` = 0 is the whole "0 W" mode: `ac` and `c4` drop to 0 with it, `c6` doesn't change, and `fb` / `fc` stay the same (a third-party device test on an A17C1).
- `fc` is a constant 21-byte capability array.
- The app's parser (app code) also reads `a4` (a second SoC), `ae`, `af`, `b8`, `b9` (self-test enabled), `ba` (a percentage, ÷ 100), `bb` (heating power), `e9` (battery capacity).

### Worked example: Solarbank 2 `c405`

A SolixBLE capture, 511 B of cleartext: battery 58 %, no solar, discharging 50 W to the home in manual mode.

```
a1 01 31                       routing: device → BLE
a2 11 00 "APCGQ80000000001"    serial
a3 02 01 3a                    SoC 58 %
a4 02 01 01                    (app: second SoC value)
a5 03 02 0000                  error code 0
a6 05 03 0100060a              firmware
a7 05 03 00000631              controller firmware
a8 05 03 00030306              expansion firmware
a9 02 01 00                    °C
aa 02 01 11                    temperature 17 °C
ab 05 03 00000000              solar input 0 W
ac 05 03 f4010000              AC output 500 = 50.0 W
ad 02 01 3a                    aggregate SoC 58 %
ae 02 01 00 · af 02 01 00      (no field)
b0 05 03 00000000              charge power 0 W
b1 05 03 e0bd0200              solar yield 179680 = 17.968 kWh
b2 05 03 723c0a00              charged energy 670834 = 6.70834 kWh
b3 05 03 8d840200              output energy 165005 = 16.5005 kWh
b4 02 01 05                    output cut-off 5 %
b5 02 01 04                    low-power input 4
b6 02 01 05                    input cut-off 5 %
b7 05 03 88130000              discharge power 5000 = 50.00 W
b8 02 01 01 · b9 02 01 00 · ba 05 03 28000000 · bb 02 01 00     (no field: 1, 0, 40, 0)
bc bd be bf 05 03 00000000     no grid flow, no grid energy
c0 11 00 00×16                 (empty string)
c1 02 01 00                    (no field)
c2 03 02 2003                  maximum load 800 W
c4 05 03 f4010000              house demand 50.0 W
c5 02 01 00                    (no field)
c6 02 01 01                    usage mode 1 (manual)
c7 03 02 3200                  home load preset 50 W
c8 05 03 00000000              AC sockets 0 W
c9 05 03 06000000              consumed energy 0.0006 kWh
ca cb cc cd 05 03 00000000     PV inputs 1–4: 0 W
d2 02 01 00                    light mode normal
d3 05 03 f4010000              output power 50.0 W
d4 … df                        six empty 16-byte strings, each followed by a u16 0
e0 02 01 02                    grid status 2
e1 02 01 01                    light off
e2 … e9 02 01 00               (no field)
ea 02 01 01                    (no field)
fe 05 03 00b95569              clock
fb 05 03 00000000              grid export allowed
fc 16 04 01 01 01 01 00 01 01 01 01 01 01 00×10      capability array
```

## Solarbank commands

Opcodes as anker-solix-api sends them over MQTT (`00xx`); on BLE they carry flag `0x40`. Payloads start `a1 01 22` (MQTT) or `a1 01 21` (BLE) and end with `fe`.

| opcode | function | payload | models |
|---|---|---|---|
| `0040` | status request: one `0405` at once | — | A17C0 |
| `0050` | temperature unit | `a2` 0 °C / 1 °F | all |
| `0056` | status check | `a2` serial, `a3` charging status, `a4` output preset W, `a5`–`a7` timeouts and timestamps | A17C0 |
| `0057` | realtime trigger | `a2` 0 / 1, optional `a3` timeout s | all |
| `005a` | maximum load in a parallel system | `a2` u16 W: 1200, 2400, 3600, 4800; `a3` u16 load type, default 2 | A17C1, A17C2, A17C3, A17C5 |
| `0067` | SoC reserve (older form) | `a2` output cut-off 5 / 10 %, `a3` low-power input 4 / 5, `a4` input cut-off 5 / 10 | A17C0, A17C1, A17C2, A17C3 |
| `0067` | SoC reserve (Solarbank 3 older form) | `a2` 5 / 10 % | A17C5 |
| `0067` | SoC limits (newer form) | `a2` minimum 5–20 % (1–20 on the A17C5), `a5` maximum 80–100 %, `a6` backup SoC, `a7` backup switch | A17C1, A17C2, A17C3, A17C5 |
| `0068` | inverter type and limits | `a2`–`a4` as `0067`, `a5` brand, `a6` model (raw), `a7` / `a8` u16 minimum / maximum load W, `a9`–`ad` | A17C0 |
| `0068` | light | `a2` mode 0 normal / 1 mood, `a3` light off switch 1 off / 0 on; send both | A17C1, A17C2, A17C3, A17C5 |
| `0073` | emergency AC socket | `a2` 0 / 1 | A17C5 |
| `0080` | maximum load and grid export | `a2` u16 W (350, 600, 800, 1000; 1200 also on the A17C2 and A17C5), `a3` u16 load type (0 individual, 2 parallel, 3 single); `a5` u16 0, `a6` u16 disable grid export, `a9` u16 export limit 0–100 000 in steps of 100; `a7` u16 PV limit 2000 / 3600 (A17C5); `a8` u16 AC input limit 0–1200 in steps of 100 (A17C2, A17C5) | A17C1, A17C2, A17C3, A17C5 |
| `0085` | third-party PV support | `a2` 0 / 1 | A17C5 |
| `009a` | device timeout | `a2` = minutes ÷ 30 (0, 30, 60, 120, 240, 360, 720, 1440 min) | A17C5 |

The app's Solarbank command class also names (app code; no device-verified map): `005e` `setBackPower` / `setTacticsTime` / `setPeakValley` (schedules and usage modes, the hazard above), `0071` `setElectricityPrice`, `005f` `setDeviceSelfTest`, `0081` `setDeviceMicroPowerLimit`. The app's `setTacticsTime` schedule (its Solarbank 2 class) holds at most 14 slots, each `{u16 start minute, u16 end minute, u16 power W, u16 SoC %}` with an optional weekday field, and goes out with a CRC32 tag (app code).

### Usage modes (`c6`, `005e a2`)

| value | mode (anker-solix-api) |
|---|---|
| 1 | manual |
| 2 | smart meter |
| 3 | smart plugs |
| 4 | backup |
| 5 | time of use |
| 7 | smart |
| 8 | time slots (48 hourly slots: 1 discharge, 4 charge, 6 default) |

## Solarbank 1 (A17C0)

anker-solix-api `0405` (`param_info`; every ~5 s with `0057`, or once on `0040`):

| tag | field (anker-solix-api) |
|---|---|
| `a2` | serial |
| `a3` | SoC % |
| `a5` | error code |
| `a6` / `a7` / `a8` | firmware / controller firmware / hardware version |
| `a9` | temperature unit |
| `aa` | temperature °C, signed |
| `ab` / `ac` | solar input / output power W |
| `ad` | charging status |
| `ae` | the schedule: a binary structure, per slot u16 LE start and end minutes, a priority limit byte, then the export switch and discharge priority bits |
| `b0` | battery charge power |
| `b1` / `b2` / `b3` | solar yield / charged / output energy, 0.0001 kWh |
| `b4` / `b5` / `b6` | output cut-off / low-power input / input cut-off SoC |
| `b7` / `b8` / `b9` | inverter brand / model / minimum load |
| `c0` / `c1` | the "0 W" switch's serial / Bluetooth MAC |
| `fe` | timestamp |

The app's parser (app code) also reads `bc` / `bd` as an attached sub-device (the A17Y0) and its data.

anker-solix-api `0408` (`state_info`, ~60 s): `a2` serial, `a3` / `a4` local / UTC timestamp, `a5` SoC (0.001), `a6` SoH (0.001), `a8` charging status, `a9` home load preset, `aa` solar power, `ab` charge power, `ac` output power, `b0` SoC %, `b1`–`b5` solar yield / charged / output / discharged / bypass energy (0.0001 kWh), `b6` temperature, `b7` / `b8` / `b9` PV / output / battery voltage (0.01 V).

## Solarbank 2 and 3 cloud frames

anker-solix-api's maps for the other MQTT frames (A17C1 / A17C2 / A17C3; A17C5 where named):

| frame | topic | content |
|---|---|---|
| `0407` | `state_info` | `a2` serial, `a3` WiFi network name, `a4` WiFi signal, `a5` charging status |
| `0408` | `state_info`, ~300 s | local and UTC timestamps, charging status, energy totals, temperature, home demand, PV 1–4, maximum SoC, grid export disabled |
| `040a` | `param_info`, with `0057` | `a2` expansion count, `a3` main battery SoC, then per expansion `a4`–`a8`: `[0:16]` controller serial, `[18]` status, `[19]` temperature (signed), `[21]` SoC, `[22]` SoH, `[27:44]` serial |
| `0500` | `state_info`, ~300 s | per battery `a4`, `a5`…: `[0]` position, `[143]` type (`c1` / `c2` BP1600, `c5` BP2700, `ae` BP5000), `[146:]` controller serial |

The Solarbank 3 `0405` (A17C5, also used for the A17C2) is laid out differently: `a3` main SoC, `a4` battery status, `a5` temperature, `a6` SoC, `a7`–`a9` versions, `ab` solar, `ac` battery power (signed), `ad` output, `ae` AC output (signed), `b0`–`b4` energies, `b5` minimum SoC, `b8` usage mode, `b9` home load preset, `ba[0]` flag bits (`0x40` mood light, `0x20` light off, `0x08` AC socket on, `0x01` °F), `bd` maximum load, `bf` / `c0` backup start / end timestamps, `c4` grid power (signed), `c5` home demand, `c6`–`c9` PV 1–4, `cb` expansion count, `d4` device timeout ÷ 30 min, `d5` PV limit, `d6` AC input limit, `d8[0]` / `[1]` maximum / backup SoC. SolixBLE's `Solarbank3` class reads the anker-solix-api A17C5 `0408` layout (untested).

## Smart plug (A17X8)

| opcode | function | payload (anker-solix-api; `007c` also device-tested by a third party) |
|---|---|---|
| `0040` | status request | — |
| `0057` | realtime trigger | as above |
| `007a` | relay on / off | `a2` 0 / 1 |
| `007c` | schedule | `a2` action 0 delete / 1 create / 2 modify · `a3` slot 1–10 · `a4` 1 enabled / 0 disabled · `a5` time: type `02`, value hour × 256 + minute, so the bytes are minute then hour (20:00 = `a5 03 02 00 14`) · `a6` switch to 0 off / 1 on · `a7` weekdays (below) |
| `007e` | delayed toggle | `a2` mode 0 off / 1 start / 2 paused / 3 running · `a3` delay, 3 bytes seconds : minutes : hours · `a4` the state to switch to, 0 / 1 · `a5` elapsed, 3 bytes seconds : minutes : hours |
| `007f` | timer request | — → `087f` with `a2` = the timer status (below) |

- **Weekdays are a list, not a bitmask:** one byte per day, 1 Monday … 7 Sunday, 1 to 7 bytes (`01 02 05` = Monday, Tuesday, Friday). The Prime chargers' schedules use a bitmask instead ([prime.md](prime.md)).
- The app allows 24 schedules by default; the limit comes from the cloud's `timing_limit` device attribute (app code).
- The app's plug command class also names `0079` `setMomenryPortSwitch`, `007b` (a second countdown command) and `007d` (a request) (app code).

`0405` (`param_info`, anker-solix-api):

| tag | field |
|---|---|
| `a2` | serial |
| `a4` | relay on |
| `a5` | error code (app code) |
| `a6` / `a7` | firmware / controller firmware |
| `a8` | voltage, 0.1 V |
| `a9` | current, 0.01 A |
| `aa` | power, 0.1 W |
| `ab` | output energy, 0.001 kWh |
| `ad` | timer status: `[0:3]` delay seconds : minutes : hours, `[3]` the state to switch to, `[4]` mode (0 inactive, 2 paused, 3 running), `[5:8]` elapsed seconds : minutes : hours |
| `fe` | timestamp |

`a3` reads 0 and `ae` reads 1 in every frame of a third-party device test, schedule or none.

## Smart meter (A17X7)

anker-solix-api `0405` (`param_info`, every ~5 s with `0057`):

| tag | A17X7 | A17X7US |
|---|---|---|
| `a2` | serial | serial |
| `a6` / `a7` | firmware / controller firmware, 4 B | same |
| `a8` / `a9` | grid → home / PV → grid power | — |
| `aa` / `ab` | grid import / export energy, 0.01 kWh | — |
| `b1` / `b2` / `b3` | — | grid power L1 / L2 / total, signed (negative = export) |
| `b4` / `b5`, `b6` / `b7` | — | L1 current / voltage, L2 current / voltage |
| `b8` / `b9` | — | power factor / L1–L2 voltage |
| `ba` / `bb`, `bc` / `bd` | — | system output power L1 / L2 (sign inverted), current L1 / L2 |
| `fe` | — | timestamp |

The app's A17X7 parser (app code) also reads `a3` (OTA in progress) and `a5` (grid power), and `ac` / `ad` as alternate paths to `a8` / `a9`.
