"""C2000G2 power station device tests.

.. moduleauthor:: kb1ibt

"""

import pytest

from SolixBLE.devices.c2000g2 import C2000G2
from SolixBLE.states import DisplayTimeout, LightStatus

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

C2000G2_TEST_COMMANDS = [
    # The subscribe is what starts the telemetry stream and 4057 arms the
    # realtime latch; both go out on every (re)connection.
    pytest.param(
        C2000G2,
        "_post_connect",
        [],
        [("4100", "a10121"), ("4057", "a10121a2020101")],
        id="c2000g2_post_connect",
    ),
    # The display switch, brightness, timeout and both SoC limits are all
    # fields of the 4103 system group, selected by payload tag.
    pytest.param(
        C2000G2,
        "turn_display_on",
        [],
        [("4103", "a10121a2020101")],
        id="c2000g2_display_on",
    ),
    pytest.param(
        C2000G2,
        "turn_display_off",
        [],
        [("4103", "a10121a2020100")],
        id="c2000g2_display_off",
    ),
    pytest.param(
        C2000G2,
        "set_display_mode",
        [LightStatus.OFF],
        [("4103", "a10121a2020100")],
        id="c2000g2_display_mode_off",
    ),
    pytest.param(
        C2000G2,
        "set_display_mode",
        [LightStatus.LOW],
        [("4103", "a10121a3020101")],
        id="c2000g2_display_mode_low",
    ),
    pytest.param(
        C2000G2,
        "set_display_mode",
        [LightStatus.HIGH],
        [("4103", "a10121a3020103")],
        id="c2000g2_display_mode_high",
    ),
    pytest.param(
        C2000G2,
        "set_display_mode",
        [LightStatus.SOS],
        ValueError,
        id="c2000g2_display_mode_invalid",
    ),
    # The timeout is a little-endian u16 under type 02.
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.S10],
        [("4103", "a10121a403020a00")],
        id="c2000g2_display_timeout_10",
    ),
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.S60],
        [("4103", "a10121a403023c00")],
        id="c2000g2_display_timeout_60",
    ),
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        [("4103", "a10121a403020807")],
        id="c2000g2_display_timeout_1800",
    ),
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.UNKNOWN],
        ValueError,
        id="c2000g2_display_timeout_invalid",
    ),
    pytest.param(
        C2000G2,
        "set_max_battery_percentage",
        [100],
        [("4103", "a10121aa020164")],
        id="c2000g2_max_soc_100",
    ),
    pytest.param(
        C2000G2,
        "set_max_battery_percentage",
        [99],
        [("4103", "a10121aa020163")],
        id="c2000g2_max_soc_off_menu",
    ),
    pytest.param(
        C2000G2,
        "set_max_battery_percentage",
        [101],
        ValueError,
        id="c2000g2_max_soc_invalid",
    ),
    pytest.param(
        C2000G2,
        "set_min_battery_percentage",
        [5],
        [("4103", "a10121ab020105")],
        id="c2000g2_min_soc_5",
    ),
    pytest.param(
        C2000G2,
        "set_min_battery_percentage",
        [-1],
        ValueError,
        id="c2000g2_min_soc_invalid",
    ),
    # The output timers are a u32 under type 03.
    pytest.param(
        C2000G2,
        "set_ac_timer",
        [300],
        [("4101", "a10121a305032c010000")],
        id="c2000g2_ac_timer",
    ),
    pytest.param(
        C2000G2,
        "set_dc_timer",
        [600],
        [("4102", "a10121a3050358020000")],
        id="c2000g2_dc_timer",
    ),
    pytest.param(
        C2000G2,
        "set_ac_timer",
        [0],
        [("4101", "a10121a3050300000000")],
        id="c2000g2_ac_timer_cancel",
    ),
    pytest.param(
        C2000G2,
        "set_ac_timer",
        [450],
        ValueError,
        id="c2000g2_ac_timer_bad_step",
    ),
    pytest.param(
        C2000G2,
        "set_dc_timer",
        [86700],
        ValueError,
        id="c2000g2_dc_timer_out_of_range",
    ),
    pytest.param(
        C2000G2,
        "set_ac_charging_power",
        [1200],
        [("4101", "a10121a40302b004")],
        id="c2000g2_ac_charging_power",
    ),
    pytest.param(
        C2000G2,
        "set_ac_charging_power",
        [400],
        ValueError,
        id="c2000g2_ac_charging_power_out_of_range",
    ),
    # Inherited from the C1000 G2 unchanged.
    pytest.param(
        C2000G2,
        "turn_ac_on",
        [],
        [("4101", "a10121a2020101")],
        id="c2000g2_ac_on",
    ),
    pytest.param(
        C2000G2,
        "turn_dc_off",
        [],
        [("4102", "a10121a2020100")],
        id="c2000g2_dc_off",
    ),
]
