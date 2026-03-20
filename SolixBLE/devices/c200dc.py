"""C200 DC power station model.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from ..const import DEFAULT_METADATA_BOOL
from .c300dc import C300DC


class C200DC(C300DC):
    """
    C200 DC Power Station.

    The C200 DC telemetry layout is largely compatible with C300DC telemetry.
    Some firmware variants do not expose all optional fields (e.g. f7).
    """

    _EXPECTED_TELEMETRY_LENGTH: int = 242

    @property
    def dc_12v_auto_on(self) -> bool:
        """Configured DC Port Auto On.

        :returns: Status of the DC auto on mode or default bool value if unsupported.
        """
        if self._data is None or "f7" not in self._data:
            return DEFAULT_METADATA_BOOL
        return bool(self._parse_int("f7", begin=1))
