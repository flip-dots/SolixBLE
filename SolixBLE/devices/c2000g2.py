"""SOLIX C2000 Gen 2 power station model (A1783).

.. moduleauthor:: grinco

"""

from .c1000g2 import C1000G2


class C2000G2(C1000G2):
    """
    SOLIX C2000 Gen 2 Power Station (A1783).

    The C2000 Gen 2 shares the Gen 2 encryption, telemetry framing, subscribe
    command (``4100``), telemetry commands (``c421``/``c900``) and AC/DC output
    control (``4101``/``4102``) with the :class:`C1000G2`, so it reuses that
    model's implementation.

    Confirmed on real A1783 hardware (2026-11-14), reached over a Bluetooth
    proxy: the C1000 Gen 2 decoder reads the C2000 Gen 2 telemetry correctly
    (battery %, battery health, AC in/out power, DC/solar/USB port power and
    status, temperature, charge limits), and DC output on/off control is
    obeyed. Advertised ``product_type`` is ``b11a`` (SKU ``DKKF``), local name
    ``SOLIX C2000 Gen 2``.

    C2000-specific extras carried in the telemetry frame (e.g. expansion-battery
    fields and the ``c490`` summary) are not decoded yet; add overrides here as
    they are mapped.
    """
