"""Constants for SolixBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

#: GATT Service UUID for device telemetry. Is subscribable. Handle 17.
UUID_TELEMETRY = "8c850003-0302-41c5-b46e-cf057c562025"

#: GATT Service UUID for sending commands / negotiating.
UUID_COMMAND = "8c850002-0302-41c5-b46e-cf057c562025"

#: GATT Service UUID for identifying Solix/Prime devices (Tested on C300X, C1000, and Prime 160w Charger).
UUID_IDENTIFIERS = (
    "0000ff09-0000-1000-8000-00805f9b34fb",
    "00001780-0000-1000-8000-00805f9b34fb",
)

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

#: Command used to initiate negotiations
NEGOTIATION_COMMAND_0 = "ff0936000300010001a10442ad8c69a22462326463306231372d623735642d346162662d626136652d656337633939376332336537b9"

#: Response to receiving 1st negotiation message
NEGOTIATION_COMMAND_1 = "ff093d000300010003a10442ad8c69a22462326463306231372d623735642d346162662d626136652d656337633939376332336537a30120a40200f064"

#: Response to receiving 2nd negotiation message
NEGOTIATION_COMMAND_2 = "ff0936000300010029a10442ad8c69a22462326463306231372d623735642d346162662d626136652d65633763393937633233653791"

#: Response to receiving 3rd negotiation message
NEGOTIATION_COMMAND_3 = "ff0940000300010005a10442ad8c69a22462326463306231372d623735642d346162662d626136652d656337633939376332336537a30120a40200f0a50140fb"

#: Response to receiving 4th negotiation message
NEGOTIATION_COMMAND_4 = "ff094c000300010021a140060ea168f232aedb37fb2d120c49180329ac72ab5ec3eb8fd30a2f252dc5e151dabccd9b1dc1e288704ca760a0d8c918e5c94823a1f609a4bf07fb4c33ee219085"

#: Response to receiving 5th negotiation message
NEGOTIATION_COMMAND_5 = "ff095a000300014022580bc0532a53c739adf3da7b994a7b5f221bcc16bab6392c215cb4faaf41d9d58e2c81c016e474c78eed5569147cb74a1f22ca2b3fad2e209dbbcfbdaca352034a6c479f055f68581b5f1e22348809f526"

#: The private key this program uses to perform the ECDH negotiation to
#: get a shared secret which is then used as an AES key for encrypting
#: communications between the program and the power station. Yes I know it
#: is bad security practice to hardcode keys but its a freaking power station
#: talking over Bluetooth with a range of like 10m... I don't care, the only
#: reason this has to be done at all is because Anker power stations no longer
#: support sending telemetry in plain text after the latest firmware update.
PRIVATE_KEY = "7dfbea61cd95cee49c458ad7419e817f1ade9a66136de3c7d5787af1458e39f4"

# POSIX timezone to use if determining the system time zone fails
FALLBACK_TZ = "GMT0BST,M3.5.0/1,M10.5.0"
