"""Anker Prime 160w charger tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest

from SolixBLE.devices.prime_charger_160w import PrimeCharger160w
from tests.const import NEGOTIATION_RESPONSES_PRIME

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

PRIME_CHARGER_160W_TEST_COMMANDS = [
    pytest.param(
        PrimeCharger160w,
        "turn_usb_c1_on",
        [],
        [("4207", "a10121a2020100a3020101")],
        id="prime_charger_160w_usb_c1_on",
    ),
    pytest.param(
        PrimeCharger160w,
        "turn_usb_c1_off",
        [],
        [("4207", "a10121a2020100a3020100")],
        id="prime_charger_160w_usb_c1_off",
    ),
    pytest.param(
        PrimeCharger160w,
        "set_timer_usb_c1",
        [300],
        [("4209", "a10121a2020100a305042c010000")],
        id="prime_charger_160w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        "set_timer_usb_c1",
        [7200],
        [("4209", "a10121a2020100a30504201c0000")],
        id="prime_charger_160w_usb_c1_timer_120m",
    ),
    pytest.param(
        PrimeCharger160w,
        "turn_usb_c2_on",
        [],
        [("4207", "a10121a2020101a3020101")],
        id="prime_charger_160w_usb_c2_on",
    ),
    pytest.param(
        PrimeCharger160w,
        "turn_usb_c2_off",
        [],
        [("4207", "a10121a2020101a3020100")],
        id="prime_charger_160w_usb_c2_off",
    ),
    pytest.param(
        PrimeCharger160w,
        "set_timer_usb_c2",
        [300],
        [("4209", "a10121a2020101a305042c010000")],
        id="prime_charger_160w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        "set_timer_usb_c2",
        [7200],
        [("4209", "a10121a2020101a30504201c0000")],
        id="prime_charger_160w_usb_c2_timer_120m",
    ),
    pytest.param(
        PrimeCharger160w,
        "turn_usb_c3_on",
        [],
        [("4207", "a10121a2020102a3020101")],
        id="prime_charger_160w_usb_c3_on",
    ),
    pytest.param(
        PrimeCharger160w,
        "turn_usb_c3_off",
        [],
        [("4207", "a10121a2020102a3020100")],
        id="prime_charger_160w_usb_c3_off",
    ),
    pytest.param(
        PrimeCharger160w,
        "set_timer_usb_c3",
        [300],
        [("4209", "a10121a2020102a305042c010000")],
        id="prime_charger_160w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        "set_timer_usb_c3",
        [7200],
        [("4209", "a10121a2020102a30504201c0000")],
        id="prime_charger_160w_usb_c3_timer_120m",
    ),
]


############################
# Test device commands E2E #
############################

# These tests end-to-end tests check that the correct bytes are sent
# by the command. See test_send_command_e2e() in test_commands.py.

PRIME_CHARGER_160W_TEST_COMMANDS_E2E = [
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c1_on",
        [],
        "ff092b0003000f420757e9b883d85da36ffa59e144a5881d8773e6bacd6c24e0484da6030bc35f27c50771",
        id="prime_charger_160w_usb_c1_on",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c1_off",
        [],
        "ff092b0003000f420757e9b883d85da36ffa59e044a5881d8773eea0d2dbe21151b3eae6b5fa935c38ed94",
        id="prime_charger_160w_usb_c1_off",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [300],
        "ff092e0003000f420957e9b883d85da36ffd5cccbba1679a36f5672fff283580d22c655e1542fe96137072a1c7bd",
        id="prime_charger_160w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [7200],
        "ff092e0003000f420957e9b883d85da36ffd5cc0a6a1679a36f5672fff8e8000d4aaac5a3007939a6eae1b4d0496",
        id="prime_charger_160w_usb_c1_timer_120m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_on",
        [],
        "ff092b0003000f420757e9b883d85da26ffa59e144a5881d8773304bd4926805f6746a78f6295290e98f20",
        id="prime_charger_160w_usb_c2_on",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_off",
        [],
        "ff092b0003000f420757e9b883d85da26ffa59e044a5881d87733851cb25aef4ef8a269d48109eeb1465c5",
        id="prime_charger_160w_usb_c2_off",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [300],
        "ff092e0003000f420957e9b883d85da26ffd5cccbba1679a36f5672ffffec4992c6080e02c8e856bf97dc58d4fec",
        id="prime_charger_160w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [7200],
        "ff092e0003000f420957e9b883d85da26ffd5cc0a6a1679a36f5672fff5871192ae649e409cbe86784a3ac618cc7",
        id="prime_charger_160w_usb_c2_timer_120m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_on",
        [],
        "ff092b0003000f420757e9b883d85da16ffa59e144a5881d87738958fe90bd2b343e3ef4f01744499c1611",
        id="prime_charger_160w_usb_c3_on",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_off",
        [],
        "ff092b0003000f420757e9b883d85da16ffa59e044a5881d87738142e1277bda2dc072114e2e883261fcf4",
        id="prime_charger_160w_usb_c3_off",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [300],
        "ff092e0003000f420957e9b883d85da16ffd5cccbba1679a36f5672fff47d7b32eb5ae2266da096dc76b1cf8d6dd",
        id="prime_charger_160w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [7200],
        "ff092e0003000f420957e9b883d85da16ffd5cc0a6a1679a36f5672fffe1623328336726439f6461bab5751415f6",
        id="prime_charger_160w_usb_c3_timer_120m",
    ),
]
