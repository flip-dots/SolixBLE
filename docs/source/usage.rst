=====
Usage
=====

.. _bleak: https://bleak.readthedocs.io/en/latest/usage.html/
.. _BLEDevice: https://bleak.readthedocs.io/en/latest/api/index.html#bleak.backends.device.BLEDevice/


It is recommended you read through the :doc:`examples <examples>` first to obtain an
understanding of the intended usage before diving into the documentation.

Concept
-------

This module connects to a device, negotiates a session with it,
and then periodically receives state updates from it and caches the state
of the device. The cached information can be accessed using the properties
of the class. In addition you can register callbacks to be run when the
state of the device changes.

.. note::
    State updates are only sent when something changes, they can vary from every second
    if something is drawing a varying amount of power, to every 15s if the device is 
    relatively idle. Some devices support requesting a status update manually.


Tasks
-----

Finding a device
^^^^^^^^^^^^^^^^

Anker power stations can be automatically detected by the 
:py:meth:`discover_devices() <SolixBLE.discover_devices>`
method which looks for one of
:py:attr:`UUID_IDENTIFIERS <SolixBLE.const.UUID_IDENTIFIERS>`
among the advertised service UUIDs. This method returns a list of
`BLEDevice`_, each of which have been detected as Solix power stations.

``devices = await SolixBLE.discover_devices()``


.. note::

    This mechanism may not be reliable as it has only been tested with a
    ``C300X`` and ``C1000X``, albeit with a variety of firmware. If automatic 
    detection does not work, you can alternatively obtain a `BLEDevice`_ object
    via the `Bleak`_ library.


Initializing a device
^^^^^^^^^^^^^^^^^^^^^

In order to control/monitor a devive you must initialize a
:py:class:`.SolixBLE.SolixBLEDevice` object of the correct type for that device.

``device = C1000(ble_device)``

.. note::

    This code creates a :py:class:`.SolixBLE.C1000` object but does *not*
    automatically connect to the device.


Connecting to a device
^^^^^^^^^^^^^^^^^^^^^^

The module will *not* automatically connect to device when a 
device object is initialized, you must call :py:meth:`.connect`
in order to establish a connection.

On a successful *connection* (not instantiation) the program will
negotiate and subscribe to future updates of the devices state
which may be accessed by the properties of the device object.

.. note::

    On connection the properties of the device object will be at the
    default values until a telemetry message is received, this can take
    some time (~15s) if the device is idle. 


Automatic Reconnection 
^^^^^^^^^^^^^^^^^^^^^^

This module will attempt to automatically reconnect to a device
if the connection is lost. If the module is able to reconnect within the
disconnect timeout period no callbacks will be triggered, the cached data 
remains until it is replaced and it will be as if nothing happened. The exception
to this is that any commands waiting for a response will timeout. If the module
is not able to automatically reconnect within the time limit the callbacks will
be triggered and the cached device data (e.g power out, light status, etc) will
be cleared, if the module is then able to automatically reconnect, the callbacks
will be triggered again. If you wish to implement your own retry logic it may
interfere with the automatic reconnection, in this case it is recommended
to disable automatic reconnection by setting the maximum reconnect attempts
value to 0.

.. note::

    If a power station is disconnected for an extended period of time it
    will turn off the Bluetooth connection, requiring a press of the 
    power or pairing button for it to be possible to connect again.
