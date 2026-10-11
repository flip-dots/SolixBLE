=========
Protocols
=========


Classes
-------

How a device object and its negotiation fit together:

.. code-block:: text

    bleak scan result (AdvertisementData)
       |-- device_class_from_advertisement() --> the model class
       '-- capability_from_advertisement()  --> the outer to open with (0x04 = encrypted)

    DeviceClass(ble_device, advertisement=advertisement_data)

    SolixBLEDevice                 connect(), _send_command(), _process_notification()
      |-- C1000G2, C800, F3800, Solarbank2, ..., Generic
      '-- PrimeDevice              _OUTER_HINT = EncryptedOuter, _post_authorize()
            '-- PrimeCharger250w, PrimeCharger160w, PrimePowerBank20k, MagGo3in1

      class attributes
        _TRANSPORT     NegotiatingTransport | Transport2215 | LegacyTransport
                       (GATT characteristics, and whether to negotiate)
        _OUTER_HINT    PlainOuter unless the class overrides it

      per instance
        _outer_class   _initial_outer(advertisement); EncryptedOuter after a plain
                       refusal; then the outer that last authorized
        _session  ---> NegotiatedSession(outer, link), a new one for each opening
                         |-- outer          PlainOuter | EncryptedOuter
                         |                  open flag, x005_tags(), encrypt(), decrypt()
                         |-- path           EcdhPath, chosen after x803
                         |                  on_stage(), keys, authorized
                         |-- announcement   what the device declared
                         '-- link           the device: _send_packet(), _timestamp(),
                                            _generate_private_key(), ...

    NegotiatedSession.encrypt() / decrypt() = outer.encrypt() / decrypt() under path.keys

- The outer is how the negotiation travels and which cipher the session uses (see `Outer protocols`_).
- The path is the key exchange and authorization after the shared opening.
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

.. code-block:: text

    _send_command(cmd, parameters)            session commands: pattern 03000f, adds fe
    NegotiatedSession.send(msgtype, ...)      negotiation: pattern 030001, cmd from
         |                                    PacketCommand.build(flags, msgtype)
         v
    _send_packet(pattern, cmd, parameters)
      Parameters.build()        tag-length-value parameters (lambdas called with the device)
      _encrypt_payload()        -> session.encrypt() -> outer.encrypt(payload, path.keys)
      Packet.build()            ff09, length, pattern, cmd, payload, XOR checksum
      write_gatt_char(UUID_COMMAND, packet)

Receiving, on the telemetry characteristic:

.. code-block:: text

    _process_notification(client, handle, data)
      Packet.parse()            checks the ff09 header and the checksum
      PacketPattern.parse()     family, composer, channel
      PacketCommand.parse()     fragmented (0x80), encrypted (0x40), msgtype
      |
      |-- fragmented?           _reassemble(): FragmentedPayload, buffered by pattern + cmd,
      |                         the joined payload once every fragment is in
      |-- channel 0x01          _process_negotiation() -> session.on_reply()
      |                         (decrypts if 0x40 is set; see `Negotiation flow`_)
      |-- not 0x0f / 0x11       logged, dropped
      |-- encrypted?            _decrypt_payload() -> session.decrypt(), once
      |-- future for            future.set_result(payload)   (_listen_for_packet())
      |   pattern + cmd?
      '-- otherwise             _process_session(cmd, payload, encrypted=...)
                                  msgtype 0x300 or in _TELEMETRY_COMMANDS:
                                    Parameters.parse()
                                    encrypted -> session.on_session_push()
                                    _process_telemetry() -> state callbacks
                                  any other msgtype: logged

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

.. code-block:: text

    connect()
      |-- establish_connection(); start_notify(UUID_TELEMETRY, _process_notification)
      |-- _negotiate()        until negotiated, the link drops, an UnsupportedNegotiation,
      |     |                 or NEGOTIATION_TIMEOUT
      |     '-- _initiate_negotiations()      again if the device sends nothing for
      |           |                           NEGOTIATION_RESPONSE_TIMEOUT seconds
      |           |-- _session = NegotiatedSession(_outer_class(), self)
      |           '-- _session.open()         sends x001
      |
      |   each reply: _process_notification() -> _process_negotiation()
      |                 -> NegotiatedSession.on_reply() -> on_plaintext()
      |                      x801, x803    handled by the session
      |                      later         path.on_stage() (EcdhPath)
      |
      |-- negotiated:     _on_authorized()    _outer_class = type(outer); _post_authorize()
      |                   _post_connect(); the reconnect and keep-alive tasks start
      '-- not negotiated: _reopen_if_refused()
                            link dropped, no reply, outer was PlainOuter
                              -> _outer_class = EncryptedOuter; connect() once more
                            otherwise -> False

Each reply and what it sends next:

.. code-block:: text

    reply   handled in                                     sends
    -----   --------------------------------------------   ---------------------------
    -       NegotiatedSession.open()                       x001  time (+ client id)
    x801    NegotiatedSession.on_plaintext()               x003  client MTU
    x803    _record_capability(): MTU, capability, auth    x029
            path = _choose_path() -> EcdhPath
    x829    EcdhPath.on_stage(): _record_identity()        x005  method (ECDH), MTU
            serial, MAC                                          (outer.x005_tags())
    x805    link._generate_private_key()                   x021  client public key
    x821    keys = Keys.parse(ecdh_shared_secret(...))     x022  time, time zone
            plain outer: authorized
    x822    encrypted outer, not yet authorized            x027  client token
    x827    _register(): status 00 authorized; 09 sets
            confirmation_window, and the device pushes x827
            on pattern 030101 once its button is pressed

- ``x`` is the flag nibble: ``0`` on the plain outer until keys are installed and ``4`` after (``0021``, then ``4022``), always ``4`` on the encrypted outer. Replies set ``0x800`` (``0801`` / ``4801``).
- Before keys, the plain outer sends in clear and the encrypted outer under the static GCM key. Once ``x821`` installs the keys, the session cipher is CBC (plain) or GCM (encrypted).
- The plain outer authorizes at ``0821``. The encrypted outer authorizes at ``4827`` status ``00``, the ``030101`` grant, or the first session push the client can decrypt (``on_session_push()``).
- ``(+ client id)``: the plain outer inserts the client id as ``a2`` in ``0001``, ``0003``, ``0029``, ``0005`` and ``4022``; the encrypted outer sends none.
