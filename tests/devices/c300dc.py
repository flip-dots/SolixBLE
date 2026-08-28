"""C300(X) DC power station device tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest

from SolixBLE.devices.c300dc import C300DC
from SolixBLE.states import DisplayTimeout, LightStatus
from tests.const import NEGOTIATION_RESPONSES_SOLIX

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

C300DC_TEST_COMMANDS = [
    pytest.param(
        C300DC,
        "turn_dc_on",
        [],
        [("404b", "a10121a2020101")],
        id="c300dc_dc_on",
    ),
    pytest.param(
        C300DC,
        "turn_dc_off",
        [],
        [("404b", "a10121a2020100")],
        id="c300dc_dc_off",
    ),
    pytest.param(
        C300DC,
        "turn_display_on",
        [],
        [("4052", "a10121a2020101")],
        id="c300dc_display_on",
    ),
    pytest.param(
        C300DC,
        "turn_display_off",
        [],
        [("4052", "a10121a2020100")],
        id="c300dc_display_off",
    ),
    pytest.param(
        C300DC,
        "set_light_mode",
        [LightStatus.LOW],
        [("404f", "a10121a2020101")],
        id="c300dc_light_low",
    ),
    pytest.param(
        C300DC,
        "set_light_mode",
        [LightStatus.MEDIUM],
        [("404f", "a10121a2020102")],
        id="c300dc_light_med",
    ),
    pytest.param(
        C300DC,
        "set_light_mode",
        [LightStatus.HIGH],
        [("404f", "a10121a2020103")],
        id="c300dc_light_high",
    ),
     pytest.param(
        C300DC,
        "set_display_timeout",
        [DisplayTimeout.S20],
        [("4046", "a10121a203021400")],
        id="c300dc_display_timeout_20s",
    ),
    pytest.param(
        C300DC,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        [("4046", "a10121a203020807")],
        id="c300dc_display_timeout_30m",
    ),
    pytest.param(
        C300DC,
        "set_display_mode",
        [LightStatus.LOW],
        [("404c", "a10121a2020101")],
        id="c300dc_display_low",
    ),
    pytest.param(
        C300DC,
        "set_display_mode",
        [LightStatus.MEDIUM],
        [("404c", "a10121a2020102")],
        id="c300dc_display_med",
    ),
    pytest.param(
        C300DC,
        "set_display_mode",
        [LightStatus.HIGH],
        [("404c", "a10121a2020103")],
        id="c300dc_display_high",
    ),
    pytest.param(
        C300DC,
        "set_display_mode",
        [LightStatus.SOS],
        ValueError,
        id="c300dc_display_sos",
    ),
    pytest.param(
        C300DC,
        "set_display_mode",
        [LightStatus.UNKNOWN],
        ValueError,
        id="c300dc_display_unknown",
    ),
]


############################
# Test device commands E2E #
############################

# These tests end-to-end tests check that the correct bytes are sent
# by the command. See test_send_command_e2e() in test_commands.py.

C300DC_TEST_COMMANDS_E2E = [
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_on",
        [],
        "ff091a0003000f404bcf1b676bb8c648a6f066b90d0c2025028a",
        id="c300dc_dc_on",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_off",
        [],
        "ff091a0003000f404ba665f0bcc4f9a3a154d50bb71d7c300e39",
        id="c300dc_dc_off",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_on",
        [],
        "ff091a0003000f4052cf1b676bb8c648a6f066b90d0c20250293",
        id="c300dc_display_on",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_off",
        [],
        "ff091a0003000f4052a665f0bcc4f9a3a154d50bb71d7c300e20",
        id="c300dc_display_off",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.LOW],
        "ff091a0003000f404fcf1b676bb8c648a6f066b90d0c2025028e",
        id="c300dc_light_low",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.MEDIUM],
        "ff091a0003000f404f78e6e204ae7a3858b1aac611fd4bdec146",
        id="c300dc_light_med",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_light_mode",
        [LightStatus.HIGH],
        "ff091a0003000f404f3fa145b4757507f18b3503e0cc3bcae3f5",
        id="c300dc_light_high",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_timeout",
        [DisplayTimeout.S20],
        "ff091a0003000f4046def18b6e3fa7434937ef01fecb95dfd3cb",
        id="c300dc_display_timeout_20s",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        "ff091a0003000f404665b9a755e0b46d3947a6937b5f7be4d2d3",
        id="c300dc_display_timeout_30m",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.LOW],
        "ff091a0003000f404ccf1b676bb8c648a6f066b90d0c2025028d",
        id="c300dc_display_low",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.MEDIUM],
        "ff091a0003000f404c78e6e204ae7a3858b1aac611fd4bdec145",
        id="c300dc_display_med",
    ),
    pytest.param(
        C300DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.HIGH],
        "ff091a0003000f404c3fa145b4757507f18b3503e0cc3bcae3f6",
        id="c300dc_display_high",
    ),
]
