# Other Anker devices

Short notes on three families with no captured frames for this documentation: the V1 smart EV charger, the X1 home energy system and the EverFrost coolers. Every table names its basis: the anker-solix-api map (Thom's, built from MQTT captures) or the Anker app's code.

## V1 smart EV charger (A5191, A5190)

anker-solix-api names the A5191 "V1 Smart EV Charger"; the app also carries A5190 assets (app code). The charger takes TLV commands like the other families, with its settings grouped into command opcodes (anker-solix-api; MQTT form `01xx`):

| opcode | command | field | values |
|---|---|---|---|
| `0057` | realtime trigger | `a2`, `a3` | as on the other families; starts `0410` |
| `0100` | settings group | `a3` plug lock | 1 on, 2 off |
| | | `a4` auto start | 0 off, 1 on |
| | | `a8` maximum charge current | u16, 0.1 A: 6 A up to the model's rated current, steps of 1 A |
| | | `aa` light brightness | 0–100 %, steps of 10 |
| | | `ac` auto charge restart | 0 / 1 |
| | | `ad` random delay | 0 / 1 |
| | | `af` / `b0` swipe up / down action | 0 off, 1 start, 2 stop, 3 boost |
| | | `b2` touch mode | 0 simple, 1 anti-mistouch |
| | | `b4` / `b5` / `b6` light-off schedule | switch 0 / 1; start and end times (below) |
| | | `b7` Modbus | 0 / 1 |
| `0105` | charge control | `a2` | 1 start, 2 stop, 3 skip delay, 4 boost; sent with encoding type 2 |
| `0106` | schedule | `a2` switch (1 on, 2 off), `a8` mode (0 normal, 1 smart); `a3` / `a4` weekday start / end, `a5` / `a6` weekend start / end (times, below), `a7` weekend 1 same / 2 different | |
| `0108` | power mode | `a2` | 5 restart; sent with encoding type 2 |
| `010c` | load balancing | `a2` switch, `a3` main breaker limit u16 A (10–500), `a4` / `a5` settings, `a6` monitoring device serial (16 B) | |
| `010e` | solar charging | `a2` switch, `a3` 0 solar and grid / 1 solar only, `a4` minimum current u16 A (6–32), `a5` phases 1 / 3, `a6` monitoring mode, `a7` automatic phase switching, `a8` monitoring device serial | |

**Times** (`0100 b5` / `b6`, `0106 a3`–`a6`, and the `0405` `b5` / `b6` and `e7`–`ea` that report them): type `02`, value hour × 256 + minute, so the bytes are minute then hour (20:00 = `03 02 00 14`) (anker-solix-api).

The app sends charge control through its device SDK as the action `action_control_charging {controlType: 1 start / 2 stop / 3 start now / 4 boost}` (app code).

Frames (anker-solix-api):

| frame | topic | content |
|---|---|---|
| `0405` (also `0840`, `0900`) | `param_info` | the settings above at `a3`–`b7`; `cc` Modbus TCP timeout s, `ce` rated current limit (0.1 A), `cf` Modbus TCP port, `d0` IP address; `d3`–`d7` load balancing; `d8`–`de` solar charging; `df` boost; `e0` CP signal (0 A 12 V, 3 B1, 4 B2, 5 C1, 6 C2, 7 error, 8 D1, 9 D2, 10 E, 11 F); `e2` plug connected; `e3` charger status; `e6`–`ec` schedule; `f1` / `f2` / `f3` firmware / controller / hardware versions |
| `0410` | `param_info`, with `0057` | `a2`–`a4` voltage L1–L3 (0.1 V), `a5`–`a7` current L1–L3 (0.1 A), `a8` charge power W, `a9` session duration s, `aa` session energy (0.001 kWh), `ab` session start timestamp, `ad` / `ae` plug / start countdown s, `af` charging window s, `b0`–`b2` power L1–L3, `b3`–`b5` energy L1–L3, `b8` OCPP link (0 disconnected, 1 connecting, 2 connected), `ba` phase mode (0 auto, 1 single), `bb` charger status |
| `0403` | `param_info` | `a5` charging window s, `a6` solar minimum current |
| `0400` | `state_info`, every 5 min | three unnamed settings |

Charger status (`e3`, `bb`): 0 standby, 1 preparing, 2 charging, 3 paused by charger, 4 paused by vehicle, 5 completed, 6 reserving, 7 disabled, 8 error.

## X1 home energy system (A5101, A5102, A5103)

The X1 storage systems (A5101 X1-P6K-US/S, A5102 X1-H(3.68~6)K-S, A5103 X1-H (5~12)K-T) do not use `ff09` TLV tags for their data. Over BLE the app addresses settings by attribute id (`att_id`, a 131-value data-code enumeration) and serialises them as JSON strings; the cloud side is plain JSON over HTTP and MQTT (app code). Two functions use opcodes instead: `002d` for the automatic backup data and `0030` for the version query (app code).

Attribute ids, by direction (app code):

| direction | ids |
|---|---|
| set only | `0x02be`–`0x02d1` generator parameters (14), `0x09c9` grid sensitivity, `0x09d3` charge permission, `0x09d4` export limit, `0x0284` CLS reset |
| get only | `0x014c` PV state, `0x014d` battery remaining, `0x0155` supported functions, `0x0160` minimum SoC, `0xe004` system status |
| both | `0xf009` grid standard, `0x0137` backup mode, `0x0222` PV → load power, `0x020e` battery → load power, `0xf00c` grid → battery power, `0x0221` grid → load power |

The MQTT JSON status (anker-solix-api), under `ems_data`: `bs` charge source (0 none, 1 solar, 2 AC, 3 both), `gs` grid status, `ps` plant status (1 on-grid, 2 off-grid, 3 standby, 4 fault), `soc`, the power flows `pp`, `p2lp`, `p2bp`, `p2gp`, `bp`, `b2lp`, `b2gp`, `gp`, `g2bp`, `g2lp`, `lp`, `d2bp`, `d2lp`, `dp` (W), and daily and lifetime energies (`pe`, `p2le` … `pae`, `bac`, `bad`; 0.001 kWh). Under `pack_data`: `t` pack temperatures, `batv` battery voltage, `usoc` SoC, `soh`, and `wm` usage mode (0 self-consumption, 1 time of use, 2 backup only, 3 third-party control, 4 user-defined, 5 socket aggregation).

## EverFrost coolers (A17A0–A17A5)

Names only: Powered Cooler 30 / 40 / 50 (A17A0 / A17A1 / A17A2) and SOLIX EverFrost 2 23L / 40L / 58L (A17A3 / A17A4 / A17A5) (anker-solix-api). No command or telemetry layout is mapped. anker-solix-api reads `0830` versions on the A17A4 and A17A5, five unnamed settings in an A17A4 `0889`, and on the A17A5 a `0405` with `a2` serial and `a4` part number. The app's cooler reports are named per function (`uploadDeviceInfo`, `uploadInputPower`, `uploadBatteryValue`, `uploadSingleBoxTemp`, `uploadDoubleBoxLSetTemp`, …) rather than by tag (app code).
