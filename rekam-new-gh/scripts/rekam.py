#!/usr/bin/env python3
"""rekam.py — GUI perekam + monitor angka live (peak, clipping, gain).

Gabungan: organisasi ML-rapi dari rekam.py + monitor angka dari referensi.
File & CSV & aturan sesi sama persis dengan rekam.py.
Monitor: peak kini/maks, clipping %, gain firmware, drop, gap + peak bar.
Tombol Buka folder hasil. Tanpa grafik gelombang.

Mode Data: jenis + plants(angka) + hari + sesi(1/2/3) + durasi
  -> data/raw_audio/<jenis>/hari-<N>/<jenis>_P<plant>_hari<N>_sesi<M>_<dur>s_<stamp>.wav
Mode Kontrol Sesi: hari + sesi + durasi (jenis+plants disembunyikan).
  Kontrol ikut sesi: 1=awal, 2=tengah, 3=akhir
  -> data/controls/<jenis>/hari-<N>/kontrol-sesi<M>_hari<N>_<dur>s_<stamp>.wav
Hari ganti tapi kontrol sesi itu belum ada: warning, boleh lanjut.
Aturan: tanpa alas seragam, tutup box + diamkan 2 menit, port auto-isi saat
tombol pertama ditekan, operator opsional, anti-overwrite, CSV log + status.
LIVE: gelombang cermin (atas-bawah garis tengah) geser kiri, update 0,5 detik.
Firmware tetap baseline 62.500 Hz; kodingan alat tidak diubah dari sini.
"""
from __future__ import annotations
import array, csv, datetime as dt, hashlib, os, queue, sys, threading, time, wave
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # rekam-new/
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sawt_protocol as sawt  # noqa: E402  # protokol lokal, tanpa clone referensi

JENIS = ["kosong", "air-kelebihan", "air-normal", "air-kekeringan", "ph-normal", "ph-asam"]
DURASI = ["10", "15", "20", "25", "30", "60", "120", "300", "600"]
SESI = ["1", "2", "3"]
SESI_POSISI = {"1": "awal", "2": "tengah", "3": "akhir"}
RATE = 62500
NO_AUDIO_TIMEOUT_SECONDS = 5.0
CSV = ROOT / "metadata" / "captures" / "keseluruhan.csv"
CSV_HEADER = ["waktu", "mode", "jenis", "plant", "hari", "sesi", "posisi",
              "durasi_s", "file", "sha256", "sampel", "peak", "gain",
              "clip_pct", "drop", "gap", "operator", "box", "status"]


class CancelRecording(Exception):
    """Raised when the operator deliberately aborts before recording."""


CONTROL_CHOICES = ("control", "continue", "cancel")


def prompt_missing_control(*_args, **_kwargs) -> str:
    """Show the missing-control dialog; overridden in the GUI.

    Returns one of CONTROL_CHOICES. A plain string, not a tuple, so the GUI
    implementation and the default cannot disagree on the return shape.
    """
    return "cancel"


def parse_duration(raw: str) -> float:
    """Accept a typed duration in seconds; reject blanks and junk."""
    text = str(raw).strip()
    if not text:
        raise ValueError("Durasi harus diisi (contoh: 20 atau 600)")
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"Durasi harus angka, bukan '{text}'") from exc
    if value <= 0:
        raise ValueError("Durasi harus lebih dari 0 detik")
    return value


