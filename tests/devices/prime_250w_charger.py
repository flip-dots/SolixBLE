"""Anker Prime 250w charger tests.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""
import pytest

from SolixBLE.devices.prime_charger_250w import PrimeCharger250w
from tests.const import NEGOTIATION_RESPONSES_PRIME

########################
# Test device commands #
########################

# These tests are for sending commands to the device and making sure the
# correct calls are made to the command sending functions and errors are
# raised where appropriate. See test_send_command() in test_commands.py.

PRIME_CHARGER_250W_TEST_COMMANDS = [
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c1_on",
        [],
        [("4207", "a10121a2020100a3020101")],
        id="prime_charger_250w_usb_c1_on",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c1_off",
        [],
        [("4207", "a10121a2020100a3020100")],
        id="prime_charger_250w_usb_c1_off",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c1",
        [300],
        [("4209", "a10121a2020100a306042c01000000")],
        id="prime_charger_250w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c1",
        [7200],
        [("4209", "a10121a2020100a30604201c000000")],
        id="prime_charger_250w_usb_c1_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c2_on",
        [],
        [("4207", "a10121a2020101a3020101")],
        id="prime_charger_250w_usb_c2_on",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c2_off",
        [],
        [("4207", "a10121a2020101a3020100")],
        id="prime_charger_250w_usb_c2_off",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c2",
        [300],
        [("4209", "a10121a2020101a306042c01000000")],
        id="prime_charger_250w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c2",
        [7200],
        [("4209", "a10121a2020101a30604201c000000")],
        id="prime_charger_250w_usb_c2_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c3_on",
        [],
        [("4207", "a10121a2020102a3020101")],
        id="prime_charger_250w_usb_c3_on",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c3_off",
        [],
        [("4207", "a10121a2020102a3020100")],
        id="prime_charger_250w_usb_c3_off",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c3",
        [300],
        [("4209", "a10121a2020102a306042c01000000")],
        id="prime_charger_250w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c3",
        [7200],
        [("4209", "a10121a2020102a30604201c000000")],
        id="prime_charger_250w_usb_c3_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c4_on",
        [],
        [("4207", "a10121a2020103a3020101")],
        id="prime_charger_250w_usb_c4_on",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_c4_off",
        [],
        [("4207", "a10121a2020103a3020100")],
        id="prime_charger_250w_usb_c4_off",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c4",
        [300],
        [("4209", "a10121a2020103a306042c01000000")],
        id="prime_charger_250w_usb_c4_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c4",
        [7200],
        [("4209", "a10121a2020103a30604201c000000")],
        id="prime_charger_250w_usb_c4_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_a1_a2_on",
        [],
        [("4207", "a10121a2020104a3020101")],
        id="prime_charger_250w_usb_a1_a2_on",
    ),
    pytest.param(
        PrimeCharger250w,
        "turn_usb_a1_a2_off",
        [],
        [("4207", "a10121a2020104a3020100")],
        id="prime_charger_250w_usb_a1_a2_off",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_a1_a2",
        [300],
        [("4209", "a10121a2020104a306042c01000000")],
        id="prime_charger_250w_usb_a1_a2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_a1_a2",
        [7200],
        [("4209", "a10121a2020104a30604201c000000")],
        id="prime_charger_250w_usb_a1_a2_timer_120m",
    ),
]


############################
# Test device commands E2E #
############################

# These tests end-to-end tests check that the correct bytes are sent
# by the command. See test_send_command_e2e() in test_commands.py.

PRIME_CHARGER_250W_TEST_COMMANDS_E2E = [
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c1_on",
        [],
        "ff092b0003000f420757e9b883d85da36ffa59e144a5881d8773e6bacd6c24e0484da6030bc35f27c50771",
        id="prime_charger_250w_usb_c1_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c1_off",
        [],
        "ff092b0003000f420757e9b883d85da36ffa59e044a5881d8773eea0d2dbe21151b3eae6b5fa935c38ed94",
        id="prime_charger_250w_usb_c1_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [300],
        "ff092f0003000f420957e9b883d85da36ffe5cccbba16764cc1ef1e323304e7635b22b4abb99ae19c243af2bf10a43",
        id="prime_charger_250w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [7200],
        "ff092f0003000f420957e9b883d85da36ffe5cc0a6a16764cc1ef1e32330e8c3b5b4ad83bfbceb74ce3e71421dc968",
        id="prime_charger_250w_usb_c1_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_on",
        [],
        "ff092b0003000f420757e9b883d85da26ffa59e144a5881d8773304bd4926805f6746a78f6295290e98f20",
        id="prime_charger_250w_usb_c2_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_off",
        [],
        "ff092b0003000f420757e9b883d85da26ffa59e044a5881d87733851cb25aef4ef8a269d48109eeb1465c5",
        id="prime_charger_250w_usb_c2_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [300],
        "ff092f0003000f420957e9b883d85da26ffe5cccbba16764cc1ef1e3233098872c4c67af05a062623fa9a29cdd8212",
        id="prime_charger_250w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [7200],
        "ff092f0003000f420957e9b883d85da26ffe5cc0a6a16764cc1ef1e323303e32ac4ae1660185270f33d47cf5314139",
        id="prime_charger_250w_usb_c2_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_on",
        [],
        "ff092b0003000f420757e9b883d85da16ffa59e144a5881d87738958fe90bd2b343e3ef4f01744499c1611",
        id="prime_charger_250w_usb_c3_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_off",
        [],
        "ff092b0003000f420757e9b883d85da16ffa59e044a5881d87738142e1277bda2dc072114e2e883261fcf4",
        id="prime_charger_250w_usb_c3_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [300],
        "ff092f0003000f420957e9b883d85da16ffe5cccbba16764cc1ef1e323302194064eb281c7ea36ee3997b445a81b23",
        id="prime_charger_250w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [7200],
        "ff092f0003000f420957e9b883d85da16ffe5cc0a6a16764cc1ef1e32330872186483448c3cf738335ea6a2c44d808",
        id="prime_charger_250w_usb_c3_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c4_on",
        [],
        "ff092b0003000f420757e9b883d85da06ffa59e144a5881d87735fa9e76ef1ce8a07f28f0dfd49feb09e40",
        id="prime_charger_250w_usb_c4_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c4_off",
        [],
        "ff092b0003000f420757e9b883d85da06ffa59e044a5881d877357b3f8d9373f93f9be6ab3c485854d74a5",
        id="prime_charger_250w_usb_c4_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c4",
        [300],
        "ff092f0003000f420957e9b883d85da06ffe5cccbba16764cc1ef1e32330f7651fb0fe6479d3fa95c47db9f2849372",
        id="prime_charger_250w_usb_c4_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c4",
        [7200],
        "ff092f0003000f420957e9b883d85da06ffe5cc0a6a16764cc1ef1e3233051d09fb678ad7df6bff8c800679b685059",
        id="prime_charger_250w_usb_c4_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_a1_a2_on",
        [],
        "ff092b0003000f420757e9b883d85da76ffa59e144a5881d8773397eaa951776b0aa97ecfc6b69fb7725b1",
        id="prime_charger_250w_usb_a1_a2_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_a1_a2_off",
        [],
        "ff092b0003000f420757e9b883d85da76ffa59e044a5881d87733164b522d187a954db094252a5808acf54",
        id="prime_charger_250w_usb_a1_a2_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_a1_a2",
        [300],
        "ff092f0003000f420957e9b883d85da76ffe5cccbba16764cc1ef1e3233091b2524b18dc437e9ff635eb99f7432883",
        id="prime_charger_250w_usb_a1_a2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_a1_a2",
        [7200],
        "ff092f0003000f420957e9b883d85da76ffe5cc0a6a16764cc1ef1e323303707d24d9e15475bda9b3996479eafeba8",
        id="prime_charger_250w_usb_a1_a2_timer_120m",
    ),
]
