"""Example usage of SolixBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
import SolixBLE


logging.basicConfig(level=logging.DEBUG)


async def main():

    # Find device
    devices = await SolixBLE.discover_devices()

    selected_device = None
    for device in devices:
        if device.name is not None and "C300" in device.name:
            selected_device = device
            break

    if selected_device is None:
        print("Device not found!")
        return

    # Initialize the device
    device = SolixBLE.C300(selected_device)
    # device = SolixBLE.C1000(selected_device)

    # Connect
    connected = await device.connect()

    if not connected:
        raise Exception

    # Do nothing, the library will print status updates in debug mode
    await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
