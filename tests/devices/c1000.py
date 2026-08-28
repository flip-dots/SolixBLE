"""C1000(X) power station device tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest

from SolixBLE.devices.c1000 import C1000
from SolixBLE.states import DisplayTimeout, LightStatus
from tests.const import NEGOTIATION_RESPONSES_SOLIX

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

C1000_TEST_COMMANDS = [
    pytest.param(
        C1000,
        "turn_ac_on",
        [],
        [("404a", "a10121a2020101")],
        id="c1000_ac_on",
    ),
    pytest.param(
        C1000,
        "turn_ac_off",
        [],
        [("404a", "a10121a2020100")],
        id="c1000_ac_off",
    ),
    pytest.param(
        C1000,
        "turn_dc_on",
        [],
        [("404b", "a10121a2020101")],
        id="c1000_dc_on",
    ),
    pytest.param(
        C1000,
        "turn_dc_off",
        [],
        [("404b", "a10121a2020100")],
        id="c1000_dc_off",
    ),
    pytest.param(
        C1000,
        "set_light_mode",
        [LightStatus.LOW],
        [("404f", "a10121a2020101")],
        id="c1000_light_low",
    ),
    pytest.param(
        C1000,
        "set_light_mode",
        [LightStatus.MEDIUM],
        [("404f", "a10121a2020102")],
        id="c1000_light_med",
    ),
    pytest.param(
        C1000,
        "set_light_mode",
        [LightStatus.HIGH],
        [("404f", "a10121a2020103")],
        id="c1000_light_high",
    ),
    pytest.param(
        C1000,
        "set_light_mode",
        [LightStatus.SOS],
        [("404f", "a10121a2020104")],
        id="c1000_light_sos",
    ),
    pytest.param(
        C1000,
        "set_light_mode",
        [LightStatus.UNKNOWN],
        ValueError,
        id="c1000_light_unknown",
    ),
    pytest.param(
        C1000,
        "set_display_mode",
        [LightStatus.LOW],
        [("404c", "a10121a2020101")],
        id="c1000_display_low",
    ),
    pytest.param(
        C1000,
        "set_display_mode",
        [LightStatus.MEDIUM],
        [("404c", "a10121a2020102")],
        id="c1000_display_med",
    ),
    pytest.param(
        C1000,
        "set_display_mode",
        [LightStatus.HIGH],
        [("404c", "a10121a2020103")],
        id="c1000_display_high",
    ),
    pytest.param(
        C1000,
        "set_display_mode",
        [LightStatus.SOS],
        ValueError,
        id="c1000_display_sos",
    ),
    pytest.param(
        C1000,
        "set_display_mode",
        [LightStatus.UNKNOWN],
        ValueError,
        id="c1000_display_unknown",
    ),
    pytest.param(
        C1000,
        "set_display_timeout",
        [DisplayTimeout.S20],
        [("4046", "a10121a203021400")],
        id="c1000_display_timeout_20s",
    ),
    pytest.param(
        C1000,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        [("4046", "a10121a203020807")],
        id="c1000_display_timeout_30m",
    ),
    pytest.param(
        C1000,
        "set_display_timeout",
        [DisplayTimeout.UNKNOWN],
        ValueError,
        id="c1000_display_timeout_unknown",
    ),
    pytest.param(
        C1000,
        "turn_display_on",
        [],
        [("4052", "a10121a2020101")],
        id="c1000_display_on",
    ),
    pytest.param(
        C1000,
        "turn_display_off",
        [],
        [("4052", "a10121a2020100")],
        id="c1000_display_off",
    ),
]


####################################
# Test device commands & responses #
####################################

# These tests are for sending commands to the device and making sure the correct
# calls are made to the command sending functions, that the response is handled
# appropriately, the correct value is returned, and errors are raised where
# appropriate. See test_send_command_response() in test_commands.py.

C1000_TEST_COMMANDS_RESPONSES = [
    pytest.param(
        C1000,
        "get_status_update",
        [],
        [("4040", "a10121")],
        [("03010f", "c840", None)],
        TimeoutError,
        id="c1000_status_update_error",
    ),
]


############################
# Test device commands E2E #
############################

# These tests end-to-end tests check that the correct bytes are sent
# by the command. See test_send_command_e2e() in test_commands.py.

C1000_TEST_COMMANDS_E2E = [
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_on",
        [],
        "ff091a0003000f404acf1b676bb8c648a6f066b90d0c2025028b",
        id="c1000_ac_on",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_off",
        [],
        "ff091a0003000f404aa665f0bcc4f9a3a154d50bb71d7c300e38",
        id="c1000_ac_off",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_on",
        [],
        "ff091a0003000f404bcf1b676bb8c648a6f066b90d0c2025028a",
        id="c1000_dc_on",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_off",
        [],
        "ff091a0003000f404ba665f0bcc4f9a3a154d50bb71d7c300e39",
        id="c1000_dc_off",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.LOW],
        "ff091a0003000f404fcf1b676bb8c648a6f066b90d0c2025028e",
        id="c1000_light_low",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.MEDIUM],
        "ff091a0003000f404f78e6e204ae7a3858b1aac611fd4bdec146",
        id="c1000_light_med",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.HIGH],
        "ff091a0003000f404f3fa145b4757507f18b3503e0cc3bcae3f5",
        id="c1000_light_high",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.SOS],
        "ff091a0003000f404f2c28e49e5cd5ed57b9749702b802f3fb48",
        id="c1000_light_sos",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.LOW],
        "ff091a0003000f404ccf1b676bb8c648a6f066b90d0c2025028d",
        id="c1000_display_low",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.MEDIUM],
        "ff091a0003000f404c78e6e204ae7a3858b1aac611fd4bdec145",
        id="c1000_display_med",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.HIGH],
        "ff091a0003000f404c3fa145b4757507f18b3503e0cc3bcae3f6",
        id="c1000_display_high",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_timeout",
        [DisplayTimeout.S20],
        "ff091a0003000f4046def18b6e3fa7434937ef01fecb95dfd3cb",
        id="c1000_display_timeout_20s",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        "ff091a0003000f404665b9a755e0b46d3947a6937b5f7be4d2d3",
        id="c1000_display_timeout_30m",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_on",
        [],
        "ff091a0003000f4052cf1b676bb8c648a6f066b90d0c20250293",
        id="c1000_display_on",
    ),
    pytest.param(
        C1000,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_off",
        [],
        "ff091a0003000f4052a665f0bcc4f9a3a154d50bb71d7c300e20",
        id="c1000_display_off",
    ),
]
