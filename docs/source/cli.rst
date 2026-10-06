Console
=======

``solixble`` is an interactive console for finding, connecting to and driving
devices by hand, and for seeing every frame each way in clear text. It uses
the library's own classes and commands, so what works here works in code.

.. code-block:: bash

    pip install "SolixBLE[cli]"
    solixble                     # or: python -m SolixBLE

.. code-block:: text

    solixble> scan 10
    #  address            name        mac           type  sku  cap  class             rssi
    0  AA:BB:CC:DD:EE:01  A2345_B345  aa12deadb345  b402  QJB  04   PrimeCharger250w  -58
    solixble> connect 0
    [0] connected
    class       PrimeCharger250w
    ...
    solixble> frames 5

Commands
--------

.. list-table::
   :header-rows: 1

   * - Command
     - Does
   * - ``scan [secs] [raw]``
     - Lists advertising Anker devices: address, name, the MAC, product type,
       sku and capability from the advertisement, and the class the factory
       picks for it. ``raw`` adds each device's advertisement as bytes: the
       Anker ``0xffff`` record (marked when it doesn't parse), other
       manufacturer data, service data and the advertised services.
   * - ``connect <n|mac|address> [class]``
     - Connects a scanned device, as the class named or the factory's choice.
   * - ``devices``, ``use <n>``, ``disconnect [n]``
     - The open links and which one the other commands act on.
   * - ``info``
     - The class, link state, outer protocol, path and what the device
       announced while negotiating.
   * - ``data [verbose]``, ``props``, ``constants``
     - Decoded telemetry tags, public properties, and the device modules'
       ``CMD_*`` / ``PARAMETERS_*``.
   * - ``call <method> [args]``
     - Calls a public method; enum arguments by member name, e.g.
       ``call set_display_timeout ['S30']``.
   * - ``send <cmd> <params> [kwargs]``
     - ``_send_command``: a session command with the timestamp trailer.
   * - ``packet <pattern> <cmd> <params> [kwargs]``
     - ``_send_packet`` on any pattern, as typed.
   * - ``nego <cmd> <params> [kwargs]``
     - A frame on the negotiation pattern ``030001`` under the live session.
   * - ``frames [n]``
     - The last frames, both directions, with their status and tags.
   * - ``capture <file>`` / ``capture off``
     - Appends every frame to a file, one dated line each with the raw bytes.
   * - ``token [id]``, ``region [cc]``
     - The client token sent in ``4027`` and as the Prime ``420a`` owner; the
       region (:py:func:`SolixBLE.set_region`).
   * - ``console``
     - A Python prompt on the console's event loop, with ``console``,
       ``devices``, ``device`` and ``frames`` in scope and ``await`` at the top
       level; ``exit()`` returns.

``<params>`` is a parameter dict as a device module writes it, as JSON or a
Python literal (``{'a1': {'value': '21'}, 'a2': {'type': 1, 'value': 1}}``), or
the name of a ``PARAMETERS_*`` constant. A value of ``'@ts'`` is the live
timestamp. ``[kwargs]`` feeds lambda values, e.g. ``{'seconds': 300}``.
After a send the console shows the frames of the next two seconds
(``--reply-wait``).

Options
-------

.. list-table::
   :header-rows: 1

   * - Option
     - Does
   * - ``--capture FILE``
     - Start capturing to ``FILE`` (appended, never truncated).
   * - ``--token ID``
     - The client token; the class's UUID otherwise.
   * - ``--region CC``
     - The region for Prime devices.
   * - ``--allow-factory-channel``
     - Let ``packet`` send on channel ``0c``, the factory lane.
   * - ``--reply-wait SECS``
     - How long to collect frames after a send (default 2).
   * - ``--log-level LEVEL``
     - The library's log level (default ``warning``).

.. warning::

   ``send``, ``packet`` and ``nego`` send exactly what is typed. Some
   commands change settings or reset a device: on the Prime Charger 250W,
   ``4201`` is a factory reset. The factory lane (channel ``0c``) is refused
   unless the console is started with ``--allow-factory-channel``.

.. note::
   :collapsible: closed

   On a Prime device, ``420a`` stores the owner, and a different owner makes
   the device reset its custom settings. To keep a device paired with the
   Anker app as it is, start with ``--token`` set to that account's owner id.
