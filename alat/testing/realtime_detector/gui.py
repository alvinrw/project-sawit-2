from __future__ import annotations

import datetime as dt
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from serial.tools import list_ports

from .config import (
    APP_TITLE,
    LABEL_PLANT,
    RAK_USB_VID,
    STABLE_SEGMENTS,
    Calibration,
)
from .features import build_calibration
from .ml import load_ml_model
from .recorder import record_stream


class RealtimeDetectorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("860x690")
        self.root.minsize(780, 630)
        self.base = Path(__file__).resolve().parent.parent
        self.messages: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.calibration: Calibration | None = None
        self.model: dict | None = None
        self.model_info: dict = {"loaded": False, "detail": "model belum dimuat"}
        self.port_map: dict[str, str] = {}
        self.closing = False

        self.port_var = tk.StringVar()
        self.empty_var = tk.StringVar(value=str(self.base / "kosong"))
        self.plant_var = tk.StringVar(value=str(self.base / "sawit_sehat"))
        self.duration_var = tk.StringVar(value="0")
        self.output_var = tk.StringVar(value=str(self._new_output()))
        self.calibration_var = tk.StringVar(value="Kalibrasi belum dimuat")
        self.status_var = tk.StringVar(value="Sambungkan alat, muat kalibrasi, lalu mulai.")
        self.decision_var = tk.StringVar(value="MENUNGGU")
        self.reason_var = tk.StringVar(value="Keputusan diperbarui setiap 10 detik")
        self.progress_var = tk.StringVar(value="0/3 segmen")
        self.time_var = tk.StringVar(value="0,0 s")
        self.peak_var = tk.StringVar(value="0")
        self.clip_var = tk.StringVar(value="0,0000%")
        self.drop_var = tk.StringVar(value="0 / 0")
        self.distance_var = tk.StringVar(value="Kosong -  |  Tanaman -")
        self.vote_var = tk.StringVar(value="Kosong 0  |  Tanaman 0")

        self._build_ui()
        self.refresh_ports()
        self.load_calibration()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.poll_messages)

    def _new_output(self) -> Path:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.base / f"realtime_{stamp}.wav"

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Decision.TLabel", font=("Segoe UI", 28, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 14, "bold"))

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Raw PCM 62.500 Hz · keputusan 20–28 kHz setiap 10 detik").pack(
            anchor="w", pady=(2, 12)
        )

        settings = ttk.LabelFrame(outer, text="Pengaturan", padding=10)
        settings.pack(fill="x")
        settings.columnconfigure(1, weight=1)
        self._settings_row(settings, 0, "Port alat", self.port_var, self.refresh_ports, "Muat ulang", combo=True)
        self._settings_row(
            settings, 1, "Referensi kosong", self.empty_var,
            lambda: self.choose_folder(self.empty_var), "Pilih..."
        )
        self._settings_row(
            settings, 2, "Referensi tanaman", self.plant_var,
            lambda: self.choose_folder(self.plant_var), "Pilih..."
        )
        self._settings_row(settings, 3, "File WAV raw", self.output_var, self.choose_output, "Pilih...")
        ttk.Label(settings, text="Durasi detik").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(settings, textvariable=self.duration_var, width=12).grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="0 = sampai tombol Berhenti").grid(row=4, column=1, sticky="e", pady=4)
        ttk.Button(settings, text="Kalibrasi ulang", command=self.load_calibration).grid(row=4, column=2, padx=(8, 0))

        ttk.Label(outer, textvariable=self.calibration_var).pack(anchor="w", pady=(7, 8))
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Mulai deteksi", command=self.start, state="disabled")
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Berhenti", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)

        result = ttk.LabelFrame(outer, text="Hasil langsung", padding=14)
        result.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(result, textvariable=self.decision_var, style="Decision.TLabel").pack()
        self.reason_label = tk.Label(result, textvariable=self.reason_var, font=("Segoe UI", 10, "bold"))
        self.reason_label.pack(pady=(2, 4))
        ttk.Label(result, textvariable=self.progress_var).pack()
        ttk.Label(result, textvariable=self.distance_var).pack(pady=(8, 2))
        ttk.Label(result, textvariable=self.vote_var).pack()

        metrics = ttk.Frame(result)
        metrics.pack(pady=(18, 8))
        for column, (title, variable) in enumerate((
            ("Durasi", self.time_var),
            ("Peak saat ini", self.peak_var),
            ("Clipping", self.clip_var),
            ("Drop / Gap", self.drop_var),
        )):
            box = ttk.Frame(metrics, padding=(18, 2))
            box.grid(row=0, column=column)
            ttk.Label(box, text=title).pack()
            ttk.Label(box, textvariable=variable, style="Metric.TLabel").pack()

        self.signal_bar = ttk.Progressbar(result, maximum=32768)
        self.signal_bar.pack(fill="x", pady=(4, 10))
        ttk.Separator(outer).pack(fill="x", pady=(12, 8))
        ttk.Label(outer, textvariable=self.status_var, wraplength=810).pack(anchor="w")

    def _settings_row(self, parent, row, title, variable, command, button_text, combo=False):
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        if combo:
            self.port_combo = ttk.Combobox(parent, textvariable=variable, state="readonly")
            widget = self.port_combo
        else:
            widget = ttk.Entry(parent, textvariable=variable)
        widget.grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text=button_text, command=command).grid(row=row, column=2, padx=(8, 0), pady=4)

    def refresh_ports(self):
        previous = self.port_map.get(self.port_var.get())
        self.port_map.clear()
        preferred = None
        for port in list_ports.comports():
            if port.vid != RAK_USB_VID:
                continue
            label = f"{port.device} — {port.description}"
            self.port_map[label] = port.device
            if port.device == previous or preferred is None:
                preferred = label
        self.port_combo["values"] = list(self.port_map)
        self.port_var.set(preferred or "")
        if not self.port_map:
            self.status_var.set("RAK4631 tidak terdeteksi. Sambungkan USB dan tekan RESET sekali.")

    def choose_folder(self, variable: tk.StringVar):
        selected = filedialog.askdirectory(initialdir=variable.get())
        if selected:
            variable.set(selected)

    def choose_output(self):
        selected = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV lossless", "*.wav")],
            initialfile=Path(self.output_var.get()).name,
        )
        if selected:
            self.output_var.set(selected)

    def load_calibration(self):
        if self.worker and self.worker.is_alive():
            return
        self.calibration = None
        self.start_button.configure(state="disabled")
        self.calibration_var.set("Memuat kalibrasi...")
        threading.Thread(
            target=self._calibration_worker,
            args=(Path(self.empty_var.get()), Path(self.plant_var.get())),
            daemon=True,
        ).start()

    def _calibration_worker(self, empty_folder: Path, plant_folder: Path):
        try:
            calibration = build_calibration(empty_folder, plant_folder)
            self.model, self.model_info = load_ml_model(self.base)
            self.messages.put(("calibration", calibration))
        except Exception as exc:
            self.messages.put(("error_calibration", f"{type(exc).__name__}: {exc}"))

    def start(self):
        port = self.port_map.get(self.port_var.get())
        if not port or self.calibration is None:
            messagebox.showerror("Belum siap", "Sambungkan RAK4631 dan muat kalibrasi terlebih dahulu.")
            return
        try:
            duration = float(self.duration_var.get().replace(",", "."))
            if duration < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Durasi salah", "Durasi harus angka 0 atau lebih.")
            return
        output = Path(self.output_var.get()).resolve()
        if output.suffix.lower() != ".wav":
            output = output.with_suffix(".wav")
            self.output_var.set(str(output))

        self.stop_event.clear()
        self.decision_var.set("MENGUMPULKAN DATA")
        self.reason_var.set("Keputusan pertama muncul setelah 10 detik")
        self.progress_var.set("0/3 segmen")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.port_combo.configure(state="disabled")
        self.status_var.set(f"Membuka {port}...")
        self.worker = threading.Thread(
            target=record_stream,
            args=(port, output, duration, self.calibration, self.stop_event, self.messages),
            kwargs={"model": self.model},
            daemon=True,
        )
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status_var.set("Menghentikan alat dan merapikan WAV...")

    def poll_messages(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "calibration":
                    self.calibration = payload
                    validation = (
                        f" · validasi antarsesi {payload.validation_accuracy * 100:.1f}%"
                        if payload.validation_accuracy is not None
                        else " · perlu ≥2 WAV per kelas untuk validasi antarsesi"
                    )
                    engine = (
                        f" · {self.model_info['detail']}"
                        if self.model_info.get("loaded")
                        else " · model absen: memakai ambang kontras lama"
                    )
                    self.calibration_var.set(
                        f"Kalibrasi siap: {payload.empty_files} WAV kosong/{payload.empty_segments} segmen · "
                        f"{payload.plant_files} WAV tanaman/{payload.plant_segments} segmen"
                        f"{validation}{engine}"
                    )
                    self.start_button.configure(state="normal")
                elif kind == "error_calibration":
                    self.calibration_var.set(f"Kalibrasi gagal: {payload}")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "metrics":
                    self._show_metrics(payload)
                elif kind == "decision":
                    self._show_decision(payload)
                elif kind == "done":
                    self._finish(payload)
                elif kind == "error_record":
                    self._error(payload)
        except queue.Empty:
            pass
        if self.closing and self.worker is None:
            return
        self.root.after(100, self.poll_messages)

    def _show_metrics(self, data: dict):
        self.time_var.set(f"{data['seconds']:.1f} s")
        self.peak_var.set(str(data["current_peak"]))
        self.clip_var.set(f"{data['clip']:.4f}%")
        self.drop_var.set(f"{data['dropped']} / {data['gaps']}")
        self.signal_bar["value"] = min(data["current_peak"], 32768)
        if data["dropped"] or data["gaps"]:
            self.reason_var.set("DATA HILANG — hasil tidak boleh dipakai")
            self.reason_label.configure(fg="#b00020")

    def _show_decision(self, data: dict):
        label = data["label"]
        self.decision_var.set(label)
        self.progress_var.set(f"{data['segments']}/{STABLE_SEGMENTS} segmen")
        if data.get("ml"):
            probability = data["probability"] * 100
            self.distance_var.set(
                f"Probabilitas tanaman {probability:.0f}%  |  kontras {data['contrast_db']:+.2f} dB"
            )
        else:
            self.distance_var.set(
                f"Kontras relatif {data['contrast_db']:+.2f} dB  |  batas {data['decision_threshold']:+.2f} dB"
            )
        self.vote_var.set(f"Vote: Kosong {data['empty_votes']}  |  Tanaman {data['plant_votes']}")
        if data["quality"] == "SEMENTARA":
            reason, color = "Keputusan sementara — masih mengumpulkan data", "#a05a00"
        elif data["quality"] == "LEMAH":
            if data.get("ml"):
                reason, color = (
                    f"{label}, tetapi kualitas LEMAH (prob {data['probability'] * 100:.0f}%)",
                    "#a05a00",
                )
            else:
                reason, color = (
                    f"{label}, tetapi kualitas LEMAH (kontras {data['contrast_db']:+.2f} dB)",
                    "#a05a00",
                )
        elif data.get("ml"):
            reason, color = (
                f"Kualitas BAIK · {label} · prob {data['probability'] * 100:.0f}%",
                "#147a3e" if label == LABEL_PLANT else "#1769aa",
            )
        elif label == LABEL_PLANT:
            reason, color = (
                f"Kualitas BAIK · pola tanaman · kontras {data['contrast_db']:+.2f} dB",
                "#147a3e",
            )
        else:
            reason, color = (
                f"Kualitas BAIK · pola kosong · kontras {data['contrast_db']:+.2f} dB",
                "#1769aa",
            )
        self.reason_var.set(reason)
        self.reason_label.configure(fg=color)

    def _idle(self):
        self.start_button.configure(state="normal" if self.calibration else "disabled")
        self.stop_button.configure(state="disabled")
        self.port_combo.configure(state="readonly")
        self.worker = None

    def _finish(self, data: dict):
        self._idle()
        self.status_var.set(
            f"Selesai {data['seconds']:.3f}s · clipping {data['clip']:.4f}% · "
            f"drop/gap {data['dropped']}/{data['gaps']} · {data['output']}"
        )
        self.output_var.set(str(self._new_output()))
        if data["dropped"] or data["gaps"]:
            messagebox.showwarning("Ada data hilang", self.status_var.get())
        else:
            messagebox.showinfo("Deteksi selesai", self.status_var.get())
        if self.closing:
            self.root.destroy()

    def _error(self, error: str):
        self._idle()
        self.status_var.set(f"Gagal: {error}")
        messagebox.showerror("Deteksi gagal", f"{error}\n\nTutup recorder/Serial Monitor dan periksa port.")
        if self.closing:
            self.root.destroy()

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Deteksi berjalan", "Hentikan, rapikan WAV, lalu tutup?"):
                return
            self.closing = True
            self.stop()
        else:
            self.closing = True
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    RealtimeDetectorGUI(root)
    root.mainloop()
