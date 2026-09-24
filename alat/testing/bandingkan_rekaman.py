#!/usr/bin/env python3
"""Bandingkan WAV acoustic box kosong dengan WAV sawit sehat.

Skrip ini tidak mengubah file WAV. Hasil analisis ditulis ke folder `hasil`.
Rentang utama 20-28 kHz dipilih karena firmware saat ini merekam 62.5 kS/s.
"""

from __future__ import annotations

import argparse
import csv
import math
import wave
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


DEFAULT_SAMPLE_RATE = 62_500
FREQ_LOW_HZ = 20_000.0
FREQ_HIGH_HZ = 28_000.0
N_FFT = 2048
HOP_LENGTH = 512
BATCH_FRAMES = 256
STARTUP_IGNORE_SECONDS = 0.1


@dataclass
class AudioResult:
    group: str
    path: Path
    sample_rate: int
    duration_s: float
    rms: float
    peak: float
    clipping_percent: float
    band_energy_dbfs: float
    noise_floor_dbfs: float
    event_threshold_dbfs: float
    candidate_events: int
    events_per_minute: float
    frame_count: int
    frequencies: np.ndarray
    mean_psd: np.ndarray
    band_times: np.ndarray
    band_db: np.ndarray


def read_pcm16_mono(path: Path) -> tuple[np.ndarray, int]:
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            compression = wav.getcomptype()
            raw = wav.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV rusak/tidak didukung: {exc}") from exc

    if channels != 1:
        raise ValueError(f"harus mono, ditemukan {channels} channel")
    if sample_width != 2:
        raise ValueError(f"harus PCM 16-bit, ditemukan {sample_width * 8}-bit")
    if compression != "NONE":
        raise ValueError(f"harus PCM tanpa kompresi, ditemukan {compression}")

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if samples.size < N_FFT:
        raise ValueError(f"terlalu pendek; minimal {N_FFT} sampel")
    return samples, sample_rate


def count_events(values_db: np.ndarray, threshold_db: float) -> int:
    """Hitung awal region aktif; angka ini kandidat, bukan label biologis."""
    active = values_db > threshold_db
    if not np.any(active):
        return 0
    starts = active & np.concatenate(([True], ~active[:-1]))
    return int(np.count_nonzero(starts))


def analyze_file(path: Path, group: str) -> AudioResult:
    samples, sample_rate = read_pcm16_mono(path)
    nyquist = sample_rate / 2.0
    if nyquist <= FREQ_LOW_HZ:
        raise ValueError(
            f"sample rate {sample_rate} Hz terlalu rendah untuk analisis 20 kHz"
        )

    high_hz = min(FREQ_HIGH_HZ, 0.90 * nyquist)
    startup_samples = min(
        int(STARTUP_IGNORE_SECONDS * sample_rate),
        max(0, samples.size - N_FFT),
    )
    analysis_samples = samples[startup_samples:]
    frequencies = np.fft.rfftfreq(N_FFT, d=1.0 / sample_rate)
    band_mask = (frequencies >= FREQ_LOW_HZ) & (frequencies <= high_hz)
    if not np.any(band_mask):
        raise ValueError("tidak ada bin FFT dalam rentang analisis")

    window = np.hanning(N_FFT).astype(np.float32)
    window_power = float(np.sum(window * window))
    df = sample_rate / N_FFT
    starts = np.arange(0, analysis_samples.size - N_FFT + 1, HOP_LENGTH)
    psd_sum = np.zeros(frequencies.size, dtype=np.float64)
    band_energy: list[np.ndarray] = []

    for offset in range(0, starts.size, BATCH_FRAMES):
        batch_starts = starts[offset : offset + BATCH_FRAMES]
        frames = np.stack([analysis_samples[s : s + N_FFT] for s in batch_starts])
        spectrum = np.fft.rfft(frames * window, axis=1)
        psd = (np.abs(spectrum) ** 2) / (sample_rate * window_power)
        if psd.shape[1] > 2:
            psd[:, 1:-1] *= 2.0
        psd_sum += psd.sum(axis=0)
        band_energy.append(psd[:, band_mask].sum(axis=1) * df)

    mean_psd = psd_sum / starts.size
    band_linear = np.concatenate(band_energy)
    band_db = 10.0 * np.log10(np.maximum(band_linear, 1e-20))
    median_db = float(np.median(band_db))
    mad_db = float(np.median(np.abs(band_db - median_db)))
    # Delapan MAD mengikuti pendekatan threshold konservatif pada panduan.
    threshold_db = median_db + 8.0 * max(mad_db, 0.25)
    events = count_events(band_db, threshold_db)

    duration_s = samples.size / sample_rate
    rms = float(np.sqrt(np.mean(samples * samples)))
    peak = float(np.max(np.abs(samples)))
    clipping_percent = float(100.0 * np.mean(np.abs(samples) >= (32760 / 32768)))
    mean_band_db = float(10.0 * np.log10(max(float(np.mean(band_linear)), 1e-20)))
    analysis_duration_s = analysis_samples.size / sample_rate
    events_per_minute = events / (analysis_duration_s / 60.0)
    times = (startup_samples + starts + N_FFT / 2) / sample_rate

    return AudioResult(
        group=group,
        path=path,
        sample_rate=sample_rate,
        duration_s=duration_s,
        rms=rms,
        peak=peak,
        clipping_percent=clipping_percent,
        band_energy_dbfs=mean_band_db,
        noise_floor_dbfs=median_db,
        event_threshold_dbfs=threshold_db,
        candidate_events=events,
        events_per_minute=events_per_minute,
        frame_count=int(starts.size),
        frequencies=frequencies,
        mean_psd=mean_psd,
        band_times=times,
        band_db=band_db,
    )


