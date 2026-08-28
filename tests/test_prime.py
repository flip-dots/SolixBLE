"""
Tests for the Anker Prime specific functionality.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
"""

import pytest

from SolixBLE import prime_device
from SolixBLE.constructs import Packet
from SolixBLE.prime_device import PrimeDevice
from tests.const import MOCK_BLE_DEVICE


@pytest.mark.parametrize(
    "packet,decrypted_payload,shared_secret",
    [
        pytest.param(
            "ff094000030001402257ec69586f3500c8f858e0ba047f237f4e2ed8c50d2f39ba3587e4010275bea22242936f08788849272fb3f4cf7493be4a60bb9c9f0693",
            "a104f079b569a30400000000a518474d54304253542c4d332e352e302f312c4d31302e352e30",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_5_response",
        ),
        pytest.param(
            "ff094600030001402757ec69586f3501e8cf6185d8c4035707377af9af3a2e40b02b86e7531974f1c22440de6e43705566b77cf940e235b65abf4d413ece5f2c3781712f3742",
            "a104f079b569a22437396562656433352d646339632d343930342d623430632d373263346538363361613130",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_6_response",
        ),
        pytest.param(
            "ff09230003000f420057e9b8dfdeacda7991d3eb7f12093e55ff002aa9799bcc9216e3",
            "a10121fe04f079b569",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_7a_response",
        ),
        pytest.param(
            "ff09530003000f420a57e9b883d958e48e5b7de48d980206577e2dafbb3d604dea3686f3011969f0db2311906d142b5730ee2bfb11e3fbbe7485aac8877995310669156ec74645c962b419e579b385fd079967",
            "a10121a203044742a3250437396562656433352d646339632d343930342d623430632d373263346538363361613130a5020101fe04f079b569",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            id="stage_7b_response",
        ),
        pytest.param(
            "ff092d0003000140221462ecff54785e445fd4ebc9c574f6e91ee4b316f4458b9bd1af3515b6b0820cdb4f1c4f",
            "a104b70eab69a304808fffffa5054353542d38",
            "c0779a39bfa7b290ba9cd3d96b6fdc22a1f6a9746d4fc81e942c3d95a3892d2f",
            id="from_external_logs",
        ),
    ],
)
def test_negotiation_encryption_session(
    packet: str, decrypted_payload: str, shared_secret: str
):
    """
    Test that the encrypted packets produced by the library
    for negotiation are correct.

    This test takes a packet, extracts its payload, decrypts the
    payload, and then re-encrypts the payload and asserts that
    the encrypted and decrypted-then-re-encrypted payload are
    identical.

    This test also asserts that the decrypted payload matches
    the expected one.
    """

    prime = PrimeDevice(MOCK_BLE_DEVICE)

    payload = Packet.parse(bytes.fromhex(packet)).payload_bytes
    prime._shared_secret = bytes.fromhex(shared_secret)

    decrypted = prime._decrypt_payload(payload)
    assert decrypted.hex() == decrypted_payload

    re_encrypted = prime._encrypt_payload(decrypted)
    assert payload.hex() == re_encrypted.hex()
