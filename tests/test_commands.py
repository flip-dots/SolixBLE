"""Tests for the execution of on-device commands.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
from contextlib import nullcontext
from unittest import mock

import pytest

from SolixBLE import C300
from SolixBLE.constructs import Channel, PacketCommand
from SolixBLE.device import SolixBLEDevice
from tests.const import MOCK_BLE_DEVICE
from tests.devices.c300 import (
    C300_TEST_COMMANDS,
    C300_TEST_COMMANDS_E2E,
    C300_TEST_COMMANDS_RESPONSES,
)
from tests.devices.c300dc import C300DC_TEST_COMMANDS, C300DC_TEST_COMMANDS_E2E
from tests.devices.c800 import (
    C800_TEST_COMMANDS,
    C800_TEST_COMMANDS_E2E,
    C800_TEST_COMMANDS_RESPONSES,
)
from tests.devices.c1000 import (
    C1000_TEST_COMMANDS,
    C1000_TEST_COMMANDS_E2E,
    C1000_TEST_COMMANDS_RESPONSES,
)
from tests.devices.c1000g2 import C1000G2_TEST_COMMANDS, C1000G2_TEST_COMMANDS_E2E
from tests.devices.f2600 import (
    F2600_TEST_COMMANDS,
    F2600_TEST_COMMANDS_E2E,
    F2600_TEST_COMMANDS_RESPONSES,
)
from tests.devices.f3800 import F3800_TEST_COMMANDS, F3800_TEST_COMMANDS_E2E
from tests.devices.maggo_3in1 import MAGGO_3IN1_TEST_COMMANDS
from tests.devices.prime_160w_charger import (
    PRIME_CHARGER_160W_TEST_COMMANDS,
    PRIME_CHARGER_160W_TEST_COMMANDS_E2E,
)
from tests.devices.prime_250w_charger import (
    PRIME_CHARGER_250W_TEST_COMMANDS,
    PRIME_CHARGER_250W_TEST_COMMANDS_E2E,
)
from tests.helpers import MockDevice, install_session_keys

#: A session message type (the C300's AC output switch).
AC_OUTPUT = 0x101


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_class", "function", "arguments", "expected"),
    [
        *C300_TEST_COMMANDS,
        *C300DC_TEST_COMMANDS,
        *C800_TEST_COMMANDS,
        *C1000_TEST_COMMANDS,
        *C1000G2_TEST_COMMANDS,
        *F2600_TEST_COMMANDS,
        *F3800_TEST_COMMANDS,
        *MAGGO_3IN1_TEST_COMMANDS,
        *PRIME_CHARGER_160W_TEST_COMMANDS,
        *PRIME_CHARGER_250W_TEST_COMMANDS,
    ],
)
async def test_send_command(
    fake_time,
    device_class: type[SolixBLEDevice],
    function: str,
    arguments: list,
    expected: Exception | list[(str, str)],
) -> None:
    """
    Test that the correct build command is executed for a command or an error is raised.

    :param device_class: Class of device under test.
    :param function: Function to be called.
    :param arguments: Arguments to be given to function.
    :param expected: Error or expected cmd and payload output.
    """
    device = device_class(MOCK_BLE_DEVICE)
    device._client = mock.AsyncMock()
    device._encrypt_payload = lambda x: x
    with (
        mock.patch("SolixBLE.constructs.Packet.build") as mock_build,
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
        pytest.raises(expected) if isinstance(expected, type) else nullcontext(),
    ):

        fn = getattr(device, function)
        await fn(*arguments)

        # The send command function automatically adds a
        # timestamp to the parameters which we need to account for
        timestamp_bytes = f"fe0503{device._timestamp().hex()}"

        for call in expected:
            mock_build.assert_called_once_with({
                **PacketCommand.parse(bytes.fromhex(call[0])),
                "channel": Channel.SESSION,
                "payload_bytes": bytes.fromhex(call[1] + timestamp_bytes),
            })


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("secret", "encrypted"),
    [
        pytest.param(bytes(range(32)), True, id="keyed_session"),
        pytest.param(b"", False, id="plain_before_keys"),
    ],
)
async def test_send_command_message_type(
    fake_time,  # noqa: ANN001, ARG001
    secret: bytes,
    encrypted: bool,  # noqa: FBT001
) -> None:
    """A message type is sent with the encrypted flag the session sets on its frames."""
    device = C300(MOCK_BLE_DEVICE)
    device._client = mock.AsyncMock()  # noqa: SLF001
    install_session_keys(device, secret)
    with (
        mock.patch.object(
            device, "_encrypt_payload", side_effect=lambda payload: payload,
        ),
        mock.patch("SolixBLE.constructs.Packet.build") as mock_build,
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
    ):
        await device._send_command(AC_OUTPUT, {})  # noqa: SLF001

    built = mock_build.call_args.args[0]
    assert (built["channel"], built["fragmented"], built["encrypted"]) == (
        Channel.SESSION,
        False,
        encrypted,
    )
    assert built["msgtype"] == AC_OUTPUT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_class", "function", "arguments", "expected", "listen", "returned"),
    [
        *C300_TEST_COMMANDS_RESPONSES,
        *C800_TEST_COMMANDS_RESPONSES,
        *C1000_TEST_COMMANDS_RESPONSES,
        *F2600_TEST_COMMANDS_RESPONSES,
    ],
)
async def test_send_command_response(  # noqa: PLR0913, PLR0917
    fake_time,  # noqa: ANN001, ARG001
    device_class: type[SolixBLEDevice],
    function: str,
    arguments: list,
    expected: list[(str, str)],
    listen: list[str, str, str | None],
    returned: dict | Exception | None,
) -> None:
    """
    Test sending of commands and handling of response.

    Test that the expected command is sent to the mock device
    and return a response and assert that the correct result
    is returned by the function, if any.

    :param device_class: Class of device under test.
    :param function: Function to be called.
    :param arguments: Arguments to be given to function.
    :param expected: Expected cmd and payload calls to _send_command.
    :param listen: Result(s) of calling _listen_for_packet(pattern, cmd).
    :param returned: Expected return value of the function.
    """
    device = device_class(MOCK_BLE_DEVICE)
    device._client = mock.AsyncMock()
    device._encrypt_payload = lambda x: x

    with (
        mock.patch("SolixBLE.constructs.Packet.build") as mock_build,
        mock.patch("SolixBLE.SolixBLEDevice.negotiated", return_value=True),
        mock.patch("SolixBLE.SolixBLEDevice._listen_for_packet") as mock_listen,
        pytest.raises(returned) if isinstance(returned, type) else nullcontext(),
    ):
        mock_listen.side_effect = [bytes.fromhex(p[2] or "") for p in listen]

        fn = getattr(device, function)
        result = await fn(*arguments)
        assert result == returned

        # The send command function automatically adds a
        # timestamp to the parameters which we need to account for
        timestamp_bytes = f"fe0503{device._timestamp().hex()}"

        for call in expected:
            mock_build.assert_called_once_with({
                **PacketCommand.parse(bytes.fromhex(call[0])),
                "channel": Channel.SESSION,
                "payload_bytes": bytes.fromhex(call[1] + timestamp_bytes),
            })

        for call in listen:
            mock_listen.assert_called_once_with(
                bytes.fromhex(call[0]),
                bytes.fromhex(call[1]),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_class", "negotiation", "function", "arguments", "expected"),
    [
        *C300_TEST_COMMANDS_E2E,
        *C300DC_TEST_COMMANDS_E2E,
        *C800_TEST_COMMANDS_E2E,
        *C1000_TEST_COMMANDS_E2E,
        *C1000G2_TEST_COMMANDS_E2E,
        *F2600_TEST_COMMANDS_E2E,
        *F3800_TEST_COMMANDS_E2E,
        *PRIME_CHARGER_160W_TEST_COMMANDS_E2E,
        *PRIME_CHARGER_250W_TEST_COMMANDS_E2E,
    ],
)
async def test_send_command_e2e(  # noqa: PLR0913, PLR0917
    fake_time,  # noqa: ANN001, ARG001
    fast_sleep,  # noqa: ANN001, ARG001
    fast_timeouts,  # noqa: ANN001, ARG001
    device_class: type[SolixBLEDevice],
    negotiation: dict,
    function: str,
    arguments: list,
    expected: str,
) -> None:
    """
    Test that the expected command is sent to the mock device.

    :param device_class: Class of device under test.
    :param negotiation: Negotiation requests and responses.
    :param function: Function to be called.
    :param arguments: Arguments to be given to function.
    :param expected: Expected bytes sent to the device.
    """

    async def _keep_alive(*args: list, **kwargs: dict) -> None:  # noqa: ARG001
        return None

    async with MockDevice() as mock_bluetooth:

        device = device_class(MOCK_BLE_DEVICE)
        device._keep_alive = _keep_alive  # noqa: SLF001

        # We first expect a negotiation
        for k, v in negotiation.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(k),
                [bytes.fromhex(x) for x in v],
            )

        # We expect the negotiations to succeed
        assert await device.connect(), "Expected connect to return True"
        await asyncio.sleep(0.5)
        assert device.connected, "Expected connected to be True"
        assert device.negotiated, "Expected connected to be True"
        mock_bluetooth.check_assertions()

        mock_bluetooth.expect_ordered(bytes.fromhex(expected))

        fn = getattr(device, function)
        await fn(*arguments)

        mock_bluetooth.check_assertions()
