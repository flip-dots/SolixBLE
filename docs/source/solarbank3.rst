Solarbank 3
===========

The Solarbank 3 E2700 Pro (A17C5) implementation has been tested with
firmware 1.0.7.1.  It requires the 40-character hexadecimal Anker account ID
used by the device during local authentication::

    device = Solarbank3(ble_device, anker_user_id="...")

The device supports the following local controls:

* ``set_schedule(power_w)`` writes the seven-day ``405e`` schedule in 50 W
  steps from 0 to 1200 W.
* ``set_max_load(max_load_w)`` writes the ``4080`` limit for 350, 600, 800 or
  1200 W.

These controls change the Solarbank itself over BLE.  They do not update the
cloud-side plan metadata shown by the Anker app.

.. autoclass:: SolixBLE.Solarbank3
   :members: 
   :inherited-members: connect, disconnect, add_callback, remove_callback, connected, available, address, name, supports_telemetry, last_update
   :special-members: __init__
   :member-order: groupwise
   :no-index:
