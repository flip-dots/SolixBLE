"""Tests for the C1000 Gen 2's Structs, clock theme and time-of-use plan.

.. moduleauthor:: kb1ibt
"""

import dataclasses
from typing import Any
from unittest import mock

import pytest

from SolixBLE.constructs import PPS_M6_TOU, Packet, PacketCommand, Parameters
from SolixBLE.devices.c1000g2 import (
    A3_STATUS,
    A4_SETTINGS,
    A6_POWER,
    A7_AC,
    C1000G2,
    DA_DISPLAY_PLAN,
    F9_VERSIONS,
    NO_ESTIMATE,
    PORT_STATUS_POWER,
)
from SolixBLE.states import ClockTheme, TouPeriod
from tests.const import MOCK_BLE_DEVICE
from tests.devices.c1000g2 import (
    B2_A1763_DC_ON,
    C900_A1763_IDLE,
    C1000G2_TOU_PLANS,
    C1000G2_TOU_PLANS_OUT_OF_RANGE,
)
from tests.helpers import install_session_keys

#: Session keys for a negotiated device, so commands carry the encrypted flag.
SESSION_SECRET = bytes(range(32))

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
    tou = PPS_M6_TOU.parse(params["d9"].value)

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("theme_byte", "theme"),
    [
        pytest.param("82", ClockTheme.THEME_3, id="theme_3"),
        pytest.param("83", ClockTheme.CATALOG, id="catalog"),
        pytest.param("85", ClockTheme.THEME_1, id="past_catalog_shows_theme_1"),
        pytest.param("f1", ClockTheme.THEME_2, id="unread_bits_ignored"),
    ],
)
async def test_display_plan_clock_theme(theme_byte: str, theme: ClockTheme) -> None:
    """The clock theme is the low nibble; indexes past CATALOG show Theme 1.

    :param theme_byte: The clock screen's first byte.
    :param theme: The theme it reads as.
    """
    device = C1000G2(MOCK_BLE_DEVICE)
    frame = C900_A1763_IDLE.replace("da180400", f"da1804{theme_byte}")
    await device._process_telemetry(Parameters.parse(bytes.fromhex(frame)))  # noqa: SLF001

    plan = device.display_plan
    assert plan is not None
    assert plan.clock_theme is theme


@pytest.mark.asyncio
async def test_set_display_plan_keeps_a_catalog_theme() -> None:
    """A catalog theme can stay while other settings change, but not be chosen."""
    device = C1000G2(MOCK_BLE_DEVICE)
    frame = C900_A1763_IDLE.replace("da180400", "da180483")
    await device._process_telemetry(Parameters.parse(bytes.fromhex(frame)))  # noqa: SLF001
    current = device.display_plan
    assert current is not None

    with mock.patch.object(C1000G2, "_send_command") as send:
        await device.set_display_plan(dataclasses.replace(current, clock_24h=False))
        send.assert_awaited_once_with(
            0x091,
            {"a1": {"value": "21"}, "a7": {"type": 1, "value": 0}},
        )

    device = C1000G2(MOCK_BLE_DEVICE)
    await device._process_telemetry(  # noqa: SLF001
        Parameters.parse(bytes.fromhex(C900_A1763_IDLE)),
    )
    current = device.display_plan
    assert current is not None
    with pytest.raises(ValueError, match="THEME_1, THEME_2 or THEME_3"):
        await device.set_display_plan(
            dataclasses.replace(current, clock_theme=ClockTheme.CATALOG),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("periods", "options", "payload"), C1000G2_TOU_PLANS)
async def test_set_tou_plan(
    fake_time: None,  # noqa: ARG001
    periods: list[TouPeriod],
    options: dict[str, Any],
    payload: str,
) -> None:
    """The plan is written to the device as 4090 with its periods in a7.

    :param periods: The plan's periods.
    :param options: The mode and reserve.
    :param payload: The payload expected before the timestamp.
    """
    device = C1000G2(MOCK_BLE_DEVICE)
    device._client = mock.AsyncMock()  # noqa: SLF001
    install_session_keys(device, SESSION_SECRET)
    with (
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
        mock.patch.object(C1000G2, "_encrypt_payload", lambda _, payload: payload),
    ):
        await device.set_tou_plan(periods, **options)

    (_, written), _ = device._client.write_gatt_char.call_args  # noqa: SLF001
    packet = Packet.parse(written)
    timestamp = device._timestamp().hex()  # noqa: SLF001
    assert PacketCommand.build(packet).hex() == "4090"
    assert packet.payload_bytes.hex() == f"{payload}fe0503{timestamp}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("periods", "options"), C1000G2_TOU_PLANS_OUT_OF_RANGE)
async def test_set_tou_plan_out_of_range(
    periods: list[TouPeriod],
    options: dict[str, Any],
) -> None:
    """A plan the device can't take is refused before sending.

    :param periods: The plan's periods.
    :param options: The reserve, when it is the setting out of range.
    """
    device = C1000G2(MOCK_BLE_DEVICE)
    with mock.patch.object(C1000G2, "_send_command") as send:
        with pytest.raises(ValueError, match=r"must|at most"):
            await device.set_tou_plan(periods, enabled=True, **options)
        send.assert_not_awaited()


def test_f9_versions_with_parts_not_fitted() -> None:
    """The controller slot matches a2's firmware; unfitted parts read 0.0.0.0."""
    params = Parameters.parse(bytes.fromhex(C900_A1763_IDLE))
    versions = F9_VERSIONS.parse(params["f9"].value)

    assert versions.controller == "1.1.2.6"
    assert versions.mppt == NOT_FITTED
    assert versions.expansion_bms == NOT_FITTED
