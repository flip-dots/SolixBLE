Solarbank 1
===========

.. warning::
   **Known BLE Quirks & Limitations**
   
   When communicating with the Solarbank 1 via BLE, please be aware of the following known behaviors:

   * **State Reporting:** The charging schedule currently always reports its state as *discharging*, regardless of the actual physical state.
   * **Minimum Output:** When controlling the device via BLE, the minimum configurable output is hard-capped at **100W**.
   * **Secondary Schedule Control:** There is an additional schedule control that forces the system to discharge *only* via the battery, completely ignoring solar input. Strangely, when this mode is active, the protocol reports a ``max_soc`` value of **336**.

.. autoclass:: SolixBLE.Solarbank1
   :members: 
   :inherited-members: connect, disconnect, add_callback, remove_callback, connected, available, address, name, supports_telemetry, last_update
   :special-members: __init__
   :member-order: groupwise
   :no-index: