# Discovery, advertisement and GATT

How an Anker BLE device is found, identified before connecting, and reached once connected. Each row names the products or builds it was established on.

## Transport families

The Anker app scans with one fixed service filter, the same in every app version from 2.8.1 (2024) to 3.23.0:

```
scan serviceIDs [0000ff09, 00002215, 00001780, 00001770, 000017a0, 000017a1, 000017a2, 00002540, 0000effe]
```

Each entry is a 16-bit service UUID (Bluetooth base form `0000xxxx-0000-1000-8000-00805f9b34fb`) that a device family advertises. The app's string table also carries the 128-bit GATT triples the families serve once connected:

| advertised | GATT service | write (commands) | notify (frames) | products | frames |
|---|---|---|---|---|---|
| `ff09` | `8c850001-0302-41c5-b46e-cf057c562025` | `8c850002-0302-41c5-b46e-cf057c562025` | `8c850003-0302-41c5-b46e-cf057c562025` | C-series power stations (A1722 C300, A1753–A1755 C800, A1761 C1000, A1763 / A1765 C1000 Gen 2, A1783 C2000 Gen 2), F3800 (A1790 / A1790P), S2000 (AS220), Solarbank 2 (A17C1), Prime chargers (A2345, A2687), Prime station A91B2 | `ff09` frames, negotiated session |
| `2215` | `22150001-4002-81c5-b46e-cf057c562025` | `22150002-4002-81c5-b46e-cf057c562025` | `22150003-4002-81c5-b46e-cf057c562025` | A1340 Prime Power Bank | `ff09` frames, negotiated session |
| `2540` | `25400001-4002-81c5-b46e-cf057c562025` | `25400002-4002-81c5-b46e-cf057c562025` | `25400003-4002-81c5-b46e-cf057c562025` | not identified | — |
| — | `41580001-4002-81c5-b46e-cf057c562025` | `41580002-4002-81c5-b46e-cf057c562025` | `41580003-4002-81c5-b46e-cf057c562025` | the ESP32-C3 comms module's built-in defaults (below) | `ff09` frames |
| `1780` | `1780` | `7777` | `8888` | 767 PowerHouse / F2000 (A1780) on older firmware | no negotiation; the device takes commands once subscribed |
| `1770` | not identified | not identified | not identified | product code A1770 (F1200) carries the same digits | — |
| `17a0` / `17a1` / `17a2` | not identified | not identified | not identified | product codes A17A0 / A17A1 / A17A2 (Powered Cooler 30 / 40 / 50) carry the same digits | — |
| `effe` | not identified | not identified | not identified | not identified | — |

- The app's string table also holds `0000ef0a-…`, `0000ef0b-…` and six base-form UUIDs ending `f5da` (`014bf5da`, `0156f5da`, `0157f5da`, `0158f5da`, `0159f5da`, `016df5da`), none of them in the scan filter. Their products and roles are not identified.
- The app picks `serviceUUID` / `writeCharacteristicUUID` / `notifyCharacteristicUUID` per device class.
- `ff09` is the advertised identifier only. No device in the `ff09` family serves a GATT service `ff09`: the frames run on the `8c85…` service.
- The 128-bit families share the tail `-b46e-cf057c562025`; `8c85` uses `-0302-41c5-`, the others `-4002-81c5-`. Within a family `…0001` is the service, `…0002` write, `…0003` notify.

## Advertisement

Two parts identify a device before connecting: the advertised 16-bit service UUID (the family, above) and a manufacturer-data record under company id `0xffff`. Field names are the app's own parse:

```
versionCode(1) │ bleMacAddress(6) │ bindType(1) │ productType(2) │ sku (3–4 ASCII) │ capability(0–1)

01 aabbccddee02 01 b402 514a42 04
   versionCode 1 · MAC aabbccddee02 · bindType 1 (bound) · productType b402 (A2345) · sku "QJB" · capability 04
```