def find_wavs(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*.wav") if path.is_file())


def analyze_group(folder: Path, group: str) -> list[AudioResult]:
    files = find_wavs(folder)
    if not files:
        raise SystemExit(f"Tidak ada file WAV di: {folder.resolve()}")

    results: list[AudioResult] = []
    for index, path in enumerate(files, 1):
        print(f"[{group}] {index}/{len(files)}: {path.name}")
        try:
            results.append(analyze_file(path, group))
        except ValueError as exc:
            raise SystemExit(f"Gagal membaca {path}: {exc}") from exc
    return results


def require_matching_sample_rates(results: list[AudioResult]) -> int:
    rates = sorted({result.sample_rate for result in results})
    if len(rates) != 1:
        raise SystemExit(f"Sample rate tidak sama: {rates}. Jangan resample data raw.")
    return rates[0]


def write_csv(results: list[AudioResult], output: Path) -> None:
    fields = [
        "group",
        "file",
        "sample_rate_hz",
        "duration_s",
        "rms",
        "peak",
        "clipping_percent",
        "band_energy_20_28khz_dbfs",
        "noise_floor_dbfs",
        "event_threshold_dbfs",
        "candidate_events",
        "events_per_minute",
    ]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "group": result.group,
                    "file": str(result.path.resolve()),
                    "sample_rate_hz": result.sample_rate,
                    "duration_s": f"{result.duration_s:.6f}",
                    "rms": f"{result.rms:.9f}",
                    "peak": f"{result.peak:.9f}",
                    "clipping_percent": f"{result.clipping_percent:.6f}",
                    "band_energy_20_28khz_dbfs": f"{result.band_energy_dbfs:.6f}",
                    "noise_floor_dbfs": f"{result.noise_floor_dbfs:.6f}",
                    "event_threshold_dbfs": f"{result.event_threshold_dbfs:.6f}",
                    "candidate_events": result.candidate_events,
                    "events_per_minute": f"{result.events_per_minute:.6f}",
                }
            )


def group_mean_psd(results: list[AudioResult]) -> np.ndarray:
    return np.mean(np.stack([result.mean_psd for result in results]), axis=0)


