"""
Tests for the module utilities.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>
"""

from unittest import mock

import pytest

from SolixBLE.utilities import get_posix_tz


@pytest.mark.parametrize(
    ("tz", "output"),
    [
        pytest.param(
            "Europe/London",
            "GMT0BST,M3.5.0/1,M10.5.0",
            id="london",
        ),
        pytest.param(
            "America/New_York",
            "EST5EDT,M3.2.0,M11.1.0",
            id="new_york",
        ),
        pytest.param(
            Exception,
            None,
            id="no_tz",
        ),
        pytest.param(
            "not_a_tz",
            None,
            id="invalid_tz",
        ),
    ],
)
def test_util_tz(
    tz: str | Exception, output: str | None,
) -> None:
    """
    Test the generation of POSIX timezone strings.

    :param tz: The time zone (e.g Europe/London) or error.
    :param output: Expected output of function.
    """
    with mock.patch("tzlocal.get_localzone_name", side_effect=[tz]):
        assert get_posix_tz() == output
