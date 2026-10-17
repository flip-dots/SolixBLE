# Negotiation and encryption

Before commands, a client negotiates a session on channel `0x01`. The negotiation fixes the session cipher and key; authorization (whether the device controller answers) is a separate step, in [authorization.md](authorization.md).

## Generations

| generation | how a client recognises it | negotiation | session cipher |
|---|---|---|---|
| none | legacy `1780` transport | no `ff09` negotiation; commands work once the notify characteristic is subscribed | — |
| legacy confer | `0803 a3 04` with no `a5`, or no `0803` at all (A1340) | `0001 0003 0029 0005 0022` with `0005 a5 02`; no key exchange | AES-128-CBC, session key delivered in `0822` |
| cleartext ECDH | `0803 a5 00`, or any build on a cleartext connect | `0001 0003 0029 0005 0021` in the clear, then `4022` / `4023` encrypted | AES-128-CBC, key `ss[:16]`, IV `ss[16:32]`, PKCS7 |
| encrypted ECDH | advert capability `04`, `0803 a5 02` | `4001 4003 4029 4005 4021` under the static key, then `4022 4027` under `ss` | AES-128-GCM, key `ss[:16]`, nonce `ss[16:28]`, static AAD, 16-byte tag |

- `ss` is the raw P-256 ECDH X coordinate, 32 bytes, big-endian, with no KDF. The device makes a fresh key pair per session; no device secret, certificate or cloud credential is involved.
- The connect frame picks the link cipher: `4001` → GCM, `0001` → CBC.
- Some 2025 Solarbank 2 firmware sent cleartext frames (`8405` fragments, `0409`) with no encryption flag at all.

### Which products run which

| product | path observed | client | also accepted |
|---|---|---|---|
| A1783 C2000 Gen 2, module v0.3.3.0 | encrypted ECDH | Anker app | — (cleartext `0001` refused, [authorization.md](authorization.md)) |
| A1783 C2000 Gen 2, module v0.3.0.6 | encrypted ECDH | Anker app | cleartext ECDH, legacy confer |
| A2345 Prime Charger 250 W, module v0.2.9.7 | encrypted ECDH | Anker app | cleartext ECDH, legacy confer |
| A2345, 2024 module (v0.2.3.3 era) | legacy confer (`0803 a3 04`, no `a5`) | Anker app | ECDH |
| A91B2 Prime Charging Station | cleartext ECDH | Anker app | legacy confer on either outer; not encrypted-outer ECDH |
| A2687 Prime Charger 160 W | encrypted ECDH | Anker app | cleartext ECDH |
| A1790 F3800 | legacy confer (`0803 a3 04`, no `a5`) | Anker app | |
| AS220 S2000 | encrypted ECDH | third-party client | |
| A1761 C1000, A1722 C300 | cleartext ECDH (`0803 a5 02`) | third-party client | |
| A17C1 Solarbank 2, 2026 firmware | cleartext ECDH (`0803 a5 02`) | third-party client | legacy confer, with no account check |
| A1340 Prime Power Bank, firmware 1.6.x | legacy confer (`0005 a5 02`, no `0803`) | third-party client | ECDH (`0021`) when `0005` selects it |

## Static key

The encrypted negotiation runs under a fixed key. Every ESP32-C3 module build and the A1340's TLSR8253 BLE chip derive it the same way, from two 16-byte firmware constants `A` / `B`: `key[i] = A[i] ^ B[15-i]`, `iv[i] = B[(i+11)&15] ^ A[(i+5)&15]`.

| parameter | value |
|---|---|
| `A` | `248734303fc1b1a38a6f965f38395569` |
| `B` | `305011489b343b5f15ff9caa1240789c` |
| cipher | AES-128-GCM, payload = ciphertext + 16-byte tag |
| key | `b8ff7422955d4eb6d554a2c470280559` |
| nonce | `6ba3e3f2f3a60f2971ce5d1f` (the first 12 bytes of the 16-byte IV `6ba3e3f2f3a60f2971ce5d1fd821cfa3`) |
| AAD | `3322110077665544bbaa9988ffeeddcc` |

```python
AESGCM(KEY).decrypt(NONCE, ct_4801, AAD)   # -> 00a10101
AESGCM(KEY).decrypt(NONCE, ct_4803, AAD)   # -> 00a10102a202fd00a30144a40101a50102
```

The stage-1 and stage-2 responses are fixed byte strings, tag included, on every A2345 and A1783, so a client can recognise them by exact match:

```
4801  ff091e000300014801 ab273ed3e27270c3f4d676ac7d69a00572793732 a6
4803  ff092b000300014803 ab273ed04438d4b25db54c6d4a6ec3d481f5ad58ff7cc2be8bc8369fd98c0b914e 03
```

