Welcome to SolixBLE's documentation!
====================================

.. image:: https://img.shields.io/pypi/v/SolixBLE.svg
    :target: https://pypi.python.org/pypi/SolixBLE

.. image:: https://readthedocs.org/projects/solixble/badge/?version=latest
    :target: https://solixble.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status
      
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Black

Unofficial Python module for monitoring and controlling Anker Solix power stations
and other devices

 - 👌 Free software: MIT license
 - 🍝 Sauce: https://github.com/flip-dots/SolixBLE
 - 📦 PIP: https://pypi.org/project/SolixBLE/

This Python module enables you to monitor and control (some) Anker Solix devices
directly from your computer, without the need for any cloud services or Anker app.
It leverages the Bleak library to interact with Bluetooth Anker devices.
No pairing is required in order to receive telemetry data or control the device.


.. note::

   This project is under active development.


Power station support
---------------------

======================= ======== ========== ========= ========= ========= ============ ======
Parameter               C300(X)  C300(X) DC C800(X)   C1000(X)  C1000 G2  F2000 (767)  F3800  
======================= ======== ========== ========= ========= ========= ============ ====== 
Charging status         ✅        ✅          ❌        ❌        ❌         ❌           ✅ 
Time remaining          ✅        ✅          ✅        ✅        ❌         ✅           ✅  
Battery percentage      ✅        ✅          ✅        ✅        ✅         ✅           ✅ 
Battery health          ❌        ✅          ✅        ✅        ✅         ✅           ❌
Temperature             ✅        ✅          ✅        ✅        ✅         ✅           ✅
Total Power In          ✅        ✅          ✅        ✅        ❌         ❌           ✅     
Total Power Out         ✅        ✅          ✅        ✅        ✅         ❌           ✅ 
AC on/off control       ✅        N/A         ✅        ✅        ✅         ❌           ❌  
AC Power in             ✅        N/A         ✅        ✅        ✅         ✅           ✅     
AC Power out            ✅        N/A         ✅        ✅        ✅         ✅           ✅  
AC on/off state         ✅        N/A         ✅        ✅        ✅         ❌           ✅   
AC Timer                ✅        N/A         ✅        ✅        ❌         ❌           ❌  
DC on/off control       ✅        ❌          ✅        ✅        ✅         ❌           ❌
DC Power in             ✅        ✅          ✅        ✅        ✅         ✅           ✅   
DC Power out            ✅        ✅          ❌        ✅        ✅         ✅           ✅  
DC Power in status      ✅        ✅          ❌        ❌        ✅         ❌           ❌ 
DC Power out status     ✅        ❌          ❌        ✅        ✅         ❌           ✅   
DC Timer                ✅        ✅          ❌        ❌        ❌         ❌           ❌ 
USB Power out           ✅        ✅          ✅        ✅        ✅         ✅           ✅     
USB Port status         ✅        ✅          ❌        ❌        ✅         ❌           ✅ 
Light control           ✅        ❌          ✅        ✅        ❌         ❌           ❌  
Light status            ✅        ✅          ❌        ❌        N/A        ❌           ❌ 
Display on/off control  ✅        ❌          ✅        ✅        ❌         ❌           ❌ 
Display on/off status   ❌        ✅          ❌        ❌        ❌         ❌           ❌ 
Display brightness ctrl ✅        ❌          ✅        ✅        ❌         ❌           ❌ 
Display brightness stat ❌        ✅          ❌        ❌        ❌         ❌           ❌ 
Display timeout ctrl    ✅        ❌          ✅        ✅        ❌         ❌           ❌ 
Display timeout stat    ❌        ✅          ❌        ❌        ❌         ❌           ❌
Firmware version        ✅        ✅          ✅        ✅        ❌         ✅           ✅  
Serial number           ✅        ✅          ✅        ✅        ✅         ✅           ✅     
Expansion temperature   N/A       N/A         N/A      ✅        N/A       ✅           ❌  
Expansion percentage    N/A       N/A         N/A      ✅        N/A       ✅           ✅  
Expansion health        N/A       N/A         N/A      ✅        N/A       ✅           ❌    
Expansion firmware      N/A       N/A         N/A      ✅        N/A       ✅           ✅     
Expansion num           N/A       N/A         N/A      ✅        N/A       ✅           ❌ 
Polled status updates   ✅        ❌          ✅        ✅        ❌         ❌           ❌ 
======================= ======== ========== ========= ========= ========= ============ ======


