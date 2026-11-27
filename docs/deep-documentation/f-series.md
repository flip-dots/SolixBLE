# SOLIX F-series power stations

The F-series stations (F1200, F1500, F2000, F2600, F3800) speak the first-generation C-series protocol ([c-series.md](c-series.md) "First generation"): one `40xx` opcode per setting, a `4040` status poll, and flat telemetry tags pushed as `c402` / `0405`. The F3800 adds expansion-battery and power-panel frames. Discovery, transports and negotiation are in [discovery-and-gatt.md](discovery-and-gatt.md) and [negotiation.md](negotiation.md).

No F-series unit has been captured for this documentation. Every table names its basis: a SolixBLE test frame (Harvey's), the anker-solix-api map (Thom's), or the Anker app's code. Placeholders are those in [README.md](README.md); this file adds the F2600 serial `AZV3NM0000000001` (16 B).

## Models

| model | name | transport and negotiation | sources |
|---|---|---|---|
| A1770 | F1200 (Bluetooth) | — | app code |
| A1771 | F1200 (Bluetooth and WLAN) | — | app code |
| A1772 | SOLIX F1500 | — | app code (asset pack only) |
| A1780 | 767 PowerHouse / SOLIX F2000 | legacy `1780` transport on older firmware: no negotiation | anker-solix-api; SolixBLE (from anker-solix-api data, untested) |
| A1780P | F2000 with WLAN | — | anker-solix-api (the A1780 maps) |
| A1781 | SOLIX F2600 | `ff09`; SolixBLE drives it on the negotiating transport | SolixBLE test frames; anker-solix-api (the A1780 maps) |
| A1790 | SOLIX F3800 | `ff09`, productType `b106`, no capability byte; legacy confer (`0803 a3 04`, no `a5`) | anker-solix-api; SolixBLE (untested) |
| A1790P | SOLIX F3800 Plus | `ff09`, productType `b112`, capability `04` | anker-solix-api (the A1790 maps) |

Model names are anker-solix-api's. The A1771 is the F1200, not the C1000: the app's A1771 parser reads the same settings tags (`d0`–`de`) as the C1000 (A1761) map, plus its own (below).

## Session

As on the first-generation C-series: requests `a1 01 21 <fields> fe 05 03 <u32 LE epoch>` on `03000f`, replies `00 a1 01 31`, response = request `| 0x0800`. The F3800 streams nothing after negotiation until it receives `4040 a1 01 21` (SolixBLE).

## Commands

| BLE | function | payload | models | basis | name (SolixBLE / anker-solix-api) |
|---|---|---|---|---|---|
| `4040` | status request | `a1 01 21` | F2600, F3800 | SolixBLE | `get_status_update()`; reply `c840` |
| `4042` | AC output timer | `a2 05 03 <u32 LE s>`, 0–86 400 in steps of 300; SolixBLE sends `a2 05 02 <u32 LE s>` (`2c010000` = 300 s) | F2600 | anker-solix-api, SolixBLE | `set_ac_timer(seconds)` / `ac_output_timeout_seconds` |
| `4043` | DC output timer | as `4042` | F2600 | anker-solix-api, SolixBLE | `set_dc_timer(seconds)` / `dc_output_timeout_seconds` |
| `4044` | AC charge limit | `a2 03 02 <u16 LE W>` | F2000, F2600: 100–1440 in steps of 100 (the F2600 app offers from 200); F3800: 100–1800, its maximum per variant in `e6` | anker-solix-api, SolixBLE | `set_ac_charging_power(watts)` / `ac_input_limit` |
| `4045` | device timeout | `a2 03 02 <u16 LE min>`: 0 (never), 30, 60, 120, 240, 360, 720, 1440 | F2000, F3800; the F2600 reports `d2` = 0 and ignores the write | anker-solix-api | `device_timeout_minutes` |
| `4046` | display timeout | `a2 03 02 <u16 LE s>`: 20, 30, 60, 300, 1800 | all | anker-solix-api, SolixBLE | `set_display_timeout(DisplayTimeout)` / `display_timeout_seconds` |
| `404a` / `404b` | AC / DC output | `a2 02 01 <00\|01>` | all | anker-solix-api, SolixBLE | `turn_ac_on()` … / `ac_output_power_switch`, `dc_output_power_switch` |
| `404c` | display brightness | `a2 02 01 <0 off / 1 low / 2 medium / 3 high>` | all | anker-solix-api, SolixBLE | `set_display_mode(LightStatus)` / `display_mode` |
| `404e` | power saving | `a2 02 01 <00\|01>` | F2600 | anker-solix-api, SolixBLE | `turn_power_saving_mode_on()` / `energy_saving_switch` |
| `404f` | LED light | `a2 02 01 <0 off / 1 low / 2 medium / 3 high / 4 blinking>` | all | anker-solix-api, SolixBLE | `set_light_mode(LightStatus)` / `light_mode` |
| `4050` | temperature unit | `a2 02 01 <0 °C / 1 °F>` | all | anker-solix-api | `temp_unit_fahrenheit` |
| `4052` | display on / off | `a2 02 01 <00\|01>` | all | anker-solix-api, SolixBLE | `turn_display_on()` / `display_switch` |
| `4057` | realtime trigger | `a2 02 01 <00\|01>`, optional `a3` timeout s | all | anker-solix-api | `realtime_trigger` |
| `405e` | ultrafast AC charge | `a2 02 01 <00\|01>` | F2000, F2600 | anker-solix-api | `ac_fast_charge_switch` |
| `4076` / `4077` | 12 V / AC output mode | `a2 02 01 <1 normal / 0 smart>`; reported as Normal 1 / Smart 2 | F3800 | anker-solix-api | `dc_12v_output_mode` / `ac_output_mode` |
| `4079` | port memory | `a2 02 01 <00\|01>` | F3800 | anker-solix-api | `port_memory_switch` |

Requests as SolixBLE builds them (F2600):

```
4042  a1 01 21 | a2 05 02 2c010000     AC timer 300 s
4044  a1 01 21 | a2 03 02 bc02         AC charge limit 700 W
404e  a1 01 21 | a2 02 01 01           power saving on
4040  a1 01 21                         status request
```

F3800 setters in the app's code with no device-verified map (app code): `0078` `setThirdATSData` (`a2`–`a5` generator parameters, u16 each), `005f` `setBMSSubBatteryPowerSwitch` and `0060` `setBMSSubBatteryLightSwitch` (`a2` battery id, `a3` switch, `a4` unnamed).

## F2000 and F2600 telemetry

anker-solix-api reads the F2000, F2000 Plus and F2600 with one map (`0405` on `param_info`). The SolixBLE F2600 class keeps the F2000 class's names where they agree and overrides the rest after testing on an F2600.

| tag | type | field | SolixBLE | anker-solix-api |
|---|---|---|---|---|
| `a2` / `a3` | u32 | AC / DC output timer remaining, s | `ac_timer_remaining` / `dc_timer_remaining` (F2600) | `ac_output_timeout_seconds` / `dc_output_timeout_seconds` |
| `a4` | u16 | time to full or empty, 0.1 h | `time_remaining` | `remaining_time_hours` |
| `a5` | u16 | AC input W | `ac_power_in` (F2600), `ac_to_battery` (F2000) | `ac_input_power` |
| `a6` | u16 | AC output W | `ac_power_out` (F2600), `ac_power_out_sockets` (F2000) | `ac_output_power` |
| `a7` / `a8` / `a9` | u16 | USB-C 1 / 2 / 3 W | `usb_c1_power` … | `usbc_1_power` … |
| `aa` / `ab` | u16 | USB-A 1 / 2 W | `usb_a1_power` / `usb_a2_power` | `usba_1_power` / `usba_2_power` |
| `ac` / `ad` | u16 | 12 V outputs 1 / 2 W | `dc_1_power_out` / `dc_2_power_out` | `dc_12v_1_power` / `dc_12v_2_power` |
| `ae` | u16 | DC (solar) input W | `solar_power_in` | `dc_input_power` |
| `af` | u16 | total input W on the F2600 (AC and solar) | `power_in` (F2600), `ac_power_in` (F2000) | `photovoltaic_power` |
| `b0` | u16 | total output W on the F2600 | `power_out` (F2600), `ac_power_out` (F2000) | `output_power_total` |
| `b3` | u16 | firmware, decimal digits (346 = v3.4.6) | `software_version` | `sw_version` |
| `b9` | u16 | expansion firmware | `software_version_expansion` | `sw_expansion` |
| `ba` | u16 | controller firmware | `software_version_controller` | `sw_controller` |
| `bb` | u16 | AC output on | `ac_output` (F2600) | — |
| `bc` | u8 | charge source: 0 none, 1 solar, 2 AC, 3 both | `charging_status` (F2600) | `charging_status` |
| `bd` / `be` | u8, signed | temperature / expansion temperature °C | `temperature` / `temperature_expansion` | `temperature` / `exp_1_temperature` |
| `bf` | u8 | 0 / 1 / 2; reads 2 while AC charging and 1 on solar with a load | `solar_port` = `bf == 1` (F2600) | `battery_status` (0 standby, 1 discharging, 2 charging) |
| `c1` / `c2` | u8 | battery / expansion SoC % | `battery_percentage` / `battery_percentage_expansion` | `main_battery_soc` / `exp_1_soc` |
| `c3` / `c4` | u8 | SoH / expansion SoH % | `battery_health` / `battery_health_expansion` | `battery_soh` / `exp_1_soh` |
| `c5` | u8 | expansion count | `num_expansion` | `expansion_packs` |
| `c6`–`ca` | u8 | USB-C 1–3, USB-A 1–2 on | `usb_port_c1` … `usb_port_a2` (F2600) | `usbc_1_status` … `usba_2_status` |
| `cb` / `cc` | u8 | 12 V outputs 1 / 2 on | `dc_output` = `cb` (F2600) | `dc_12v_1_status` / `dc_12v_2_status` |
| `cf` | u8 | LED light 0–3 | `light` (F2600) | — |
| `d0` | string | serial | `serial_number` | `device_sn` |
| `d1` | u16 | AC charge limit W | `ac_charging_power` (F2600) | `ac_input_limit` |
| `d2` / `d3` | u16 | device timeout min / display timeout s | `display_timeout` = `d3` (F2600) | `device_timeout_minutes` / `display_timeout_seconds` |
| `d7` / `d8` | u8 | AC / DC output switch | — | `ac_output_power_switch` / `dc_output_power_switch` |
| `d9` | u8 | display brightness 0–3 | `display_mode` (F2600) | `display_mode` |
| `da` | u8 | AC frequency, 50 / 60 Hz | — | `ac_frequency` |
| `db` | u8 | power saving | `power_saving_mode_enabled` (F2600) | `energy_saving_switch` |
| `dc` | u8 | LED light 0–3, 4 blinking | — | `light_mode` |
| `dd` / `de` | u8 | temperature unit / display on | `is_display_on` = `de` (F2600) | `temp_unit_fahrenheit` / `display_switch` |
| `e5` | u8 | ultrafast charge | — | `ac_fast_charge_switch` |
| `f8` | raw | `[0]` 12 V output mode, `[1]` AC output mode: Normal 1, Smart 2 | — | `dc_12v_output_mode` / `ac_output_mode` |
| `fd` | string | type string (`"A1781_5Ah"` on an F2600) | — | `exp_1_type` |
| `fe` | u32 | timestamp | — | `msg_timestamp` |

