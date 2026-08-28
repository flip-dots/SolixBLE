"""F3800 power station device tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest

from SolixBLE.devices.f3800 import F3800
from tests.const import NEGOTIATION_RESPONSES_SOLIX

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

F3800_TEST_COMMANDS = [
    pytest.param(
        F3800,
        "turn_ac_on",
        [],
        [("404a", "a10121a2020101")],
        id="f3800_ac_on",
    ),
    pytest.param(
        F3800,
        "turn_ac_off",
        [],
        [("404a", "a10121a2020100")],
        id="f3800_ac_off",
    ),
    pytest.param(
        F3800,
        "turn_dc_on",
        [],
        [("404b", "a10121a2020101")],
        id="f3800_dc_on",
    ),
    pytest.param(
        F3800,
        "turn_dc_off",
        [],
        [("404b", "a10121a2020100")],
        id="f3800_dc_off",
    ),
]


############################
# Test device commands E2E #
############################

# These tests end-to-end tests check that the correct bytes are sent
# by the command. See test_send_command_e2e() in test_commands.py.

F3800_TEST_COMMANDS_E2E = [
    pytest.param(
        F3800,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_on",
        [],
        "ff091a0003000f404acf1b676bb8c648a6f066b90d0c2025028b",
        id="f3800_ac_on",
    ),
    pytest.param(
        F3800,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_off",
        [],
        "ff091a0003000f404aa665f0bcc4f9a3a154d50bb71d7c300e38",
        id="f3800_ac_off",
    ),
    pytest.param(
        F3800,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_on",
        [],
        "ff091a0003000f404bcf1b676bb8c648a6f066b90d0c2025028a",
        id="f3800_dc_on",
    ),
    pytest.param(
        F3800,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_off",
        [],
        "ff091a0003000f404ba665f0bcc4f9a3a154d50bb71d7c300e39",
        id="f3800_dc_off",
    ),
]
