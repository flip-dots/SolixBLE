# SOLIX C2000 Gen 2 (A1783) telemetry TLV map

Reverse-engineered on 2026-11-14 from a live A1783 (product_type `b11a`, SKU
`DKKF`), reached over an ESP32 Bluetooth proxy. Telemetry arrives on commands
`c421`/`c900` (same as the C1000 Gen 2) after the `4100` subscribe. Each payload
is a list of TLVs; the hex below is `value_legacy` (the 1-byte type prefix at
offset 0, then the value), so byte offsets match the `_parse_int(key, begin=…)`
calls in `c1000g2.py`.

## Method

15 telemetry frames were captured over ~40 s while the station's AC load varied
naturally (148–211 W, read from `a6[1:3]`). A field is **live** if its bytes
changed across frames and **static** if they did not. Live fields were confirmed
by correlation against the known AC power series; static fields were decoded by
value (e.g. `0x08fc` = 2300 = 230.0 V) and are marked with a confidence level.

**Result: every field that changes is already decoded by `C1000G2`.** The
C2000-specific TLVs (`a3 a4 c0 ce da dc f9 fa fd`) were all static in this
capture — they are device identity / ratings / settings / capability blocks and
expansion-battery placeholders, not additional live sensors. No speculative
sensors are shipped; this file documents the structure for future work.

## Decoded and live (handled by C1000G2, confirmed on the A1783)

| TLV | field(s) | notes |
|-----|----------|-------|
| `a2` | serial (`APCDKKF0G14600188`), part number (`A1783`) | static identity |
| `a5` | `[1]` temperature °C (signed), `[3]` battery %, `[4]` battery health | live |
| `a6` | `[1:3]` total output W, `[3:5]` AC input W | live |
| `a7` | `[1]` AC output status, `[2:4]` AC output W | live; see `a7[5:7]` below |
| `a8` | `[1]` solar port status, `[2:]` solar input W | live |
| `aa` `ab` `ac` | USB-C ports: `[1]` status, `[2:]` W | live |
| `ae` | USB-A port: `[1]` status, `[2:]` W | live |
| `b2` | `[1]` DC output status, `[2:]` DC output W | live (DC on/off control confirmed) |
| `d9` | `[4]` max charge %, `[5]` min charge % | static settings; `[3]`=0x19 unknown |

## C2000-specific TLVs (all static in this capture)

Confidence: **H** strong value match, **M** plausible, **L** guess.

| TLV | len | raw (example) | reading | conf |
|-----|-----|---------------|---------|------|
| `a1` | 1 | `31` | frame/version marker `'1'` | M |
| `a3` | 14 | `04 00000000 fc08 0064 cc00 5802 00` | `[5:7]`=`0x08fc`=2300 → **AC voltage 230.0 V ×10** (nominal: perfectly constant); plus `0x64`,`0xcc`(204),`0x0258`(600) AC ratings | H (voltage), L (rest) |
| `a4` | 34 | `… e803 32 01 … d002 1e … 01 50 14 … 02` | settings block: `0x50`/`0x14` = **max/min charge 80/20** (echoes `d9`), `0x32`=**AC frequency 50 Hz**, `0x03e8`=1000, `0x02d0`=720 (timer?), `0x1e`=30 | M |
| `c0` | 35 | `04 10 00…00 01 …ef00 e801 …02 2020` | **expansion battery #1** block — zero/idle with none attached | M (structure) |
| `ce` | 44 | `04 10 00…00 11 00…` | **expansion battery #2 / reserved** — zero/idle | L |
| `da` | 24 | `… e001 3804 7f 00… 3804 6405` | static battery-pack detail: `0x01e0`=480 → **pack voltage 48.0 V ×10?**, `0x0438`=1080 (×2), `0x7f`=127, `0x0564`=1380 | M (voltage), L (rest) |
| `dc` | 6 | `04 00000000 00` | reserved / unused (all zero) | — |
| `f9` | 29 | `04 06 01 02 01 07 00 05 …` | hardware/port **capability descriptor** (port counts/types) | L |
| `fa` | 21 | `04 01010101 00 1f 35 00…` | feature toggles (`01 01 01 01`) + `0x1f`(31),`0x35`(53) settings | L |
| `fd` | 14 | `00` + ascii `1794654073078` | **unix-ms timestamp** (string); static across the run → boot / last-sync time, not a live clock | H |
| `fe` | 5 | `03 de 5b f8 6a` | `[1]` varies non-monotonically, `[2:]` ~constant → rolling/heartbeat byte, **not a metric** | H (not useful) |

### Partially-decoded extras in live TLVs
- `a6[7:9]` = `0x0c80` = 3200 (constant) — likely an **AC power rating (W)**; `a6[9]`=`0x60`=96 constant (ambiguous: equals battery % which was also constant).
- `a7[5:7]` = a second AC power reading that tracks the load (inverter vs socket power?).

## To confirm (needs controlled conditions)
- **Charge-limit block (`a4`/`d9`):** change max/min charge by 1 % and watch which bytes move (safe, non-AC write).
- **Expansion battery (`c0`/`ce`):** attach an expansion pack; the zero blocks should populate (SOC, voltage, temp per pack).
- **Remaining energy / runtime:** none seen varying here because the battery held ~96 % for the whole 40 s capture; a multi-hour discharge capture would expose any remaining-Wh / time-to-empty field.
- **AC voltage (`a3`) measured vs nominal:** it was exactly 2300 with zero jitter, so it is probably a nominal/rated value rather than a live measurement.