- On the F2600 the `c840` status reply carries the settings tags `d1`–`de`, `f8` and `fd`; the unsolicited pushes omit them (SolixBLE).
- The app's F2000 parser reads the same fields in the same tag order (`a4`–`b0`, `b3`, `b9`, `ba`, `bd`, `be`, `c1`–`c5`, `d7`, `d8`, `db`, `de`, `dd`, `e5`, `d9`, `dc`) and also reads `c0` (app code).

### Worked example: F2600 `c840`, AC charging

A SolixBLE capture: an F2600 charging from the wall at 1444 W with a 280 W load on the AC output; firmware v3.4.6, battery 64 %.

```
a1 01 31                       routing: device → BLE
a2 05 03 00000000              AC timer remaining 0 s
a3 05 03 00000000              DC timer remaining 0 s
a4 03 02 0900                  time to full 0.9 h
a5 03 02 a405                  AC input 1444 W
a6 03 02 1801                  AC output 280 W
a7 a8 a9 03 02 0000            USB-C 1–3: 0 W
aa ab 03 02 0000               USB-A 1–2: 0 W
ac ad 03 02 0000               12 V outputs 1–2: 0 W
ae 03 02 0000                  DC input 0 W
af 03 02 a405                  total input 1444 W
b0 03 02 1801                  total output 280 W
b1 b2 03 02 0000               (no field)
b3 03 02 5a01                  firmware 346 = v3.4.6
b4 03 02 2e01 · b5 03 02 7400 · b6 03 02 6c00 · b7 03 02 0000 · b8 03 02 7500     (no field: 302, 116, 108, 0, 117)
b9 03 02 0000                  expansion firmware 0
ba 03 02 5a01                  controller firmware v3.4.6
bb 03 02 0100                  AC output on
bc 02 01 02                    charge source AC
bd 02 01 22                    temperature 34 °C
be 02 01 00                    expansion temperature 0
bf 02 01 02                    2 (charging)
c0 02 01 00                    (no field)
c1 02 01 40                    battery 64 %
c2 02 01 00                    expansion SoC 0
c3 02 01 64                    SoH 100 %
c4 02 01 00 · c5 02 01 00      expansion SoH 0, 0 expansions
c6 c7 c8 c9 ca 02 01 00        USB-C 1–3, USB-A 1–2 off
cb cc 02 01 00                 12 V outputs off
cd ce 02 01 00                 (no field)
cf 02 01 00                    LED light off
d0 11 00 "AZV3NM0000000001"    serial
d1 03 02 a005                  AC charge limit 1440 W
d2 03 02 0000                  device timeout 0
d3 03 02 1400                  display timeout 20 s
d4 03 02 3c00 · d5 03 02 0000 · d6 03 02 0000                                     (no field: 60, 0, 0)
d7 02 01 01                    AC output switch on
d8 02 01 00                    DC output switch off
d9 02 01 03                    display brightness high
da 02 01 3c                    AC frequency 60 Hz
db 02 01 00                    power saving off
dc 02 01 00                    LED light off
dd 02 01 01                    °F
de 02 01 00                    display off
f8 15 04 00 00 00 00 01 00×16  output modes
fd 0a 00 "A1781_5Ah"           type string
fe 05 03 00b95569              timestamp
```