def plot_spectrum(
    empty: list[AudioResult], healthy: list[AudioResult], output: Path
) -> None:
    freq = empty[0].frequencies
    empty_psd = group_mean_psd(empty)
    healthy_psd = group_mean_psd(healthy)

    fig, axis = plt.subplots(figsize=(11, 6))
    axis.plot(freq / 1000, 10 * np.log10(np.maximum(empty_psd, 1e-20)), label="Box kosong")
    axis.plot(
        freq / 1000,
        10 * np.log10(np.maximum(healthy_psd, 1e-20)),
        label="Sawit sehat",
    )
    axis.axvspan(FREQ_LOW_HZ / 1000, FREQ_HIGH_HZ / 1000, color="#f0b429", alpha=0.18)
    axis.set_xlim(0, freq[-1] / 1000)
    axis.set_xlabel("Frekuensi (kHz)")
    axis.set_ylabel("PSD rata-rata (dBFS/Hz)")
    axis.set_title("Perbandingan Spektrum Box Kosong dan Sawit Sehat")
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_metrics(
    empty: list[AudioResult], healthy: list[AudioResult], output: Path
) -> None:
    groups = [empty, healthy]
    labels = ["Box kosong", "Sawit sehat"]
    energy = [np.mean([r.band_energy_dbfs for r in group]) for group in groups]
    events = [np.mean([r.events_per_minute for r in group]) for group in groups]

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    axes[0].bar(labels, energy, color=["#777777", "#2d8659"])
    axes[0].set_ylabel("Energi rata-rata (dBFS)")
    axes[0].set_title("Energi 20-28 kHz")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(labels, events, color=["#777777", "#2d8659"])
    axes[1].set_ylabel("Kandidat event per menit")
    axes[1].set_title("Kandidat Klik Ultrasonik")
    axes[1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def mean_metric(results: list[AudioResult], name: str) -> float:
    return float(np.mean([getattr(result, name) for result in results]))


def write_report(
    empty: list[AudioResult], healthy: list[AudioResult], sample_rate: int, output: Path
) -> None:
    empty_energy = mean_metric(empty, "band_energy_dbfs")
    healthy_energy = mean_metric(healthy, "band_energy_dbfs")
    empty_events = mean_metric(empty, "events_per_minute")
    healthy_events = mean_metric(healthy, "events_per_minute")
    energy_difference = healthy_energy - empty_energy

    if energy_difference >= 3.0:
        interpretation = (
            "Energi 20-28 kHz pada rekaman sawit lebih tinggi setidaknya 3 dB dari box kosong. "
            "Ada perbedaan yang layak diperiksa lebih lanjut, tetapi belum membuktikan bahwa "
            "sumbernya adalah emisi biologis tanaman."
        )
    elif energy_difference <= -3.0:
        interpretation = (
            "Energi 20-28 kHz pada rekaman sawit lebih rendah daripada box kosong. Keberadaan "
            "pot/tanaman dapat mengubah akustik box; ulangi pengukuran dan periksa penempatan sensor."
        )
    else:
        interpretation = (
            "Energi 20-28 kHz box kosong dan sawit sehat masih mirip. Belum ada perbedaan kuat "
            "pada pilot ini; tambah durasi dan jumlah pengulangan sebelum menyimpulkan."
        )

    text = f"""LAPORAN PERBANDINGAN PILOT

Sample rate       : {sample_rate} Hz
Rentang analisis  : {FREQ_LOW_HZ/1000:.0f}-{FREQ_HIGH_HZ/1000:.0f} kHz
Transien diabaikan: {STARTUP_IGNORE_SECONDS:.1f} detik pertama
File box kosong   : {len(empty)}
File sawit sehat  : {len(healthy)}

Energi box kosong : {empty_energy:.3f} dBFS
Energi sawit sehat: {healthy_energy:.3f} dBFS
Selisih sawit-box : {energy_difference:+.3f} dB

Event box kosong  : {empty_events:.3f} kandidat/menit
Event sawit sehat : {healthy_events:.3f} kandidat/menit

Interpretasi awal
-----------------
{interpretation}

Peringatan
----------
Ini hanya membandingkan acoustic box kosong dengan box berisi pot dan sawit sehat.
Perbedaan dapat berasal dari tanaman, pot, tanah, perubahan pantulan suara, atau noise.
Hasil ini belum membuktikan kondisi sehat/sakit dan belum boleh dipakai sebagai klaim biologis.
"""
    output.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Bandingkan WAV box kosong dengan WAV sawit sehat."
    )
    parser.add_argument("--kosong", type=Path, default=base / "kosong")
    parser.add_argument("--sawit", type=Path, default=base / "sawit_sehat")
    parser.add_argument("--hasil", type=Path, default=base / "hasil")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.hasil.mkdir(parents=True, exist_ok=True)

    empty = analyze_group(args.kosong, "kosong")
    healthy = analyze_group(args.sawit, "sawit_sehat")
    all_results = empty + healthy
    sample_rate = require_matching_sample_rates(all_results)

    if sample_rate != DEFAULT_SAMPLE_RATE:
        print(
            f"PERINGATAN: sample rate {sample_rate} Hz, bukan {DEFAULT_SAMPLE_RATE} Hz "
            "seperti firmware saat ini."
        )

    write_csv(all_results, args.hasil / "ringkasan.csv")
    plot_spectrum(empty, healthy, args.hasil / "perbandingan_spektrum.png")
    plot_metrics(empty, healthy, args.hasil / "perbandingan_metric.png")
    write_report(empty, healthy, sample_rate, args.hasil / "laporan.txt")

    print("\nAnalisis selesai. Hasil tersimpan di:")
    print(args.hasil.resolve())
    print("- ringkasan.csv")
    print("- perbandingan_spektrum.png")
    print("- perbandingan_metric.png")
    print("- laporan.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
