"""C2000(X) Gen 2 power station model.

.. moduleauthor:: kb1ibt

"""

from ..parsing import walk_lv
from .c1000g2 import C1000G2


class C2000G2(C1000G2):
    """
    C2000(X) Gen 2 Power Station.

    Use this class to connect, monitor and control a Gen 2 C2000(X) power
    station. This model is also known as the A1783.

    The C2000 G2 is the larger sibling of the C1000 G2 (A1763) and shares its
    Gen 2 BLE stack: the same ``c421``/``c900`` telemetry framing and TLV field
    map, the same ``4100`` subscribe command, and the same AC (``4101``) and DC
    (``4102``) control. Its three USB-C ports, single USB-A port, AC, DC and
    solar all decode identically -- confirmed against a live A1783 frame (serial,
    part number ``A1783``, temperature, battery percentage and min/max SOC all
    read correctly through the inherited
    :class:`~SolixBLE.devices.c1000g2.C1000G2` properties) -- so it is driven
    almost entirely by that inherited behaviour.

    The C2000 additionally reports a parallel/expansion battery (a BP2000) in tag
    ``ce`` of the ``c421`` telemetry. Unlike the flat fields, ``ce`` is a nested
    length-value block (the app's "并机"/``DeviceCombinationInfo``) whose first
    field is a 16-byte combination-device ID -- all-zero when no unit is combined.
    :attr:`expansion_present` decodes that ID via :func:`SolixBLE.parsing.walk_lv`;
    the remaining sub-fields (the combined pack's identity/mode/power) are left
    undecoded pending a capture from a device that actually has one combined. The
    ``c490`` protobuf device summary (exposed via :attr:`summary`) carries the
    cumulative energy ledgers.
    """

    @property
    def expansion_present(self) -> bool:
        """Whether a parallel/expansion battery (e.g. a BP2000) is combined.

        The ``ce`` tag's first length-value field is a 16-byte combination-device
        ID: all-zero means no unit is combined (the app's
        ``DeviceCombinationInfo.status == single``), non-zero means one is.

        :returns: True if a parallel/expansion unit is combined, else False.
        """
        if not self._data or "ce" not in self._data:
            return False
        # ce value is a `bin` field (0x04 type byte) wrapping a length-value block.
        fields = walk_lv(self._data["ce"][1:])
        return bool(fields and any(fields[0]))
