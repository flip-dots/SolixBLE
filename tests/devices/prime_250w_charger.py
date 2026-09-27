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
        [("4209", "a10121a2020100a30604012c010000")],
        id="prime_charger_250w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c1",
        [7200],
        [("4209", "a10121a2020100a3060401201c0000")],
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
        [("4209", "a10121a2020101a30604012c010000")],
        id="prime_charger_250w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c2",
        [7200],
        [("4209", "a10121a2020101a3060401201c0000")],
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
        [("4209", "a10121a2020102a30604012c010000")],
        id="prime_charger_250w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c3",
        [7200],
        [("4209", "a10121a2020102a3060401201c0000")],
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
        [("4209", "a10121a2020103a30604012c010000")],
        id="prime_charger_250w_usb_c4_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_c4",
        [7200],
        [("4209", "a10121a2020103a3060401201c0000")],
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
        [("4209", "a10121a2020104a30604012c010000")],
        id="prime_charger_250w_usb_a1_a2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        "set_timer_usb_a1_a2",
        [7200],
        [("4209", "a10121a2020104a3060401201c0000")],
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
        "ff092f0003000f420957e9b883d85da36ffe5ce196a06764cc1ef1e323303446e2ec2e576dda0f8a17ff2937517a1d",
        id="prime_charger_250w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [7200],
        "ff092f0003000f420957e9b883d85da36ffe5ce19abd6764cc1ef1e32330a726576c28d1a4de2acf7af354e93896a0",
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
        "ff092f0003000f420957e9b883d85da26ffe5ce196a06764cc1ef1e32330e2b7fb1262b2d3e3c3f1ea1524807df24c",
        id="prime_charger_250w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [7200],
        "ff092f0003000f420957e9b883d85da26ffe5ce19abd6764cc1ef1e3233071d74e9264341ae7e6b48719595e141ef1",
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
        "ff092f0003000f420957e9b883d85da16ffe5ce196a06764cc1ef1e323305ba4d110b79c11a9977dec2b3259086b7d",
        id="prime_charger_250w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [7200],
        "ff092f0003000f420957e9b883d85da16ffe5ce19abd6764cc1ef1e32330c8c46490b11ad8adb23881274f876187c0",
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
        "ff092f0003000f420957e9b883d85da06ffe5ce196a06764cc1ef1e323308d55c8eefb79af905b0611c13fee24e32c",
        id="prime_charger_250w_usb_c4_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c4",
        [7200],
        "ff092f0003000f420957e9b883d85da06ffe5ce19abd6764cc1ef1e323301e357d6efdff66947e437ccd42304d0f91",
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
        "ff092f0003000f420957e9b883d85da76ffe5ce196a06764cc1ef1e32330eb8285151dc1953d3e65e0571febe358dd",
        id="prime_charger_250w_usb_a1_a2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_a1_a2",
        [7200],
        "ff092f0003000f420957e9b883d85da76ffe5ce19abd6764cc1ef1e3233078e230951b475c391b208d5b62358ab460",
        id="prime_charger_250w_usb_a1_a2_timer_120m",
    ),
]