Solar system support
--------------------

=================================  ============ ============ ============ 
Parameter                          Solarbank 1  Solarbank 2  Solarbank 3  
=================================  ============ ============ ============  
AC power out                        ❌            ✅           ❌
AC power out (sockets)              ❌            ✅           ❌
Total power out                     ✅            ✅           ✅
Total energy out                    ✅            ✅           ✅
Solar power in                      ✅            ✅           ✅
Solar energy in                     ✅            ✅           ✅
Individual solar power in           ❌            ✅           ✅
Battery power in                    ✅            ✅           ✅
Battery power out                   ❌            ✅           ✅
Battery energy in                   ✅            ✅           ✅
Battery energy out                  ✅            ❌           ✅
Battery charge power                ✅            ❌           ❌
Battery percentage                  ✅            ✅           ✅
Battery percentage aggregate        ❌            ✅           ✅
Expansion battery percentage        ❌            ❌           ❌
Charging status                     ✅            ❌           ❌
Battery health                      ❌            ❌           ✅
Expansion battery health            ❌            ❌           ❌
Schedule                            ✅            ❌           ❌
Control schedule                    ✅            ❌           ❌
Temperature                         ✅            ✅           ✅
Temperature unit                    ❌            ❌           ❌
Expansion battery temperature       ❌            ❌           ❌
Battery heating                     ❌            ❌           ❌
Batter heating power                ❌            ❌           ❌
Grid status                         ❌            ❌           ❌
Grid power in/out                   ❌            ❌           ✅
Grid to Home power                  ❌            ✅           ✅
PV to Grid power                    ❌            ✅           ❌
Grid import energy                  ❌            ✅           ✅
Grid export energy                  ❌            ✅           ✅
Grid export disable/enable          ❌            ❌           ❌
House demand                        ❌            ✅           ✅
House consumption                   ❌            ❌           ✅
Consumed energy                     ❌            ✅           ❌
Error codes                         ❌            ❌           ❌
Max load                            ❌            ❌           ❌
Usage mode                          ❌            ❌           ❌
Presets                             ❌            ❌           ❌
Light mode                          ❌            ❌           ❌
PV limitations                      ❌            ❌           ❌
AC limitations                      ✅            ❌           ❌
Software version                    ✅            ✅           ❌  
Software version controller         ✅            ✅           ❌
Software version expansion          ❌            ✅           ❌
Hardware version                    ✅            ❌           ❌
Serial number                       ✅            ✅           ✅                    
Expansion battery serial number     ❌            ❌           ❌
Inverter brand                      ✅            ❌           ❌
Inverter model                      ✅            ❌           ❌
=================================  ============ ============ ============ 


Prime charger support
---------------------

======================= ============= ============= ===================
Parameter               250w (A2345)  160w (A2687)  MagGo 3in1 (A25X7)
======================= ============= ============= ===================
Display status           ❌            ❌            ❌
Total power out          ❌            ❌            ✅
Port on/off control      ❌            ✅            ❌
Port protocol control    ❌            ❌            ❌
Timer control            ❌            ✅            ❌
Individual port status   ✅            ✅            ✅
Individual port voltage  ✅            ✅            ❌
Individual port current  ✅            ✅            ❌
Individual port power    ✅            ✅            ✅
Temperature              ❌            ❌            ❌
Firmware version         ❌            ❌            ❌
Serial number            ❌            ❌            ❌
======================= ============= ============= ===================


Prime power bank support
------------------------

======================= ================= 
Parameter               20k/220w (A110B)
======================= =================
Battery percentage       ✅
Display status           ❌
Total power out          ✅
Port on/off control      ❌
Port protocol control    ❌
Individual port status   ✅
Individual port voltage  ✅
Individual port current  ✅
Individual port power    ✅
Temperature              ✅
Firmware version         ❌
Serial number            ❌
======================= =================

Disclaimer
----------

SolixBLE is a software library designed to work with Anker Solix/Prime devices.
ANKER is a registered trademark of Anker Innovations Limited. 
This project is not affiliated with, endorsed by, or sponsored by Anker Innovations Limited (Though I wouldn't mind being sponsored 😉).
All other trademarks cited herein are the property of their respective owners.


Contents
--------

.. toctree::

   Home <self>
   examples
   usage
   api
   limitations
   new_devices
   app_decoding
   source
