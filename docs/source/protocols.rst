=========
Protocols
=========


Overview
========

Anker has implemented many protocols over the years for communicating with their devices,
with each generally getting more complicated than the last. Some devices support older 
protocols, some accept both older and newer ones, and some only accept the latest, with 
this often changing with firmware updates and dependant on hardware revision. This page
details the underlying protocol and the structure that SolixBLE uses to handle this. 


The legacy protocol (Not supported)
-----------------------------------

This is the first protocol used only by early hardware revisions of the F2000, is 
is completely distinct from the later protocols and shares nothing with them. These 
devices are currently not supported.


The early `Solix` protocol (Removed in firmware update)
-------------------------------------------------------

This is the first protocol that was used by multiple devices. It used no encryption and 
transmitted data in plain text and was used by the C300(X), C800(X), C1000(X) and potentially
more. This was the first version that SolixBLE supported and this protocol was removed in 
a firmware update forcing all devices to use the encryption of the next protocol.


The `Solix` protocol (Used by old devices)
------------------------------------------

This is the protocol used by G1 Solix devices today, such as the C300(X) and C1000(X), it 
implements encryption by performing ECDH key negotiation during connection and then uses
AES CBC for encrypting all communication using the shared secret.


The `Prime` protocol
--------------------

This is the protocol used by older `Prime` devices today such as the 160w and 250w desktop 
chargers. It differs from the `Solix` protocol in that it uses AES GCM for encryption and 
the initial negotiation and ECDH exchange is encrypted using a static key. It is worth 
noting that there is a newer variant of this protocol which requires you to press a button 
when pairing.


Packet structure
================


The overall structure
---------------------

With the exception of the earliest devices, all Anker devices use the same packet structure 
for sending data. Later versions of the protocol implement support for payloads to be spread
across multiple packets (fragmentation), see the later diagram.

.. mermaid::

  packet-beta
  title General Packet Layout Example
  0-15: "Header (2B)"
  16-31: "Length (2B)"
  32-55: "Pattern (3B)"
  56-71: "CMD (2B)"
  72-327: "Payload (variable)"
  328-335: "Checksum (1B)"


Example of a decoded packet:

.. mermaid::

  packet-beta
  title Packet Structure for ff090e00030001080100a1010152
  0-15: "Header: 0xFF09 (2B)"
  16-31: "Length: 0x0E00 (2B)"
  32-55: "Pattern: 0x030001 (3B)"
  56-71: "CMD: 0x0801 (2B)"
  72-103: "Payload: 0x00A10101 (4B)"
  104-111: "Checksum: 0x52 (1B)"


.. note::

  In this example the payload is not encrypted (encryption is determined by the pattern field) as the example
  is from a negotiation packet of an older Solix device, normal payloads may require defragmentation and will
  require decryption.


Advanced packet structure
-------------------------

The basic packet structure shown above can be further broken down to extract more details, 
though these details are not always needed.

Frames on the negotiating transport have this layout (0-based byte offsets):

.. mermaid::

  packet-beta
  0-15: "magic (ff09)"
  16-31: "length (u16 LE)"
  32-39: "pattern family (03)"
  40-47: "composer"
  48-55: "channel"
  56-59: "flags"
  60-71: "message type"
  72-79: "fragment index / total (only when fragmented)"
  80-95: "payload (...)"
  96-103: "XOR checksum"

* Magic is the packet header used by all packets sent/received to/from the device.
* Length is the total length of the packet.
* The pattern is made up of 3 bytes and is used for packet routing with each byte specifying something.

  * The first byte is always 0x03.
  * The second byte is the channel and is 0x01 if the packet was sent by the device on its own and is 0x00 if its an echo of a command.
  * The third byte is the dispatch key and specifies what type of command the packet contains.
* The flags specify if the message is fragmented (0x08), encrypted (0x04), or neither (0x00).
* The message type is effectively the command of the packet (e.g switch USB on/off, send negotiation stage 1 payload, etc).
* The fragment index is an optional field only present if the fragmented field is set and contains the index of this fragment and the total number of fragments.
* The payload is the TLV encoded parameters of the message type / command (e.g specifying which USB port to turn on/off).
* The last byte of the packet is an XOR checksum of the entire content of the packet.


.. code-block:: text

    b0-1  ff09          magic
    b2-3  length        u16 LE, whole packet
    b4    03            pattern family
    b5    composer      01 = sent by the device on its own (pushes, relayed replies); 00 = echoed from the request (local replies)
    b6    channel       the device's dispatch key
    b7    flags | msgtype hi   high nibble: 0x80 fragmented, 0x40 encrypted; low nibble: message type bits 8-11
    b8    msgtype lo
    b9    fragment index << 4 | total   (only when 0x80 is set)
    ...   payload
    last  XOR checksum

Bytes ``b4-6`` are the pattern
(:py:data:`PacketPattern <SolixBLE.constructs.PacketPattern>`) and bytes
``b7-8`` the command
(:py:data:`PacketCommand <SolixBLE.constructs.PacketCommand>`).

- Message type = ``(b7 & 0x0f) << 8 | b8``. A response is the request's message
  type with ``0x800`` set.
- The flag nibble is the frame's own state. On the session channels the library
  decrypts a received frame only when ``0x40`` is set.
- The library reassembles fragments only when ``0x80`` is set. The first payload
  byte is then ``index << 4 | total``, counting from 1; a single fragment reads
  ``11``. Fragments are reassembled before decryption.


Channels
--------

The channel is the second byte of the pattern and specifies the routing of the 
packet. These are the channel values that have been observed.

.. list-table::
   :header-rows: 1

   * - Channel
     - Carries
     - Handled as
   * - ``0x01``
     - negotiation requests and replies, and the grant the device pushes on
       pattern ``030101`` after its button is pressed
     - negotiation
   * - ``0x0f``, ``0x11``
     - session commands, replies (composer ``00``) and pushes (composer ``01``)
     - futures, then telemetry
   * - ``0x02``, ``0x13``
     - WiFi provisioning
     - logged, not handled
   * - ``0x0c``
     - factory
     - logged, not handled
   * - ``0x10``
     - MCU link
     - logged, not handled
   * - any other
     -
     - logged

.. note::

    Negotiation frames are decrypted by the negotiation itself, whatever their
    ``0x40`` flag.


Decrypted payload structure
---------------------------

Once the payload has been defragmented and decrypted (protocol specific) the plain text payload may be decoded. 
This structure is the same across all protocols (except for early revisions of the F2000) and uses TLV encoding, where the
payload is made up of a list of parameters and each parameter contains a key, length field, optional type field,
and value. 

.. mermaid::

  packet-beta
  title General Parameters Layout
  0-7: "Key (1B)"
  8-15: "Length (1B)"
  16-23: "Type (optional) (1B)"
  24-31: "Value (Length bytes)"
 
Example of a decoded payload:

.. mermaid::

    packet-beta
    title Anker Payload TLV Structure (00a10102a202fd00a30144a40101a50102)
    0-7: "Prefix / Status: 0x00 (1B)"
    8-15: "P1 Key: 0xA1 (1B)"
    16-23: "P1 Length: 0x01 (1B)"
    24-31: "P1 Value: 0x02 (1B)"
    32-39: "P2 Key: 0xA2 (1B)"
    40-47: "P2 Length: 0x02 (1B)"
    48-55: "P2 Type: 0xFD (1B)"
    56-63: "P2 Value: 0x00 (1B)"
    64-71: "P3 Key: 0xA3 (1B)"
    72-79: "P3 Length: 0x01 (1B)"
    80-87: "P3 Value: 0x44 (1B)"
    88-95: "P4 Key: 0xA4 (1B)"
    96-103: "P4 Length: 0x01 (1B)"
    104-111: "P4 Value: 0x01 (1B)"
    112-119: "P5 Key: 0xA5 (1B)"
    120-127: "P5 Length: 0x01 (1B)"
    128-135: "P5 Value: 0x02 (1B)"

The exact steps in decoding a payload:

.. mermaid::

  flowchart TD
      Start([Start Payload Parsing]) --> ReadPrefix{Status Prefix < 0xA1?}
      ReadPrefix -- Yes --> HasPrefix[Read Status Byte / Prefix: 1B]
      ReadPrefix -- No / None --> ReadKey
      HasPrefix --> ReadKey[Read Parameter Key: 1B]
      
      ReadKey --> ReadLen[Read Parameter Length: 1B]
      ReadLen --> CheckLen{Length > 1?}
      
      CheckLen -- Yes --> HasType[Read Optional Type Field: 1B]
      CheckLen -- No --> SkipType[No Type Field]
      
      HasType --> ReadVal[Read Remaining Bytes as Value]
      SkipType --> ReadVal
      
      ReadVal --> MoreBytes{More bytes left in payload?}
      MoreBytes -- Yes --> ReadKey
      MoreBytes -- No --> End([End Parsing / Build Dict])

      style Start fill:#f9f,stroke:#333,stroke-width:2px
      style End fill:#bbf,stroke:#333,stroke-width:2px


Advertisement
-------------

Anker devices publish a record under the BLE company identifier ``0xffff``, readable
before connecting in the BLE advertisements and these contain useful information 
about the hardware and its capabilities.

.. mermaid::

  packet-beta
  0-7: "version (1B)"
  8-55: "mac (6B)"
  56-63: "bind_type (1B)"
  64-79: "product_type (2B)"
  80-103: "sku (3B or 4B by version)"
  104-111: "capability (1B)"

.. code-block:: text

    version(1) | mac(6) | bind_type(1) | product_type(2) | sku(3 or 4 by version) | capability(0-1)



Implementation
==============

This section covers how the protocols are implemented in the classes and the control flow 
when communicating with a device.


SolixBLE structure
------------------

SolixBLE is structured into a hierarchy of classes, with devices able to override or implement additional 
functionality to handle device (e.g C1000) or device class specific (Prime style) quirks.

The `SolixBLEDevice` class is the main class of the program which implements the main control flow of the
program with device class specific details (such as the transport implementation) being split out into 
helper classes.


.. mermaid::

  classDiagram
      direction TB
      class SolixBLEDevice {
          _TRANSPORT
          _OUTER_HINT = PlainOuter
          _outer_class
          _session
          connect()
          _send_command()
          _process_notification()
          _initial_outer(advertisement)
      }
      class PrimeDevice {
          _OUTER_HINT = EncryptedOuter
          _post_authorize()
      }
      SolixBLEDevice <|-- C1000G2
      SolixBLEDevice <|-- C800
      SolixBLEDevice <|-- F3800
      SolixBLEDevice <|-- Solarbank2
      SolixBLEDevice <|-- Generic
      SolixBLEDevice <|-- PrimeDevice
      PrimeDevice <|-- PrimeCharger250w
      PrimeDevice <|-- PrimeCharger160w
      PrimeDevice <|-- PrimePowerBank20k
      PrimeDevice <|-- MagGo3in1
      note for SolixBLEDevice "and the other device classes"

      SolixBLEDevice --> NegotiatingTransport : _TRANSPORT
      SolixBLEDevice --> Transport2215 : _TRANSPORT
      SolixBLEDevice --> LegacyTransport : _TRANSPORT

      class Link {
          <<protocol>>
          _send_packet()
          _timestamp()
          _generate_private_key()
      }
      SolixBLEDevice ..|> Link

      class NegotiatedSession {
          outer
          path
          announcement
          link
          open()
          on_reply()
          encrypt(payload)
          decrypt(payload)
      }
      SolixBLEDevice --> NegotiatedSession : _session, a new one for each opening
      NegotiatedSession --> Link : link

      class Outer {
          <<protocol>>
          open_flag
          sends_client_id
          x005_tags(announcement)
          encrypt(payload, keys)
          decrypt(payload, keys)
      }
      Outer <|.. PlainOuter
      Outer <|.. EncryptedOuter
      NegotiatedSession --> Outer : outer

      class Path {
          <<protocol>>
          keys
          authorized
          matches(announcement, outer)$
          on_stage(session, msgtype, status, parameters)
          encrypt_override(payload)
      }
      Path <|.. EcdhPath
      Path <|.. LegacyAesPath
      NegotiatedSession --> Path : path, the first of PATHS whose matches() accepts x803

- The outer is how the negotiation travels and which cipher (e.g AES CBC, GCM, etc) the session uses (see `Outer protocols`_).
- The path is the key exchange and authorization after the shared opening (see `Paths`_).
- The session ties one outer and one path to one connection; the device is its link, which builds and writes the frames.
- ``_TRANSPORT`` specifies what GATT characteristics to use to communicate with the device and whether negotiation is required..
- ``_OUTER_HINT`` is the default outer to use if this cannot be determined from the BLE advertisement and is ``PlainOuter`` unless the device class (e.g Prime 160w) overrides it.
- ``_outer_class`` is the outer to use and starts as ``_initial_outer(advertisement)`` and will be upgraded to ``EncryptedOuter`` if the connection is refused using ``PlainOuter`` and will remain as the last outer that authorized successfully.
- ``announcement`` holds what the device declared.
- ``NegotiatedSession.encrypt()`` uses ``path.encrypt_override()``, else ``outer.encrypt()`` under ``path.keys``. ``NegotiatedSession.decrypt()`` uses ``outer.decrypt()`` under ``path.keys``.


Transports
----------

Anker devices use one of three BLE transports. A device class names its
transport in the ``_TRANSPORT`` attribute, which selects the GATT
characteristics the library subscribes to and writes to.

.. list-table::
   :header-rows: 1

   * - Transport
     - Recognized by
     - Characteristics
   * - Negotiating (:py:class:`SolixBLE.transport.NegotiatingTransport`)
     - advertised service ``ff09``
     - command ``8c850002-...``, telemetry ``8c850003-...``; a session is
       negotiated before commands
   * - 2215 (:py:class:`SolixBLE.transport.Transport2215`), e.g the A1340
       Prime power bank
     - advertised service ``2215``
     - command ``22150002-4002-...``, telemetry ``22150003-4002-...``; the
       negotiating transport's frames and negotiation
   * - Legacy (:py:class:`SolixBLE.transport.LegacyTransport`), e.g the 767 /
       F2000 on older firmware
     - advertised service ``1780``
     - command ``7777``, telemetry ``8888``; no negotiation

.. note::

    A device on the legacy transport is
    :py:attr:`negotiated <SolixBLE.SolixBLEDevice.negotiated>` as soon as it is
    connected.


Sending packets
---------------

Sending a command can be achieved by calling either `_send_command()` on the device class
or `send()` on a negotiated session object. `_send_command()` can be used to send a command 
to the device and it uses the command pattern and adds and it automatically adds additional 
information such as the current timestamp to the command which is required by some Anker devices to 
provide protection against replay attacks.

`send()` is a lower level implementation which is used during negotiation and allows for the pattern 
to be set and does not automatically include the timestamp.

Both functions call the same underlying `_send_packet()` command which converts the parameters into 
bytes to make up the payload, optionally encrypts the payload using `_encrypt_payload()`, and then 
builds a packet using the payload with the specified pattern and command and then writes it to the 
device.

.. mermaid::

  flowchart TD
      cmd["_send_command(cmd, parameters)<br/>session commands: pattern 03000f, adds fe"]
      neg["NegotiatedSession.send(msgtype, ...)<br/>negotiation: pattern 030001,<br/>cmd from PacketCommand.build(flags, msgtype)"]
      sp["_send_packet(pattern, cmd, parameters)"]
      cmd --> sp
      neg --> sp
      sp --> build["Parameters.build()<br/>tag-length-value parameters<br/>(lambdas called with the device)"]
      build --> enc["_encrypt_payload() -> session.encrypt()<br/>path.encrypt_override(), else<br/>outer.encrypt(payload, path.keys)"]
      enc --> pkt["Packet.build()<br/>ff09, length, pattern, cmd, payload, XOR checksum"]
      pkt --> write["write_gatt_char(UUID_COMMAND, packet)"]


Receiving packets
-----------------


Packets from the device are received by subscribing to a telemetry GATT characteristic defined in 
the transport which calls `_process_notification()` when a new packet is received. 

The basic metadata of the packet (e.g pattern, cmd, etc) is parsed first and this is used to
determine if the packet is fragmented and requires reassembly using the flags part. 
Fragmented packets are not processed until the last fragment arrives, at which point
the payload is reconstructed.

Next the channel part of the pattern is used to determine what to do with the packet, negotiation 
packets are processed and responses sent under the `_process_negotiation()` function, unsupported 
channels are logged and ignored, and supported ones then proceed to the next step.

The flags part of the packet is then used to determine if the packet needs decryption, which handles by 
the `_decrypt_payload()` function. 

Once the raw payload is available the packet is then checked to see if it matches any pre-registered 
listeners. These allow for a device to listen for a packet sent by the device in response to a command 
and get the parsed payload returned to them for custom processing (e.g requesting a ToU schedule). 

If no listeners match it is then is processed by the `_process_session()` function which determines 
if the packet is a telemetry packet based upon the cmd value, and passes it to `_process_telemetry()`
which will store the values inside the device class to update any device attributes (e.g ac_output, light_status, etc)
and trigger any registered device state update callbacks.


.. mermaid::

  flowchart TD
      notif["_process_notification(client, handle, data)"]
      parse["Packet.parse(): checks the ff09 header and the checksum<br/>PacketPattern.parse(): family, composer, channel<br/>PacketCommand.parse(): fragmented (0x80), encrypted (0x40), msgtype"]
      notif --> parse
      parse --> frag{"fragmented?"}
      frag -- yes --> reasm["_reassemble(): FragmentedPayload,<br/>buffered by pattern + cmd"]
      reasm -- "the joined payload,<br/>once every fragment is in" --> chan
      frag -- no --> chan{"channel?"}
      chan -- "0x01" --> nego["_process_negotiation() -> session.on_reply()<br/>(decrypts if 0x40 is set; see Negotiation flow)"]
      chan -- "not 0x0f / 0x11" --> drop["logged, dropped"]
      chan -- "0x0f / 0x11" --> encq{"encrypted?"}
      encq -- yes --> dec["_decrypt_payload() -> session.decrypt(), once"]
      encq -- no --> fut
      dec --> fut{"future for channel + msgtype?<br/>(_future_key(): the composer<br/>and flags don't matter)"}
      fut -- yes --> setres["future.set_result(payload)<br/>(_listen_for_packet())"]
      fut -- no --> sess["_process_session(cmd, payload, encrypted=...)"]
      sess --> tel{"msgtype 0x300 or in<br/>_TELEMETRY_COMMANDS?"}
      tel -- yes --> telem["Parameters.parse()<br/>encrypted -> session.on_session_push()<br/>_process_telemetry() -> state callbacks"]
      tel -- no --> logged["logged"]

- ``_send_command()`` raises ``ConnectionError`` until the device is negotiated; its ``cmd`` carries the flags as given (e.g ``4200``).
- The library sends every packet whole; only received packets are reassembled.
- Telemetry is matched on the message type, so ``c405``, ``4405`` and a clear ``8405`` are one message.


Outer protocols
---------------

The outer class defines protocol specific information needed to negotiate an encrypted session 
with the device such as encryption algorithms (e.g AES GCM vs AES CBC), what encryption to use 
if no key has been negotiated, and what negotiation packets need to contain.

On the negotiating transport a device holds a negotiated session for each
connection. The session's outer protocol is how the negotiation travels and
which cipher the session uses afterwards; the session cipher follows the
opening frame.

.. list-table::
   :header-rows: 1

   * - Outer
     - Opening
     - Before keys
     - Session cipher
     - Client authorized at (ECDH path)
   * - Plain (:py:class:`SolixBLE.protocols.PlainOuter`)
     - ``0001``
     - clear
     - AES-128-CBC, PKCS7
     - ``0821``
   * - Encrypted (:py:class:`SolixBLE.protocols.EncryptedOuter`)
     - ``4001``
     - AES-128-GCM under a static key
     - AES-128-GCM
     - ``4827`` status ``00``, or the first session push the client can decrypt

Both outers run the same opening command (``x001``, ``x003`` for the device's
capabilities, ``x029`` for its serial and MAC), then an ECDH key exchange on
P-256 with a fresh key for every negotiation. The key is the first 16 bytes
of the shared secret; the IV is the next 16 (GCM uses 12 of them).

Which outer is tried first comes from the best hint available, strongest
first:

#. The device itself: a device that drops the link before answering the plain
   ``0001`` refuses it, and :py:meth:`connect() <SolixBLE.SolixBLEDevice.connect>`
   reopens once with the encrypted outer in the same call. A device that
   answered before dropping did not refuse, and the encrypted outer is never
   stepped down to plain.
#. The advertisement's capability byte, passed as
   ``DeviceClass(ble_device, advertisement=advertisement_data)``: bit ``0x04``
   opens encrypted, the byte without it opens plain.
