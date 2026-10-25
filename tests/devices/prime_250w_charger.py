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
        "ff092c0003000f420757e9b883d85da36ffa59e144a4648b4baf77d091fccaab65ccb786442cff739b3639b5",
        id="prime_charger_250w_usb_c1_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c1_off",
        [],
        "ff092c0003000f420757e9b883d85da36ffa59e044a4648b4baf77d88be37d6d94d549caa192c6bfe0cbd350",
        id="prime_charger_250w_usb_c1_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [300],
        "ff09300003000f420957e9b883d85da36ffe5cccbba16764cc1f1d75efec6ad099ab238f47df869517e1239ccabd8a99",
        id="prime_charger_250w_usb_c1_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c1",
        [7200],
        "ff09300003000f420957e9b883d85da36ffe5cc0a6a16764cc1f1d75efec6a762c2b25098edba3d07aed5e42a35149b2",
        id="prime_charger_250w_usb_c1_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_on",
        [],
        "ff092c0003000f420757e9b883d85da26ffa59e144a4648b4baf770660e534e780728e4a3fd1157e2c1ab1e4",
        id="prime_charger_250w_usb_c2_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c2_off",
        [],
        "ff092c0003000f420757e9b883d85da26ffa59e044a4648b4baf770e7afa8321716b7006da6f2cb257e75b01",
        id="prime_charger_250w_usb_c2_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [300],
        "ff09300003000f420957e9b883d85da26ffe5cccbba16764cc1f1d75efec6a0668b2ddc3a261bf596c1cc9917d9102c8",
        id="prime_charger_250w_usb_c2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c2",
        [7200],
        "ff09300003000f420957e9b883d85da26ffe5cc0a6a16764cc1f1d75efec6aa0dd32db456b659a1c0110b44f147dc1e3",
        id="prime_charger_250w_usb_c2_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_on",
        [],
        "ff092c0003000f420757e9b883d85da16ffa59e144a4648b4baf77bf73cf3632aeb0c41eb3d72b68f56f28d5",
        id="prime_charger_250w_usb_c3_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c3_off",
        [],
        "ff092c0003000f420757e9b883d85da16ffa59e044a4648b4baf77b769d081f45fa93a52566912a48e92c230",
        id="prime_charger_250w_usb_c3_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [300],
        "ff09300003000f420957e9b883d85da16ffe5cccbba16764cc1f1d75efec6abf7b98df168ca3f50de01af787a4e49bf9",
        id="prime_charger_250w_usb_c3_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c3",
        [7200],
        "ff09300003000f420957e9b883d85da16ffe5cc0a6a16764cc1f1d75efec6a19ce18d99045a7d0488d168a59cd0858d2",
        id="prime_charger_250w_usb_c3_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c4_on",
        [],
        "ff092c0003000f420757e9b883d85da06ffa59e144a4648b4baf776982d6c87e4b0efdd2c82ac1654243a084",
        id="prime_charger_250w_usb_c4_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_c4_off",
        [],
        "ff092c0003000f420757e9b883d85da06ffa59e044a4648b4baf776198c97fb8ba17039e2d94f8a939be4a61",
        id="prime_charger_250w_usb_c4_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c4",
        [300],
        "ff09300003000f420957e9b883d85da06ffe5cccbba16764cc1f1d75efec6a698a81215a691dccc19be71d8a13c813a8",
        id="prime_charger_250w_usb_c4_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_c4",
        [7200],
        "ff09300003000f420957e9b883d85da06ffe5cc0a6a16764cc1f1d75efec6acf3f0127dca019e984f6eb60547a24d083",
        id="prime_charger_250w_usb_c4_timer_120m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_a1_a2_on",
        [],
        "ff092c0003000f420757e9b883d85da76ffa59e144a4648b4baf770f559b3398f33450b7abdb574547841b75",
        id="prime_charger_250w_usb_a1_a2_on",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "turn_usb_a1_a2_off",
        [],
        "ff092c0003000f420757e9b883d85da76ffa59e044a4648b4baf77074f84845e022daefb4e656e893c79f190",
        id="prime_charger_250w_usb_a1_a2_off",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_a1_a2",
        [300],
        "ff09300003000f420957e9b883d85da76ffe5cccbba16764cc1f1d75efec6a0f5dccdabcd12761a4f8168baa160fa859",
        id="prime_charger_250w_usb_a1_a2_timer_5m",
    ),
    pytest.param(
        PrimeCharger250w,
        NEGOTIATION_RESPONSES_PRIME,
        "set_timer_usb_a1_a2",
        [7200],
        "ff09300003000f420957e9b883d85da76ffe5cc0a6a16764cc1f1d75efec6aa9e84cdc3a182344e1951af6747fe36b72",
        id="prime_charger_250w_usb_a1_a2_timer_120m",
    ),
]
