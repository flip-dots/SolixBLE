"""Tests for client-token pairing with physical button confirmation.

.. moduleauthor:: kb1ibt
"""

import asyncio

import pytest

from SolixBLE import PrimeCharger160w
from tests.const import MOCK_BLE_DEVICE, NEGOTIATION_RESPONSES_PRIME
from tests.helpers import MockDevice, install_session_keys, negotiation_steps_through

#: Substitute reply to 4027: status 09, a1 = a 30-second confirmation window.
#: Derived from the NEGOTIATION_RESPONSES_PRIME session (the pinned test key
#: and the recorded device public point), the same way as that fixture's own
#: post-stage-5 vectors.
CONFIRM_4827_FRAME = "ff091f000300014827ff499b3fdac997f2cceca2fad16986d660c6849a0cc4"

#: The unsolicited grant the device pushes on 030101 once its button is
#: pressed, authorizing the same client: status 00, no parameters. Derived
#: from the same session, immediately after the confirm frame above.
GRANT_4827_FRAME = "ff091b000301014827f60b45600839b2c171b33dc5790ed64ae329"

#: 4001, 4003, 4029, 4005, 4021, 4022, 4027 - nothing resent while waiting.
WRITES_THROUGH_4027 = 7


@pytest.mark.asyncio
async def test_pairing_callback_runs_once_then_grant_authorizes(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A button-press confirmation runs the pairing callback once, then authorizes."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    confirmation_requested = asyncio.Event()
    calls: list[bool] = []

    def on_pairing_required() -> None:
        calls.append(device.pairing_required)
        confirmation_requested.set()

    device.add_pairing_callback(on_pairing_required)

    async with MockDevice() as mock_bluetooth:
        for sent, responses in negotiation_steps_through(
            NEGOTIATION_RESPONSES_PRIME,
            stop_after_cmd="4022",
        ):
            mock_bluetooth.expect_ordered(sent, responses)
        mock_bluetooth.expect_ordered(response=[bytes.fromhex(CONFIRM_4827_FRAME)])

        async def push_grant_after_callback() -> None:
            await confirmation_requested.wait()
            await mock_bluetooth.send_data([bytes.fromhex(GRANT_4827_FRAME)])

        pusher = asyncio.create_task(push_grant_after_callback())
        assert await device.connect()
        await pusher

        mock_bluetooth.check_assertions()

    assert calls == [True]
    assert len(mock_bluetooth.writes) == WRITES_THROUGH_4027


@pytest.mark.asyncio
async def test_pairing_window_expiry_fails_the_connect(
    fake_time: None,  # noqa: ARG001
    fast_sleep: None,  # noqa: ARG001
    fast_timeouts: None,  # noqa: ARG001
) -> None:
    """A button never pressed fails the connect once the window and grace pass."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    async with MockDevice() as mock_bluetooth:
        for sent, responses in negotiation_steps_through(
            NEGOTIATION_RESPONSES_PRIME,
            stop_after_cmd="4022",
        ):
            mock_bluetooth.expect_ordered(sent, responses)
        mock_bluetooth.expect_ordered(response=[bytes.fromhex(CONFIRM_4827_FRAME)])

        assert not await device.connect()
        mock_bluetooth.check_assertions()

    # Nothing resent while waiting out the window either
    assert len(mock_bluetooth.writes) == WRITES_THROUGH_4027


def test_restart_refused_while_pairing_required() -> None:
    """The opener is never resent while the device waits for its button."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    install_session_keys(device, b"")

    assert not device.pairing_required
    assert device._negotiation_should_restart()  # noqa: SLF001

    assert device.announcement is not None
    device.announcement.confirmation_window = 30

    assert device.pairing_required
    assert not device._negotiation_should_restart()  # noqa: SLF001


def test_client_token_defaults_to_class_identifier() -> None:
    """Without a token the class identifier is used, shared by every client."""
    device = PrimeCharger160w(MOCK_BLE_DEVICE)
    assert device._client_token == device._UUID_STRING  # noqa: SLF001


def test_client_token_overrides_the_default() -> None:
    """A caller-supplied token is kept stable across connections."""
    device = PrimeCharger160w(
        MOCK_BLE_DEVICE,
        client_token="my-stable-token",  # noqa: S106
    )
    assert device._client_token == "my-stable-token"  # noqa: S105, SLF001