#. The outer that last authorized on this device instance.
#. The model's default (encrypted for the Prime devices, plain otherwise).

.. note::
   :collapsible: closed

   The outer belongs to the device's firmware, not its model: the same model
   can accept the plain negotiation on one firmware and refuse it on the
   next, so a device that updates is picked up at the next reconnect.
   :py:attr:`announcement <SolixBLE.SolixBLEDevice.announcement>` holds what
   the device declared in the latest negotiation (MTU, capability and auth
   methods, serial, MAC and the client registration status).

.. note::

   The Prime chargers expect the region and owner (``420a``) once a client is
   authorized. The owner sent is this client's identifier; the region is the
   one set with :py:func:`set_region() <SolixBLE.set_region>`, else the host
   locale's, else ``GB``.


The Bluetooth advertisement
---------------------------

The Bluetooth advertisement from an Anker device is useful for two purposes, first to 
return the correct device class for the device (e.g c1000x.py for C1000(X)), second for 
finding out what protocols the device supports, since a model might support multiple protocols.

The former is achieved using `device_class_from_advertisement` which given a BLE advertisement returns
the correct class to use to connect to the device, with the advertisement passed to the device class 
during initialization being used to determine which protocol to use to connect to the device.

It is possible to connect using no advertisement and the default protocol will be used for the model, but 
this may result in failure if the device does not support the default protocol, (i.e because its running 
firmware too old or too new).

.. mermaid::

  flowchart LR
    adv["Bleak scan result<br/>(AdvertisementData)"]
    adv -- "device_class_from_advertisement()" --> cls["The model class (e.g C300, C1000, etc)"]
    adv -- "capability_from_advertisement()" --> cap["The outer to open with (The protocol)<br/>(e.g 0x04 = encrypted)"]
    cls --> inst["DeviceClass(ble_device, advertisement=advertisement_data)"]
    cap --> inst