### F2000 `0408` (MQTT `state_info`)

anker-solix-api maps it with provisional names: `a3` serial, `a4` local timestamp, `a5` UTC timestamp, `a6` battery voltage (0.001 V), `a7` PV voltage (0.001 V), `aa` AC output power (inverted), `ab` battery power (signed), `ac` main battery SoC %.

## F3800 telemetry

anker-solix-api maps `0405` (and the status reply `0840`, the same layout) for the F3800 and F3800 Plus. SolixBLE's F3800 class takes its tags from that map and also accepts telemetry on `c840`, `c402`, `4300` and `c405`. Where the two disagree, both names are given.

| tag | type | field | SolixBLE | anker-solix-api |
|---|---|---|---|---|
| `a2` / `a3` | u32 | AC / DC output timer remaining, s | — | `ac_output_timeout_seconds` / `dc_output_timeout_seconds` |
| `a4` | u16 | time to full or empty, 0.1 h | `time_remaining` | `remaining_time_hours` |
| `a5` / `a6` | u16 | AC input / AC output W | `ac_power_in` / `ac_power_out` | `ac_input_power` / `ac_output_power` |
| `a7` / `a8` / `a9` | u16 | USB-C 1 / 2 / 3 W | `usb_c1_power` … | `usbc_1_power` … |
| `aa` / `ab` | u16 | USB-A 1 / 2 W | `usb_a1_power` / `usb_a2_power` | `usba_1_power` / `usba_2_power` |
| `ac` | u16 | 12 V output | `dc_output` (status) | `dc_12v_1_power` |
| `ad` | u8 | battery SoC % | `battery_percentage` | `battery_soc` (main and expansions together) |
| `ae` | u16 | total solar input W | `solar_power_in` | `photovoltaic_power` |
| `af` / `b0` | u16 | PV 1 / PV 2 input W | `solar_pv_1_power_in` / `solar_pv_2_power_in` | `pv_1_power` / `pv_2_power` |
| `b1` | u16 | battery charge power W (AC and solar) | `battery_charge_power` | `bat_charge_power` |
| `b2` | u16 | total output W | `power_out` | `output_power_total` |
| `b4` | u16 | battery discharge power W | `battery_discharge_power` | `bat_discharge_power` |
| `b5` | u16 | firmware | `software_version` | `sw_version` |
| `ba` / `bb` | u16 | expansion / controller firmware | `software_version_expansion` / — | `sw_expansion` / `sw_controller` |
| `bc` | u8 | AC output on | `ac_output` | `ac_output_power_switch` |
| `bd` | u8 | charge source: 0 none, 1 solar, 2 AC, 3 both | `charging_status` | `charging_status` |
| `be` | u8, signed | temperature °C | `temperature` | `temperature` |
| `bf` | u8 | 0 standby, 1 discharging, 2 charging | — | `battery_status` |
| `c0` | u8 | SoC % | `battery_percentage_aggregate` | `main_battery_soc` |
| `c1` | u8 | — | `max_battery_percentage` | `battery_soh` |
| `c2`–`c6` | u8 | USB-C 1–3, USB-A 1–2 on | `usb_port_c1` … `usb_port_a2` | `usbc_1_status` … `usba_2_status` |
| `c7` | u8 | 12 V output on | — | `dc_12v_1_status` |
| `cc` | string | serial | `serial_number` | `device_sn` |
| `cd` | u16 | AC charge limit W, 200–1800 in steps of 100 | — | `ac_input_limit` |
| `ce` / `cf` | u16 | device timeout min / display timeout s | `display_timeout` = `cf` | `device_timeout_minutes` / `display_timeout_seconds` |
| `d3` / `d4` | u8 | AC / DC output switch | — | `ac_output_power_switch_dup` / `dc_output_power_switch` |
| `d5` | u8 | display brightness 0–3 | — | `display_mode` |
| `d6` | u8 | AC frequency, 50 / 60 Hz | — | `ac_frequency` |
| `d8` / `d9` | u8 | temperature unit / LED light 0–4 | — | `temp_unit_fahrenheit` / `light_mode` |
| `e6` | u16 | AC charge limit maximum for this variant | — | `ac_input_limit_max` |
| `f6` | raw | two ASCII characters, the country code (`"US"`) | — | `country_code` |
| `f7` | u8 | port memory | — | `port_memory_switch` |
| `fd` | — | expansion type | — | `exp_1_type` |
| `fe` | u32 | timestamp | — | `msg_timestamp` |

