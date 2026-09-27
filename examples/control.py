"""Example usage of SolixBLE for controlling a C1000.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging

from SolixBLE import C1000, AnkerBLEDevice, discover_devices
from SolixBLE.states import LightStatus

logging.basicConfig(level=logging.DEBUG)


async def test_ac_output(device: AnkerBLEDevice):

    await asyncio.sleep(10)
    await device.turn_ac_on()

    await asyncio.sleep(10)
    await device.turn_ac_off()


async def test_light_mode(device: AnkerBLEDevice):

    await asyncio.sleep(5)
    await device.set_light_mode(LightStatus.LOW)

    await asyncio.sleep(5)
    await device.set_light_mode(LightStatus.MEDIUM)

    await asyncio.sleep(5)
    await device.set_light_mode(LightStatus.HIGH)

    await asyncio.sleep(5)
    await device.set_light_mode(LightStatus.SOS)

    await asyncio.sleep(5)
    await device.set_light_mode(LightStatus.OFF)


async def main():

    # Find device
    devices = await discover_devices()

    selected_device = None
    for device in devices:
        if device.name is not None and "C1000" in device.name:
            selected_device = device
            break

    if selected_device is None:
        print("Device not found!")
        return

    # Initialize the device
    # device = C300(selected_device)
    device = C1000(selected_device)

    # Connect
    connected = await device.connect()

    if not connected:
        raise Exception

    await test_light_mode(device)

    await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
