"""Tests for the AS220 (SOLIX S2000) device.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
"""

from SolixBLE import AS220
from SolixBLE.prime_device import AAD, NEGOTIATION_KEY, NEGOTIATION_NONCE
from SolixBLE.states import PortStatus
from tests.const import MOCK_BLE_DEVICE

from Crypto.Cipher import AES

# A real, decrypted ``c421`` telemetry payload captured from a live S2000.
REAL_TELEMETRY = bytes.fromhex(
    "00a10131a221062011415043445054433047323734303034363900054153323230090200"
    "010000a30e0400000000b0040064cc00580200a4220400000000b0043c010000000001d0"
    "021e000200010000016401005553f000000200a506041a00646400a60e04370037000000"
    "00006401013700a70c040137000137000000000000a80404000000aa0404000000d91a04"
    "00000664010000000000000000000000000000000000000000dc06040000000000dd0204"
    "00de020400df0704000000000000f0050401000000f806040100280a0ff91d0409020001"
    "000000000000000004020100000000000000000000030300fa15040101010100d7110000"
    "0000000000000000000000fd0e0031373837313039363534383937fe0503b61f8e6a"
)

# The 4829 negotiation response (device info), encrypted with the static key.
# Decrypts to: 00 a1 01 03 a2 05 "ESP32" a3 07 "0.0.0.3" a4 11 <serial> a5 06 <mac>
DEVICE_INFO_PLAINTEXT = bytes.fromhex(
    "00a10103a2054553503332a307302e302e302e33a411"
    "4150434450544330473237343030343639a506007f1d6d77a0"
)


def test_telemetry_parsing():
    """Real telemetry decodes to the expected sensor values."""
    s = AS220(MOCK_BLE_DEVICE)
    s._data = s._parse_payload(REAL_TELEMETRY)

    assert s.serial_number == "APCDPTC0G27400469"
    assert s.model == "AS220"
    assert s.battery_percentage == 100
    assert s.battery_health == 100
    assert s.temperature == 26
    assert s.power_out == 55
    assert s.ac_input == PortStatus.INPUT  # f0[1]=01 -> charger connected
    assert s.ac_power_in == 55
    assert s.ac_output == PortStatus.OUTPUT  # a7[1]=01
    assert s.ac_power_out == 55
    assert s.solar_power_in == 0
    assert s.usb_port_c1 == PortStatus.NOT_CONNECTED  # aa[1]=00
    assert s.usb_c1_power == 0
    assert s.max_battery_percentage == 100
    assert s.min_battery_percentage == 1


def test_missing_tlv_is_defensive():
    """Properties for TLVs the S2000 omits return the default, not an error."""
    s = AS220(MOCK_BLE_DEVICE)
    s._data = {"a1": bytes.fromhex("31")}  # only a1 present
    assert s.battery_percentage == -1  # DEFAULT_METADATA_INT
    assert s.serial_number == "Unknown"  # DEFAULT_METADATA_STRING


def test_device_serial_extracted_from_negotiation():
    """The device serial is learned from the 4829 device-info response."""
    s = AS220(MOCK_BLE_DEVICE)
    # Encrypt the device-info plaintext the way the device would (static key/nonce)
    cipher = AES.new(bytes.fromhex(NEGOTIATION_KEY), AES.MODE_GCM,
                     nonce=bytes.fromhex(NEGOTIATION_NONCE))
    cipher.update(bytes.fromhex(AAD))
    ct, mac = cipher.encrypt_and_digest(DEVICE_INFO_PLAINTEXT)

    info = s._parse_payload(s._dec_nego(ct + mac)[1:])
    assert info["a4"] == b"APCDPTC0G27400469"


def test_default_uuid_is_generated():
    """Omitting client_uuid yields a usable random UUID."""
    s = AS220(MOCK_BLE_DEVICE)
    assert len(s.client_uuid) == 36  # standard UUID string length
    # explicit UUID is preserved
    s2 = AS220(MOCK_BLE_DEVICE, client_uuid="a5220000-5011-4000-b000-000000000001")
    assert s2.client_uuid == "a5220000-5011-4000-b000-000000000001"
