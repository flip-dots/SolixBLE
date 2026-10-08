Solarbank 2
===========

.. autoclass:: SolixBLE.Solarbank2Common
   :members:
   :inherited-members: connect, disconnect, add_callback, remove_callback, connected, available, address, name, supports_telemetry, last_update
   :special-members: __init__
   :member-order: groupwise
   :no-index:


.. autoclass:: SolixBLE.Solarbank2
   :members:
   :special-members: __init__
   :member-order: groupwise
   :no-index:


.. autoclass:: SolixBLE.Solarbank2Prime
   :members:
   :special-members: __init__
   :member-order: groupwise
   :no-index:


Error codes
-----------

:attr:`Solarbank2Common.error` maps the raw :attr:`Solarbank2Common.error_code`
onto Anker's published error list. Parts of this mapping are inferred, see the
note below.

.. autoclass:: SolixBLE.devices.solarbank2.ErrorCodeSB2
   :members:
   :undoc-members:
   :member-order: bysource
   :no-index:
