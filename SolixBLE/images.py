"""Checks on images sent to a device's display.

.. moduleauthor:: kb1ibt
"""

from dataclasses import dataclass

from construct import ConstructError  # type: ignore[import-untyped]  # construct ships no type stubs

from SolixBLE.constructs import JPEG_FRAME, JPEG_HEADER, JPEG_SOF0, JPEG_SOS

#: Sample precision, in bits, of a baseline JPEG.
JPEG_PRECISION = 8


@dataclass(frozen=True)
class JpegLimits:
    """The JPEG images a device's display decodes.

    :param width: Image width in pixels.
    :param height: Image height in pixels.
    :param max_size: Largest file size in bytes.
    :param components: Number of colour components.
    :param luma_sampling: Allowed (horizontal, vertical) sampling factors of
        the luma component, e.g. ``(2, 2)`` for 4:2:0.
    """

    width: int
    height: int
    max_size: int
    components: int
    luma_sampling: frozenset[tuple[int, int]]


def check_jpeg(image: bytes, limits: JpegLimits) -> None:
    """Check that an image is a baseline JPEG the display can decode.

    .. note::
       :collapsible: closed

       Only the header up to the scan is read: the markers before it must be
       ``APPn``, ``COM``, ``DQT``, ``DHT``, one ``SOF0`` and ``SOS``, so a
       progressive image, restart markers or fill bytes are refused.

    :param image: The JPEG file.
    :param limits: What the display decodes.
    :raises ValueError: If the image is outside the limits.
    """
    if not 0 < len(image) <= limits.max_size:
        msg = f"Image size must be 1 to {limits.max_size} bytes, not {len(image)}"
        raise ValueError(msg)

    try:
        header = JPEG_HEADER.parse(image)
    except ConstructError as error:
        msg = "Image is not a JPEG with a readable header"
        raise ValueError(msg) from error

    markers = [segment.marker for segment in header.segments]
    if markers[-1] != JPEG_SOS:
        msg = f"Image has the JPEG marker {markers[-1]:02x} before its scan"
        raise ValueError(msg)

    frames = [s.segment.data for s in header.segments if s.marker == JPEG_SOF0]
    if len(frames) != 1:
        msg = "Image must have exactly one SOF0 (baseline) frame header"
        raise ValueError(msg)

    try:
        frame = JPEG_FRAME.parse(frames[0])
    except ConstructError as error:
        msg = "Image has an unreadable SOF0 frame header"
        raise ValueError(msg) from error

    if frame.precision != JPEG_PRECISION:
        msg = f"Image precision must be {JPEG_PRECISION} bits, not {frame.precision}"
        raise ValueError(msg)

    if len(frame.components) != limits.components:
        msg = (
            f"Image must have {limits.components} components, "
            f"not {len(frame.components)}"
        )
        raise ValueError(msg)

    luma = frame.components[0].sampling
    if (luma.horizontal, luma.vertical) not in limits.luma_sampling:
        msg = f"Image luma sampling {luma.horizontal}x{luma.vertical} is not supported"
        raise ValueError(msg)

    if (frame.width, frame.height) != (limits.width, limits.height):
        msg = (
            f"Image must be {limits.width}x{limits.height} pixels, "
            f"not {frame.width}x{frame.height}"
        )
        raise ValueError(msg)
