from __future__ import annotations

import array
import queue
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import serial

from .config import (
    CLIP_LEVEL,
    SAMPLE_RATE,
    SEGMENT_SECONDS,
    STABLE_SEGMENTS,
    STARTUP_IGNORE_SECONDS,
    Calibration,
)
from .features import classify, segment_features
from .ml import classify_ml
from .protocol import PacketReader


def _send_stop(ser: serial.Serial) -> None:
    try:
        ser.write(b"S")
        ser.flush()
    except serial.SerialException:
        pass


def record_stream(
    port: str,
    output: Path,
    duration: float,
    calibration: Calibration,
    stop_event: threading.Event,
    messages: queue.Queue,
    model: dict | None = None,
) -> None:
    segment_bytes = int(SEGMENT_SECONDS * SAMPLE_RATE) * 2
    detection_buffer = bytearray()
    recent: list[np.ndarray] = []
    startup_skip = int(STARTUP_IGNORE_SECONDS * SAMPLE_RATE)
    received = clipped = max_peak = gaps = dropped = 0
    last_sequence = None
    last_update = 0.0

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with serial.Serial(port, 1_000_000, timeout=0.2, write_timeout=2) as ser:
            try:
                ser.set_buffer_size(rx_size=1_048_576, tx_size=4_096)
            except (AttributeError, OSError, serial.SerialException):
                pass
            time.sleep(1.5)
            ser.reset_input_buffer()
            ser.write(b"R")
            ser.flush()
            reader = PacketReader(ser, stop_event)
            messages.put(("status", f"Merekam dari {port}; WAV: {output}"))

            with wave.open(str(output), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)

                while not stop_event.is_set() and (duration == 0 or received < duration * SAMPLE_RATE):
                    packet = reader.read()
                    if packet is None:
                        break
                    sequence, count, gain, dropped, pcm = packet

                    if last_sequence is not None:
                        expected = (last_sequence + 1) & 0xFFFFFFFF
                        if sequence != expected:
                            gaps += (sequence - expected) & 0xFFFFFFFF
                    last_sequence = sequence

                    if duration:
                        remaining = int(duration * SAMPLE_RATE) - received
                        if remaining < count:
                            pcm = pcm[: remaining * 2]
                            count = remaining
                    wav.writeframesraw(pcm)

                    values = array.array("h")
                    values.frombytes(pcm)
                    if sys.byteorder != "little":
                        values.byteswap()
                    current_peak = max((abs(value) for value in values), default=0)
                    max_peak = max(max_peak, current_peak)
                    clipped += sum(abs(value) >= CLIP_LEVEL for value in values)

                    detection_pcm = pcm
                    if startup_skip:
                        skip = min(startup_skip, count)
                        detection_pcm = pcm[skip * 2 :]
                        startup_skip -= skip
                    detection_buffer.extend(detection_pcm)
                    received += count

                    while len(detection_buffer) >= segment_bytes:
                        raw_segment = bytes(detection_buffer[:segment_bytes])
                        del detection_buffer[:segment_bytes]
                        samples = np.frombuffer(raw_segment, dtype="<i2").astype(np.float32) / 32768.0
                        feature = segment_features(samples, ignore_seconds=0.0)[0]
                        recent.append(feature)
                        if len(recent) > STABLE_SEGMENTS:
                            del recent[0]
                        if model is not None:
                            decision = classify_ml(np.vstack(recent), model)
                        else:
                            decision = classify(np.vstack(recent), calibration)
                        messages.put(("decision", decision))

                    now = time.monotonic()
                    if now - last_update >= 0.15:
                        messages.put(("metrics", {
                            "seconds": received / SAMPLE_RATE,
                            "current_peak": current_peak,
                            "max_peak": max_peak,
                            "clip": 100.0 * clipped / received if received else 0.0,
                            "dropped": dropped,
                            "gaps": gaps,
                            "gain": gain,
                        }))
                        last_update = now
            _send_stop(ser)

        messages.put(("done", {
            "seconds": received / SAMPLE_RATE,
            "clip": 100.0 * clipped / received if received else 0.0,
            "dropped": dropped,
            "gaps": gaps,
            "output": output,
        }))
    except Exception as exc:
        messages.put(("error_record", f"{type(exc).__name__}: {exc}"))
