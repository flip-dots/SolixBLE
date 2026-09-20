"""C1000G2 power station device tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest

from SolixBLE.devices.c1000g2 import C1000G2
from SolixBLE.states import DisplayTimeout, LightStatus
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
    # The display switch, brightness, timeout and both SoC limits are all
    # fields of the 4103 system group, selected by payload tag.
    pytest.param(
        C1000G2,
        "turn_display_on",
        [],
        [("4103", "a10121a2020101")],
        id="c1000g2_display_on",
    ),
    pytest.param(
        C1000G2,
        "turn_display_off",
        [],
        [("4103", "a10121a2020100")],
        id="c1000g2_display_off",
    ),
    pytest.param(
        C1000G2,
        "set_display_mode",
        [LightStatus.OFF],
        [("4103", "a10121a2020100")],
        id="c1000g2_display_mode_off",
    ),
    pytest.param(
        C1000G2,
        "set_display_mode",
        [LightStatus.LOW],
        [("4103", "a10121a3020101")],
        id="c1000g2_display_mode_low",
    ),
    pytest.param(
        C1000G2,
        "set_display_mode",
        [LightStatus.HIGH],
        [("4103", "a10121a3020103")],
        id="c1000g2_display_mode_high",
    ),
    pytest.param(
        C1000G2,
        "set_display_mode",
        [LightStatus.SOS],
        ValueError,
        id="c1000g2_display_mode_invalid",
    ),
    # The timeout is a little-endian u16 under type 02.
    pytest.param(
        C1000G2,
        "set_display_timeout",
        [DisplayTimeout.S10],
        [("4103", "a10121a403020a00")],
        id="c1000g2_display_timeout_10",
    ),
    pytest.param(
        C1000G2,
        "set_display_timeout",
        [DisplayTimeout.S60],
        [("4103", "a10121a403023c00")],
        id="c1000g2_display_timeout_60",
    ),
    pytest.param(
        C1000G2,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        [("4103", "a10121a403020807")],
        id="c1000g2_display_timeout_1800",
    ),
    pytest.param(
        C1000G2,
        "set_display_timeout",
        [DisplayTimeout.UNKNOWN],
        ValueError,
        id="c1000g2_display_timeout_invalid",
    ),
    pytest.param(
        C1000G2,
        "set_max_battery_percentage",
        [100],
        [("4103", "a10121aa020164")],
        id="c1000g2_max_soc_100",
    ),
    pytest.param(
        C1000G2,
        "set_max_battery_percentage",
        [99],
        [("4103", "a10121aa020163")],
        id="c1000g2_max_soc_off_menu",
    ),
    pytest.param(
        C1000G2,
        "set_max_battery_percentage",
        [101],
        ValueError,
        id="c1000g2_max_soc_invalid",
    ),
    pytest.param(
        C1000G2,
        "set_min_battery_percentage",
        [5],
        [("4103", "a10121ab020105")],
        id="c1000g2_min_soc_5",
    ),
    pytest.param(
        C1000G2,
        "set_min_battery_percentage",
        [-1],
        ValueError,
        id="c1000g2_min_soc_invalid",
    ),
    # The output timers are a u32 under type 03.
    pytest.param(
        C1000G2,
        "set_ac_timer",
        [300],
        [("4101", "a10121a305032c010000")],
        id="c1000g2_ac_timer",
    ),
    pytest.param(
        C1000G2,
        "set_dc_timer",
        [600],
        [("4102", "a10121a3050358020000")],
        id="c1000g2_dc_timer",
    ),
    pytest.param(
        C1000G2,
        "set_ac_timer",
        [0],
        [("4101", "a10121a3050300000000")],
        id="c1000g2_ac_timer_cancel",
    ),
    pytest.param(
        C1000G2,
        "set_ac_timer",
        [450],
        ValueError,
        id="c1000g2_ac_timer_bad_step",
    ),
    pytest.param(
        C1000G2,
        "set_dc_timer",
        [86700],
        ValueError,
        id="c1000g2_dc_timer_out_of_range",
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
