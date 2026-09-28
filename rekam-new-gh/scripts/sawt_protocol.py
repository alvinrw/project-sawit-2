"""SAWT v1 wire format — host-side parser constants.

This module is the single host-side source of truth for the SAWT v1 packet
layout, so `rekam-new/` runs on its own without the reference clone.

The layout must stay byte-identical to the firmware header
`src/firmware/RawSawitRecorder/sawt_protocol.h`:

    SAWT_PROTOCOL_VERSION = 1
    SAWT_HEADER_SIZE      = 24
    SAWT_SAMPLE_RATE_HZ   = 62500

Frame layout (little-endian, no padding, 24 bytes):

    offset  size  field
    0       4     magic       b"SAWT"
    4       1     version
    5       1     flags       reserved, 0
    6       2     header_size 24
    8       4     sequence    uint32, wraps
    12      4     rate        sample rate in Hz
    16      2     count       samples in this packet, 1..256
    18      2     gain        PDM gain applied by firmware
    20      4     dropped     samples dropped by firmware since last packet

The PCM payload follows the header: `count` signed 16-bit little-endian samples.

Changing anything here requires updating `docs-protocol/SAWT_PROTOCOL.md` and
re-running `tests/test_rekam.py`, which cross-checks these constants against the
firmware header.
"""

import struct

MAGIC = b"SAWT"
PROTOCOL_VERSION = 1
HEADER = struct.Struct("<4sBBHIIHHI")
SAMPLES_PER_PACKET_MAX = 256

assert HEADER.size == 24, "SAWT v1 header must stay 24 bytes"