The app's F3800 parser (app code) reads `b3` as a hex string (a battery serial), `b6`–`b9` and `bb` as further firmware versions, and `f8` as a port-saving-mode list.

### Expansions (`040a`)

The F3800 reports up to six expansion batteries on `param_info` (anker-solix-api): `a2` expansion count, `a3` total expansion SoC, then one record per expansion at `a4`–`a9`:

| offset | field |
|---|---|
| `[0:16]` | serial, 16 ASCII |
| `[19]` | temperature °C, signed |
| `[21]` | SoC % |
| `[22]` | SoH % |
| `[28:38]` | type, 10 ASCII |

The app's expansion model (app code) also names `heatingFilmOpened`, `isLightBlink`, `lightOff`, `powerOff`, `errorCode`, `equalType` and `batteryPackType`.

### Power panel (`0410`)

With a home power panel, the F3800 reports the panel and up to two linked stations (anker-solix-api): `a2[0:16]` panel serial; `a3` / `a4` each `[0:16]` station serial, `[19]` SoC %, `[20]` temperature °C (signed); `a5` / `a6` the stations' part numbers. `0804` has no mapped fields.

### Network message (`0407`)

On MQTT `state_info` (anker-solix-api, F2000, F2600, F3800): `a2` serial, `a3` WiFi network name, `a4` WiFi signal, `a6` AC charge limit W.

## F1200 (A1770, A1771)

No captured frame and no library map. The app's A1771 parser (app code) reads these tags from the full status:

| tag | app field |
|---|---|
| `d0` | serial |
| `d1` | maximum load |
| `d2` / `d3` | device timeout / display timeout |
| `d7` / `d8` | AC / DC output switch |
| `d9` | display brightness |
| `db` | power saving |
| `dc` | LED light |
| `dd` / `de` | temperature unit / display on |
| `df` | green-power mode |
| `e0` | green-power charge limit |
| `e2` / `e4` | peak-valley (time-of-use) enable / data |
| `e3` | a flag (read as `== 1`) |
| `fe` | timestamp |