- The nonce is static, so these frames have no confidentiality against anyone holding one known plaintext. The keystream is `C ^ P` (GCM is CTR underneath), and `AES_K⁻¹(ks[:16])` = `nonce ‖ 00000002`; one 16-byte block of known plaintext (`4803` has 17) recovers the nonce and confirms the key.
- The session nonce `ss[16:28]` is fixed for the whole session too, so equal plaintexts encrypt identically after ECDH: an A1783 `4822 00` and `4827 00` carry the same 17-byte body, differing only in opcode and checksum.
- Cipher by length: GCM = plaintext + 16 (any length); CBC = a multiple of 16.
- Send-side plaintext length = frame length − 26 (9 header + 1 checksum + 16 tag).
- Strip the 16-byte tag before walking TLVs: an unstripped tag ends the walk mid-field.

## Encrypted ECDH, worked example (A1783)

Plaintexts as sent and received; every frame on the wire is GCM-sealed (static key through `4821`, `ss` from `4022`).

```
4001 →  a1 04 00b95569                                        a1 timestamp
4801 ←  00 | a1 01 01                                         status 00, a1 fixed 01

4003 →  a1 04 00b95569 | a3 01 20 | a4 02 00f0                a3 logged and unused; a4 client MTU ceiling 0xf000 (no limit)
4803 ←  00 | a1 01 02 | a2 02 fd00 | a3 01 44 | a4 01 01 | a5 01 02
          a1 base capability (0x02 AES, constant) · a2 MTU = min(client a4, port cap) = 253 · a3 advanced capability
          (0x04 ECDH; 44 on every current build) · a4 build constant 01 · a5 authMethod 02 (encrypted)

4029 →  a1 04 00b95569
4829 ←  00 | a1 01 03 | a2 05 "ESP32" | a3 07 "0.0.0.3" | a4 11 "APCDKKE0000000001" | a5 06 aabbccddee01
          a1 fixed 03 · a2 chip · a3 protocol-library version (constant) · a4 serial, 17 B · a5 MAC
          plaintext 00a10103a2054553503332a307302e302e302e33a411415043444b4b4530303030303030303031a506aabbccddee01

4005 →  a1 04 00b95569 | a3 01 20 | a4 02 fd00 | a5 01 44 | a6 01 02
          a4 the 0803 MTU echoed (not read) · a5 method: ECDH · a6 = the 0803 a5 authMethod
4805 ←  00

4021 →  a1 40 <client P-256 point X‖Y, 64 B>
4821 ←  00 | a1 40 <device P-256 point X‖Y, 64 B>             ss = ECDH X (32 B); key ss[:16], nonce ss[16:28]

4022 →  a1 04 00b95569 | a3 04 f0f1ffff | a5 1a "CET-1CEST,M3.5.0,M10.5.0/3"
          a3 UTC offset, int32 LE seconds, west positive (−3600 for CET) · a5 POSIX TZ, length varies
4822 ←  00

4027 →  a1 04 00b95569 | a2 28 "0000000000000000000000000000000000000000"
          a2 the 40-byte owner id (or any enrolled token)
4827 ←  00                                                    authorized; no button needed for an enrolled id

4100 →  a1 01 21 | fe 05 03 00b95569                          C-series status request
c900 ←  status snapshot (fragmented, 253 + rest), then c421 pushes
```

Frame lengths of the app's A1783 sends (plaintext + 26): `4001` 32, `4003` 39, `4029` 32, `4005` 45, `4021` 92, `4022` 62 (a 22-byte TZ such as `EST5EDT,M3.2.0,M11.1.0`; 66 with the 26-byte CET string above), `4027` 74; a bind adds `4023` (70 B plaintext: `a1`, `a2` account, `a3` serial, `a4`; 96 B frame).

On the A2345 the app also sends `a2` on every negotiation request except `4021`, empty (`a2 00`) when it has nothing: `4001` 34, `4003` 41, `4029` 74 (`a2 28 <account>`), `4005` 47, `4021` 92, `4022` 64, `4027` 74. The one published S2000 client sends `4027 a2` as a 36-character UUID string; any enrollable id works ([authorization.md](authorization.md)).

## Cleartext ECDH, worked example (A91B2)

