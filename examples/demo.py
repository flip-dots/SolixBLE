"""More advanced usage example of SolixBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
import sys

# Allows for reading and writing to the console at the same time
# pip3 install aioconsole
from aioconsole import ainput
from bleak import BLEDevice

from SolixBLE import (
    C300,
    C300DC,
    C800,
    C1000,
    C1000G2,
    F2000,
    F3800,
    Generic,
    MagGo3in1,
    PrimeCharger160w,
    PrimeCharger250w,
    PrimePowerBank20k,
    Solarbank2,
    Solarbank3,
    SolixBLEDevice,
    discover_devices,
)

MODELS = {
    "C300": C300,
    "C300DC": C300DC,
    "C800": C800,
    "C1000": C1000,
    "C1000 G2": C1000G2,
    "F2000 (767 PowerHouse)": F2000,
    "F3800": F3800,
    "Solarbank 2": Solarbank2,
    "Solarbank 3": Solarbank3,
    "PrimeCharger160w": PrimeCharger160w,
    "PrimeCharger250w": PrimeCharger250w,
    "Prime Power Bank 20k/220w": PrimePowerBank20k,
    "MagGo 3-in-1 Wireless Charger": MagGo3in1,
    "Unknown": Generic,
}


async def prompt_debug_mode():
    """
    Prompt the user to enable/disable debug logging.
    """
    while True:

        print("Show debug info? [Y/N]")
        response = input().lower()

        if response == "y":
            logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
            break

        elif response == "n":
            break


async def prompt_select_device(devices: list[BLEDevice]) -> SolixBLEDevice:
    """
    Prompt the user to select the device and model they want to connect to.

    :param devices: List of discovered power stations.
    :returns: Selected power station with initialized class.
    """

    # Get Bluetooth device
    print("Which device would you like to connect to?")
    for i in range(1, len(devices) + 1):
        device = devices[i - 1]
        print(f"""{i}. "{device.name}"  ({device.address}) """)
    ble_device = devices[int(await ainput("> ")) - 1]

    # Get model/class of device
    print("What model is this device?")
    model_keys = list(MODELS.keys())
    model_values = list(MODELS.values())
    for i in range(1, len(MODELS) + 1):
        print(f"""{i}. "{model_keys[i - 1]}" """)
    device_class = model_values[int(await ainput("> ")) - 1]

    # Return instantiated device
    return device_class(ble_device)


async def main():
    """
    Main program loop.

    This prompts the user for logging mode.
    Looks for power stations.
    Asks user to select a power station.
    Asks user to select the model of the power station.
    Connects to the power station.
    Prints status updates of the power station.
    """

    # Ask user for desired logging mode
    await prompt_debug_mode()

    # Find power stations
    devices: list[BLEDevice] = []
    while not devices:

        print("Looking for power station...")
        devices = await discover_devices()
        if not devices:
            print("No devices found! Trying again...")

    # Ask user to select power station and model
    device = await prompt_select_device(devices)

    # Register callback
    def my_callback():
        """
        Callback executed by library whenever there is a telemetry update.
        """
        print("==== REMOTE STATE CHANGE DETECTED ====")
        print(device)
        print("==== END OF STATE CHANGE REPORT ====")

    device.add_callback(my_callback)

    # Connect to device
    await device.connect()

    # Prompt user for action
    while True:
        print("What action would you like to perform?")
        print("1. Print state")
        print("2. Exit")

        try:
            action = int(await ainput("> ")) - 1
            match action:

                # Print state of device
                case 0:
                    print(device)

                # Exit program
                case 1:
                    await device.disconnect()
                    print("Goodbye :)")
                    return

        except ValueError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
