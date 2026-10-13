# Authorization

A negotiated session is not yet an authorized one. Until the link is authorized a client gets nothing back from the device controller: no reply to an opcode ≥ `0x40` (`4100`, `4057`, `4200`) and no telemetry. How a link becomes authorized depends on the negotiation path and on the device's `auth_mode`.

Everything here is the ESP32-C3 comms module's behaviour, by module build: C-series Gen 2 v0.3.0.6 and v0.3.3.0 (A1783; the S2000 runs v0.3.3.0), Prime v0.2.9.7 (A2345, A91B2). Other comms chips are noted where known.

## `auth_mode`

A policy byte the module stores as `{auth_mode, auth_timeout, keep_unauth_mode}`, persisted under the key `ble_auth_config`. The device controller provisions it in the configuration record it pushes to the module on every module start-up; a module with no stored value runs `0, 30, 0`.

| device | `auth_mode` | `auth_timeout` | `keep_unauth_mode` |
|---|---|---|---|
| A1783 C2000 Gen 2 (controller v1.2.1.1, v1.2.1.6) | 2 | 180 s | 1 |
| A2345 Prime Charger 250 W | 2 | not sent (module default 30 s) | 0 |
| A91B2 Prime Charging Station | not sent (module default 0) | not sent (30 s) | not sent |

- The values are constants in the device firmware, so a factory-fresh A1783 runs `auth_mode 2` from its first boot.
- The device reports its `auth_mode` as `0803 a5` (`02` / `00` above).
- `keep_unauth_mode` has no reader in the module.
- `auth_mode` 3 and 4 take a password (`b5` of the configuration record); the A1783, A2345 and A91B2 don't use them.

## How a link becomes authorized

| negotiation path | authorized at |
|---|---|
| cleartext ECDH (`0001` … `0021`) | `0821`, whatever the `auth_mode` |
| legacy confer, either outer | `0822` / `4822`, when `auth_mode` is 0 |
| encrypted ECDH (`4001` … `4021`) | only a successful `0027`; `4822` authorizes nothing |

| device | route | authorizes at |
|---|---|---|
| A1783 | encrypted ECDH, `4027` with an enrolled id | `4827 00` |
| A2345 | encrypted ECDH, `4027` | `4827 00` |
| A2345 | cleartext ECDH (`0005 a5 40`) | `0821`; `4200` / `420a` / `420b` answered with no `4027` |
| A91B2 (`auth_mode 0`) | cleartext ECDH | `0821` |
| A91B2 | legacy confer on either outer | `4822` |
| AS220 S2000 | encrypted ECDH, `4027` with a 36-byte client UUID | `4827 00`; a new token needs one press of the Power button |

`0027` on an `auth_mode 0` unit answers `00` and drops the link 19 ms later, so a client must not send it there.

## `0027` (`getAuthentication`)

`a1` timestamp · `a2` account or token (≤ 63 B) · `a3` password (`auth_mode` 3).

| `auth_mode` | result |
|---|---|
| 1 | `00` when an account is saved or the binding time window is open |
| 2 | `00` when this `a2` is enrolled; otherwise `09 a1 <u16 LE auth_timeout>`: a confirmation window opens, and pressing the device's button sends an unsolicited `4827 00` on `030101` and enrolls `a2` |
| 3 | `00` on a correct password (or no `a3` with the account saved); `0a` / `0b` on a wrong one |
| 0 or ≥ 4 | `00`, then the module disconnects; also `auth_mode` 3 with no `a3` and no account saved |

- `01`: `a2` missing or > 63 B, a password > 16 B, a policy hook missing; on module v0.3.3.0 also "not ECDH-done or not encrypted".
- `a2` is any byte string: an account, a serial, a 16-byte token, a 36-byte UUID and a 40-byte owner id all take the same path. Each new value costs one press; an enrolled value is accepted silently from then on.
- `a3` = the serial with no `a2` answers `01` (`Set Account ID Failed`).
- After ECDH against an unknown client, an A2345 sends `4827 09 a1 02 1e00` on its own about 94 ms after the `4822` ack, before any `4027`; a client that does send `4027` gets the `09` as the reply.
- The link stays up during the window; it drops `auth_timeout + 5` s later if nobody presses.
- The account id is on the wire before the grant (in `4029` and the first session frame), so the press authorizes this client; it doesn't deliver the account.
- The S2000 is single-owner: binding a new token replaces the previous one, the phone app's included.

Registration on a unit with no enrolled client (A2345):

| step | frame | result |
|---|---|---|
| 1 | `4027` with a new token in `a2` | `09 a1 02 1e00`: awaiting confirmation, 30 s |
| 2 | press the side button | unsolicited `4827 00` on `030101` |
| 3 | `4200` / `420a` / `420b` | `4303` + `ca00` telemetry |
| 4 | reconnect with the same token | `4827 00` at once, no button |

## Authorize timer

Every 10 s, while the link is unauthorized and the device isn't in factory mode, the module drops it 30 s after connect, or `auth_timeout + 5` s after a confirmation window opened. The checks run every 10 s, so a drop fires up to 10 s late (measured on an A91B2: 38.0–38.3 s after the `4822` ack). Log strings: `BLE auth timeout after %d seconds`, `BLE not AUTH, factory_mode = %d, disconnecting`.

## Forwarding gate

| module build | client → controller | controller → client |
|---|---|---|
| C-series Gen 2 v0.3.3.0 | forwarded only when authorized | — |
| C-series Gen 2 v0.3.0.6 | logs `ble not auth, not transfer` and forwards anyway | — |
| Prime v0.2.9.7 | logs `ble not auth, not transfer` and forwards anyway | dropped while unauthorized |

So on an unauthorized Prime link a request reaches the controller but its reply never reaches the client: an unauthorized encrypted-outer A91B2 link gets no reply to `4057`, `4100`, `4200` or `4300`, while the same `4200 a1 01 21` on an authorized link returns the `4a00` snapshot within half a second.

## Module v0.3.3.0 enforcement

C-series Gen 2 module v0.3.3.0 (A1783 from September 2026) adds three refusals, all active when `auth_mode ≠ 0`:

- `0001` (cleartext connect) is refused with `enforce: reject non-GCM connect` and a disconnect; there is no `0801`, and the link drops 31–124 ms after the write, sometimes before the write itself returns. A client must read the advert capability byte and open with `4001`.
- `0005` without an ECDH bit is refused (status 1).
- `0027` requires a completed ECDH and an encrypted frame.

v0.3.0.6 had the same `auth_mode` but refused none of these. The Prime module v0.2.9.7 has no enforcement branch at all.

## Binding

| device | request | reply | streams afterwards |
|---|---|---|---|
| A91B2 | `4023` + `a3 10 <serial>` with `a2 28 <account>` | `00 a1 10 <serial>` | yes |
| A91B2 | the same without `a2` | `04` | yes: the A91B2 streams on `4022` + `4200` / `420b` without a bind |
| A2345 | `4023` + serial | `04` | no |
| A2345 | `4027` + `a2 28 <owner id>` | `00` | yes |

`0023` (bind user) takes `a1` timestamp, `a2` account (required, else `04`) and `a4` retained bind data. It stores the account the module presents to its own controller and checks account-bearing commands against, starts a WiFi pre-scan, changes no key and authorizes nothing. Cloud activation takes its account from the WiFi activation command, not from `0023`.

## Client checklist

| requirement | why |
|---|---|
| open with `4001` under the static key when the advert capability is `04` | module v0.3.3.0 drops a cleartext `0001` |
| after encrypted-outer ECDH (`4001`), send `0027` with an enrolled id or the account before any opcode ≥ `0x40`; never send `0027` to an `auth_mode 0` unit | a `4001` ECDH session is authorized only by `0027`; cleartext ECDH authorizes at `0821` and legacy confer at `0822`; on `auth_mode 0` `0027` disconnects |
| route `030101` | the button grant arrives there |
| send an ECDH bit in `0005 a5` (`44` encrypted, `40` cleartext) with `a6` = `0803 a5` | only ECDH sets capability mode 4 and lets `0021` through |
| send `0022 a3` as a 4-byte signed offset computed at send time | the device reads 4 bytes; DST and non-US zones |
| derive every TLV length from its value | TZ strings vary (`JST-9` 5, `CET-1CEST,M3.5.0,M10.5.0/3` 26); serials are 16 or 17 B |
| strip the 16-byte GCM tag before walking TLVs | an unstripped tag ends the walk mid-field |
| use `0803 a2` as the fragment cap | BlueZ `mtu_size` |
| write commands without response | the characteristic offers both; the app writes without response, and a with-response `4100` hangs through an ESPHome proxy |
