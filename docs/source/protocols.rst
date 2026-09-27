=========
Protocols
=========

.. _BLEDevice: https://bleak.readthedocs.io/en/latest/api/index.html#bleak.backends.device.BLEDevice/

Anker devices share one packet format but negotiate a session in more than one
way. Which path a device takes is a property of its firmware, and the device
says so before you connect: the ``0xffff`` manufacturer record in its
advertisement ends in a capability byte whose ``0x04`` bit means the device
accepts the encrypted negotiation.

=========================== ============================ ===========================
Path                        Negotiation                  Session
=========================== ============================ ===========================
Plain text                  ``0xxx`` commands, in clear  AES-CBC under the ECDH key
Encrypted                   ``4xxx`` commands, AES-GCM   AES-GCM under the ECDH key
                            under a static key
Solarbank                   plain-text negotiation       see the Solarbank pages
=========================== ============================ ===========================

Both paths perform the same ECDH exchange (P-256) and derive the session key
from the shared secret; a fresh key pair is generated for every negotiation.


Choosing the path
-----------------

Read the capability byte from the advertisement and pass it to the device when
you construct it; the correct path is then chosen automatically::

    from SolixBLE import C1000G2, capability_from_advertisement

    capability = capability_from_advertisement(advertising_data)
    device = C1000G2(ble_device, capability=capability)

.. note::

    A `BLEDevice`_ cannot carry the capability itself, so it is passed to the
    constructor rather than attached to the device. When it is not supplied
    the class default is used: the Prime devices default to the encrypted
    path, the Solix power stations to plain text. The ``advertising_data``
    comes from your own Bleak scan (for example a Home Assistant Bluetooth
    callback).


Plain text negotiation
----------------------

The client opens with ``0001`` and the device answers each stage with the
same command number plus ``0x0800``: ``0001 → 0801``, ``0003 → 0803``,
``0029 → 0829``, ``0005 → 0805``, ``0021 → 0821``. The ``0021``/``0821``
exchange carries the ECDH public keys; from the ``4022`` timezone confer on,
payloads are AES-CBC encrypted with the first 16 bytes of the shared secret as
the key and the next 16 as the IV.


Encrypted negotiation
---------------------

The same stages run under AES-GCM from the first frame, keyed by a static
negotiation key and nonce until the ``4021``/``4821`` exchange derives the
shared secret; after that the first 16 bytes are the key and the next 12 the
nonce, and the same cipher protects the session. Two stages carry extra
information:

* ``4803`` reports the device's MTU and its authentication mode; the client
  echoes both back in ``4005`` together with the cipher selection (``0x44`` =
  ECDH).
* ``4022`` carries the client's timezone as a POSIX string and its UTC offset
  in seconds west of UTC, which newer firmware validates.

The device then expects a client registration (``4027``) and answers with a
status (``4827``); ``00`` means the link is authorized and telemetry can be
requested.


Solarbank
---------

The Solarbank family negotiates in plain text but differs in its session
commands and telemetry layout; see :doc:`solarbank2` and :doc:`solarbank3`.
