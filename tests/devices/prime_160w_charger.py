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
        "ff092c0003000f420757e9b883d85da36ffa59e144a4648b4baf77d091fccaab65ccb786442cff739b3639b5",
        id="prime_charger_160w_usb_c1_on",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c1_off",
        [],
        "ff092c0003000f420757e9b883d85da36ffa59e044a4648b4baf77d88be37d6d94d549caa192c6bfe0cbd350",
        id="prime_charger_160w_usb_c1_off",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [300],
        "ff092f0003000f420957e9b883d85da36ffd5cccbba1679a3719f1e323308fb5b083f7f8944549eedb7d7cd9347dcd",
        id="prime_charger_160w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [7200],
        "ff092f0003000f420957e9b883d85da36ffd5cc0a6a1679a3719f1e3233029003085713190600c83d700a2b0d8bee6",
        id="prime_charger_160w_usb_c1_timer_120m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_on",
        [],
        "ff092c0003000f420757e9b883d85da26ffa59e144a4648b4baf770660e534e780728e4a3fd1157e2c1ab1e4",
        id="prime_charger_160w_usb_c2_on",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_off",
        [],
        "ff092c0003000f420757e9b883d85da26ffa59e044a4648b4baf770e7afa8321716b7006da6f2cb257e75b01",
        id="prime_charger_160w_usb_c2_off",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [300],
        "ff092f0003000f420957e9b883d85da26ffd5cccbba1679a3719f1e323305944a97dbb1d2a7c85952697716e18f59c",
        id="prime_charger_160w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [7200],
        "ff092f0003000f420957e9b883d85da26ffd5cc0a6a1679a3719f1e32330fff1297b3dd42e59c0f82aeaaf07f436b7",
        id="prime_charger_160w_usb_c2_timer_120m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_on",
        [],
        "ff092c0003000f420757e9b883d85da16ffa59e144a4648b4baf77bf73cf3632aeb0c41eb3d72b68f56f28d5",
        id="prime_charger_160w_usb_c3_on",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_off",
        [],
        "ff092c0003000f420757e9b883d85da16ffa59e044a4648b4baf77b769d081f45fa93a52566912a48e92c230",
        id="prime_charger_160w_usb_c3_off",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [300],
        "ff092f0003000f420957e9b883d85da16ffd5cccbba1679a3719f1e32330e057837f6e33e836d11920a967b76d6cad",
        id="prime_charger_160w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger160w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [7200],
        "ff092f0003000f420957e9b883d85da16ffd5cc0a6a1679a3719f1e3233046e20379e8faec1394742cd4b9de81af86",
        id="prime_charger_160w_usb_c3_timer_120m",
    ),
]
