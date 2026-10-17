"""Base Anker Prime device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import logging

from SolixBLE.device import SolixBLEDevice
from SolixBLE.protocols import EncryptedOuter, Outer
from SolixBLE.utilities import region

_LOGGER = logging.getLogger(__name__)

#: The pattern used in telemetry packets from Anker Prime and Solix devices
TELEMETRY_PATTERN = "03000f"

#: The UUID sent to the device during negotiation
UUID_STRING = "79ebed35-dc9c-4904-b40c-72c4e863aa10"



class PrimeDevice(SolixBLEDevice):
    """
    This is a base class based upon SolixBLEDevice which contains logic
    unique to Anker Prime devices that is designed to be overridden for
    specific implementations, e.g 160w, 250w, etc.

    Anker Prime devices negotiate with the encrypted outer protocol unless
    the device's advertisement says otherwise.
    """

    _OUTER_HINT: type[Outer] = EncryptedOuter

    _UUID_STRING: str = UUID_STRING

    async def _post_authorize(self) -> None:
        """Start the session the way the app does once the client is authorized.

        ``4200`` asks for all device information; ``420a`` sets the region
        and the owner, which the device stores. The device treats a different
        owner as a new one, so the owner sent is this client's token.
        """
        await self._send_command("4200", {
            "a1": {
                "key": bytes.fromhex("a1"),
                "type": None,
                "value": bytes.fromhex("21"),
            },
        })
        await self._send_command("420a", {
            "a1": {
                "key": bytes.fromhex("a1"),
                "type": None,
                "value": bytes.fromhex("21"),
            }, "a2": {
                "key": bytes.fromhex("a2"),
                "type": 2,
                "value": region().encode(),
            }, "a3": {
                "key": bytes.fromhex("a3"),
                "type": 4,
                "value": self._client_token.encode(),
            },
        })
