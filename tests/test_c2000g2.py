"""Tests for the C2000 Gen 2's device summary, pushes and display plan.

.. moduleauthor:: kb1ibt
"""

import dataclasses
import logging
from functools import reduce
from typing import Any
from unittest import mock

import pytest

from SolixBLE import C2000G2
from SolixBLE.constructs import PacketCommand, Parameters
from tests.const import MOCK_BLE_DEVICE
from tests.devices.c2000g2 import (
    C421_0009,
    C490_0009,
    C490_UNKNOWN_SCHEMA,
    C2000G2_TEST_PUSHES,
    C2000G2_TEST_SUMMARIES,
)

#: Message type of the device summary post (``c490`` on the wire).
SUMMARY_MSGTYPE = 0x490

#: Main battery state of charge in C490_0009 (``.23.1``).
SUMMARY_BATTERY_PERCENTAGE = 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("telemetry", "summary", "properties", "fields"),
    C2000G2_TEST_SUMMARIES,
)
async def test_summary(
    telemetry: str,
    summary: str,
    properties: dict[str, Any],
    fields: dict[str, Any],
) -> None:
    """A device summary is decoded against the schema it names.

    :param telemetry: A telemetry payload received before the summary.
    :param summary: The summary payload.
    :param properties: Expected values of device properties.
    :param fields: Expected values of summary fields, by name or ``.path``.
    """
    device = C2000G2(MOCK_BLE_DEVICE)
    telemetry_parameters = Parameters.parse(bytes.fromhex(telemetry))
    await device._process_telemetry(telemetry_parameters)  # noqa: SLF001
    await device._process_session(  # noqa: SLF001
        SUMMARY_MSGTYPE,
        bytes.fromhex(summary),
        encrypted=False,
    )

    for name, expected in properties.items():
        assert getattr(device, name) == expected, f"Mismatch for property '{name}'!"
    for name, expected in fields.items():
        assert device.summary[name] == expected, f"Mismatch for summary field '{name}'!"
    assert device.last_summary_update is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(("cmd", "payload", "expected"), C2000G2_TEST_PUSHES)
async def test_pushes(cmd: str, payload: str, expected: dict[str, Any]) -> None:
    """Event and firmware-update readiness pushes update the device.

    :param cmd: The push's command code.
    :param payload: The push's payload.
    :param expected: Expected values, by dotted attribute path.
    """
    device = C2000G2(MOCK_BLE_DEVICE)
    callbacks: list[None] = []
    device.add_callback(lambda: callbacks.append(None))
    await device._process_session(  # noqa: SLF001
        PacketCommand.parse(bytes.fromhex(cmd)).msgtype,
        bytes.fromhex(payload),
        encrypted=False,
    )

    for path, value in expected.items():
        actual = reduce(getattr, path.split("."), device)
        assert actual == value, f"Mismatch for '{path}'!"
    assert len(callbacks) == 1, "Expected one state change callback"


@pytest.mark.asyncio
async def test_summary_reset_with_data() -> None:
    """The summary is kept across a dropped link and cleared with the data."""
    device = C2000G2(MOCK_BLE_DEVICE)
    await device._process_session(  # noqa: SLF001
        SUMMARY_MSGTYPE,
        bytes.fromhex(C490_0009),
        encrypted=False,
    )

    device._reset_session(reset_data=False)  # noqa: SLF001
    assert device.summary_schema == "charging_pps_series_c_0009"
    assert device.summary

    device._reset_session()  # noqa: SLF001
    assert device.summary_schema is None
    assert device.summary == {}
    assert device.last_summary_update is None


@pytest.mark.asyncio
async def test_unknown_summary_schema(caplog: pytest.LogCaptureFixture) -> None:
    """A schema with no field map keeps every field by path and warns once."""
    device = C2000G2(MOCK_BLE_DEVICE)
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            await device._process_session(  # noqa: SLF001
                SUMMARY_MSGTYPE,
                bytes.fromhex(C490_UNKNOWN_SCHEMA),
                encrypted=False,
            )

    assert device.summary_schema == "charging_pps_series_c_9999"
    assert device.summary[".23.1"] == SUMMARY_BATTERY_PERCENTAGE
    assert device.battery_health == -1
    assert caplog.text.count("has no field map") == 1


@pytest.mark.asyncio
async def test_set_display_plan_sends_only_changes() -> None:
    """Only the clock-screen settings that differ from the device's are sent."""
    device = C2000G2(MOCK_BLE_DEVICE)
    telemetry_parameters = Parameters.parse(bytes.fromhex(C421_0009))
    await device._process_telemetry(telemetry_parameters)  # noqa: SLF001
    current = device.display_plan
    assert current is not None

    with mock.patch.object(C2000G2, "_send_command") as send:
        await device.set_display_plan(current)
        send.assert_not_awaited()

        await device.set_display_plan(
            dataclasses.replace(current, clock_24h=False, night_brightness=5),
        )
        send.assert_awaited_once_with(
            message=0x091,
            parameters={
                "a1": {"value": "21"},
                "a7": {"type": 1, "value": 0},
                "ad": {"type": 1, "value": 0},
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"day_start": 1441},
        {"clock_theme": 0},
        {"weekdays": frozenset({7})},
        {"day_brightness": 50},
    ],
)
async def test_set_display_plan_out_of_range(change: dict[str, Any]) -> None:
    """A display plan setting out of range is refused before sending.

    :param change: The out-of-range setting.
    """
    device = C2000G2(MOCK_BLE_DEVICE)
    telemetry_parameters = Parameters.parse(bytes.fromhex(C421_0009))
    await device._process_telemetry(telemetry_parameters)  # noqa: SLF001
    current = device.display_plan
    assert current is not None

    with pytest.raises(ValueError, match="must"):
        await device.set_display_plan(dataclasses.replace(current, **change))
