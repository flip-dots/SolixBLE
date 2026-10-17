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
                         |-- path           the first of PATHS = (EcdhPath, LegacyAesPath)
                         |                  whose matches() accepts x803
                         |                  on_stage(), keys, authorized, encrypt_override()
                         |-- announcement   what the device declared
                         '-- link           the device: _send_packet(), _timestamp(),
                                            _generate_private_key(), ...

    NegotiatedSession.encrypt()  path.encrypt_override(), else outer.encrypt() under path.keys
    NegotiatedSession.decrypt()  outer.decrypt() under path.keys

- The outer is how the negotiation travels and which cipher the session uses (see `Outer protocols`_).
- The path is the key exchange and authorization after the shared opening (see `Paths`_).
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
      _encrypt_payload()        -> session.encrypt(): path.encrypt_override(), else
                                   outer.encrypt(payload, path.keys)
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
      |-- status byte only, on  dropped: a bare status carries no data
      |   a telemetry/snapshot
      |   msgtype?
      |-- future for            future.set_result(payload)   (_listen_for_packet())
      |   channel + msgtype?    _future_key(): the composer and flags don't matter
      '-- otherwise             _process_session(cmd, payload, encrypted=...)
                                  msgtype in _ALWAYS_TELEMETRY_MSGTYPES (0x300; none on the Primes) or in _TELEMETRY_COMMANDS:
                                    Parameters.parse()
                                    encrypted -> session.on_session_push()
                                    _process_telemetry() -> state callbacks
                                  msgtype in _SNAPSHOT_COMMANDS:
                                    _process_snapshot() -> state callbacks
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

