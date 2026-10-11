=========
Protocols
=========


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
