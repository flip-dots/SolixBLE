"""Tests for the USB-PD device identity constructs and tables.

.. moduleauthor:: kb1ibt
"""

from SolixBLE.constructs import (
    DEVICE_IDENTITIES,
    IDENTITY_NONE,
    USB_PD_IDENTITIES,
)
from SolixBLE.usb_pd_identity import (
    DEVICE_NAMES,
    PRODUCT_CODES,
    VENDOR_CLASSES,
    device_name,
    vendor_name,
)

#: The worked A2345 snapshot's ``bd`` value (prime-a2345-a91b2.md:148).
BD_VALUE = "ac051173" + "ac051771" + "fafffbff" + "00000000"

#: The same snapshot's ``be`` value (prime-a2345-a91b2.md:150).
BE_VALUE = "0100ffff" + "01003600" + "ffffffff" + "ffffffff"

#: The vendor class and code the snapshot identifies on USB-C 2.
APPLE = 1
IPAD_PRO_M4 = 54

#: USB vendor and product IDs read on USB-C 1 and 2.
APPLE_VID = 0x05AC
USB_C1_PID = 0x7311
USB_C2_PID = 0x7117

#: The vendor and product IDs a USB-C port reads with no device connected.
NO_DEVICE_VID = 0xFFFA
NO_DEVICE_PID = 0xFFFB

#: The firmware's default variant in :data:`PRODUCT_CODES`.
DEFAULT_VARIANT = 0xFFFF


def test_usb_pd_identities_worked_frame() -> None:
    """``bd`` reads each USB-C port's vendor and product ID."""
    ids = USB_PD_IDENTITIES.parse(bytes.fromhex(BD_VALUE))

    assert (ids.usb_c1.vid, ids.usb_c1.pid) == (APPLE_VID, USB_C1_PID)
    assert (ids.usb_c2.vid, ids.usb_c2.pid) == (APPLE_VID, USB_C2_PID)
    assert (ids.usb_c3.vid, ids.usb_c3.pid) == (NO_DEVICE_VID, NO_DEVICE_PID)
    assert (ids.usb_c4.vid, ids.usb_c4.pid) == (0, 0)
    assert USB_PD_IDENTITIES.build(ids).hex() == BD_VALUE


def test_device_identities_worked_frame() -> None:
    """``be`` reads each USB-C port's vendor class and model code."""
    ids = DEVICE_IDENTITIES.parse(bytes.fromhex(BE_VALUE))

    assert (ids.usb_c1.device_class, ids.usb_c1.code) == (APPLE, IDENTITY_NONE)
    assert (ids.usb_c2.device_class, ids.usb_c2.code) == (APPLE, IPAD_PRO_M4)
    assert (ids.usb_c3.device_class, ids.usb_c3.code) == (IDENTITY_NONE,) * 2
    assert (ids.usb_c4.device_class, ids.usb_c4.code) == (IDENTITY_NONE,) * 2
    assert DEVICE_IDENTITIES.build(ids).hex() == BE_VALUE


def test_worked_frame_names() -> None:
    """USB-C 2's identity names the device; the unidentified ports have none.

    The table keeps the firmware's series name with its trailing space; the
    name returned drops it.
    """
    assert vendor_name(APPLE) == "Apple"
    assert DEVICE_NAMES[APPLE, IPAD_PRO_M4] == "iPad Pro M4 "
    assert device_name(APPLE, IPAD_PRO_M4) == "iPad Pro M4"
    assert device_name(APPLE, IDENTITY_NONE) is None
    assert device_name(IDENTITY_NONE, IDENTITY_NONE) is None
    assert vendor_name(IDENTITY_NONE) is None


def test_tables_resolve_the_worked_frame() -> None:
    """``bd``'s IDs resolve through the tables to the codes ``be`` reports.

    USB-C 2's PID has a default code, the iPad Pro M4; USB-C 1's PID has no
    row, so its code stays unidentified.
    """
    defaults = {
        pid: code for pid, variant, code in PRODUCT_CODES if variant == DEFAULT_VARIANT
    }

    assert VENDOR_CLASSES[APPLE_VID] == APPLE
    assert defaults[USB_C2_PID] == IPAD_PRO_M4
    assert USB_C1_PID not in {pid for pid, _, _ in PRODUCT_CODES}


def test_table_sizes() -> None:
    """The tables hold the firmware's 14 vendors, 96 products and 102 names."""
    assert (len(VENDOR_CLASSES), len(PRODUCT_CODES), len(DEVICE_NAMES)) == (14, 96, 102)
