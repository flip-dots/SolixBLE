"""Tests for the Gen 2 telemetry Structs on a real C1000 Gen 2 frame.

.. moduleauthor:: kb1ibt
"""

from SolixBLE.constructs import Parameters
from SolixBLE.devices.c1000g2 import (
    A3_STATUS,
    A4_SETTINGS,
    A6_POWER,
    A7_AC,
    D9_TOU,
    DA_DISPLAY_PLAN,
    F9_VERSIONS,
    NO_ESTIMATE,
    PORT_STATUS_POWER,
)
from tests.devices.c1000g2 import B2_A1763_DC_ON, C900_A1763_IDLE

#: The unit's charge-input limit (W) and its 30 s display timeout.
MAX_INPUT_POWER = 1200
DISPLAY_TIMEOUT = 30

#: The DC output's load (W) in the DC-on frame.
DC_ON_POWER = 6

#: The clock's day period, in minutes from midnight (08:00-23:00).
DAY_START = 480
DAY_END = 1380

#: The firmware version a slot reads when the part isn't fitted.
NOT_FITTED = "0.0.0.0"  # noqa: S104


def test_a3_status_without_the_trailing_fields() -> None:
    """Firmware that predates a3's last two fields reads them as None."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    status = A3_STATUS.parse(params["a3"].value)

    assert status.max_input_power == MAX_INPUT_POWER
    assert status.silent_recharge_power is None
    assert status.weak_light_lock_flag is None


def test_a4_settings_without_the_flag_tail() -> None:
    """The 26-byte settings block, before v1.2.1.6, has no flag byte."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    settings = A4_SETTINGS.parse(params["a4"].value)

    assert settings.ac_charging_power == MAX_INPUT_POWER
    assert settings.display_timeout == DISPLAY_TIMEOUT
    assert settings.flags is None


def test_a6_power_with_no_estimate() -> None:
    """An idle unit reports the no-estimate time remaining."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    power = A6_POWER.parse(params["a6"].value)

    assert power.power_out == 0
    assert power.time_remaining == NO_ESTIMATE


def test_a7_ac_mains_in_with_the_output_off() -> None:
    """The AC output's switch and the mains lead's presence are separate."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    ac = A7_AC.parse(params["a7"].value)

    assert ac.output.status == 0
    assert ac.input_status == 1
    assert ac.input_power == 0


def test_port_status_power_dc_output_off_and_on() -> None:
    """The port record reads the DC output both off and on with a load."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    off = PORT_STATUS_POWER.parse(params["b2"].value)
    on = PORT_STATUS_POWER.parse(bytes.fromhex(B2_A1763_DC_ON))

    assert (off.status, off.power) == (0, 0)
    assert (on.status, on.power) == (1, DC_ON_POWER)


def test_d9_tou_with_no_periods() -> None:
    """A plan with no periods still carries the backup-plan tail."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    tou = D9_TOU.parse(params["d9"].value)

    assert tou.period_count == 0
    assert tou.periods == []
    assert tou.backup.storm_guard_enabled is True
    assert tou.backup.fast_charging_plan_enabled is False
    assert tou.backup.backup_window_start == 0


def test_da_display_plan_with_the_night_period_off() -> None:
    """The clock screen reads a day period every day and no night period."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    plan = DA_DISPLAY_PLAN.parse(params["da"].value)

    assert plan.clock_24h is True
    assert (plan.day_start, plan.day_end) == (DAY_START, DAY_END)
    assert plan.weekdays == frozenset(range(7))
    assert plan.night_enabled is False


def test_f9_versions_with_parts_not_fitted() -> None:
    """The controller slot matches a2's firmware; unfitted parts read 0.0.0.0."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    versions = F9_VERSIONS.parse(params["f9"].value)

    assert versions.controller == "1.1.2.6"
    assert versions.mppt == NOT_FITTED
    assert versions.expansion_bms == NOT_FITTED
