# Frame format

Every transport except the legacy `1780` one carries `ff09` frames: the negotiated `8c85` and `2215` services over BLE, the device's internal link between comms chip and controller, and the cloud's MQTT payloads. One parser serves all of them.

## Layout

```
ff09 │ len (2 B LE, whole frame incl. magic) │ pattern (3 B) │ cmd (2 B) │ payload │ checksum (1 B)

ff09 1b00 030001 0803 00a10102a202fd00a30144a40101a50100 fd
     len 27 · pattern 030001 · cmd 0803 · payload: status 00 + TLVs · checksum fd
```

The checksum is the XOR of every preceding byte, `ff09` included. The frame carries no other integrity check. Payload-level checks differ by family and payload: large schedule records carry a CRC32 tag; OTA images are checked by the device, by CRC32 on the A1340 1.6.1 and by CRC32 plus a P-256 ECDSA signature from A1340 1.6.2.

## Pattern

`pattern = 03 <b5> <channel>`.

- The channel (< `0x18`) is the comms chip's dispatch key, and each channel has its own opcode namespace: `0x22` is `getAesKey` on `0x01` but `scanWifi` on `0x13`.
- `b5` names the composer that built the frame. The send composer (device pushes, replies relayed from the device controller, relays toward the controller) writes `01`. The reply composer (the comms chip's own answers to opcodes < `0x40`) copies the request header and so echoes the client's `00`.
- The comms chip rebuilds the header on every hop: it keeps channel, opcode and payload, encrypts only toward the client, and recomputes length, flags and checksum.

Channels of the ESP32-C3 comms module (C-series Gen 2 builds v0.3.0.6 / v0.3.3.0, Prime build v0.2.9.7):

| pattern | channel | carries |
|---|---|---|
| `030001` | `0x01` negotiation | client requests; the module's own replies (`4803`, `4805`, `4821`, `4829`, `4822`) |
| `030101` | `0x01` negotiation | device-initiated: the `4827` grant after the button press |
| `030002` | `0x02` WiFi provisioning | `4030` / `4031` / `4032`; A1783 replies `4830` `00 a1 01 06`, `4831` `01`, `4832` `04`. `0000` and `4200` sent here get no reply |
| `03000c` | `0x0c` factory | op `0x00` only; the module checks no authorization on it |
| `03000f` | `0x0f` session | client get / set; the module's local session replies (`4820`, `4830`) |
| `03010f` | `0x0f` session | relayed replies (`4857`, `c900`) and pushes (`c421`, `c490`, `4303`) |
| `030010` | `0x10` controller link | the module ↔ device-controller UART link. The dispatch doesn't check which port a frame came in on, so a BLE frame on this channel runs controller-link handlers; `0863` here switches the module's UART to 921 600 baud |
| `030011` / `030111` | `0x11` app channel, the same handler as `0x0f` | client requests / device pushes and relayed replies |
| `030013` | `0x13` WiFi provisioning | ops `0x22`–`0x25` (`0x22` = `scanWifi`) |

- A client must route every `0301cc` pattern: the authorization grant arrives on `030101`.
- A locally handled reply echoes the request's pattern: a `4830` answer to a `03000f` request arrives on `03000f`.
- The A2687 answers every session request on `030111`, replies and pushes alike.
- The A1340's controller handles channel `0x01` (negotiation, crypto on the BLE chip) and channel `0x11` (status, configuration and pushes).
- Scanning ciphertext for `ff09` finds phantom frames: anchor on the ATT operation boundaries.

## cmd

`msgtype = (cmd[0] & 0x0f) << 8 | cmd[1]`; a response is the request `| 0x0800`. The high nibble of `cmd[0]` holds link flags, independent of the message. SolixBLE's `Packet` reads the header as `composer` and `channel` (pattern), and `fragmented`, `encrypted`, `response` (`0x0800`), `message` (the low 11 bits) and `msgtype` (cmd).

| flag | meaning |
|---|---|
| `0x40` | encrypted / authorized link. It says nothing about the cipher: the A91B2 sends `4022` / `4023` under AES-CBC |
| `0x80` | fragment: the first payload byte is `index << 4 \| total`; the receiver reassembles and clears the flag |
| `0xc0` | both |

`c900` = flags `0xc0` + msgtype `0x900`, the response to `0x100`. The same msgtype arrives as `4900` (flag `0x40` only) when the reply fits one write: an A1783's one-byte decrypt-failure `01` ("Status byte") comes back `4900`, on the same channel as the fragmented `c900` snapshot. MQTT frames carry flag nibble `0` (`0421`, not `c421`), so `0425`, `4425` and `c425` are one message. Key on the msgtype, never the literal cmd.

**The comms-chip boundary.** On the app channels (`0x0f` / `0x11`) a msgtype with `(opcode & ~0x800) < 0x40` is handled by the comms chip (negotiation, admin, WiFi, OTA); `≥ 0x40` is forwarded unchanged to the device controller. One dispatch table serves every port (BLE, controller UART, cloud), keyed by channel alone.

| group | requests | responses | role |
|---|---|---|---|
| `0` → `8` | `0001 0003 0005 0021 0022 0023 0027 0029 0030` · `0040 0043`–`0052 0057 005a 005e 0060 0067`–`0069 0071 0073 0075`–`0082 0089 0091 0092 009a` | `0801 0803 0805 0821 0822 0823 0827 0829 0830 0857 085e 0872 0889 0892` | the control plane: negotiation and admin below `0x40`, device get / set above |
| `1` → `9` | `0100 0101 0103` | `0900 0901 0903` | subscribe / parameters |
| `2` → `a` | `0200 020a 020b` | `0a00 0a0a 0a0b` | status / control |
| `3` → `b` | `0300 0302 0303` | — | push |
| `4` → `c` | `0402 0405 0409 0421 0490` | — | push |
| `5` | `0500`–`0524` | | A1340 status, configuration and pushes (channel `0x11`) |

Status requests and telemetry by family:

| family | status request | telemetry |
|---|---|---|
| C-series Gen 2 (A1763, A1783), S2000 (AS220) | `0100` (`4100`) → `0900` (`c900`) | pushes `0421` (`c421`), `0490` (`c490`, C-series Gen 2) |
| C-series first generation (A1761 C1000, A1722 C300) | `0040` (`4040`) → `0840` (`c840`) | push `0402` (`c402`), the cloud's `0405` layout |
| Solarbank (A17C1, A17C5) | `0040` (`4040`); the answer is the `0405` push | pushes `0405` (`c405`), `0409` |
| Prime chargers and station (A2345, A91B2, A2687) | `0200` (`4200`) → `0a00` (`4a00` / `ca00`) | pushes `0300`, `0303` |
| A1340 Prime Power Bank | `0500` → 158-byte status | pushes `050e` (live power), `0522` (temperature) |

## Status byte

A response payload starts with a 1-byte status; pushes have none, so a `c900` and a `c421` carry the same fields one byte apart.

- `00` success, `01` fail, `02` account check failed and `04` parameter check failed (a required field missing) are the module's wire codes.
- A session frame that fails to decrypt under the link's current key gets a one-byte `01` from the comms module itself (module v0.3.3.0), on the request's own pattern and sealed under the current key: a `4100` sent under a stale session is answered `4900 01` on `03000f` instead of `c900` on `03010f`. The frame isn't relayed to the device controller and the link stays up, so every such frame gets the same 17-byte reply (`01` + tag) until the client renegotiates. This is the case when two clients share one BLE connection, for example through a relay: the module keeps one session key per link, and the second client's ECDH replaces the first's ([authorization.md](authorization.md#client-checklist)).
- Codes above `04` are per opcode: `4827` `09` = awaiting the button, `0827` `0a` / `0b` = wrong password, `0824` `23` / `24` = WiFi connect failed / activation missing IP.
- The OTA replies (`4064` / `0864` device OTA, `402f` / `082f` module OTA data) and the device controller's `0x80c` OTA chunk reply use `10` / `11` / `12` for complete / image failed to finalize / resend. Outside OTA the modules send no `11`.
- The app names statuses through an enum (`success`, `fail`, `accountVerifyFailed`, `timestampVerifyFailed`, `parameterVerifyFailed`, `noMoreData`, `lowPower`, WiFi `scanFailed` … `activateCommFailed`, `crc32VerifyFailed`, `fireWarmVerifyFailed`, `needAuthentication`, `authPasswordWrong`, `authRetryExceeded`), but it maps wire bytes onto that enum per opcode, so an enum ordinal is not a wire code.

## Payload

Negotiation frames (channel `0x01`) carry untyped TLVs; session frames (channels `0x0f` / `0x11`) carry typed ones after an untyped routing marker:

```
negotiation   tag len value                 0803:  a1 01 02 · a2 02 fd00 · a3 01 44
session       tag len type value            ca00:  a1 01 31 · a2 03 02 7a07 · b0 02 01 01 · fe 05 03 00b95569
              (type byte counted in len)           marker    u16 0x077a     u8 1         4-byte epoch
```

| type | value | the app's type table |
|---|---|---|
| `00` | string | string |
| `01` | u8 | unsigned int, 1 byte |
| `02` | 2-byte integer, LE | signed int, 2 bytes, LE |
| `03` | 4 bytes, LE (the `fe` epoch) | variable, 1–4 bytes, may be signed |
| `04` | raw bytes, often a bitmap or a packed struct | bitmap |
| `05` | | signed float, 4 bytes, LE; not seen on the wire |

All multi-byte integers are little-endian.

- Tags run from `0xa1` per opcode and are ordinal: a decoder keys on `(device, msgtype, field index)`. The same index means different things per opcode (`4027` `a3` is a password, `0023` `a3` the serial) and per device (the same opcode's `a2` can have another shape on another model).
- Never hardcode a length byte: `a228` = field 2 of 40 bytes (an account id), `a224` = 36 (a dashed UUID), `a516` = 22 (a POSIX time zone), `a140` = 64 (a P-256 point without `04`).
- Session requests are `a1 01 21 <fields> fe 05 03 <u32 LE epoch>`; the `fe` trailer is the UTC epoch.

### Routing marker

In session frames `a1` is a 1-byte routing marker: low nibble = source (1 BLE, 2 MQTT, 4 MQTT 2, 9 offline, `a` HTTPS event), high nibble = destination (2 device controller, 3 BLE / app, 7 troubleshoot topic).

| `a1` | meaning |
|---|---|
| `21` | a client request to the device controller |
| `31` | the controller's reply or push to BLE |
| `34` | to MQTT `param_info` |
| `32` | to MQTT (`state_info` when the frame names a custom topic) |
| `12` | MQTT push from the controller (S2000 `0504`) |
| `1a` | to HTTPS `upload_pb_events` |

| sent | reply | meaning |
|---|---|---|
| `a1 01 21` · `a2 02 012c` · `fe 05 03 00b95569` | `4857` `00 a1 01 31` | handled and answered |
| `a1 01 31` · same | `4057`: the request back + `0202` | relayed verbatim, never handled: it returns on the request opcode |

A reply on the un-incremented opcode means the frame was routed past the handler.

### Over MQTT

The cloud wraps the whole `ff09` frame in base64 inside the JSON `payload.data` of a `dt/anker_power/<PN>/<SN>/param_info` message. The frame is cleartext with flag nibble `0`; the routing marker reads `34` or `32` instead of `31`. A C1000's BLE `c402` is its MQTT `0405` with `a1 31` in place of `a1 34`.
