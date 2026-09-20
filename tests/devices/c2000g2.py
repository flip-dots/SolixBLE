"""C2000G2 power station device tests.

.. moduleauthor:: kb1ibt

"""

import pytest

from SolixBLE.devices.c2000g2 import C2000G2
from SolixBLE.states import DisplayTimeout

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
    pytest.param(
        C2000G2,
        "set_display_timeout",
        [DisplayTimeout.S300],
        [("4103", "a10121a403022c01")],
        id="c2000g2_display_timeout_300",
    ),
]
