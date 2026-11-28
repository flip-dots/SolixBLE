"""C200 DC power station device tests.

.. moduleauthor:: Eric Schoeller

"""
import pytest

from SolixBLE.devices.c200dc import C200DC
from SolixBLE.states import DisplayTimeout, LightStatus
from tests.const import NEGOTIATION_RESPONSES_SOLIX

########################
# Test device commands #
########################

C200DC_TEST_COMMANDS = [
    pytest.param(
        C200DC,
        "turn_display_on",
        [],
        [("4052", "a10121a2020101")],
        id="c200dc_display_on",
    ),
    pytest.param(
        C200DC,
        "turn_display_off",
        [],
        [("4052", "a10121a2020100")],
        id="c200dc_display_off",
    ),
    pytest.param(
        C200DC,
        "set_display_timeout",
        [DisplayTimeout.S20],
        [("4046", "a10121a203021400")],
        id="c200dc_display_timeout_20s",
    ),
    pytest.param(
        C200DC,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        [("4046", "a10121a203020807")],
        id="c200dc_display_timeout_30m",
    ),
    pytest.param(
        C200DC,
        "set_display_mode",
        [LightStatus.LOW],
        [("404c", "a10121a2020101")],
        id="c200dc_display_low",
    ),
    pytest.param(
        C200DC,
        "set_display_mode",
        [LightStatus.MEDIUM],
        [("404c", "a10121a2020102")],
        id="c200dc_display_med",
    ),
    pytest.param(
        C200DC,
        "set_display_mode",
        [LightStatus.HIGH],
        [("404c", "a10121a2020103")],
        id="c200dc_display_high",
    ),
    pytest.param(
        C200DC,
        "set_display_mode",
        [LightStatus.SOS],
        ValueError,
        id="c200dc_display_sos",
    ),
    pytest.param(
        C200DC,
        "set_display_mode",
        [LightStatus.UNKNOWN],
        ValueError,
        id="c200dc_display_unknown",
    ),
]


############################
# Test device commands E2E #
############################

C200DC_TEST_COMMANDS_E2E = [
    pytest.param(
        C200DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_on",
        [],
        "ff091a0003000f4052cf1b676bb8c648a6f066b90d0c20250293",
        id="c200dc_display_on",
    ),
    pytest.param(
        C200DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "turn_display_off",
        [],
        "ff091a0003000f4052a665f0bcc4f9a3a154d50bb71d7c300e20",
        id="c200dc_display_off",
    ),
    pytest.param(
        C200DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_timeout",
        [DisplayTimeout.S20],
        "ff091a0003000f4046def18b6e3fa7434937ef01fecb95dfd3cb",
        id="c200dc_display_timeout_20s",
    ),
    pytest.param(
        C200DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_timeout",
        [DisplayTimeout.S1800],
        "ff091a0003000f404665b9a755e0b46d3947a6937b5f7be4d2d3",
        id="c200dc_display_timeout_30m",
    ),
    pytest.param(
        C200DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.LOW],
        "ff091a0003000f404ccf1b676bb8c648a6f066b90d0c2025028d",
        id="c200dc_display_low",
    ),
    pytest.param(
        C200DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.MEDIUM],
        "ff091a0003000f404c78e6e204ae7a3858b1aac611fd4bdec145",
        id="c200dc_display_med",
    ),
    pytest.param(
        C200DC,
        NEGOTIATION_RESPONSES_SOLIX,
        "set_display_mode",
        [LightStatus.HIGH],
        "ff091a0003000f404c3fa145b4757507f18b3503e0cc3bcae3f6",
        id="c200dc_display_high",
    ),
]
