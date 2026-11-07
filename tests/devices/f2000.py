"""F2000 power station device tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest
from construct import Container

from SolixBLE.devices.f2000 import F2000
from SolixBLE.states import LightStatus
from tests.const import NEGOTIATION_RESPONSES_SOLIX

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

F2000_TEST_COMMANDS = [
    pytest.param(
        F2000,
        "turn_ac_on",
        [],
        [("404a", "a10121a2020101")],
        id="f2000_ac_on",
    ),
    pytest.param(
        F2000,
        "turn_ac_off",
        [],
        [("404a", "a10121a2020100")],
        id="f2000_ac_off",
    ),
    pytest.param(
        F2000,
        "turn_dc_on",
        [],
        [("404b", "a10121a2020101")],
        id="f2000_dc_on",
    ),
    pytest.param(
        F2000,
        "turn_dc_off",
        [],
        [("404b", "a10121a2020100")],
        id="f2000_dc_off",
    ),
    pytest.param(
        F2000,
        "set_light_mode",
        [LightStatus.LOW],
        [("404f", "a10121a2020101")],
        id="f2000_light_low",
    ),
    pytest.param(
        F2000,
        "set_light_mode",
        [LightStatus.MEDIUM],
        [("404f", "a10121a2020102")],
        id="f2000_light_med",
    ),
    pytest.param(
        F2000,
        "set_light_mode",
        [LightStatus.HIGH],
        [("404f", "a10121a2020103")],
        id="f2000_light_high",
    ),
    pytest.param(
        F2000,
        "set_light_mode",
        [LightStatus.SOS],
        [("404f", "a10121a2020104")],
        id="f2000_light_sos",
    ),
    pytest.param(
        F2000,
        "set_light_mode",
        [LightStatus.UNKNOWN],
        ValueError,
        id="f2000_light_unknown",
    ),
    pytest.param(
        F2000,
        "turn_display_on",
        [],
        [("4052", "a10121a2020101")],
        id="f2000_display_on",
    ),
    pytest.param(
        F2000,
        "turn_display_off",
        [],
        [("4052", "a10121a2020100")],
        id="f2000_display_off",
    ),
    pytest.param(
        F2000,
        "turn_power_saving_mode_on",
        [],
        [("404e", "a10121a2020101")],
        id="f2000_power_saving_on",
    ),
    pytest.param(
        F2000,
        "turn_power_saving_mode_off",
        [],
        [("404e", "a10121a2020100")],
        id="f2000_power_saving_off",
    ),
]

####################################
# Test device commands & responses #
####################################

# These tests are for sending commands to the device and making sure the correct
# calls are made to the command sending functions, that the response is handled
# appropriately, the correct value is returned, and errors are raised where
# appropriate. See test_send_command_response() in test_commands.py.


F2000_TEST_COMMANDS_RESPONSES = [
    pytest.param(
        F2000,
        "get_status_update",
        [],
        [("4040", "a10121")],
        [("03010f", "c840", "00a10131a2050300000000a3050300000000a403020900a50302a405a603021801a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af0302a405b003021801b103020000b203020000b303025a01b403022e01b503027400b603026c00b703020000b803027500b903020000ba03025a01bb03020100bc020102bd020122be020100bf020102c0020100c1020140c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d01100415a56334e4d30463038373030343131d10302a005d203020000d303021400d403023c00d503020000d603020000d7020101d8020100d9020103da02013cdb020100dc020100dd020101de020100f815040000000001000000000000000000000000000000fd0a0041313738315f354168fe0503372b136a")],  # noqa: E501
        {'a1': Container(key=b'\xa1', length=1, type=None, value=b'1'), 'a2': Container(key=b'\xa2', length=5, type=3, value=b'\x00\x00\x00\x00'), 'a3': Container(key=b'\xa3', length=5, type=3, value=b'\x00\x00\x00\x00'), 'a4': Container(key=b'\xa4', length=3, type=2, value=b'\t\x00'), 'a5': Container(key=b'\xa5', length=3, type=2, value=b'\xa4\x05'), 'a6': Container(key=b'\xa6', length=3, type=2, value=b'\x18\x01'), 'a7': Container(key=b'\xa7', length=3, type=2, value=b'\x00\x00'), 'a8': Container(key=b'\xa8', length=3, type=2, value=b'\x00\x00'), 'a9': Container(key=b'\xa9', length=3, type=2, value=b'\x00\x00'), 'aa': Container(key=b'\xaa', length=3, type=2, value=b'\x00\x00'), 'ab': Container(key=b'\xab', length=3, type=2, value=b'\x00\x00'), 'ac': Container(key=b'\xac', length=3, type=2, value=b'\x00\x00'), 'ad': Container(key=b'\xad', length=3, type=2, value=b'\x00\x00'), 'ae': Container(key=b'\xae', length=3, type=2, value=b'\x00\x00'), 'af': Container(key=b'\xaf', length=3, type=2, value=b'\xa4\x05'), 'b0': Container(key=b'\xb0', length=3, type=2, value=b'\x18\x01'), 'b1': Container(key=b'\xb1', length=3, type=2, value=b'\x00\x00'), 'b2': Container(key=b'\xb2', length=3, type=2, value=b'\x00\x00'), 'b3': Container(key=b'\xb3', length=3, type=2, value=b'Z\x01'), 'b4': Container(key=b'\xb4', length=3, type=2, value=b'.\x01'), 'b5': Container(key=b'\xb5', length=3, type=2, value=b't\x00'), 'b6': Container(key=b'\xb6', length=3, type=2, value=b'l\x00'), 'b7': Container(key=b'\xb7', length=3, type=2, value=b'\x00\x00'), 'b8': Container(key=b'\xb8', length=3, type=2, value=b'u\x00'), 'b9': Container(key=b'\xb9', length=3, type=2, value=b'\x00\x00'), 'ba': Container(key=b'\xba', length=3, type=2, value=b'Z\x01'), 'bb': Container(key=b'\xbb', length=3, type=2, value=b'\x01\x00'), 'bc': Container(key=b'\xbc', length=2, type=1, value=b'\x02'), 'bd': Container(key=b'\xbd', length=2, type=1, value=b'"'), 'be': Container(key=b'\xbe', length=2, type=1, value=b'\x00'), 'bf': Container(key=b'\xbf', length=2, type=1, value=b'\x02'), 'c0': Container(key=b'\xc0', length=2, type=1, value=b'\x00'), 'c1': Container(key=b'\xc1', length=2, type=1, value=b'@'), 'c2': Container(key=b'\xc2', length=2, type=1, value=b'\x00'), 'c3': Container(key=b'\xc3', length=2, type=1, value=b'd'), 'c4': Container(key=b'\xc4', length=2, type=1, value=b'\x00'), 'c5': Container(key=b'\xc5', length=2, type=1, value=b'\x00'), 'c6': Container(key=b'\xc6', length=2, type=1, value=b'\x00'), 'c7': Container(key=b'\xc7', length=2, type=1, value=b'\x00'), 'c8': Container(key=b'\xc8', length=2, type=1, value=b'\x00'), 'c9': Container(key=b'\xc9', length=2, type=1, value=b'\x00'), 'ca': Container(key=b'\xca', length=2, type=1, value=b'\x00'), 'cb': Container(key=b'\xcb', length=2, type=1, value=b'\x00'), 'cc': Container(key=b'\xcc', length=2, type=1, value=b'\x00'), 'cd': Container(key=b'\xcd', length=2, type=1, value=b'\x00'), 'ce': Container(key=b'\xce', length=2, type=1, value=b'\x00'), 'cf': Container(key=b'\xcf', length=2, type=1, value=b'\x00'), 'd0': Container(key=b'\xd0', length=17, type=0, value=b'AZV3NM0F08700411'), 'd1': Container(key=b'\xd1', length=3, type=2, value=b'\xa0\x05'), 'd2': Container(key=b'\xd2', length=3, type=2, value=b'\x00\x00'), 'd3': Container(key=b'\xd3', length=3, type=2, value=b'\x14\x00'), 'd4': Container(key=b'\xd4', length=3, type=2, value=b'<\x00'), 'd5': Container(key=b'\xd5', length=3, type=2, value=b'\x00\x00'), 'd6': Container(key=b'\xd6', length=3, type=2, value=b'\x00\x00'), 'd7': Container(key=b'\xd7', length=2, type=1, value=b'\x01'), 'd8': Container(key=b'\xd8', length=2, type=1, value=b'\x00'), 'd9': Container(key=b'\xd9', length=2, type=1, value=b'\x03'), 'da': Container(key=b'\xda', length=2, type=1, value=b'<'), 'db': Container(key=b'\xdb', length=2, type=1, value=b'\x00'), 'dc': Container(key=b'\xdc', length=2, type=1, value=b'\x00'), 'dd': Container(key=b'\xdd', length=2, type=1, value=b'\x01'), 'de': Container(key=b'\xde', length=2, type=1, value=b'\x00'), 'f8': Container(key=b'\xf8', length=21, type=4, value=b'\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'), 'fd': Container(key=b'\xfd', length=10, type=0, value=b'A1781_5Ah'), 'fe': Container(key=b'\xfe', length=5, type=3, value=b'7+\x13j')},  # noqa: E501
        id="f2000_status_update",
    ),
    pytest.param(
        F2000,
        "get_status_update",
        [],
        [("4040", "a10121")],
        [("03010f", "c840", None)],
        TimeoutError,
        id="f2000_status_update_error",
    ),
]

############################
# Test device commands E2E #
############################

# These tests end-to-end tests check that the correct bytes are sent
# by the command. See test_send_command_e2e() in test_commands.py.

F2000_TEST_COMMANDS_E2E = [
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_on",
        [],
        "ff091a0003000f404acf1b676bb8c648a6f066b90d0c2025028b",
        id="f2000_ac_on",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_off",
        [],
        "ff091a0003000f404aa665f0bcc4f9a3a154d50bb71d7c300e38",
        id="f2000_ac_off",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_on",
        [],
        "ff091a0003000f404bcf1b676bb8c648a6f066b90d0c2025028a",
        id="f2000_dc_on",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_off",
        [],
        "ff091a0003000f404ba665f0bcc4f9a3a154d50bb71d7c300e39",
        id="f2000_dc_off",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.LOW],
        "ff091a0003000f404fcf1b676bb8c648a6f066b90d0c2025028e",
        id="f2000_light_low",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.MEDIUM],
        "ff091a0003000f404f78e6e204ae7a3858b1aac611fd4bdec146",
        id="f2000_light_med",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.HIGH],
        "ff091a0003000f404f3fa145b4757507f18b3503e0cc3bcae3f5",
        id="f2000_light_high",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.SOS],
        "ff091a0003000f404f2c28e49e5cd5ed57b9749702b802f3fb48",
        id="f2000_light_sos",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_on",
        [],
        "ff091a0003000f4052cf1b676bb8c648a6f066b90d0c20250293",
        id="f2000_display_on",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_off",
        [],
        "ff091a0003000f4052a665f0bcc4f9a3a154d50bb71d7c300e20",
        id="f2000_display_off",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_power_saving_mode_on",
        [],
        "ff091a0003000f404ecf1b676bb8c648a6f066b90d0c2025028f",
        id="f2000_power_saving_on",
    ),
    pytest.param(
        F2000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_power_saving_mode_off",
        [],
        "ff091a0003000f404ea665f0bcc4f9a3a154d50bb71d7c300e3c",
        id="f2000_power_saving_off",
    ),
]