```
0001 →  a1 04 00b95569 | a2 28 <account, 40 B>                 a2 optional
0801 ←  00 | a1 01 01
0003 →  a1 04 00b95569 | a2 28 <account> | a3 01 20 | a4 02 00f0
0803 ←  00 | a1 01 02 | a2 02 fd00 | a3 01 44 | a4 01 01 | a5 01 00      authMethod 0 (cleartext)
0029 →  a1 04 00b95569 | a2 28 <account>
0829 ←  00 | a1 01 03 | a2 05 "ESP32" | a3 07 "0.0.0.3" | a4 10 "AFYJTB0000000001" | a5 06 aabbccddee03
0005 →  a1 04 00b95569 | a2 28 <account> | a3 01 20 | a4 02 00f0 | a5 01 40      ECDH; no a6
0805 ←  00
0021 →  a1 40 <client point, 64 B>
0821 ←  00 | a1 40 <device point, 64 B>                       link authorized here (cleartext connect)
4022 →  (CBC under ss[:16] / ss[16:32]) a1 ts · a2 28 <account> · a3 UTC offset · a5 TZ
4822 ←  (CBC) 00
4200 →  (CBC) a1 01 21 | fe 05 03 00b95569                    Prime status request
4a00 ←  (CBC) status snapshot
```

After a cleartext connect the app's `4022` carries `a2` account; after an encrypted one it doesn't.

## Device answers by family

`0803` (capability):

```
A91B2       00 a10102 a202fd00 a30144 a40101 a50100     authMethod 0 (cleartext)
A2345       00 a10102 a202fd00 a30144 a40101 a50102     authMethod 2 (encrypted)
A1783       00 a10102 a202fd00 a30144 a40101 a50102
A1761, A1722  00 a10102 a202fd00 a30144 a40101 a50102   reached over a cleartext connect
A2687       00 a10102 a2022901 a30144 a40101 a50102     MTU 297
A2345 2024, A1790   00 a10102 a202fd00 a30104 a40101    a3 04 and no a5: legacy confer
A1340       no 0003 / 0803 exchange exists in its BLE firmware
```

`0829` (device info):

| product | `a2` chip | `a3` | `a4` serial | `a5` |
|---|---|---|---|---|
| ESP32-C3 module (A1783, A2345, A91B2, A1761, A1722, A17C1, AS220) | `"ESP32"` | `"0.0.0.3"`, a library constant | 17 B (C-series Gen 2, S2000) or 16 B | MAC, 6 B |
| A2687 | `"Charging"` | `"v0.0.5.0"` | 17 B | MAC + the serial's last 11 characters, 17 B |
| A1340 | | firmware version | serial | MAC |

## `0005`, the method choice

`0803` carries the device's capability bits; `0005` is the first message of the chosen path. The ESP32-C3 module's `0005` handler:

- `a3` is ignored and `a4` isn't read, so a wrong MTU echo is tolerated (an A1783 accepted 297).
- `a5` is a bitfield that selects the cipher:

  | `a5` | result |
  |---|---|
  | `0` | no encryption |
  | `& 0x46 == 0` | status 1 (`Encrypt err`) |
  | `auth_mode ≠ 0` and `& 0x44 == 0` | status 1 (`enforce: reject non-ECDH mode`), module v0.3.3.0 only |
  | `& 0x02` | legacy AES, capability mode 1 |
  | `& 0x44` | ECDH, capability mode 4; `0x04` and `0x40` are both ECDH bits, and ECDH wins over `0x02` |

- `a6` is stored as the link's `auth_mode` only if it equals the device's own.
- The app sends `a5 44` on the encrypted outer (A1783) and `a5 40` on the cleartext one (A91B2, no `a6`). Only the collapsed mode (0 / 1 / 4) is stored, so `0x04` and `0x40` are indistinguishable afterwards.
- Choosing as a client: `0803 a3 44` with an `a5` is an ECDH-capable build, so send an ECDH bit. `0803 a3 04` with no `a5` is the older shape (2024 A2345, F3800), where the app sends `a5 02`; on the F3800 `a5 40` draws `0805 01` and `a5 02` draws `0805 00`.
- `0021` answers a bare `00` (no `a1`, nothing installed) unless `0005` set capability mode 4: check for `a1` rather than the status. The F3800 shows this on the wire.
- `0003` with `a3` or `a4` missing answers status 4.

The A1340's BLE chip has the same modes (4 ECDH, 2 legacy with `a4`, 1 legacy plain), set by `0005 a5` (`02` → legacy, `44` → ECDH).

## Legacy confer

The 2024-era path, still the F3800's. Every negotiation frame is cleartext (flag nibble `0`) and there is no key exchange. A2345 example:

```
0001 →  a1 04 00b95569 | a2 28 <account, 40 B>                  connect: installs the bootstrap key
0801 ←  00 | a1 01 01
0003 →  a1 04 00b95569 | a2 28 <account> | a3 01 20 | a4 02 00f0
0803 ←  00 | a1 01 02 | a2 02 fd00 | a3 01 04 | a4 01 01        a3 04 (ECDH bit) but no a5: legacy
0029 →  a1 04 00b95569 | a2 28 <account>
0829 ←  00 | a1 01 03 | a2 05 "ESP32" | a3 07 "0.0.0.3" | a4 10 "ASHQJB0000000001" | a5 06 aabbccddee02
0005 →  a1 04 00b95569 | a2 28 <account> | a3 01 20 | a4 02 00f0 | a5 01 02      no a6
0805 ←  00
0022 →  (CBC under the bootstrap key) a1 ts · a3 UTC offset · a5 TZ
0822 ←  (CBC under the bootstrap key) 00 | a1 10 <16-byte session key> + PKCS7
```

