"""Tests for choosing the outer protocol and correcting it when refused.

.. moduleauthor:: kb1ibt
"""

import pytest

from SolixBLE import C300, C1000G2, PrimeCharger160w, SolixBLEDevice
from SolixBLE.advertisement import ANKER_COMPANY_ID
from SolixBLE.constructs import Packet
from SolixBLE.protocols import EncryptedOuter, Outer, PlainOuter
from tests.const import (
    MOCK_BLE_DEVICE,
    NEGOTIATION_COMMAND_0,
    NEGOTIATION_COMMAND_1,
    NEGOTIATION_RESPONSES_PRIME,
    NEGOTIATION_RESPONSES_SOLIX,
)
from tests.helpers import MockDevice, make_advertisement


@pytest.mark.asyncio
async def test_refused_plain_reopens_encrypted(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A model that defaults to plain reopens with the encrypted outer when refused."""

    class PlainFirst(PrimeCharger160w):
        _OUTER_HINT = PlainOuter

    device = PlainFirst(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.refuse_after()
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )

        assert await device.connect()
        mock_bluetooth.check_assertions()

    assert Packet.parse(mock_bluetooth.writes[0]).cmd.hex() == "0001"
    assert device._outer_class is EncryptedOuter  # noqa: SLF001
    assert type(device) is PlainFirst


@pytest.mark.asyncio
async def test_refusal_during_the_write_reopens_encrypted(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A drop that fails the ``0001`` write itself is a refusal too."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    device._outer_class = PlainOuter  # noqa: SLF001
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.refuse_after(during_write=True)
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )

        assert await device.connect()
        mock_bluetooth.check_assertions()

    assert Packet.parse(mock_bluetooth.writes[0]).cmd.hex() == "0001"
    assert device._outer_class.name == EncryptedOuter.name  # noqa: SLF001


@pytest.mark.asyncio
async def test_remembered_plain_corrected_by_refusal(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """An instance that last authorized plain follows a firmware that now refuses it."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    device._outer_class = PlainOuter  # noqa: SLF001
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.refuse_after()
        for expected, responses in NEGOTIATION_RESPONSES_PRIME.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(response) for response in responses],
            )

        assert await device.connect()
        mock_bluetooth.check_assertions()

    assert device._outer_class.name == EncryptedOuter.name  # noqa: SLF001


@pytest.mark.asyncio
async def test_refusal_then_second_drop_returns_false(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """The outer changes once per connect; a refused reopen fails the connect."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    device._outer_class = PlainOuter  # noqa: SLF001
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.refuse_after()
        mock_bluetooth.refuse_after()

        assert not await device.connect()
        mock_bluetooth.check_assertions()

    assert [Packet.parse(write).cmd.hex() for write in mock_bluetooth.writes] == [
        "0001",
        "4001",
    ]


@pytest.mark.asyncio
async def test_drop_after_reply_is_not_a_refusal(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A device that answered before dropping did not refuse the outer."""
    device = C300(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        mock_bluetooth.expect_ordered(
            bytes.fromhex(NEGOTIATION_COMMAND_0),
            [
                bytes.fromhex(r)
                for r in NEGOTIATION_RESPONSES_SOLIX[NEGOTIATION_COMMAND_0]
            ],
        )
        mock_bluetooth.refuse_after(bytes.fromhex(NEGOTIATION_COMMAND_1))

        assert not await device.connect()
        mock_bluetooth.check_assertions()

    assert len(mock_bluetooth.writes) == len(("0001", "0003"))
    assert device._outer_class is PlainOuter  # noqa: SLF001


@pytest.mark.parametrize(
    ("device_class", "record", "expected"),
    [
        pytest.param(C300, None, PlainOuter, id="solix_default"),
        pytest.param(PrimeCharger160w, None, EncryptedOuter, id="prime_default"),
        pytest.param(
            C1000G2,
            "02007f1d23a37000b118444b393604",
            EncryptedOuter,
            id="capability_04_encrypted",
        ),
        pytest.param(
            PrimeCharger160w,
            "01aa12deadb1b200b4014a544200",
            PlainOuter,
            id="capability_00_plain",
        ),
        pytest.param(
            C300,
            "01aabbccddeeff02b106373434",
            PlainOuter,
            id="no_capability_byte_uses_default",
        ),
    ],
)
def test_initial_outer(
    device_class: type[SolixBLEDevice],
    record: str | None,
    expected: type[Outer],
) -> None:
    """The advertised capability byte picks the outer, else the model's default."""
    advertisement = (
        make_advertisement(manufacturer_data={ANKER_COMPANY_ID: bytes.fromhex(record)})
        if record is not None
        else None
    )
    device = device_class(MOCK_BLE_DEVICE, advertisement=advertisement)
    assert device._outer_class is expected  # noqa: SLF001


@pytest.mark.asyncio
async def test_restart_policy_is_one_method(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """The opening re-send and the negotiation deadline come from two methods."""

    class NeverRestart(C300):
        def _negotiation_should_restart(self) -> bool:
            return False

        def _negotiation_deadline(self) -> float:
            return 1

    device = NeverRestart(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        assert not await device.connect()

    assert mock_bluetooth.writes == []
