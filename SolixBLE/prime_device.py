"""Base Anker Prime device implementation of SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from SolixBLE.device import SolixBLEDevice

#: The pattern used in telemetry packets from Anker Prime and Solix devices
TELEMETRY_PATTERN = "03000f"

#: The UUID sent to the device during negotiation
UUID_STRING = "79ebed35-dc9c-4904-b40c-72c4e863aa10"



class PrimeDevice(SolixBLEDevice):
    """
    This is a base class based upon SolixBLEDevice which contains logic
    unique to Anker Prime devices that is designed to be overridden for
    specific implementations, e.g 160w, 250w, etc.

    Anker Prime devices negotiate on the encrypted (AES-GCM) path, which
    :class:`~SolixBLE.device.SolixBLEDevice` implements; this class selects it
    by default and adds the session registration the Prime firmware expects
    once the link is authorized.
    """

    _DEFAULT_ENCRYPTED_NEGOTIATION: bool = True

    _UUID_STRING: str = UUID_STRING

    ###############
    # Negotiation #
    ###############

    async def _post_authorize(self) -> None:
        """Request the device info and register the session once authorized."""
        await self._send_packet(pattern=TELEMETRY_PATTERN, cmd="4200",
            parameters={
                "a1": {
                    "key": bytes.fromhex("a1"),
                    "type": None,
                    "value": bytes.fromhex("21"),
                }, "fe": {
                    "key": bytes.fromhex("fe"),
                    "type": None,
                    "value": lambda self: self._timestamp(),
                },
            },
        )
        await self._send_packet(pattern=TELEMETRY_PATTERN, cmd="420a",
            parameters={
                "a1": {
                    "key": bytes.fromhex("a1"),
                    "type": None,
                    "value": bytes.fromhex("21"),
                }, "a2": {
                    "key": bytes.fromhex("a2"),
                    "type": None,
                    "value": bytes.fromhex("044742"),
                }, "a3": {
                    "key": bytes.fromhex("a3"),
                    "type": 4,
                    "value": self._UUID_STRING.encode(),
                }, "a5": {
                    "key": bytes.fromhex("a5"),
                    "type": None,
                    "value": bytes.fromhex("0101"),
                }, "fe": {
                    "key": bytes.fromhex("fe"),
                    "type": None,
                    "value": lambda self: self._timestamp(),
                },
            },
        )

    #####################
    # Packet processing #
    #####################

    async def _send_command(self, cmd: str, parameters: dict, **kwargs: dict) -> None:
        """Send a command to the device.

        Parameter values may use lambda functions which will be executed at
        this point, where variables may be passed in as keyword arguments.

        :param cmd: The command type (e.g 4200, 0001, etc).
        :param parameters: Parameters of the command.
        :raises ConnectionError: If not connected/negotiated to device.
        """
        if not self.negotiated:
            raise ConnectionError("Not connected to device")

        await self._send_packet(
            pattern="03000f",
            cmd=cmd,
            parameters=parameters | { "fe": {
                "key": bytes.fromhex("fe"),
                "type": None,
                "value": lambda self: self._timestamp(),
            }},
            **kwargs,
        )
