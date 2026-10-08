"""Constants for SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

#: GATT Service UUID for device telemetry. Is subscribable. Handle 17.
UUID_TELEMETRY = "8c850003-0302-41c5-b46e-cf057c562025"

#: GATT Service UUID for sending commands / negotiating.
UUID_COMMAND = "8c850002-0302-41c5-b46e-cf057c562025"

#: GATT Service UUID for identifying Solix/Prime devices (Tested on C300X, C1000, and Prime 160w Charger).
UUID_IDENTIFIER = "0000ff09-0000-1000-8000-00805f9b34fb"

#: GATT Service UUID of devices on the legacy transport (e.g the 767 / F2000).
LEGACY_SERVICE = "00001780-0000-1000-8000-00805f9b34fb"

#: GATT Characteristic UUID for legacy transport telemetry. Is subscribable.
UUID_TELEMETRY_LEGACY = "00008888-0000-1000-8000-00805f9b34fb"

#: GATT Characteristic UUID for sending legacy transport commands.
UUID_COMMAND_LEGACY = "00007777-0000-1000-8000-00805f9b34fb"

#: GATT Service UUID of devices on the 2215 transport (e.g the A1340 Prime power bank).
SERVICE_2215 = "00002215-0000-1000-8000-00805f9b34fb"

#: GATT Characteristic UUID for 2215 transport telemetry. Is subscribable.
UUID_TELEMETRY_2215 = "22150003-4002-81c5-b46e-cf057c562025"

#: GATT Characteristic UUID for sending 2215 transport commands / negotiating.
UUID_COMMAND_2215 = "22150002-4002-81c5-b46e-cf057c562025"

#: GATT Service UUIDs that identify an Anker device on any transport.
UUID_IDENTIFIERS = (UUID_IDENTIFIER, LEGACY_SERVICE, SERVICE_2215)

#: Time to wait before re-connecting on an unexpected disconnect.
RECONNECT_DELAY = 3

#: Maximum number of automatic re-connection attempts the program will make.
RECONNECT_ATTEMPTS_MAX = -1

#: Time to allow for a re-connect before considering the
#: device to be disconnected and running state changed callbacks.
DISCONNECT_TIMEOUT = 120

#: Time to allow for encryption negotiation before timing out
NEGOTIATION_TIMEOUT = 90

#: Maximum time to get no response in any negotiation stage before retrying
NEGOTIATION_RESPONSE_TIMEOUT = 15

#: Maximum time to get no response in the 1st negotiation stage before retrying
NEGOTIATION_RESPONSE_DELAY = 10

#: String value for unknown string attributes.
DEFAULT_METADATA_STRING = "Unknown"

#: Int value for unknown int attributes.
DEFAULT_METADATA_INT = -1

#: Float value for unknown float attributes.
DEFAULT_METADATA_FLOAT = -1.0

#: Bool value for unknown boolean attributes.
DEFAULT_METADATA_BOOL = None

#: The pattern used in telemetry packers from some Anker devices
TELEMETRY_PATTERN_A = "03010f"

#: The pattern used in negotiation packets from Anker devices
NEGOTIATION_PATTERN = "030001"

#: Static AES-GCM key, nonce and additional authenticated data used on the
#: encrypted negotiation path before the ECDH shared secret exists. The nonce
#: is the full 16-byte CBC IV the legacy AES path also seals its bootstrap
#: exchange under on the encrypted outer; GCM uses only its first 12 bytes.
NEGOTIATION_KEY = "b8ff7422955d4eb6d554a2c470280559"
NEGOTIATION_NONCE = "6ba3e3f2f3a60f2971ce5d1fd821cfa3"
NEGOTIATION_AAD = "3322110077665544bbaa9988ffeeddcc"

#: Public default account the legacy AES path bootstraps from when the
#: connect frame carries no client id (``0001`` on the plain outer with no
#: ``a2``, or any connect on the encrypted outer, which never sends one).
ANKER_DEFAULT_ACCOUNT_1 = "ANKER_DEFAULT_ACCOUNT_1"

# POSIX timezone to use if determining the system time zone fails
FALLBACK_TZ = "GMT0BST,M3.5.0/1,M10.5.0"

#: Region to use if none is set and the host locale names no territory
DEFAULT_REGION = "GB"
