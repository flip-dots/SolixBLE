# SolixBLE

[![PyPI Status](https://img.shields.io/pypi/v/SolixBLE.svg)](https://pypi.python.org/pypi/SolixBLE)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Python module for monitoring and controlling Anker Solix power stations and other devices over Bluetooth.
 - 👌 Free software: MIT license
 - 🍝 Sauce: https://github.com/flip-dots/SolixBLE
 - 🖨️ Documentation: https://solixble.readthedocs.io/en/latest/
 - 📦 PIP: https://pypi.org/project/SolixBLE/


This Python module enables you to monitor and control (some) Anker Solix
devices directly from your computer, without the need for any cloud services or Anker app.
It leverages the Bleak library to interact with Bluetooth Anker Solix devices.
No pairing is required in order to receive telemetry data or control the device.


## Features

- 🔋 Battery percentage
- ⚡ Total Power In/Out
- 🎛️ AC/DC output control
- 🔌 AC Power In/Out
- 🚗 DC Power In/Out
- ⏰ AC/DC Timer value
- ⏲️ Time remaining to full/empty
- ☀️ Solar Power In
- 💻 USB Port Power
- 📱 USB Port Status
- ⚙️ Firmware version
- 🩺 Battery health
- 🌡️ Battery temperature
- ↔️ Expansion batteries (Charge, Temperature, Health, Firmware)
- 💡 Light bar status & control
- 🖥️ Display status & control
- 🔂 Simple structure
- ✔️ More emojis than strictly necessary


## Supported Devices

See the [support table](https://solixble.readthedocs.io/en/latest) in the documentation for feature support for particular devices.

- C300(X)
- C300(X) DC
- C800(X)
- C1000(X)
- C1000 Gen 2
- F2000 (767 PowerHouse)
- F3800
- Solarbank 1
- Solarbank 2
- Solarbank 3
- Prime Charger 160w
- Prime Charger 250w
- Prime MagGo 3in1 (A25X7)
- Potentially more!


## Requirements

- 🐍 Python 3.11+
- 📶 Bleak 0.19.0+
- 📶 bleak-retry-connector


## Supported Operating Systems

- 🐧 Linux (BlueZ)
  - Ubuntu Desktop
  - Arch (HomeAssistant OS)
- 🏢 Windows
  - Windows 10 
- 💾 Mac OSX
  - 15.7


## Installation


### PIP

```
pip install SolixBLE
```


## Adding support for new devices

See the `Generic` class inside `SolixBLE/devices/generic.py` and the 
[documentation](https://solixble.readthedocs.io/en/latest/new_devices.html)
for guidance on how to add support for new devices.


## Disclaimer

SolixBLE is a software library designed to work with Anker Solix/Prime devices. ANKER is a registered trademark of Anker Innovations Limited. This project is not affiliated with, endorsed by, or sponsored by Anker Innovations Limited (Though I wouldn't mind being sponsored 😉). All other trademarks cited herein are the property of their respective owners.