.. list-table::
   :header-rows: 1

   * - Helper
     - Returns
   * - :py:func:`capability_from_advertisement() <SolixBLE.capability_from_advertisement>`
     - the last byte (``capability``), or None if absent; bit ``0x04`` = the
       device accepts the encrypted negotiation
   * - :py:func:`device_class_from_advertisement() <SolixBLE.device_class_from_advertisement>`
     - the model class from ``product_type``, else from the advertised name (the
       model's own, or a Prime-style ``<part number>_<last four MAC digits>``),
       else :py:class:`SolixBLE.Generic`; None for a device on a transport no
       class speaks yet (legacy ``1780``, ``2215``)

.. note::

    :py:func:`device_class_from_advertisement() <SolixBLE.device_class_from_advertisement>`
    does not check that the device is an Anker device. Match the record or
    the advertised service first, as below; a passive scan can carry the
    record without the services. Some firmware advertises the device serial as
    its name, and the legacy transport sends only the MAC (reversed) under
    ``0xffff``, which decodes to None.


Example usage of :py:func:`capability_from_advertisement() <SolixBLE.capability_from_advertisement>` and :py:func:`device_class_from_advertisement() <SolixBLE.device_class_from_advertisement>`:

.. code-block:: python

    from bleak import BleakScanner

    from SolixBLE import capability_from_advertisement, device_class_from_advertisement
    from SolixBLE.advertisement import ANKER_COMPANY_ID
    from SolixBLE.const import UUID_IDENTIFIERS

    def detected(device, advertisement_data):
        if ANKER_COMPANY_ID not in advertisement_data.manufacturer_data and not any(
            uuid in advertisement_data.service_uuids for uuid in UUID_IDENTIFIERS
        ):
            return
        device_class = device_class_from_advertisement(advertisement_data, device.name)
        capability = capability_from_advertisement(advertisement_data)
        print(device.address, device_class and device_class.__name__, capability)

    scanner = BleakScanner(detection_callback=detected)



Negotiation flow
----------------

Before we are able to control a device or receive any telemetry from it (with the exception 
of really old firmware), devices will require us to negotiate a session with them which 
establishes an encryption key to use and other metadata such as the current time and current 
region.

The contents of the negotiation vary depending upon firmware but generally consists of a 
request to negotiate, the agreement of capabilities and some metadata, and the exchange 
of public keys, with some devices also requiring additional messages after this such as 
a subscription to telemetry updates.

Below is the execution flow of calling :py:meth:`connect() <SolixBLE.SolixBLEDevice.connect>` on 
a device:

.. mermaid::

  flowchart TD
      connect["connect()"]
      est["establish_connection()<br/>start_notify(UUID_TELEMETRY, _process_notification)"]
      nego["_negotiate()<br/>until negotiated, the link drops,<br/>an UnsupportedNegotiation, or NEGOTIATION_TIMEOUT"]
      init["_initiate_negotiations()<br/>again if the device sends nothing for<br/>NEGOTIATION_RESPONSE_TIMEOUT seconds"]
      open["_session = NegotiatedSession(_outer_class(), self)<br/>_session.open(): sends x001"]
      reply["each reply: _process_notification() -> _process_negotiation()<br/>-> NegotiatedSession.on_reply() -> on_plaintext()<br/>x801, x803: handled by the session<br/>later: path.on_stage() (EcdhPath or LegacyAesPath)"]
      connect --> est --> nego --> init --> open
      open -.-> reply
      reply -.-> nego
      nego --> done{"negotiated?"}
      done -- yes --> auth["_on_authorized(): _outer_class = type(outer), _post_authorize()<br/>_post_connect(); the reconnect and keep-alive tasks start"]
      done -- no --> refused{"_reopen_if_refused():<br/>link dropped, no reply,<br/>outer was PlainOuter?"}
      refused -- yes --> reopen["_outer_class = EncryptedOuter"]
      reopen -- "connect() once more" --> connect
      refused -- no --> fail["False"]


The first few stages of the negotiation are handled in ``NegotiatedSession`` and consist of the 
same message types/commands (with the exception of the really old ones), where the device tells us its
capabilities including what forms of negotiation it supports and the hardware MTU. Later stages 
of the negotiation differ depending upon the supported negotiation pathways of the device (i.e `Prime` style and `Solix` style).


.. mermaid::

  sequenceDiagram
    participant C as Client (NegotiatedSession)
    participant D as Device
    Note over C: open()
    C->>D: x001 time (+ client id)
    D->>C: x801
    Note over C: on_plaintext()
    C->>D: x003 client MTU
    D->>C: x803
    Note over C: _record_capability(): MTU, capability, auth<br/>path = _choose_path(): the first of PATHS<br/>whose matches() accepts x803, else UnsupportedNegotiation
    C->>D: x029


Paths
^^^^^

After the shared opening the device's capability reply (``x803``) picks the
path that establishes the session keys. Paths are tried in order; the first
that handles the reply runs the rest of the negotiation.

.. list-table::
   :header-rows: 1

   * - ``x803``
     - Path
     - Outer
     - Keys
     - Client authorized at
   * - ``a3 & 0x44`` (ECDH) and an auth method in ``a5``
     - ECDH (:py:class:`SolixBLE.protocols.EcdhPath`): ``x005`` states ECDH,
       ``x021`` / ``x821`` exchange P-256 points, ``x022`` sets the clock,
       ``4027`` registers the client
     - plain or encrypted
     - P-256 with a fresh key for every negotiation; the shared secret's first 16 bytes, IV the next 16 (GCM uses 12 of them)
     - see `Outer protocols`_
   * - otherwise ``a1 & 0x02`` (AES), e.g. ``a1 02`` · ``a3 04`` with no
       ``a5`` on older module builds
     - Legacy AES (:py:class:`SolixBLE.protocols.LegacyAesPath`): ``x005``
       states AES (``a5 02``), ``4022`` sets the clock, ``4822`` returns the
       session key, ``4023`` binds the client
     - plain or encrypted
     - until ``4822``, CBC under the client id's and the serial's first 16 bytes (plain) or the static key and IV (encrypted); after it, the key ``4822`` carries, with the serial (plain) or the static IV (encrypted)
     - ``4822``
   * - neither
     - none: ``connect()`` returns ``False`` and logs
       :py:class:`SolixBLE.UnsupportedNegotiation` naming the values
     - N/A
     - N/A
     - N/A

A device that rejects the stated method (an ``x805`` status other than
``00``) or answers ``x821`` without its key also fails the connect with
:py:class:`SolixBLE.UnsupportedNegotiation`, naming the stage.

.. note::
   :collapsible: closed

   A path is a class with a ``matches(announcement, outer)`` class method,
   which says whether it handles what the device declared on that outer,
   and an ``on_stage(session, msgtype, status, parameters)`` coroutine that
   handles each reply after ``x829``. It sets ``keys`` when it installs
   session keys and ``authorized`` when the device accepts the client. New
   paths are added to :py:data:`SolixBLE.protocols.PATHS`.



A. The Prime style negotiation
""""""""""""""""""""""""""""""

This is the negotiation path for devices which use the newer `Prime` style handshake which contain 
additional information such as device region. This is handled by ``EcdhPath.on_stage()``.

.. mermaid::

  sequenceDiagram
    participant C as Client (EcdhPath)
    participant D as Device
    D->>C: x829
    Note over C: record_identity(): serial, MAC
    C->>D: x005 method ECDH, MTU (outer.x005_tags())
    D->>C: x805
    Note over C: status 00, else UnsupportedNegotiation<br/>link._generate_private_key()
    C->>D: x021 client public key
    D->>C: x821
    Note over C: _exchange_keys(): keys = Keys.parse(ecdh_shared_secret(...))<br/>plain outer: authorized
    C->>D: x022 time, time zone (send_clock())
    D->>C: x822
    opt encrypted outer, not yet authorized
        C->>D: x027 client token
        D->>C: x827
        Note over C: _register(): status 00 authorized<br/>09 sets confirmation_window
        opt status 09, once the device's button is pressed
            D->>C: x827 pushed on pattern 030101
        end
    end


B. The Solix style negotiation
""""""""""""""""""""""""""""""

This is the negotiation path for devices which use the older `Solix` style handshake which does not 
contain information like device region. This is handled by ``LegacyAesPath.on_stage()``.


.. mermaid::

  sequenceDiagram
    participant C as Client (LegacyAesPath)
    participant D as Device
    D->>C: x829
    Note over C: record_identity(): serial, MAC
    C->>D: x005 method AES (a5 02), MTU
    D->>C: x805
    Note over C: status 00, else UnsupportedNegotiation<br/>keys = _bootstrap_keys()
    C->>D: x022 time, time zone (send_clock()), CBC-sealed by encrypt_override()
    D->>C: x822
    Note over C: status 00 with a1, else UnsupportedNegotiation<br/>keys = a1[:16] + _ongoing_iv(), authorized
    C->>D: x023 serial
    D->>C: x823
    Note over C: bind status logged

- ``x`` is the flag nibble: ``0`` on the plain outer until a path installs keys and ``4`` after (``0021``, then ``4022``), always ``4`` on the encrypted outer. Replies set ``0x800`` (``0801`` / ``4801``).
- Before keys, the plain outer sends in clear and the encrypted outer under the static GCM key. Once the path installs keys, the session cipher is the outer's: CBC (plain) or GCM (encrypted). The legacy path's bootstrap request is the one exception: ``encrypt_override()`` seals it in CBC on either outer until ``4822`` authorizes the path.
- ECDH authorizes at ``0821`` on the plain outer; on the encrypted outer at ``4827`` status ``00``, the ``030101`` grant, or the first session push the client can decrypt (``on_session_push()``). Legacy AES authorizes at ``4822`` on either outer.
- ``(+ client id)``: the plain outer inserts the client id as ``a2`` in ``0001``, ``0003``, ``0029``, ``0005``, ``4022`` and the legacy ``4023``; the encrypted outer sends none.


.. note::
    :collapsible: closed

    The Prime Charging Station 240W (A91B2) advertises capability ``00``, and the library follows it: the device opens on the plain outer, where ECDH runs in clear and authorizes at ``0821``. Its capability reply is ``a1 02 · a2 fd00 · a3 44 · a4 01 · a5 00``: it offers both ECDH and AES, and its auth method ``a5`` is ``00``.

    The device also answers the encrypted outer, although its capability byte lacks ``0x04``, and there only legacy AES authorizes it: stating AES in ``4005`` (``a5 02``), the ``4022`` key request CBC-sealed under the static key returns the session key in ``4822``, and the session then runs GCM under that key with the static nonce, with no ``4027``. ECDH on the encrypted outer completes the key exchange, but auth method ``00`` answers ``4027`` with ``4827 00`` and then drops the link. Neither encrypted-outer combination is how the library connects this device.
