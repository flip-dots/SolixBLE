"""C1000G2 power station device tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from datetime import datetime

import pytest

from SolixBLE.devices.c1000g2 import C1000G2, DisplayLanguage
from SolixBLE.states import DisplayTimeout, LightStatus
from tests.const import NEGOTIATION_RESPONSES_SOLIX

#: An idle C1000 Gen 2 (A1763, MainMcu v1.1.2.6) with the mains lead in,
#: the frame of test_devices.py's "c1000g2" case.
C900_A1763_IDLE = (
    "a10134a221062011415043444b39363146333734303032393000054131373633060201010100"
    "a30b0400000000b0040058dc00a41b0400000000b0043201000000000000001e000100000000"
    "00640103a506041700646400a60a04000000000000ab2a64a70704000000010000a804040000"
    "00aa0404000000ab0404000000ac0404000000ae0404000000b20404000000d91a0400001964"
    "010000000100000000000000000000000000000000da18040000000000000000000001e00164"
    "057f00000000000000dc06040000000000f91d04060201010500050000000000050005000503"
    "00010000000000020200fa150401010101001f0300000000000000000000000000fd0e003137"
    "3634363538323735393838fe0503638c2e69f0"
)

#: Its DC output (b2) on with a 6 W load, as test_devices.py's "c1000g2_dc_on".
B2_A1763_DC_ON = "010600"

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
    pytest.param(
        C1000G2,
        "set_ac_timer",
        [1200],
        [("4101", "a10121a30503b0040000")],
        id="c1000g2_ac_timer",
    ),
    pytest.param(
        C1000G2,
        "set_dc_timer",
        [7200],
        [("4102", "a10121a30503201c0000")],
        id="c1000g2_dc_timer",
    ),
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
        [LightStatus.LOW],
        [("4103", "a10121a3020101")],
        id="c1000g2_display_mode_low",
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
        "set_display_timeout",
        [DisplayTimeout.S60],
        [("4103", "a10121a403023c00")],
        id="c1000g2_display_timeout_60",
    ),
    pytest.param(
        C1000G2,
        "set_display_language",
        [DisplayLanguage.JAPANESE],
        [("4103", "a10121a9020104")],
        id="c1000g2_display_language",
    ),
    pytest.param(
        C1000G2,
        "set_display_plan",
        [None],
        ValueError,
        id="c1000g2_display_plan_before_telemetry",
    ),
    pytest.param(
        C1000G2,
        "turn_fast_charging_plan_on",
        [],
        [("405e", "a10121a3020103a4020100a5020101")],
        id="c1000g2_fast_charging_plan_on",
    ),
    pytest.param(
        C1000G2,
        "turn_fast_charging_plan_off",
        [],
        [("405e", "a10121a3020103a4020100a5020100")],
        id="c1000g2_fast_charging_plan_off",
    ),
    pytest.param(
        C1000G2,
        "set_fast_charging_plan_window",
        [datetime.fromtimestamp(1767225600)],  # noqa: DTZ006
        [("405e", "a10121a3020103a4020100a5020101a6020101a70b04640000b95569ffffffff")],
        id="c1000g2_fast_charging_plan_window_no_end",
    ),
    pytest.param(
        C1000G2,
        "turn_storm_guard_on",
        [],
        [("405e", "a10121a3020103a4020101a5020101")],
        id="c1000g2_storm_guard_on",
    ),
    pytest.param(
        C1000G2,
        "turn_storm_guard_off",
        [],
        [("405e", "a10121a3020103a4020101a5020100")],
        id="c1000g2_storm_guard_off",
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
