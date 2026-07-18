Finding your owner_user_id
==========================

Some Anker Prime devices ship (or update to) a hardened firmware that will **not**
stream telemetry over BLE until the client proves it belongs to the account that owns
the device. On those units, the registration step must carry your Anker account's
``owner_user_id``; without it the device accepts the connection, acknowledges the
registration, and then stays silent until the link idle-drops. This section explains
what that value is and how to obtain it **without** the Anker app running, so it can be
passed to ``PrimeDevice`` (see `Using it`_).


Background
----------

The Prime negotiation completes with an ECDH handshake, after which the client sends a
registration command (``4027``) and a subscribe (``4200``). On older firmware the
registration is cosmetic and any value is accepted. On hardened firmware the device
inspects the registration and only arms telemetry when it binds the **owning account**:

.. code-block::

    4027 = a104<timestamp> a228<owner_user_id>     ->  ack 00 (accepted); telemetry streams
    4027 = a104<timestamp> a224<app-uuid>          ->  ack 09 (rejected); device stays silent

The ``owner_user_id`` is a 40-character hex string identifying your Anker account. It is
**static** and the **same for every device you own**, so you only need to fetch it once.

.. note::
    This is not a per-device secret and it is not read from the device -- it is your
    account identity. There is no on-device or cloud-free way to derive it; it must come
    from your Anker account (login), which is what the methods below do.


What you are looking for
------------------------

A value that looks like this (40 hex characters)::

    0123456789abcdef0123456789abcdef01234567

The same string appears in your account's cloud MQTT topics
(``dt/anker_power/<owner_user_id>/...``) and as ``user_id`` in the Anker login response,
which is why either can be used to recover it.


Method 1: anker-solix-api (recommended)
---------------------------------------

`anker-solix-api <https://github.com/thomluther/anker-solix-api>`__ is a Python client for
the Anker cloud. Logging in once returns your ``user_id``. This needs only your Anker
account credentials -- no phone, no rooted device.

Requirements:

- `anker-solix-api <https://pypi.org/project/anker-solix-api/>`__ (``pip install anker-solix-api``)
- Your Anker account email and password

.. code-block:: python

    import asyncio

    from aiohttp import ClientSession
    from api.api import AnkerSolixApi  # anker-solix-api


    async def main() -> None:
        async with ClientSession() as session:
            api = AnkerSolixApi("EMAIL", "PASSWORD", "US", session)
            await api.async_authenticate()
            print(api.apisession.get_login_info("user_id"))


    asyncio.run(main())

.. note::
    The exact accessor has moved across anker-solix-api versions. If
    ``get_login_info("user_id")`` is not available, use the version-independent fallback
    below: any successful login caches the full response (including ``user_id``) to disk.

anker-solix-api writes the login response to a JSON cache named after your email. After a
successful login you can read the value straight out of it:

.. code-block:: bash

    # the cache is a JSON file named after your account email; locate it, then read user_id
    find ~ . -name '*@*.json' 2>/dev/null
    python -c "import json,sys; print(json.load(open(sys.argv[1]))['user_id'])" <that-file>.json


Method 2: Anker app traffic
---------------------------

If you are already intercepting the Anker app (see :doc:`app_decoding`), the value is in
plain sight and no extra login is needed.

- **Android (Frida):** the packet/log dump prints the outgoing registration payload
  ``A104<ts>A228<owner_user_id ascii>`` and the MQTT topics the app subscribes to
  (``dt/anker_power/<owner_user_id>/...``). The 40 hex characters after ``A228`` (decoded
  from ASCII) are the value.
- **iOS backup:** the app's ``app_log.log`` (inside an unencrypted device backup) records
  the login response and the same MQTT topics. Grep for the topic prefix:

  .. code-block:: bash

      grep -oE 'anker_power/[0-9a-f]{40}' app_log.log | head -1

.. note::
    In the raw app frames the id is sent as its **ASCII characters** (each hex digit is a
    byte), i.e. tag ``a2`` length ``0x28`` (40) followed by the 40-byte string. When you
    read it from a login response or MQTT topic it is already the plain 40-char string.


Using it
--------

Set the value on the module before connecting; ``PrimeDevice`` reads it when it builds the
registration. When it is ``None`` (the default) the legacy registration is used, which is
fine for older firmware but will not stream on a hardened unit.

.. code-block:: python

    import SolixBLE.prime_device

    SolixBLE.prime_device.OWNER_USER_ID = "0123456789abcdef0123456789abcdef01234567"
    # ... now connect() your PrimeDevice as usual

.. note::
    ``OWNER_USER_ID`` is a module-level default shared by every ``PrimeDevice`` in the
    process. That is intentional for the common single-account case; if you drive devices
    from more than one Anker account in one process, set it per connection instead.