- Bootstrap: key = the first 16 ASCII bytes of the `0001` `a2` account. With no `a2` it is `ANKER_DEFAULT_AC`, from the default account `ANKER_DEFAULT_ACCOUNT_1`, a string in both the Prime module and the A91B2 controller firmware. IV = the serial's 16 ASCII bytes (`0829 a4`). Nothing compares the account with a stored or bound one.
- `0822 a1` is a fresh device-generated 16-byte key; every later frame uses it, with the IV still the serial. In capability mode 2 the device installs it XORed with the request's 16-byte `a4`; in mode 1 as is.
- On the encrypted outer (`4001` … `4005 a5 02`, GCM under the static key), a legacy `4022` goes CBC-sealed under the static key with the full 16-byte static IV; `4822` comes back GCM-sealed under the static key and nonce, `00 a1 10 <session key>`. The session then runs GCM with that key and the static nonce, never the serial.
- A client holding the static key, the default account and the serial (cleartext in `0829`) can open a session without ECDH. The only refusal is the module v0.3.3.0 `0005` check, active whenever `auth_mode ≠ 0`:

  | build | refuses a non-ECDH `0005` |
  |---|---|
  | Prime module v0.2.3.3, v0.2.9.7 | no |
  | C-series Gen 2 module v0.3.0.6 | no |
  | C-series Gen 2 module v0.3.3.0 | yes; the A1783 runs `auth_mode 2` from first boot |

- On the A17C1 Solarbank 2 the legacy confer succeeds with no account check, and a Solarbank 1 schedule (`405e`) sent after it factory-resets the unit.

## Field reference

| request → response | app name | request | response |
|---|---|---|---|
| `0001` → `0801` | `ConnectCmd` | `a1` ts (4) [`a2` account (≤ 40)] | `a1 01` |
| `0003` → `0803` | capability negotiation | `a1` ts [`a2`] `a3 20` `a4 00f0` | `a1 02` base capability · `a2` MTU · `a3 44` advanced capability · `a4 01` · `a5` authMethod |
| `0029` → `0829` | `DeviceBaseInfoCmd` | `a1` ts [`a2`]; nothing is read | `a1 03` · `a2` chip · `a3` library version · `a4` serial (16 / 17) · `a5` MAC |
| `0005` → `0805` | `SetCapabilityCmd` | `a1` ts [`a2`] `a3 20` · `a4` MTU (not read) · `a5` cipher bitfield · `a6` authMethod | status |
| `0021` → `0821` | `GCMPubilcKeyCmd` (app spelling) | `a1` P-256 point without `04` (64) | `a1` device point (64) |
| `0022` → `0822` | `GetAesKeyCmd` | `a1` ts · `a3` UTC offset (int32 LE s, west positive) · `a5` POSIX TZ; after a cleartext connect the app also sends `a2` account | status (ECDH) / `a1` session key (legacy) |
| `0023` → `0823` | bind user | `a1` ts · `a2` account · `a3` serial · `a4` | `a1` serial |
| `0027` → `0827` | `getAuthentication` | `a1` ts · `a2` account / token · [`a3` password] | `00` / `09` / `0a` / `0b` / `01` |
| `0030` → `0830` | `getZXOTAState` (channel `0x0f`) | — | `a1` module fw · `a2` device fw · `a3` model · `a4` controller name · `a5` ESP32 name |

- No negotiation handler checks the `a1` timestamp; `0022` takes it as the clock value (`04` if missing). The app's timestamps are not replay protection.
- `0022` `a1` / `a3` / `a5` set the device clock and time zone and authorize nothing on the ECDH path. `a3` is a 4-byte field: a 1-byte `a3` is read as garbage. The app recomputes offset and TZ from the OS each time, so they track DST.
- The WiFi setup flow sends its own `4022` (`a2` account, `a3` 2-letter country) and `4023` after negotiation.
- `0830` by family: the A1761 answers `a1` / `a2` only (`"v0.2.3.1"` / `"v1.5.9"`); the A1722 adds `a3` `"A1722_high"`, `a4` `"A1722_mcu_high"`, `a5` `"A1722_esp32_high"`; the C-series Gen 2 uses `_low`; the A2345 `"A2345"`, `"A2345_mcu"`, `"A2345_esp32"`.
