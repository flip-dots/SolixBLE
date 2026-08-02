New devices
===========

Introduction
----------------

Each device encodes different information, often in different orders in the telemetry data, this
requires the work of people with the hardware and time to spend the time mapping out what
values correspond to what.


Decoding
----------------

To start decoding telemetry you can run the :doc:`examples <examples>` program with debug logging enabled.
Select the device model as unknown/generic. This results in the telemetry data being printed to
the console with section printed in multiple formats, as well as an additional diff value being
printed between updates which will list what values changed since the previous update.

While the program is running you should look at the values on your devices screen and write down
any correlations you see, for example if you plug in a USB device to port C1 and it starts drawing
5w, you should look in the logs for a value that goes from 0 to 5, and then goes from 5 to 0 when
you unplug the device. 

.. note::
    Be aware that some values are influenced by others, for example if you plug in a device which
    draws 100w, you may see multiple values go from 0 to 100, this is because some values are 
    aggregates of others (e.g USB power out and Total power out, AC power out and Total power out, etc).
    You can determine which is which by plugging in multiple things to cause the aggregate value to change.

You should take note of any observed correlations and either submit a PR adding support, or make a 
GitHub issue with a table documenting the values for your model. If you wish to submit a PR it is
important to add tests to ensure that any future changes do not break compatibility. You should
aim to flip every state at least once (e.g AC charging, AC discharging, DC charging, USB discharging, etc).


.. _new_device_control:

Control
-------

If you wish to add support for controlling a function of a device, you must first figure out what
command the Anker app sends to perform that operation. See the :doc:`app decoding <app_decoding>`
section for more information on how to capture these commands and the :doc:`C300 <c300>`, 
:doc:`800 <c800>`, and :doc:`C1000 <c1000>` source code for examples of how to implement the 
control functions.

.. note::
    Some Anker devices accept more than one BLE handshake protocol, and a new device 
    class may be needed per protocol. The :doc:`Solarbank 2 <solarbank2>` is an example: 
    its firmware accepts both the legacy base-Solix handshake and an 
    Anker-Prime-style handshake (8-stage), 
    exposed as ``Solarbank2`` and ``Solarbank2Prime`` respectively.


Example telemetry data
----------------------

These are example snippets of the telemetry debug log of a C300X. "c5" contains the serial number
and "a6" is the AC power out, going from 87w to 93w, and "ae" is the total power out, going from
91w to 97w.

.. code-block:: json
   :linenos:
   :caption: Example telemetry log

   DEBUG:SolixBLE.device:Parsed telemetry packet: 
    {
        "a1": {
            "bytes": "b'1'",
            "hex": "31",
            "int": "0",
            "uint": "0"
        },
        "a2": {
            "bytes": "b'\\x03\\x00\\x00\\x00\\x00'",
            "hex": "0300000000",
            "int": "0",
            "uint": "0"
        },
        "a3": {
            "bytes": "b'\\x03\\x00\\x00\\x00\\x00'",
            "hex": "0300000000",
            "int": "0",
            "uint": "0"
        },
        ...
        "c5": {
            "bytes": "b'\\x00AZVSBJ0E39200048'",
            "hex": "00415a5653424a30453339323030303438",
            "int": "74707744574127872767229667665704802881",
            "uint": "74707744574127872767229667665704802881"
        },
        ...
        "d1": {
            "bytes": "b'\\x01\\x00'",
            "hex": "0100",
            "int": "0",
            "uint": "0"
        }
    }


.. code-block:: json
   :linenos:
   :caption: Example telemetry difference log

   DEBUG:SolixBLE.device:Data changes: 
    {
        "a6": {
            "bytes": "b'\\x02W\\x00' -> b'\\x02]\\x00'",
            "hex": "025700 -> 025d00",
            "int": "87 -> 93",
            "uint": "87 -> 93"
        },
        "ae": {
            "bytes": "b'\\x02[\\x00' -> b'\\x02a\\x00'",
            "hex": "025b00 -> 026100",
            "int": "91 -> 97",
            "uint": "91 -> 97"
        }
    }
