"""MagGo 3-in-1 wireless charger device tests.

.. moduleauthor:: kb1ibt

"""

import pytest

from SolixBLE.devices.maggo_3in1 import MagGo3in1

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

MAGGO_3IN1_TEST_COMMANDS = [
    pytest.param(
        MagGo3in1,
        "_post_connect",
        [],
        [("4200", "a10121")],
        id="maggo_3in1_subscribe",
    ),
]
