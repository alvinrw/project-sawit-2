from __future__ import annotations

import struct
import threading

import serial

from .config import SAMPLE_RATE


MAGIC = b"SAWT"
HEADER = struct.Struct("<4sBBHIIHHI")


class PacketReader:
    def __init__(self, ser: serial.Serial, stop_event: threading.Event):
        self.ser = ser
        self.stop_event = stop_event
        self.buffer = bytearray()

    def read(self):
        while not self.stop_event.is_set():
            marker = self.buffer.find(MAGIC)
            if marker < 0:
                if len(self.buffer) > 3:
                    del self.buffer[:-3]
            elif marker:
                del self.buffer[:marker]

            if len(self.buffer) >= HEADER.size and self.buffer.startswith(MAGIC):
                fields = HEADER.unpack_from(self.buffer)
                magic, version, _flags, header_size, sequence, rate, count, gain, dropped = fields
                valid = (
                    magic == MAGIC
                    and version == 1
                    and header_size == HEADER.size
                    and rate == SAMPLE_RATE
                    and 0 < count <= 256
                )
                if not valid:
                    del self.buffer[0]
                    continue
                packet_size = header_size + count * 2
                if len(self.buffer) >= packet_size:
                    pcm = bytes(self.buffer[header_size:packet_size])
                    del self.buffer[:packet_size]
                    return sequence, count, gain, dropped, pcm

            chunk = self.ser.read(4096)
            if chunk:
                self.buffer.extend(chunk)
        return None