| product | advert name | versionCode | bindType | productType | sku | capability | advertised service |
|---|---|---|---|---|---|---|---|
| A1783 C2000 Gen 2 | `SOLIX C2000 Gen 2` | `02` | `00` → `01` once bound | `b11a` | `DKKE` | `04` | `ff09` |
| A2345 Prime Charger 250 W | `A2345_EE02` | `01` | `00` → `01` once bound | `b402` | `QJB` | `04` | `ff09` |
| A91B2 Prime Charging Station 240 W | none | `01` | `00` | `b401` | `JTB` | `00` | `ff09` |
| A1790 F3800 | `Anker SOLIX F3800` | `01` | `02` | `b106` | `744` | absent | `ff09` |
| A1790P F3800 Plus | `Anker SOLIX F3800 Plus` | `01` | `02` | `b112` | `T27` | `04` | `ff09` |
| A1340 Prime Power Bank | — | `01` | `02` | `0101` | `000000` | `04` | `2215` |
| A1780 F2000 (older firmware) | — | the record holds only the MAC, byte-reversed | | | | | `1780` |

A1340 record as advertised: `01 aabbccddee04 02 0101 000000 04`.

### Fields

| field | rule |
|---|---|
| versionCode | `01` with a 3-character sku, `02` with 4. It fixes the sku length, not whether the capability byte is present (F3800: `01`, 13 B, no capability) |
| MAC | the only pre-connect MAC source on macOS, where CoreBluetooth hands out a host-assigned UUID; on Linux bleak's address is the MAC |
| bindType | `00` unbound (power-on default); `01` once an owner account is stored or while the binding time window is open. The A1783, A2345 and A91B2 module builds write only these two values; the F3800 line and the A1340 advertise `02` |
| productType | the model key; read both bytes as one value. The high byte sorts chargers (`b4xx`) from power stations (`b1xx`) in every known sample, but it is not a separate field |
| sku | a substring of the serial, the app's `productSku` |
| capability | the last byte when present; absent on some families, so never read it at a fixed offset. A bitmap: `0x04` offers the encrypted negotiation (see [negotiation.md](negotiation.md)). Whether the cleartext negotiation is refused depends on the module build, not on this byte. On the Prime ESP32 module it comes from four flags in the per-device BLE configuration, so one firmware build advertises `04` (A2345) or `00` (A91B2) |
| name | Prime: `<model>_<last 2 MAC bytes, uppercase hex>`; C-series: a marketing name sent by the device controller at boot. The device writes it during first boot, so it is absent for the first minutes while the manufacturer record is already complete. Resolve the model from the manufacturer record, not the name |
| OUI | several OUI blocks are in service at once and shared across models; match on the record or the advertised service |

### productType

| productType | product |
|---|---|
| `b006` | A17C1 Solarbank 2 |
| `b103` | A1753 / A1754 / A1755 C800 family |
| `b106` | A1790 F3800 |
| `b112` | A1790P F3800 Plus |
| `b118` | A1763 C1000 Gen 2 |
| `b119` | A1765 |
| `b11a` | A1783 C2000 Gen 2 |
| `b11b` | A1785 |
| `b401` | A91B2 Prime Charging Station 240 W |
| `b402` | A2345 Prime Charger 250 W |
| `b403` | A1341 |
| `b404` | A110A Prime Power Bank 26K 300 W |
| `b405` | A2687 Prime Charger 160 W |
| `b406` | A110B Prime Power Bank 20K 220 W |
| `b407` | A1903 Prime Charging Base 150 W |
| `b408` | A25X7 wireless charger |
| `b409` | A2692 |
| `b40a` | A110G |

`b118`, `b119`, `b11a` and `b11b` come from one C-series display-board model table: a single firmware build serves the A1763, A1765, A1783 and A1785 and picks its identity from a factory record. `b401`–`b40a` are the app's Prime product map.

## Link

- One BLE connection at a time. The device stops advertising while a client holds the link, so a second client (the app, another integration) can't connect; "not found" usually means another client holds it.
- No BLE pairing or bonding. Authorization happens inside the negotiation ([authorization.md](authorization.md)).
- Each connection negotiates its own session.

## GATT layout

GATT discovery on the A1783, A2345 and A91B2 returns the same table. The A2345:

| handle | type | UUID | properties | notes |
|---|---|---|---|---|
| `0x0001` | primary service | `1800` GAP | | |
| `0x0003` | characteristic value | `2a00` Device Name | | the advert name |
| `0x0006` | primary service | `1801` GATT | | |
| `0x0008` | characteristic value | `2a05` Service Changed | `0x20` indicate | CCCD `0x0009` |
| `0x000b` | characteristic value | `2b3a` Server Supported Features | `0x02` read | |
| `0x000d` | characteristic value | `2b29` Client Supported Features | `0x0a` read, write | |
| `0x000e` | primary service | `8c850001-0302-41c5-b46e-cf057c562025` | | |
| `0x000f` | characteristic declaration | → `0x0010` | | |
| `0x0010` | characteristic value | `8c850002-0302-41c5-b46e-cf057c562025` | `0x0c` write without response, write | commands, client → device |
| `0x0011` | characteristic declaration | → `0x0012` | | |
| `0x0012` | characteristic value | `8c850003-0302-41c5-b46e-cf057c562025` | `0x12` read, notify | frames, device → client |
| `0x0013` | CCCD `2902` | | | write `0100` to enable notifications |

- bleak on BlueZ numbers a characteristic by its declaration handle: the write characteristic is `0x000f` and the notify characteristic `0x0011` there, while an ATT capture shows the value handles `0x0010` / `0x0012`.
- The characteristic properties are compile-time constants in the ESP32-C3 module firmware (the same in Prime build v0.2.9.7 and C-series build v0.3.3.0). No configuration field or capability bit changes them.

### Where the UUIDs come from

The ESP32-C3 comms module ships with the `4158…` triple and overwrites only the UUID values at boot, from its per-device BLE configuration. On the C-series Gen 2 the device controller sends that configuration to the module on every start-up; three of its fields carry the GATT UUIDs, 16 bytes each, in string byte order:

| field | value on the A1783 |
|---|---|
| `a9` | `8c850001-0302-41c5-b46e-cf057c562025` (service) |
| `aa` | `8c850002-0302-41c5-b46e-cf057c562025` (write) |
| `ab` | `8c850003-0302-41c5-b46e-cf057c562025` (notify) |

A module that never received its configuration serves the `4158…` triple, which is why the app's string table carries it.

On the A1340 the BLE chip is a Telink TLSR8253, not the ESP32 module; its firmware carries the `2215…` service UUID itself.

## Write type

- The app sends every command as an ATT Write Command (write without response). PacketLogger captures show it for every write to `0x0010` on the A1783 (20 of 20), A2345 (32 of 32) and A91B2 (30 of 30), whatever the advert's capability byte.
- The characteristic offers both write types. A client that leaves the choice to its BLE stack can end up with write-with-response; bleak's default (`response=None`) picks with-response when both are offered.
- Through an ESPHome Bluetooth proxy, an A1783 write-with-response `4100` hangs and fails with GATT error 133. Pass `response=False`.

## MTU and fragmentation

- The A1783, A2345 and A91B2 grant ATT MTU 256, so a notification carries at most 253 bytes (ATT MTU − 3). The device also declares the cap in its negotiation reply `0803 a2` (`fd00` = 253). The A2687 declares 297 (`2901`).
- The module stores `MTU − 3` when the MTU exchange completes and caps each port by it: BLE = that value, other module ports 1 100, 244 or 1 024.
- A frame longer than the cap is split across notifications: the cmd byte carries the `0x80` flag, and the first payload byte is `index << 4 | total`, counting from 1. A fragment that fills the cap means more follow; a shorter one closes the run. A C-series `c900` arrives as 253 + 156; an A17C1 `c405` as 253 + 253 + 39 (`13`, `23`, `33`).
- Reassemble before decrypting.
- The app splits its own long writes the same way, `MTU − 10` payload bytes per fragment (9 header bytes + 1 checksum), assuming MTU 200 when none is known.
- Only frames longer than the cap fragment: the A91B2's largest frame is an unfragmented 250 B `4a00`.
- bleak on BlueZ reports `mtu_size` 23 until the MTU has been acquired, so a length guard of `mtu_size − 3` collapses to 20. Use `0803 a2`, falling back to `mtu_size − 3`.
