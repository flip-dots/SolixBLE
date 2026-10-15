"""C1000G2 power station device tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest

from SolixBLE.devices.c1000g2 import C1000G2
from tests.const import NEGOTIATION_RESPONSES_SOLIX

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

C1000G2_TEST_COMMANDS = [
    pytest.param(
        C1000G2,
        "_post_connect",
        [],
        [("4100", "a10121")],
        id="c1000g2_subscribe",
    ),
    pytest.param(
        C1000G2,
        "turn_ac_on",
        [],
        [("4101", "a10121a2020101")],
        id="c1000g2_ac_on",
    ),
    pytest.param(
        C1000G2,
        "turn_ac_off",
        [],
        [("4101", "a10121a2020100")],
        id="c1000g2_ac_off",
    ),
    pytest.param(
        C1000G2,
        "turn_dc_on",
        [],
        [("4102", "a10121a2020101")],
        id="c1000g2_dc_on",
    ),
    pytest.param(
        C1000G2,
        "turn_dc_off",
        [],
        [("4102", "a10121a2020100")],
        id="c1000g2_dc_off",
    ),
    pytest.param(
        C1000G2,
        "set_max_battery_percentage",
        [100],
        [("4103", "a10121aa020164")],
        id="c1000g2_max_battery",
    ),
    pytest.param(
        C1000G2,
        "set_min_battery_percentage",
        [10],
        [("4103", "a10121ab02010a")],
        id="c1000g2_min_battery",
    ),
    pytest.param(
        C1000G2,
        "set_min_battery_percentage",
        [-1],
        ValueError,
        id="c1000g2_min_battery_out_of_range",
    ),
    pytest.param(
        C1000G2,
        "set_ac_charging_power",
        [1200],
        [("4101", "a10121a40302b004")],
        id="c1000g2_ac_charging_power",
    ),
    pytest.param(
        C1000G2,
        "turn_ac_fast_charge_on",
        [],
        [("4101", "a10121a7020101")],
        id="c1000g2_fast_charge_on",
    ),
    pytest.param(
        C1000G2,
        "turn_ac_fast_charge_off",
        [],
        [("4101", "a10121a7020100")],
        id="c1000g2_fast_charge_off",
    ),
]


############################
# Test device commands E2E #
############################

# These tests end-to-end tests check that the correct bytes are sent
# by the command. See test_send_command_e2e() in test_commands.py.

C1000G2_TEST_COMMANDS_E2E = [
    pytest.param(
        C1000G2,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_on",
        [],
        "ff091a0003000f4101cf1b676bb8c648a6f066b90d0c202502c1",
        id="c1000g2_ac_on",
    ),
    pytest.param(
        C1000G2,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_ac_off",
        [],
        "ff091a0003000f4101a665f0bcc4f9a3a154d50bb71d7c300e72",
        id="c1000g2_ac_off",
    ),
    pytest.param(
        C1000G2,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_on",
        [],
        "ff091a0003000f4102cf1b676bb8c648a6f066b90d0c202502c2",
        id="c1000g2_dc_on",
    ),
    pytest.param(
        C1000G2,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_dc_off",
        [],
        "ff091a0003000f4102a665f0bcc4f9a3a154d50bb71d7c300e71",
        id="c1000g2_dc_off",
    ),
]