Both outers run the same opening (``x001``, ``x003`` for the device's capabilities, ``x029`` for its serial and MAC), then the key exchange of the path the capability reply selects (see `Paths`_). The legacy AES path authorizes at ``4822`` on either outer.

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


Paths
-----

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


Negotiation flow
^^^^^^^^^^^^^^^^

What :py:meth:`connect() <SolixBLE.SolixBLEDevice.connect>` runs:

.. code-block:: text

    connect()
      |-- establish_connection(); start_notify(UUID_TELEMETRY, _process_notification)
      |-- _negotiate()        until negotiated, the link drops, an UnsupportedNegotiation,
      |     |                 NEGOTIATION_TIMEOUT, or pairing_required (x827 status 09)
      |     '-- _initiate_negotiations()      again if the device sends nothing for
      |           |                           NEGOTIATION_RESPONSE_TIMEOUT seconds,
      |           |                           never while pairing_required
      |           |-- _session = NegotiatedSession(_outer_class(), self)
      |           '-- _session.open()         sends x001
      |
      |-- pairing_required: _wait_for_pairing_confirmation()
      |     runs the pairing callbacks once, then waits confirmation_window +
      |     PAIRING_CONFIRMATION_GRACE for the 030101 grant, without resending
      |
      |   each reply: _process_notification() -> _process_negotiation()
      |                 -> NegotiatedSession.on_reply() -> on_plaintext()
      |                      x801, x803    handled by the session
      |                      later         path.on_stage() (EcdhPath or LegacyAesPath)
      |
      |-- negotiated:     _on_authorized()    _outer_class = type(outer); _post_authorize()
      |                   _post_connect(); the reconnect and keep-alive tasks start
      '-- not negotiated: _reopen_if_refused()
                            link dropped, no reply, outer was PlainOuter
                              -> _outer_class = EncryptedOuter; connect() once more
                            otherwise -> False

The shared opening, then each path's replies and what each sends next:

.. code-block:: text

    reply   handled in                                     sends
    -----   --------------------------------------------   ---------------------------
    -       NegotiatedSession.open()                       x001  time (+ client id)
    x801    NegotiatedSession.on_plaintext()               x003  client MTU
    x803    _record_capability(): MTU, capability, auth    x029
            path = _choose_path(): the first of PATHS
            whose matches() accepts x803, else
            UnsupportedNegotiation

    EcdhPath.on_stage()
    x829    record_identity(): serial, MAC                 x005  method ECDH, MTU
                                                                 (outer.x005_tags())
    x805    status 00, else UnsupportedNegotiation;        x021  client public key
            link._generate_private_key()
    x821    _exchange_keys(): keys = Keys.parse(           x022  time, time zone
            ecdh_shared_secret(...));                            (send_clock())
            plain outer: authorized
    x822    encrypted outer, not yet authorized            x027  client token
    x827    _register(): status 00 authorized; 09 sets
            confirmation_window, and the device pushes x827
            on pattern 030101 once its button is pressed

    LegacyAesPath.on_stage()
    x829    record_identity(): serial, MAC                 x005  method AES (a5 02), MTU
    x805    status 00, else UnsupportedNegotiation;        x022  time, time zone
            keys = _bootstrap_keys()                             (send_clock()), CBC-sealed
                                                                 by encrypt_override()
    x822    status 00 with a1, else                        x023  serial
            UnsupportedNegotiation; keys = a1[:16] +
            _ongoing_iv(); authorized
    x823    bind status logged

- ``x`` is the flag nibble: ``0`` on the plain outer until a path installs keys and ``4`` after (``0021``, then ``4022``), always ``4`` on the encrypted outer. Replies set ``0x800`` (``0801`` / ``4801``).
- Before keys, the plain outer sends in clear and the encrypted outer under the static GCM key. Once the path installs keys, the session cipher is the outer's: CBC (plain) or GCM (encrypted). The legacy path's bootstrap request is the one exception: ``encrypt_override()`` seals it in CBC on either outer until ``4822`` authorizes the path.
- ECDH authorizes at ``0821`` on the plain outer; on the encrypted outer at ``4827`` status ``00``, the ``030101`` grant, or the first session push the client can decrypt (``on_session_push()``). Legacy AES authorizes at ``4822`` on either outer.
- ``(+ client id)``: the plain outer inserts the client id as ``a2`` in ``0001``, ``0003``, ``0029``, ``0005``, ``4022`` and the legacy ``4023``; the encrypted outer sends none.

.. note::
   :collapsible: closed

   The Prime Charging Station 240W (A91B2) advertises capability ``00``, and the library follows it: the device opens on the plain outer, where ECDH runs in clear and authorizes at ``0821``. Its capability reply is ``a1 02 · a2 fd00 · a3 44 · a4 01 · a5 00``: it offers both ECDH and AES, and its auth method ``a5`` is ``00``.

   The device also answers the encrypted outer, although its capability byte lacks ``0x04``, and there only legacy AES authorizes it: stating AES in ``4005`` (``a5 02``), the ``4022`` key request CBC-sealed under the static key returns the session key in ``4822``, and the session then runs GCM under that key with the static nonce, with no ``4027``. ECDH on the encrypted outer completes the key exchange, but auth method ``00`` answers ``4027`` with ``4827 00`` and then drops the link. Neither encrypted-outer combination is how the library connects this device.


.. _pairing-with-a-button-press:

Pairing with a button press
----------------------------

Firmware that pairs clients checks the client token carried in the ECDH
path's registration (``x027``). The first time it sees a token it answers
``x827`` with status ``09`` and a confirmation window in seconds, and waits
for its button to be pressed. Once pressed, it pushes an unsolicited
``4827`` status ``00`` on pattern ``030101``, which authorizes the client
the same way a direct ``00`` reply would - :py:meth:`connect()
<SolixBLE.SolixBLEDevice.connect>` routes both through
:py:meth:`EcdhPath._register() <SolixBLE.protocols.EcdhPath>`. The device
then remembers the token, so a later connection with the same one is
authorized at once. Firmware that doesn't pair clients answers ``00``
straight away, and no account or cloud service is involved either way.

Pass a stable ``client_token`` so the device recognises the client across
runs, and register a callback to prompt the user when a press is needed:

.. code-block:: python

    device = PrimeCharger250w(ble_device, client_token=my_saved_token)
    device.add_pairing_callback(lambda: print("Press the button on the device"))
    await device.connect()

The callback runs once, when the device first asks.
:py:attr:`pairing_required <SolixBLE.SolixBLEDevice.pairing_required>` is
True for as long as it is waiting. :py:meth:`connect()
<SolixBLE.SolixBLEDevice.connect>` then waits for the press for the window
the device announced
(:py:attr:`announcement.confirmation_window <SolixBLE.SolixBLEDevice.announcement>`)
plus :py:data:`PAIRING_CONFIRMATION_GRACE <SolixBLE.const.PAIRING_CONFIRMATION_GRACE>`,
without resending the opening request meanwhile - resending it would start a
fresh key exchange and void the confirmation already in progress. A connect
that runs out of that window, or loses the link while waiting, returns
False. Without a token the class identifier is used, which every client of
that class shares, so the button only needs pressing once per class per
firmware's memory of it.

.. note::
   :collapsible: closed

   The firmware enrolls whatever bytes the token happens to be; a 16-byte
   random value, a serial, and a longer cloud account id all take the same
   path. On firmware that binds a device to an Anker account, sending that
   account id as the token reproduces the same registration the app itself
   sends, and the device answers ``00`` at once without a press - but
   obtaining the account id needs the Anker cloud, which is why it isn't the
   default here.
