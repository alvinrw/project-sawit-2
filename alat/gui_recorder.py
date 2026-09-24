#!/usr/bin/env python3
"""GUI Windows untuk merekam stream PCM biner RawSawitRecorder.ino."""

from __future__ import annotations

import array
import datetime as dt
import queue
import struct
import sys
import threading
import time
import wave
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
SAMPLE_RATE = 62_500
CLIP_LEVEL = 32_760


class PacketReader:
    def __init__(self, ser: serial.Serial, stop_event: threading.Event):
        self.ser = ser
        self.stop_event = stop_event
        self.buffer = bytearray()

    def read(self):
        """Baca satu paket atau None ketika tombol Berhenti ditekan."""
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
                    and version == PROTOCOL_VERSION
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
                    return sequence, rate, count, gain, dropped, pcm

            chunk = self.ser.read(4096)
            if chunk:
                self.buffer.extend(chunk)

        return None


class RecorderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PalmSonic Raw WAV Recorder")
        self.root.geometry("720x560")
        self.root.minsize(680, 520)

        self.messages: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.port_map: dict[str, str] = {}
        self.closing = False

        self.port_var = tk.StringVar()
        self.duration_var = tk.StringVar(value="30")
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_var = tk.StringVar(value=f"rekaman_sawit_{stamp}.wav")
        self.status_var = tk.StringVar(value="Siap. Pilih port alat lalu mulai merekam.")
        self.elapsed_var = tk.StringVar(value="0,0 detik")
        self.current_peak_var = tk.StringVar(value="0")
        self.max_peak_var = tk.StringVar(value="0")
        self.clip_var = tk.StringVar(value="0,0000%")
        self.drop_var = tk.StringVar(value="0")
        self.gap_var = tk.StringVar(value="0")
        self.gain_var = tk.StringVar(value="-")

        self._build_ui()
        self.refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.poll_messages)

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 16, "bold"))

        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="PalmSonic Raw WAV Recorder", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="RAK4631 + RAK18032 · PCM mentah 16-bit mono · 62.500 sampel/detik",
        ).pack(anchor="w", pady=(2, 16))

        setup = ttk.LabelFrame(outer, text="Pengaturan rekaman", padding=12)
        setup.pack(fill="x")
        setup.columnconfigure(1, weight=1)

        ttk.Label(setup, text="Port alat").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.port_combo = ttk.Combobox(setup, textvariable=self.port_var, state="readonly")
        self.port_combo.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Button(setup, text="Muat ulang", command=self.refresh_ports).grid(
            row=0, column=2, padx=(8, 0), pady=5
        )

        ttk.Label(setup, text="Durasi (detik)").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(setup, textvariable=self.duration_var, width=14).grid(
            row=1, column=1, sticky="w", pady=5
        )
        ttk.Label(setup, text="0 = sampai tombol Berhenti ditekan").grid(
            row=1, column=1, sticky="e", pady=5
        )

        ttk.Label(setup, text="File WAV").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(setup, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Button(setup, text="Pilih...", command=self.choose_output).grid(
            row=2, column=2, padx=(8, 0), pady=5
        )

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=14)
        self.start_button = ttk.Button(controls, text="Mulai merekam", command=self.start_recording)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            controls, text="Berhenti", command=self.stop_recording, state="disabled"
        )
        self.stop_button.pack(side="left", padx=8)

        meter = ttk.LabelFrame(outer, text="Monitor sinyal", padding=12)
        meter.pack(fill="both", expand=True)
        meter.columnconfigure((0, 1, 2), weight=1)

        ttk.Label(meter, text="Peak saat ini").grid(row=0, column=0)
        ttk.Label(meter, text="Peak maksimum").grid(row=0, column=1)
        ttk.Label(meter, text="Clipping").grid(row=0, column=2)
        ttk.Label(meter, textvariable=self.current_peak_var, style="Metric.TLabel").grid(row=1, column=0)
        ttk.Label(meter, textvariable=self.max_peak_var, style="Metric.TLabel").grid(row=1, column=1)
        ttk.Label(meter, textvariable=self.clip_var, style="Metric.TLabel").grid(row=1, column=2)

        self.peak_bar = ttk.Progressbar(meter, maximum=32768, mode="determinate")
        self.peak_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        self.warning_label = tk.Label(
            meter,
            text="Belum ada data",
            fg="#555555",
            font=("Segoe UI", 10, "bold"),
        )
        self.warning_label.grid(row=3, column=0, columnspan=3, pady=(2, 12))

        details = ttk.Frame(meter)
        details.grid(row=4, column=0, columnspan=3)
        for column, (label, variable) in enumerate(
            (
                ("Durasi", self.elapsed_var),
                ("Drop alat", self.drop_var),
                ("Gap USB", self.gap_var),
                ("Gain firmware", self.gain_var),
            )
        ):
            box = ttk.Frame(details, padding=(14, 2))
            box.grid(row=0, column=column)
            ttk.Label(box, text=label).pack()
            ttk.Label(box, textvariable=variable, font=("Segoe UI", 11, "bold")).pack()

        ttk.Separator(outer).pack(fill="x", pady=(14, 10))
        ttk.Label(outer, textvariable=self.status_var, wraplength=660).pack(anchor="w")

    def refresh_ports(self):
        previous_device = self.port_map.get(self.port_var.get())
        self.port_map.clear()
        preferred = None
        for port in list_ports.comports():
            label = f"{port.device} — {port.description}"
            self.port_map[label] = port.device
            if port.device == previous_device:
                preferred = label
            if port.vid == 0x239A and preferred is None:
                preferred = label

        values = list(self.port_map)
        self.port_combo["values"] = values
        if preferred:
            self.port_var.set(preferred)
        elif values:
            self.port_var.set(values[0])
        else:
            self.port_var.set("")
        self.status_var.set(
            "Port diperbarui." if values else "Tidak ada port serial. Sambungkan alat lalu muat ulang."
        )

    def choose_output(self):
        selected = filedialog.asksaveasfilename(
            title="Simpan rekaman WAV",
            defaultextension=".wav",
            filetypes=[("WAV lossless", "*.wav")],
            initialfile=Path(self.output_var.get()).name,
        )
        if selected:
            self.output_var.set(selected)

    def start_recording(self):
        port = self.port_map.get(self.port_var.get())
        if not port:
            messagebox.showerror("Port belum dipilih", "Pilih port USB alat terlebih dahulu.")
            return

        try:
            duration = float(self.duration_var.get().replace(",", "."))
            if duration < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Durasi tidak valid", "Durasi harus berupa angka 0 atau lebih.")
            return

        output = Path(self.output_var.get().strip())
        if not output.name:
            messagebox.showerror("File belum dipilih", "Tentukan nama file WAV keluaran.")
            return
        if output.suffix.lower() != ".wav":
            output = output.with_suffix(".wav")
            self.output_var.set(str(output))

        self.stop_event.clear()
        for variable, value in (
            (self.current_peak_var, "0"),
            (self.max_peak_var, "0"),
            (self.clip_var, "0,0000%"),
            (self.drop_var, "0"),
            (self.gap_var, "0"),
            (self.gain_var, "-"),
            (self.elapsed_var, "0,0 detik"),
        ):
            variable.set(value)
        self.peak_bar["value"] = 0
        self.warning_label.configure(text="Menunggu data...", fg="#555555")
        self.status_var.set(f"Membuka {port}...")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.port_combo.configure(state="disabled")

        self.worker = threading.Thread(
            target=self._record_worker,
            args=(port, duration, output),
            daemon=True,
        )
        self.worker.start()

    def stop_recording(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status_var.set("Menghentikan dan merapikan file WAV...")

    def _record_worker(self, port: str, duration: float, output: Path):
        received = 0
        max_peak = 0
        clipped = 0
        sequence_gaps = 0
        last_sequence = None
        dropped = 0
        last_update = 0.0

        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with serial.Serial(port, 1_000_000, timeout=0.2, write_timeout=2) as ser:
                # Buffer besar mencegah stream tersendat ketika Windows/Tk sibuk
                # sesaat. Sampel tetap disimpan persis seperti diterima.
                try:
                    ser.set_buffer_size(rx_size=1_048_576, tx_size=4_096)
                except (AttributeError, OSError, serial.SerialException):
                    pass

                time.sleep(1.5)
                ser.reset_input_buffer()
                ser.write(b"R")
                ser.flush()
                reader = PacketReader(ser, self.stop_event)
                self.messages.put(("status", f"Merekam dari {port} ke {output}"))

                with wave.open(str(output), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(SAMPLE_RATE)

                    while not self.stop_event.is_set():
                        packet = reader.read()
                        if packet is None:
                            break
                        sequence, _rate, count, gain, dropped, pcm = packet

                        if last_sequence is not None:
                            expected = (last_sequence + 1) & 0xFFFFFFFF
                            if sequence != expected:
                                sequence_gaps += (sequence - expected) & 0xFFFFFFFF
                        last_sequence = sequence

                        if duration:
                            remaining = int(duration * SAMPLE_RATE) - received
                            if remaining <= 0:
                                break
                            if remaining < count:
                                pcm = pcm[: remaining * 2]
                                count = remaining

                        wav.writeframesraw(pcm)
                        received += count

                        values = array.array("h")
                        values.frombytes(pcm)
                        if sys.byteorder != "little":
                            values.byteswap()
                        current_peak = max((abs(value) for value in values), default=0)
                        max_peak = max(max_peak, current_peak)
                        clipped += sum(abs(value) >= CLIP_LEVEL for value in values)
                        clip_percent = 100.0 * clipped / received if received else 0.0

                        now = time.monotonic()
                        if now - last_update >= 0.1:
                            self.messages.put(
                                (
                                    "data",
                                    {
                                        "seconds": received / SAMPLE_RATE,
                                        "current_peak": current_peak,
                                        "max_peak": max_peak,
                                        "clip_percent": clip_percent,
                                        "dropped": dropped,
                                        "gaps": sequence_gaps,
                                        "gain": gain,
                                    },
                                )
                            )
                            last_update = now

                        if duration and received >= int(duration * SAMPLE_RATE):
                            break

                try:
                    ser.write(b"S")
                    ser.flush()
                except serial.SerialException:
                    pass

            clip_percent = 100.0 * clipped / received if received else 0.0
            self.messages.put(
                (
                    "done",
                    {
                        "seconds": received / SAMPLE_RATE,
                        "samples": received,
                        "max_peak": max_peak,
                        "clip_percent": clip_percent,
                        "dropped": dropped,
                        "gaps": sequence_gaps,
                        "output": output.resolve(),
                    },
                )
            )
        except Exception as exc:
            self.messages.put(("error", f"{type(exc).__name__}: {exc}"))

    def poll_messages(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "data":
                    self._show_data(payload)
                elif kind == "done":
                    self._recording_finished(payload)
                elif kind == "error":
                    self._recording_error(payload)
        except queue.Empty:
            pass

        if self.closing and self.worker is None:
            return
        self.root.after(100, self.poll_messages)

    def _show_data(self, data: dict):
        self.elapsed_var.set(f"{data['seconds']:.1f} detik")
        self.current_peak_var.set(str(data["current_peak"]))
        self.max_peak_var.set(str(data["max_peak"]))
        self.clip_var.set(f"{data['clip_percent']:.4f}%")
        self.drop_var.set(str(data["dropped"]))
        self.gap_var.set(str(data["gaps"]))
        self.gain_var.set(str(data["gain"]))
        self.peak_bar["value"] = min(data["current_peak"], 32768)

        if data["clip_percent"] > 0.01:
            self.warning_label.configure(
                text="CLIPPING — gain firmware terlalu tinggi; rekaman belum layak dataset",
                fg="#b00020",
            )
        elif data["clip_percent"] > 0:
            self.warning_label.configure(
                text="Clipping sangat kecil — kemungkinan transien saat mikrofon mulai",
                fg="#a05a00",
            )
        elif data["current_peak"] < 100:
            self.warning_label.configure(text="Sinyal sangat kecil / mikrofon perlu diperiksa", fg="#a05a00")
        else:
            self.warning_label.configure(text="Level sinyal aman", fg="#147a3e")

    def _set_idle(self):
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.port_combo.configure(state="readonly")
        self.worker = None

    def _recording_finished(self, data: dict):
        self._set_idle()
        message = (
            f"Selesai: {data['seconds']:.3f} detik, peak maksimum {data['max_peak']}, "
            f"clipping {data['clip_percent']:.4f}%, drop {data['dropped']}, "
            f"gap {data['gaps']}.\nFile: {data['output']}"
        )
        self.status_var.set(message)
        if data["clip_percent"] > 0.01:
            messagebox.showwarning(
                "Rekaman clipping",
                message + "\n\nTurunkan PDM_GAIN di firmware sebelum membuat dataset.",
            )
        elif data["dropped"] or data["gaps"]:
            messagebox.showwarning("Ada data hilang", message)
        else:
            messagebox.showinfo("Rekaman selesai", message)
        if self.closing:
            self.root.destroy()

    def _recording_error(self, error: str):
        self._set_idle()
        self.status_var.set(f"Gagal: {error}")
        messagebox.showerror(
            "Perekaman gagal",
            f"{error}\n\nTutup Serial Monitor/Plotter, pastikan port benar, lalu coba lagi.",
        )
        if self.closing:
            self.root.destroy()

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                "Perekaman sedang berjalan",
                "Hentikan perekaman, rapikan WAV, lalu tutup aplikasi?",
            ):
                return
            self.closing = True
            self.stop_recording()
        else:
            self.closing = True
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    RecorderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
