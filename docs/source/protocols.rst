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


With the exception of the earliest devices, all Anker devices use the same packet structure 
for sending data. Later versions of the protocol implement support for payloads to be spread
across multiple packets (fragmentation), see the later diagram.

.. mermaid::

  packet-beta
  title General Packet Layout Example
  0-15: "Header (2B)"
  16-31: "Size (2B)"
  32-55: "Pattern (3B)"
  56-71: "CMD (2B)"
  72-327: "Payload (variable)"
  328-335: "Checksum (1B)"


Example of a decoded packet:

.. mermaid::

  packet-beta
  title Packet Structure for ff090e00030001080100a1010152
  0-15: "Header: 0xFF09 (2B)"
  16-31: "Size: 0x0E00 (2B)"
  32-55: "Pattern: 0x030001 (3B)"
  56-71: "CMD: 0x0801 (2B)"
  72-103: "Payload: 0x00A10101 (4B)"
  104-111: "Checksum: 0x52 (1B)"


.. note::

  In this example the payload is not encrypted (encryption is determined by the pattern field) as the example
  is from a negotiation packet of an older Solix device, normal payloads may require defragmentation and will
  require decryption.


Decrypted payload structure
===========================

Once the payload has been defragmented and decrypted (protocol specific) the plain text payload may be decoded. 
This structure is the same across all protocols (except for early revisions of the F2000) and uses TLV encoding, where the
payload is made up of a list of parameters and each parameter contains a key, length field, optional type field,
and value. 

.. mermaid::

  packet-beta
  title General Parameters Layout
  0-7: "Key (1B)"
  8-15: "Size (1B)"
  16-23: "Type (optional) (1B)"
  24-31: "Value (Size bytes)"
 
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
    

Implementation
==============

This section covers how the protocols are implemented in the classes and the control flow 
when communicating with a device.


Initialization flow
-------------------

The Bluetooth advertisement from an Anker device is useful for two purposes, first to 
return the correct device class for the device (e.g c1000x.py for C1000(X)) and for 
finding out what protocols the device supports, since a model might support multiple protocols.

The former is achieved using `device_class_from_advertisement` which given a BLE advertisement returns
the correct class to use to connect to the device, with the advertisement passed to the device class 
during initialization providing being used to determine which protocol to use to connect to the device.

It is possible to connect using no advertisement and the default protocol will be used for the model, but 
this may result in failure if the device does not support the default protocol, (i.e because its running 
firmware too old or too new).

.. mermaid::

  flowchart LR
    adv["bleak scan result<br/>(AdvertisementData)"]
    adv -- "device_class_from_advertisement()" --> cls["the model class"]
    adv -- "capability_from_advertisement()" --> cap["the outer to open with<br/>(0x04 = encrypted)"]
    cls --> inst["DeviceClass(ble_device, advertisement=advertisement_data)"]
    cap --> inst


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

- ``_TRANSPORT`` is a class attribute: the GATT characteristics, and whether to negotiate.
- ``_OUTER_HINT`` is ``PlainOuter`` unless the class overrides it.
- ``_outer_class`` starts as ``_initial_outer(advertisement)``, becomes ``EncryptedOuter`` after a plain refusal, then the outer that last authorized.
- ``announcement`` holds what the device declared.
- ``NegotiatedSession.encrypt()`` uses ``path.encrypt_override()``, else ``outer.encrypt()`` under ``path.keys``. ``NegotiatedSession.decrypt()`` uses ``outer.decrypt()`` under ``path.keys``.
- The outer is how the negotiation travels and which cipher the session uses (see `Outer protocols`_).
- The path is the key exchange and authorization after the shared opening (see Paths).
- The session ties one outer and one path to one connection; the device is its link, which builds and writes the frames.


Transports
----------

Anker devices use one of three BLE transports. A device class names its
transport in the ``_TRANSPORT`` attribute, which selects the GATT
characteristics the library subscribes to and writes to.

.. list-table::
   :header-rows: 1

   * - Transport
     - Recognised by
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


Packet layout
^^^^^^^^^^^^^

Frames on the negotiating transport have this layout (0-based byte offsets):

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
^^^^^^^^

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


Building and parsing a packet
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sending:

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

Receiving, on the telemetry characteristic:

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


Advertisement
^^^^^^^^^^^^^

Anker devices publish a record under BLE company identifier ``0xffff``, readable
before connecting:

.. code-block:: text

    version(1) | mac(6) | bind_type(1) | product_type(2) | sku(3 or 4 by version) | capability(0-1)

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


Outer protocols
---------------

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
     - Client authorized at
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

Both outers run the same opening (``x001``, ``x003`` for the device's
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


Negotiation flow
^^^^^^^^^^^^^^^^

What :py:meth:`connect() <SolixBLE.SolixBLEDevice.connect>` runs:

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

The shared opening, then each path's replies and what each sends next.

Shared opening (``NegotiatedSession``):

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

``EcdhPath.on_stage()``:

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

``LegacyAesPath.on_stage()``:

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

- ``x`` is the flag nibble: ``0`` on the plain outer until keys are installed and ``4`` after (``0021``, then ``4022``), always ``4`` on the encrypted outer. Replies set ``0x800`` (``0801`` / ``4801``).
- Before keys, the plain outer sends in clear and the encrypted outer under the static GCM key. Once ``x821`` installs the keys, the session cipher is CBC (plain) or GCM (encrypted).
- The plain outer authorizes at ``0821``. The encrypted outer authorizes at ``4827`` status ``00``, the ``030101`` grant, or the first session push the client can decrypt (``on_session_push()``).
- ``(+ client id)``: the plain outer inserts the client id as ``a2`` in ``0001``, ``0003``, ``0029``, ``0005`` and ``4022``; the encrypted outer sends none.


.. note::
    :collapsible: closed

    The Prime Charging Station 240W (A91B2) advertises capability ``00``, and the library follows it: the device opens on the plain outer, where ECDH runs in clear and authorizes at ``0821``. Its capability reply is ``a1 02 · a2 fd00 · a3 44 · a4 01 · a5 00``: it offers both ECDH and AES, and its auth method ``a5`` is ``00``.

    The device also answers the encrypted outer, although its capability byte lacks ``0x04``, and there only legacy AES authorizes it: stating AES in ``4005`` (``a5 02``), the ``4022`` key request CBC-sealed under the static key returns the session key in ``4822``, and the session then runs GCM under that key with the static nonce, with no ``4027``. ECDH on the encrypted outer completes the key exchange, but auth method ``00`` answers ``4027`` with ``4827 00`` and then drops the link. Neither encrypted-outer combination is how the library connects this device.
