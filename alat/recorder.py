#!/usr/bin/env python3
"""Record the binary PCM stream from RawSawitRecorder.ino to a WAV file."""

from __future__ import annotations

import argparse
import array
import datetime as dt
import struct
import sys
import time
import wave
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit(
        "pyserial belum terpasang. Jalankan: python -m pip install -r requirements.txt"
    ) from exc


MAGIC = b"SAWT"
HEADER = struct.Struct("<4sBBHIIHHI")
PROTOCOL_VERSION = 1


def choose_port(requested: str | None) -> str:
    if requested:
        return requested

    ports = list(list_ports.comports())
    if len(ports) == 1:
        print(f"Port terdeteksi otomatis: {ports[0].device} ({ports[0].description})")
        return ports[0].device

    if not ports:
        raise SystemExit("Tidak ada port serial. Sambungkan RAK4631 lalu coba lagi.")

    details = "\n".join(f"  {p.device}: {p.description}" for p in ports)
    raise SystemExit(
        "Ada beberapa port serial. Pilih satu dengan --port COMx:\n" + details
    )


def read_packet(ser: serial.Serial, buffer: bytearray):
    """Return one validated packet, resynchronizing if bytes were interrupted."""
    while True:
        while len(buffer) < HEADER.size:
            chunk = ser.read(4096)
            if chunk:
                buffer.extend(chunk)

        marker = buffer.find(MAGIC)
        if marker < 0:
            del buffer[:-3]
            continue
        if marker:
            del buffer[:marker]
        if len(buffer) < HEADER.size:
            continue

        fields = HEADER.unpack_from(buffer)
        magic, version, _flags, header_size, sequence, rate, count, gain, dropped = fields
        valid = (
            magic == MAGIC
            and version == PROTOCOL_VERSION
            and header_size == HEADER.size
            and rate == 62500
            and 0 < count <= 256
        )
        if not valid:
            del buffer[0]
            continue

        packet_size = header_size + count * 2
        while len(buffer) < packet_size:
            chunk = ser.read(packet_size - len(buffer))
            if chunk:
                buffer.extend(chunk)

        pcm = bytes(buffer[header_size:packet_size])
        del buffer[:packet_size]
        return sequence, rate, count, gain, dropped, pcm


def default_output() -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"rekaman_sawit_{stamp}.wav")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rekam PCM raw RAK4631 + RAK18032 menjadi WAV 16-bit mono."
    )
    parser.add_argument("--port", help="Port alat, contoh COM5. Otomatis jika hanya ada satu.")
    parser.add_argument(
        "--duration",
        type=float,
        default=180.0,
        help="Durasi audio dalam detik (default: 180). Gunakan 0 sampai Ctrl+C.",
    )
    parser.add_argument("--output", type=Path, default=default_output(), help="File WAV keluaran.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration < 0:
        raise SystemExit("--duration tidak boleh negatif")

    port = choose_port(args.port)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    received_samples = 0
    sequence_gaps = 0
    last_sequence = None
    device_dropped = 0
    peak = 0
    current_peak = 0
    clipped = 0
    byte_buffer = bytearray()
    sample_rate = 62500
    started_at = time.monotonic()
    last_status = started_at

    print(f"Membuka {port}; keluaran: {args.output}")
    with serial.Serial(port, 1_000_000, timeout=0.5, write_timeout=2) as ser:
        # Beri Windows ruang untuk menampung stream saat scheduler/UI berhenti
        # sebentar. Ini hanya buffer transport, tidak mengubah sampel audio.
        try:
            ser.set_buffer_size(rx_size=1_048_576, tx_size=4_096)
        except (AttributeError, OSError, serial.SerialException):
            pass

        # Opening USB serial may reset the board. Wait, discard stale bytes, then
        # explicitly request a fresh capture whose sequence starts at zero.
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"R")
        ser.flush()

        try:
            with wave.open(str(args.output), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)

                print("Merekam... tekan Ctrl+C untuk berhenti.")
                while args.duration == 0 or received_samples < args.duration * sample_rate:
                    sequence, rate, count, gain, dropped, pcm = read_packet(ser, byte_buffer)
                    if rate != sample_rate:
                        raise RuntimeError(f"Sample rate berubah dari {sample_rate} ke {rate}")

                    if last_sequence is not None:
                        expected = (last_sequence + 1) & 0xFFFFFFFF
                        if sequence != expected:
                            sequence_gaps += (sequence - expected) & 0xFFFFFFFF
                    last_sequence = sequence
                    device_dropped = dropped

                    if args.duration:
                        remaining = int(args.duration * sample_rate) - received_samples
                        if remaining < count:
                            pcm = pcm[: remaining * 2]
                            count = remaining

                    wav.writeframesraw(pcm)
                    received_samples += count

                    values = array.array("h")
                    values.frombytes(pcm)
                    if sys.byteorder != "little":
                        values.byteswap()
                    if values:
                        local_peak = max(abs(value) for value in values)
                        current_peak = local_peak
                        peak = max(peak, local_peak)
                        clipped += sum(abs(value) >= 32760 for value in values)

                    now = time.monotonic()
                    if now - last_status >= 1.0:
                        seconds = received_samples / sample_rate
                        print(
                            f"\r{seconds:7.1f} s | peak kini {current_peak:5d} | "
                            f"maks {peak:5d} | "
                            f"drop alat {device_dropped} | gap {sequence_gaps}",
                            end="",
                            flush=True,
                        )
                        last_status = now
        except KeyboardInterrupt:
            print("\nPerekaman dihentikan pengguna.")
        finally:
            try:
                ser.write(b"S")
                ser.flush()
            except serial.SerialException:
                pass

    seconds = received_samples / sample_rate
    clip_percent = (100.0 * clipped / received_samples) if received_samples else 0.0
    print(
        f"\nSelesai: {seconds:.3f} s, {received_samples} sampel, peak {peak}, "
        f"clipping {clip_percent:.4f}%, drop alat {device_dropped}, gap {sequence_gaps}."
    )
    print(f"File tersimpan: {args.output.resolve()}")

    if device_dropped or sequence_gaps:
        print("PERINGATAN: ada blok hilang. Coba kabel/port USB lain dan tutup Serial Monitor.")
        return 2
    if clip_percent > 0.01:
        print("PERINGATAN: sinyal clipping. Turunkan PDM_GAIN di firmware lalu upload ulang.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
