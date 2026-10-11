"""BLE transports Anker devices use.

The negotiating transport (GATT service ``ff09``) carries ``ff09`` frames and
negotiates a session before commands; the legacy transport (service ``1780``,
e.g the 767 / F2000 on older firmware) carries its own frames without one. The
2215 transport (service ``2215``, e.g the A1340 Prime power bank) carries the
same frames and negotiation as ``ff09`` on its own characteristics.

.. moduleauthor:: kb1ibt
"""

from typing import ClassVar

from .const import (
    LEGACY_SERVICE,
    SERVICE_2215,
    UUID_COMMAND,
    UUID_COMMAND_2215,
    UUID_COMMAND_LEGACY,
    UUID_IDENTIFIER,
    UUID_TELEMETRY,
    UUID_TELEMETRY_2215,
    UUID_TELEMETRY_LEGACY,
)


class NegotiatingTransport:
    """Service ``ff09``: a session is negotiated before commands."""

    service: ClassVar[str] = UUID_IDENTIFIER
    command: ClassVar[str] = UUID_COMMAND
    telemetry: ClassVar[str] = UUID_TELEMETRY
    negotiates: ClassVar[bool] = True


class Transport2215:
    """Service ``2215``: ``ff09`` frames and negotiation, its own characteristics."""

    service: ClassVar[str] = SERVICE_2215
    command: ClassVar[str] = UUID_COMMAND_2215
    telemetry: ClassVar[str] = UUID_TELEMETRY_2215
    negotiates: ClassVar[bool] = True


class LegacyTransport:
    """Service ``1780``: the device takes commands once subscribed."""

    service: ClassVar[str] = LEGACY_SERVICE
    command: ClassVar[str] = UUID_COMMAND_LEGACY
    telemetry: ClassVar[str] = UUID_TELEMETRY_LEGACY
    negotiates: ClassVar[bool] = False
