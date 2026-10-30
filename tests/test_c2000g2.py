"""Tests for the C2000 Gen 2's device summary, pushes and display plan.

.. moduleauthor:: kb1ibt
"""

import dataclasses
import logging
from collections.abc import Callable
from functools import reduce
from typing import Any
from unittest import mock

import pytest

from SolixBLE import C2000G2
from SolixBLE.constructs import Packet, PacketCommand, Parameters
from SolixBLE.protocols import EncryptedOuter
from SolixBLE.states import ClockTheme
from tests.const import MOCK_BLE_DEVICE
from tests.devices.c2000g2 import (
    C421_0009,
    C490_0009,
    C490_UNKNOWN_SCHEMA,
    C2000G2_TEST_PUSHES,
    C2000G2_TEST_SUMMARIES,
    C2000G2_TOU_READBACKS,
    D9_0009,
)
from tests.helpers import MockDevice

#: Message type of the device summary post (``c490`` on the wire).
SUMMARY_MSGTYPE = 0x490

#: Main battery state of charge in C490_0009 (``.23.1``).
SUMMARY_BATTERY_PERCENTAGE = 100

#: The C2000 Gen 2's own negotiation, recorded on the encrypted outer (module
#: 0.3.3.0) with its serial and MAC replaced: the reply to each request from
#: 4001 to the 4027 registration, then the key exchange's device point and the
#: ECDH secret logged with it.
NEGOTIATION_RESPONSES_A1783 = [
    "ff091e000300014801ab273ed3e27270c3f4d676ac7d69a00572793732a6",
    (
        "ff092b000300014803ab273ed04438d4b25db54c6d4a6ec3d481f5ad58ff7cc2be8bc8369fd98c"
        "0b914e03"
    ),
    (
        "ff0949000300014829ab273ed1443f6ce1ae873a6a4c5f48e5ad49ade39ef581d2b5abab1d7161"
        "cb0ee0aafc774ea6829abfc604d706632412065b22e34f27b7923aeceecd3c725291"
    ),
    "ff091b000300014805abab709a595a803dd04246b78a927453cf65",
    (
        "ff095d000300014821ab277fb15876701f2830b319835b30ef56a3f3c78b2a150a6b837693e8e1"
        "ada0a97393bf8262d546149778aab8e4d85a3b25ee0162279c6edb5786c00a5b5b3edf58d7c8db"
        "472c25e6265afd8a9fdfed3af6380b"
    ),
    "ff091b0003000148220f3864288b6b78f53a95612674e40153338a",
    "ff091b0003000148270f3864288b6b78f53a95612674e40153338f",
]
DEVICE_POINT_A1783 = bytes.fromhex(
    "63be4c59add684bbd0c834563ad5da7017b1ced5889d6c96c5dcb0569e79e95ff8fcf46679adfb"
    "6ea3133913066874c0506ab3d3f07005119ce736d777d32bb9",
)
SHARED_SECRET_A1783 = bytes.fromhex(
    "f5b21f3aaf26382b8525ec1f83d4b4faaccde0d771382c2bc02bd12c184da4a1",
)

#: The same session's c900 reply to the 4100 subscribe, in two fragments, with
#: the station's and the expansion battery's serials replaced.
SUBSCRIBE_REPLY_A1783 = [
    (
        "ff09fd0003010fc900120fd9cce192ae70016a30e542cdbcdac0a4f68aba498ce2a4589b3612cb"
        "f6ae7bfc9fdc08dcec77703c1bfcc687bc6ca74a16eee9832b12bd69626de9a80b04c6c1d706c6"
        "202867b91da544b3c4f941759158388b04b5d57f3b329a41605b44d04fd919d973927f2ccab1da"
        "26413b719fe024322929902b090dd789872d0c5ebbf9df4071d12b70986517e76ec115ea29f2a3"
        "cf38bbbfffe2e532fbcda3441f99f4ecda12d75d712a23e487d6e78e90a63e08b495d69ebb36d6"
        "4ed541f09e4c9d4d405da1fedba504672a4ec6cae74127d4ced566fbff89a5667964db0028b52b"
        "e375ad41610c36d209c35b1232eedefc7c25f1"
    ),
    (
        "ff09ac0003010fc900224f4704425c358368a2f08a7a3ef5f6f42dc8ce0d06dcae8926a7aa5bdc"
        "d41d8bf083f0d9d39d6cb0b469edc1f6514edc7b8f9a4802b2cead351df30267ac055bf7134319"
        "96fdbf212be11f2a7dc4105e1a49d1de3fde4f694052c30aa5d6f26aea478b39436477e9a95f2f"
        "97dc0d14c4e3598e4ec114c6d3141fb6b7e1842062bf56dc3aab8147bc2a4663e94e1a746b908b"
        "160b313782c0da8f4c5a457c6ded0cca"
    ),
]

#: The serials the recording carries in place of the station's and its pack's.
RECORDED_SERIAL = "APCDKKE0000000001"
RECORDED_EXPANSION_SERIAL = "APCDKJM0000000002"


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
@pytest.mark.parametrize(("d9", "expected"), C2000G2_TOU_READBACKS)
async def test_tou_readback(d9: str, expected: dict[str, Any]) -> None:
    """The time-of-use block the device stored after a write reads back.

    :param d9: The time-of-use block, as the device sent it.
    :param expected: Expected values of device properties.
    """
    device = C2000G2(MOCK_BLE_DEVICE)
    frame = C421_0009.replace(D9_0009, d9)
    await device._process_telemetry(Parameters.parse(bytes.fromhex(frame)))  # noqa: SLF001

    for name, value in expected.items():
        assert getattr(device, name) == value, f"Mismatch for property '{name}'!"


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
            0x091,
            {
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
        {"clock_theme": ClockTheme.CUSTOM},
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


@pytest.mark.asyncio
async def test_connects_with_its_recorded_negotiation(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
    pin_shared_secret: Callable[[bytes, bytes], None],
) -> None:
    """Its recorded negotiation runs on the encrypted outer, then 4100 and 4057."""
    pin_shared_secret(DEVICE_POINT_A1783, SHARED_SECRET_A1783)
    device = C2000G2(MOCK_BLE_DEVICE)
    assert device._outer_class is EncryptedOuter  # noqa: SLF001

    async with MockDevice() as mock_bluetooth:
        for response in NEGOTIATION_RESPONSES_A1783:
            mock_bluetooth.expect_ordered(None, [bytes.fromhex(response)])
        mock_bluetooth.expect_ordered(
            None,
            [bytes.fromhex(fragment) for fragment in SUBSCRIBE_REPLY_A1783],
        )
        mock_bluetooth.expect_ordered(None)
        assert await device.connect()
        mock_bluetooth.check_assertions()

    sent = [Packet.parse(write) for write in mock_bluetooth.writes]
    assert [PacketCommand.build(packet).hex() for packet in sent[-2:]] == [
        "4100",
        "4057",
    ]
    assert device.serial_number == RECORDED_SERIAL
    assert device.serial_number_expansion == RECORDED_EXPANSION_SERIAL
    assert set(mock_bluetooth.write_responses) == {False}