def duration_label(seconds: float) -> str:
    """Human label for the status line; file names always stay in seconds."""
    if seconds >= 60 and seconds % 60 == 0:
        minutes = int(seconds // 60)
        return f"{minutes} menit"
    return f"{seconds:g} detik"


def duration_suffix(seconds: float) -> str:
    """File-name token: always seconds, so names stay sortable and unambiguous."""
    return f"{seconds:g}s"


def control_target(data_root: Path, jenis: str, hari: str, sesi: str,
                   dur: float, stamp: str) -> tuple[Path, dict]:
    """Build the empty-box control target for the same category, day and session."""
    out = data_root / "controls" / jenis / f"hari-{hari}" / \
        f"kontrol-sesi{sesi}_hari{hari}_{duration_suffix(dur)}_{stamp}.wav"
    meta = {"mode": "kontrol", "jenis": jenis, "plant": "-", "hari": hari,
            "sesi": sesi, "posisi": SESI_POSISI.get(sesi, "-")}
    return out, meta


def data_target(data_root: Path, jenis: str, plant: str, hari: str, sesi: str,
                dur: float, stamp: str) -> tuple[Path, dict]:
    """Build the plant-recording target and its metadata."""
    out = data_root / "raw_audio" / jenis / f"hari-{hari}" / \
        f"{jenis}_P{plant}_hari{hari}_sesi{sesi}_{duration_suffix(dur)}_{stamp}.wav"
    meta = {"mode": "data", "jenis": jenis, "plant": plant, "hari": hari,
            "sesi": sesi, "posisi": "-"}
    return out, meta


def has_session_control(data_root: Path, jenis: str, hari: str, sesi: str) -> bool:
    """True when an empty-box control for this category, day and session exists."""
    controls = data_root / "controls" / jenis / f"hari-{hari}"
    if not controls.is_dir():
        return False
    return any(controls.glob(f"kontrol-sesi{sesi}_hari{hari}_*.wav"))


def resolve_data_target(data_root: Path, meta: dict, dur: float,
                        stamp: str | None) -> tuple[Path, dict]:
    """Return the target for a plant recording, asking about a missing control.

    The operator may cancel, continue anyway, or switch to the control target.
    `stamp` must be supplied by the caller so the UI can create one before any
    dialog appears, and so the chosen name is the one that gets used.
    """
    assert stamp is not None
    out, out_meta = data_target(data_root, meta["jenis"], meta["plant"],
                                meta["hari"], meta["sesi"], dur, stamp)
    if has_session_control(data_root, meta["jenis"], meta["hari"], meta["sesi"]):
        return out, out_meta
    choice = prompt_missing_control(meta["jenis"], meta["hari"], meta["sesi"])
    if choice == "control":
        return control_target(data_root, meta["jenis"], meta["hari"],
                              meta["sesi"], dur, stamp)
    if choice == "continue":
        return out, out_meta
    raise CancelRecording("operator membatalkan rekam data tanpa kontrol")


def partial_path(out: Path) -> Path:
    """Return the sibling path used while a WAV is still being written."""
    return out.with_suffix(".wav.partial")


def find_partial_files(root: Path) -> list[Path]:
    """Return incomplete WAV paths under one recording root, in stable order."""
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.wav.partial") if path.is_file())


def find_startup_partials(data_root: Path) -> list[Path]:
    """Find old interrupted recordings only in the three recorder data roots."""
    partials: list[Path] = []
    for folder in ("raw_audio", "controls", "pilot_test"):
        partials.extend(find_partial_files(data_root / folder))
    return sorted(partials)


def pending_startup_partial(partials: list[Path], index: int) -> Path | None:
    """Return the leftover partial to offer at this step, or None when done."""
    if 0 <= index < len(partials):
        return partials[index]
    return None


def delete_capture_file(path: Path) -> tuple[bool, str]:
    """Delete only on an explicit operator action; never claim false success."""
    if not path.exists():
        return False, "file tidak ditemukan"
    try:
        path.unlink()
    except OSError as exc:
        return False, str(exc)
    if path.exists():
        return False, "file masih ada setelah perintah hapus"
    return True, ""


def capture_failure_payload(out: Path, exc: Exception) -> dict[str, object]:
    """Describe a failed capture without authorizing deletion of an old WAV."""
    partial = partial_path(out)
    can_delete = partial.exists()
    return {
        "message": f"{type(exc).__name__}: {exc}",
        "path": partial if can_delete else out,
        "can_delete": can_delete,
        "reason": str(exc),
    }


def failure_status(action: str, reason: str) -> str:
    """Keep the operator-visible action and its reason in one CSV field."""
    return f"{action}: {reason}"


def failure_guidance(reason: str) -> str:
    """Give the operator every physical check that matches the failure kinds."""
    lowered = reason.lower()
    parts: list[str] = []
    if any(word in lowered for word in ("drop", "gap", "tidak mengirim audio")):
        parts.append("Periksa kabel USB, port laptop, dan pastikan Serial Monitor tertutup.")
    if "clipping" in lowered or "sinyal" in lowered:
        parts.append("Periksa mikrofon, box, pot/tanaman, dan benda asing seperti serangga.")
    if not parts:
        return "Periksa setup rekaman sebelum mencoba lagi."
    parts.append("Tutup box lalu diamkan 2 menit sebelum rekam ulang.")
    return " ".join(parts)


def relative_capture_path(path: Path) -> str:
    """Return a recorder-relative path, falling back to the literal path."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def build_failure_row(meta: dict, dur: float, op: str, path: Path) -> dict:
    """Build one CSV row for a failed capture; columns match the master header."""
    return {
        "waktu": dt.datetime.now().strftime("%Y%m%d_%H%M%S"),
        **meta,
        "durasi_s": dur,
        "file": relative_capture_path(path),
        "sha256": "",
        "sampel": "",
        "peak": "",
        "gain": "",
        "clip_pct": "",
        "drop": "",
        "gap": "",
        "operator": op,
        "box": "box1-tanpa-piring",
        "status": "",
    }


def build_capture_error(out: Path, meta: dict, dur: float, op: str,
                        exc: Exception) -> dict[str, object]:
    """Always return a loggable failure payload, whatever the failure path is."""
    payload = capture_failure_payload(out, exc)
    if payload["can_delete"]:
        payload["row"] = build_failure_row(meta, dur, op, payload["path"])
    return payload


def operation_button_states(operation: str) -> dict[str, str]:
    """Return the Rekam/Berhenti states for one active operation."""
    states = {
        "idle": {"start": "normal", "stop": "disabled"},
        "recording": {"start": "disabled", "stop": "normal"},
        "tool": {"start": "disabled", "stop": "disabled"},
    }
    try:
        return states[operation]
    except KeyError as exc:
        raise ValueError(f"operasi tidak dikenal: {operation}") from exc


def can_close_window(operation: str) -> bool:
    """Only an idle recorder may close without stopping an active operation."""
    operation_button_states(operation)
    return operation == "idle"


def open_in_file_manager(target: Path) -> tuple[bool, str]:
    """Open a folder in the OS file manager, on Windows, macOS, or Linux."""
    target.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # noqa: S606 - Windows shell open
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", str(target)], check=True)
        else:
            import subprocess
            subprocess.run(["xdg-open", str(target)], check=True)
    except Exception as exc:  # noqa: BLE001 - laporkan, jangan mati diam-diam
        return False, f"{type(exc).__name__}: {exc}"
    return True, ""


def find_port() -> str | None:
    from serial.tools import list_ports
    found = [p.device for p in list_ports.comports() if p.vid == 0x239A]
    return found[0] if len(found) == 1 else None


def _read_packet(ser, buf: bytearray, stop_event: threading.Event,
                 no_data_deadline: float | None = None):
    """Read one SAWT v1 packet, stopping on operator action or no-audio timeout."""
    def read_chunk(size: int) -> bytes:
        if no_data_deadline is not None and time.monotonic() >= no_data_deadline:
            raise TimeoutError("Alat tidak mengirim audio dalam batas waktu")
        return ser.read(size)

    while not stop_event.is_set():
        while len(buf) < sawt.HEADER.size and not stop_event.is_set():
            chunk = read_chunk(4096)
            if chunk:
                buf.extend(chunk)
        if stop_event.is_set():
            raise InterruptedError("dihentikan operator")
        marker = buf.find(sawt.MAGIC)
        if marker < 0:
            del buf[:-3]
            continue
        if marker:
            del buf[:marker]
        if len(buf) < sawt.HEADER.size:
            continue
        fields = sawt.HEADER.unpack_from(buf)
        magic, version, _flags, header_size, sequence, rate, count, gain, dropped = fields
        valid = (magic == sawt.MAGIC and version == sawt.PROTOCOL_VERSION
                 and header_size == sawt.HEADER.size and rate == RATE
                 and 0 < count <= sawt.SAMPLES_PER_PACKET_MAX)
        if not valid:
            del buf[0]
            continue
        packet_size = header_size + count * 2
        while len(buf) < packet_size and not stop_event.is_set():
            chunk = read_chunk(packet_size - len(buf))
            if chunk:
                buf.extend(chunk)
        if stop_event.is_set():
            raise InterruptedError("dihentikan operator")
        pcm = bytes(buf[header_size:packet_size])
        del buf[:packet_size]
        return sequence, rate, count, gain, dropped, pcm
    raise InterruptedError("dihentikan operator")


def record_to(duration: float, port: str, out: Path, stop_event: threading.Event,
              msg: queue.Queue | None = None,
              no_audio_timeout: float = NO_AUDIO_TIMEOUT_SECONDS) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f"tolak overwrite: {out}")
    tmp = partial_path(out)
    received = gaps = dropped = peak = clipped = 0
    last_seq = None
    fw_gain = None
    buf = bytearray()
    import serial
    with serial.Serial(port, 1_000_000, timeout=0.5, write_timeout=2) as ser:
        try:
            ser.set_buffer_size(rx_size=1_048_576, tx_size=4_096)
        except Exception:
            pass
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"R"); ser.flush()
        try:
            with wave.open(str(tmp), "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE)
                last_live = time.monotonic()
                while received < duration * RATE and not stop_event.is_set():
                    seq, r, count, gain, drop, pcm = _read_packet(
                        ser,
                        buf,
                        stop_event,
                        no_data_deadline=time.monotonic() + no_audio_timeout,
                    )
                    if r != RATE:
                        raise RuntimeError(f"rate berubah {r}")
                    if fw_gain is None:
                        fw_gain = gain
                    elif gain != fw_gain:
                        raise RuntimeError(f"gain berubah {fw_gain} -> {gain} tengah jalan")
                    if last_seq is not None and seq != ((last_seq + 1) & 0xFFFFFFFF):
                        gaps += (seq - (last_seq + 1)) & 0xFFFFFFFF
                    last_seq = seq; dropped = drop
                    need = int(duration * RATE) - received
                    if need < count:
                        pcm = pcm[: need * 2]; count = need
                    wav.writeframesraw(pcm); received += count
                    v = array.array("h"); v.frombytes(pcm)
                    if v:
                        peak = max(peak, max(abs(x) for x in v))
                        clipped += sum(abs(x) >= 32760 for x in v)
                        cur = max(abs(x) for x in v)
                    else:
                        cur = 0
                    if msg is not None and time.monotonic() - last_live >= 0.5:
                        clip_now = 100.0 * clipped / received if received else 0.0
                        msg.put(("live", received / RATE, cur, peak, clip_now, gain, dropped, gaps))
                        last_live = time.monotonic()
        finally:
            try:
                ser.write(b"S"); ser.flush()
            except Exception:
                pass
    if received < duration * RATE:
        raise InterruptedError(f"berhenti di {received}/{int(duration*RATE)} sampel")
    h = hashlib.sha256(tmp.read_bytes()).hexdigest()
    tmp.rename(out)
    clip_pct = 100.0 * clipped / received if received else 0.0
    return {"file": str(out), "sampel": received, "peak": peak,
            "clip_pct": round(clip_pct, 4), "drop": dropped, "gap": gaps,
            "sha": h, "gain": fw_gain if fw_gain is not None else "-"}


def log_csv(row: dict) -> None:
    CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not CSV.exists()
    with open(CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CSV_HEADER)
        w.writerow([row.get(k, "") for k in CSV_HEADER])


def log_row(row: dict) -> tuple[bool, str]:
    """Append one row and report a write failure instead of raising, so a
    broken CSV can never strand the GUI or fake a recorded provenance."""
    try:
        log_csv(row)
    except OSError as exc:
        return False, str(exc)
    return True, ""


def main_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk
    root = tk.Tk()
    root.title("Rekam Sawit")
    root.geometry("900x600")
    root.lift()
    root.focus_force()
    root.attributes("-topmost", True)

    def release_topmost() -> None:
        root.attributes("-topmost", False)
        root.focus_force()

    root.after(500, release_topmost)

    msgs: queue.Queue = queue.Queue()
    stop_event = threading.Event()
    worker: threading.Thread | None = None
    active_operation = "idle"
    closing = False

    mode_var = tk.StringVar(value="Data")
    jenis_var = tk.StringVar(value="kosong")
    plant_var = tk.StringVar(value="1")
    hari_var = tk.StringVar(value="1")
    sesi_var = tk.StringVar(value="1")
    dur_var = tk.StringVar(value="20")
    port_var = tk.StringVar(value="")
    op_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Siap. Tutup box + diamkan 2 menit.")

    def ensure_port() -> str | None:
        if port_var.get().strip():
            return port_var.get().strip()
        found = find_port()
        if found:
            port_var.set(found)
            return found
        messagebox.showerror("Port", "Alat tidak ketemu. Colok USB lalu isi Port manual.")
        return None

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text="Rekam Sawit", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frm, text="Khusus rekaman. Tutup box + diamkan 2 menit. "
              "Kontrol ikut sesi: 1=awal, 2=tengah, 3=akhir.").pack(anchor="w", pady=(0, 8))

    modef = ttk.Frame(frm)
    modef.pack(fill="x", pady=2)
    ttk.Radiobutton(modef, text="Data", variable=mode_var, value="Data").pack(side="left")
    ttk.Radiobutton(modef, text="Kontrol Sesi", variable=mode_var, value="Kontrol").pack(side="left", padx=12)

    grid = ttk.Frame(frm)
    grid.pack(fill="x", pady=6)
    grid.columnconfigure(1, weight=1)
    widgets: dict = {}

    def add_row(label: str, widget) -> None:
        r = len(widgets)
        ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
        widget.grid(row=r, column=1, sticky="ew", pady=3)
        widgets[label] = widget

    jenis_cb = ttk.Combobox(grid, textvariable=jenis_var, values=JENIS, state="readonly")
    plant_en = ttk.Entry(grid, textvariable=plant_var, width=10)
    hari_en = ttk.Entry(grid, textvariable=hari_var, width=10)
    dur_cb = ttk.Combobox(grid, textvariable=dur_var, values=DURASI, width=10)
    port_en = ttk.Entry(grid, textvariable=port_var, width=14)
    op_en = ttk.Entry(grid, textvariable=op_var)
    add_row("Jenis", jenis_cb)
    add_row("Plants", plant_en)
    add_row("Hari ke", hari_en)

    sesi_fr = ttk.Frame(grid)
    for s in SESI:
        ttk.Radiobutton(sesi_fr, text=s, variable=sesi_var, value=s).pack(side="left", padx=(0, 28))
    add_row("Sesi", sesi_fr)
    add_row("Durasi", dur_cb)
    ttk.Label(grid, text="detik (bisa diketik bebas, misal 45)").grid(
        row=len(widgets) - 1, column=2, sticky="w", padx=(10, 0))
    add_row("Port", port_en)
    add_row("Operator", op_en)

    livef = ttk.LabelFrame(frm, text="Monitor sinyal", padding=8)
    livef.pack(fill="x", pady=6)
    livef.columnconfigure((0, 1, 2), weight=1)
    peak_now_var = tk.StringVar(value="0")
    peak_max_var = tk.StringVar(value="0")
    clip_var = tk.StringVar(value="0,0000%")
    drop_var = tk.StringVar(value="0")
    gap_var = tk.StringVar(value="0")
    gain_var = tk.StringVar(value="-")
    ttk.Label(livef, text="Peak kini").grid(row=0, column=0)
    ttk.Label(livef, text="Peak maks").grid(row=0, column=1)
    ttk.Label(livef, text="Clipping").grid(row=0, column=2)
    ttk.Label(livef, textvariable=peak_now_var, font=("Segoe UI", 16, "bold")).grid(row=1, column=0)
    ttk.Label(livef, textvariable=peak_max_var, font=("Segoe UI", 16, "bold")).grid(row=1, column=1)
    ttk.Label(livef, textvariable=clip_var, font=("Segoe UI", 16, "bold")).grid(row=1, column=2)
    peak_bar = ttk.Progressbar(livef, maximum=32768, mode="determinate")
    peak_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 2))
    warn_var = tk.StringVar(value="Belum ada data")
    ttk.Label(livef, textvariable=warn_var, font=("Segoe UI", 10, "bold")).grid(row=3, column=0, columnspan=3)
    detf = ttk.Frame(livef)
    detf.grid(row=4, column=0, columnspan=3)
    for col, (lbl, var) in enumerate((("Drop alat", drop_var), ("Gap USB", gap_var), ("Gain firmware", gain_var))):
        ttk.Label(detf, text=lbl).grid(row=0, column=col, padx=14)
        ttk.Label(detf, textvariable=var, font=("Segoe UI", 11, "bold")).grid(row=1, column=col)

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=6)
    start_btn = ttk.Button(btns, text="Rekam")
    stop_btn = ttk.Button(btns, text="Berhenti", state="disabled")
    start_btn.pack(side="left", expand=True, fill="x")
    stop_btn.pack(side="left", expand=True, fill="x", padx=8)
    open_btn = ttk.Button(btns, text="Buka folder hasil")
    open_btn.pack(side="left", expand=True, fill="x", padx=(8, 0))
    ttk.Label(frm, textvariable=status_var, wraplength=860).pack(anchor="w", pady=(6, 0))

    def set_operation(operation: str) -> None:
        nonlocal active_operation
        active_operation = operation
        states = operation_button_states(operation)
        start_btn.configure(state=states["start"])
        stop_btn.configure(state=states["stop"])

    def show_file_action_dialog(title: str, message: str, path: Path,
                                delete_label: str | None,
                                on_deleted, on_kept, on_delete_failed) -> None:
        """Show an operator-facing failure dialog without automatic deletion."""
        status_var.set(f"{title} — menunggu keputusan operator. File: {path}")
        dialog = tk.Toplevel(root)
        dialog.title(title)
        dialog.transient(root)
        dialog.resizable(True, False)
        dialog.grab_set()

        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=message, justify="left", wraplength=620).pack(anchor="w")
        ttk.Label(body, text="Lokasi file:", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", pady=(12, 2))
        location = tk.StringVar(value=str(path))
        ttk.Entry(body, textvariable=location, state="readonly", width=92).pack(fill="x")

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(14, 0))

        def finish(callback) -> None:
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            callback()

        def open_parent() -> None:
            ok, detail = open_in_file_manager(path.parent)
            if not ok:
                messagebox.showerror("Buka folder gagal", detail)

        ttk.Button(actions, text="Buka folder", command=open_parent).pack(side="left")
        if delete_label is not None:
            def delete_file() -> None:
                ok, detail = delete_capture_file(path)
                if ok:
                    finish(on_deleted)
                else:
                    finish(lambda: on_delete_failed(detail))

            ttk.Button(actions, text=delete_label, command=delete_file).pack(side="left", padx=8)
        ttk.Button(actions, text="Tutup", command=lambda: finish(on_kept)).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(on_kept))

    def show_live(sec: float, cur: int, mx: int, clip: float, gain: int, drop: int, gap: int) -> None:
        peak_now_var.set(str(cur))
        peak_max_var.set(str(mx))
        clip_var.set(f"{clip:.4f}%")
        drop_var.set(str(drop))
        gap_var.set(str(gap))
        gain_var.set(str(gain))
        peak_bar["value"] = min(cur, 32768)
        if clip > 0.01:
            warn_var.set("CLIPPING — rekaman belum layak dataset")
        elif clip > 0:
            warn_var.set("Clipping sangat kecil — kemungkinan transien awal")
        elif cur < 100:
            warn_var.set("Sinyal sangat kecil — periksa mikrofon")
        else:
            warn_var.set("Level sinyal aman")
        status_var.set(f"Merekam... {sec:.1f} detik")

    def refresh_mode(*_args) -> None:
        is_data = mode_var.get() == "Data"
        widgets["Plants"].grid() if is_data else widgets["Plants"].grid_remove()

    def report_unlogged(row: dict, detail: str) -> None:
        """Tell the operator the CSV could not record this capture."""
        messagebox.showerror(
            "Gagal menulis CSV",
            f"{detail}\n\nFile: {row.get('file', '-')}\n"
            f"Status yang seharusnya tercatat: {row.get('status', '-')}\n"
            "Catat manual di log Operator; jangan anggap file ini sudah berstatus.",
        )

    def make_file_actions(path: Path, row: dict, reason: str, prefix: str):
        """Bind one failure dialog to its own row and reason, so no callback
        can ever write another failure's CSV row (one capture in flight)."""
        def deleted() -> None:
            row["status"] = failure_status(f"{prefix}-dihapus", reason)
            logged, detail = log_row(row)
            if not logged:
                report_unlogged(row, detail)
            status_var.set(
                f"File {prefix} dihapus. Bersihkan setup, diamkan box 2 menit, lalu tekan Rekam."
                if logged else f"File {prefix} dihapus, tapi CSV gagal ditulis."
            )
            set_operation("idle")

        def kept() -> None:
            row["status"] = failure_status(f"{prefix}-dibiarkan", reason)
            logged, detail = log_row(row)
            if not logged:
                report_unlogged(row, detail)
            status_var.set(f"File {prefix} masih disimpan: {path}")
            set_operation("idle")

        def delete_failed(detail: str) -> None:
            row["status"] = failure_status(f"{prefix}-gagal-hapus", f"{reason}; {detail}")
            logged, log_detail = log_row(row)
            if not logged:
                report_unlogged(row, log_detail)
            status_var.set(f"File {prefix} tidak terhapus: {path} ({detail})")
            set_operation("idle")

        return deleted, kept, delete_failed

    def poll() -> None:
        try:
            while True:
                kind, *payload = msgs.get_nowait()
                if closing:
                    continue
                if kind == "live":
                    sec, cur, mx, clip, gain, drop, gap = payload
                    show_live(sec, cur, mx, clip, gain, drop, gap)
                elif kind == "tool_done":
                    ok, label, tail = payload
                    status_var.set(f"{label}: {'OK' if ok else 'GAGAL'}\n{tail}")
                    if not ok:
                        messagebox.showwarning(label, tail[-500:])
                    set_operation("idle")
                elif kind == "done":
                    r, row, out = payload
                    dirty = []
                    if r["drop"] or r["gap"]:
                        dirty.append(f"blok hilang (drop {r['drop']} gap {r['gap']})")
                    if r["clip_pct"] > 0.01:
                        dirty.append(f"clipping {r['clip_pct']}%")
                    if dirty:
                        reason = ", ".join(dirty)
                        failed_path = Path(r["file"])
                        set_operation("tool")
                        deleted, kept, delete_failed = make_file_actions(
                            failed_path, row, reason, "gagal")
                        show_file_action_dialog(
                            "Rekaman gagal",
                            f"Rekaman bermasalah: {reason}\n\n{failure_guidance(reason)}",
                            failed_path,
                            "Sudah bersihkan setup — hapus file gagal",
                            deleted,
                            kept,
                            delete_failed,
                        )
                        continue
                    row["status"] = "bersih"
                    logged, detail = log_row(row)
                    if not logged:
                        report_unlogged(row, detail)
                    status_var.set(f"Selesai: {r['sampel']} sampel, clip {r['clip_pct']}%, "
                                   f"drop {r['drop']} gap {r['gap']}.\n{r['file']}")
                    messagebox.showinfo("Selesai", "Rekaman bersih.")
                    set_operation("idle")
                elif kind == "capture_error":
                    error = payload[0]
                    failed_path = error["path"]
                    reason = error["reason"]
                    if not error["can_delete"]:
                        status_var.set(f"Gagal: {error['message']}\nLokasi file: {failed_path}")
                        messagebox.showerror(
                            "Gagal",
                            f"{error['message']}\n\nLokasi file: {failed_path}",
                        )
                        set_operation("idle")
                        continue

                    set_operation("tool")
                    deleted, kept, delete_failed = make_file_actions(
                        failed_path, error["row"], reason, "putus")
                    show_file_action_dialog(
                        "Rekaman putus",
                        f"{error['message']}\n\n{failure_guidance(reason)}",
                        failed_path,
                        "Hapus file putus",
                        deleted,
                        kept,
                        delete_failed,
                    )
                elif kind == "error":
                    status_var.set(f"Gagal: {payload[0]}")
                    messagebox.showerror("Gagal", payload[0])
                    set_operation("idle")
        except queue.Empty:
            pass
        root.after(150, poll)

    def build_target() -> tuple[Path, dict, float]:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        hari = hari_var.get().strip()
        sesi = sesi_var.get()
        if not hari.isdigit():
            raise ValueError("Hari harus angka")
        dur = parse_duration(dur_var.get())
        if mode_var.get() == "Kontrol":
            jenis = jenis_var.get()
            out, meta = control_target(ROOT / "data", jenis, hari, sesi, dur, stamp)
            sibs = sorted(out.parent.glob(f"kontrol-sesi{sesi}_hari{hari}_*.wav"))
            if sibs and not messagebox.askyesno(
                    "Sudah ada", f"kontrol sesi {sesi} hari {hari} sudah ada:\n{sibs[-1].name}\nRekam lagi?"):
                raise CancelRecording("dibatalkan operator")
            return out, meta, dur

        jenis = jenis_var.get()
        plant = plant_var.get().strip()
        if not plant.isdigit():
            raise ValueError("Plants harus angka")
        meta = {"mode": "data", "jenis": jenis, "plant": plant, "hari": hari,
                "sesi": sesi, "posisi": "-"}
        out, meta = resolve_data_target(ROOT / "data", meta, dur, stamp)
        if meta["mode"] == "kontrol":
            mode_var.set("Kontrol")
            refresh_mode()
            status_var.set("Mode diubah ke Kontrol Sesi. Tekan Rekam untuk merekam kontrol.")
            return out, meta, dur
        sibs = sorted(out.parent.glob(f"{jenis}_P{plant}_hari{hari}_sesi{sesi}_*.wav"))
        if sibs and not messagebox.askyesno(
                "Sudah ada", f"P{plant} hari {hari} sesi {sesi} sudah ada:\n{sibs[-1].name}\nRekam lagi?"):
            raise CancelRecording("dibatalkan operator")
        return out, meta, dur

    def do_record(out: Path, meta: dict, dur: float, port: str, op: str) -> None:
        try:
            r = record_to(dur, port, out, stop_event, msgs)
            row = {"waktu": dt.datetime.now().strftime("%Y%m%d_%H%M%S"), **meta,
                   "durasi_s": dur, "file": relative_capture_path(out),
                   "sha256": r["sha"], "sampel": r["sampel"], "peak": r["peak"],
                   "gain": r["gain"],
                   "clip_pct": r["clip_pct"], "drop": r["drop"], "gap": r["gap"],
                   "operator": op, "box": "box1-tanpa-piring"}
            msgs.put(("done", r, row, out))
        except Exception as exc:  # noqa: BLE001 — tampil ke operator
            try:
                msgs.put(("capture_error", build_capture_error(out, meta, dur, op, exc)))
            except Exception as inner:  # noqa: BLE001 — jangan sampai GUI tersangkut
                msgs.put(("error", f"{type(inner).__name__}: {inner}"))

    def ask_missing_control(jenis: str, hari: str, sesi: str) -> str:
        """Three explicit choices; neither OK nor the X button starts recording."""
        dialog = tk.Toplevel(root)
        dialog.title("Belum ada kontrol")
        dialog.transient(root)
        dialog.resizable(True, False)
        dialog.grab_set()
        chosen = {"choice": "cancel"}

        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(f"{jenis} hari {hari} sesi {sesi} belum ada kontrol box kosong.\n\n"
                  "Kontrol jadi patokan pembanding. Tanpa kontrol, data sesi ini "
                  "sulit dipakai nanti.\n\nPilih:"),
            justify="left", wraplength=560,
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=("  1. Rekam kontrol dulu  (disarankan)\n"
                  "  2. Lanjut tanpa kontrol  (hanya kalau yakin)\n"
                  "  3. Batal"),
            justify="left", wraplength=560,
        ).pack(anchor="w", pady=(10, 0))

        def finish(choice: str) -> None:
            chosen["choice"] = choice
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Rekam kontrol dulu",
                   command=lambda: finish("control")).pack(side="left")
        ttk.Button(actions, text="Batal",
                   command=lambda: finish("cancel")).pack(side="left", padx=8)
        ttk.Button(actions, text="Lanjut tanpa kontrol",
                   command=lambda: finish("continue")).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish("cancel"))
        root.wait_window(dialog)
        choice = chosen["choice"]
        if choice not in CONTROL_CHOICES:
            raise ValueError(f"pilihan kontrol tidak dikenal: {choice!r}")
        return choice

    def on_start() -> None:
        nonlocal worker
        port = ensure_port()
        if not port:
            return
        try:
            out, meta, dur = build_target()
        except CancelRecording:
            status_var.set("Rekam dibatalkan. Tidak ada file yang dibuat.")
            return
        except ValueError as exc:
            messagebox.showerror("Salah", str(exc) or "Durasi/hari tidak valid")
            return
        stop_event.clear()
        for var, val in ((peak_now_var, "0"), (peak_max_var, "0"), (clip_var, "0,0000%"),
                         (drop_var, "0"), (gap_var, "0"), (gain_var, "-")):
            var.set(val)
        peak_bar["value"] = 0
        warn_var.set("Menunggu data...")
        status_var.set("Membuka port...")
        set_operation("recording")
        worker = threading.Thread(target=do_record,
                                  args=(out, meta, dur, port, op_var.get().strip() or "-"),
                                  daemon=True)
        worker.start()

    def on_stop() -> None:
        stop_event.set()
        status_var.set("Menghentikan...")

    def on_open_folder() -> None:
        target = ROOT / "data" / "raw_audio"
        target.mkdir(parents=True, exist_ok=True)
        open_in_file_manager(target)

    def on_window_close() -> None:
        nonlocal closing
        if can_close_window(active_operation):
            root.destroy()
            return
        if active_operation == "tool":
            messagebox.showwarning("Masih berjalan", "Tunggu proses alat selesai sebelum menutup aplikasi.")
            return
        if not messagebox.askyesno(
                "Rekaman masih berjalan",
                "Hentikan rekaman dan tutup aplikasi? File partial akan diberi peringatan saat aplikasi dibuka lagi."):
            return

        closing = True
        stop_event.set()
        set_operation("tool")
        status_var.set("Menghentikan rekaman sebelum aplikasi ditutup...")

        waited = {"seconds": 0}

        def tick_close() -> None:
            if worker is None or not worker.is_alive():
                root.destroy()
                return
            waited["seconds"] += 1
            if waited["seconds"] >= 8:
                status_var.set("Masih menunggu alat berhenti. Menutup paksa akan meninggalkan "
                               "file .wav.partial yang dilaporkan saat aplikasi dibuka lagi.")
            root.after(1000, tick_close)

        tick_close()

    def warn_startup_partials() -> None:
        partials = find_startup_partials(ROOT / "data")

        def show_next(index: int) -> None:
            path = pending_startup_partial(partials, index)
            if path is None:
                return

            def after_step(message: str) -> None:
                status_var.set(message)
                root.after_idle(lambda: show_next(index + 1))

            def deleted() -> None:
                after_step(f"File putus lama dihapus: {path}")

            def kept() -> None:
                after_step(f"File putus lama masih ada: {path}")

            def delete_failed(detail: str) -> None:
                after_step(f"File putus lama tidak terhapus: {path} ({detail})")

            show_file_action_dialog(
                "Rekaman putus sebelumnya",
                "Aplikasi menemukan rekaman yang putus sebelumnya. "
                "File ini tidak dihapus otomatis.",
                path,
                "Hapus file putus",
                deleted,
                kept,
                delete_failed,
            )

        show_next(0)

    start_btn.configure(command=on_start)
    stop_btn.configure(command=on_stop)
    open_btn.configure(command=on_open_folder)
    root.protocol("WM_DELETE_WINDOW", on_window_close)
    globals()["prompt_missing_control"] = ask_missing_control
    mode_var.trace_add("write", refresh_mode)
    refresh_mode()
    set_operation("idle")
    root.after(0, warn_startup_partials)
    root.after(150, poll)
    root.mainloop()


if __name__ == "__main__":
    main_gui()
