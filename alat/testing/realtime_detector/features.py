from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .config import (
    BANDS_HZ,
    HOP,
    LABEL_EMPTY,
    LABEL_PLANT,
    N_FFT,
    SAMPLE_RATE,
    SEGMENT_SECONDS,
    STARTUP_IGNORE_SECONDS,
    Calibration,
)


def read_wav(path: Path) -> np.ndarray:
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                raise ValueError("WAV harus PCM 16-bit mono tanpa kompresi")
            if wav.getframerate() != SAMPLE_RATE:
                raise ValueError(f"sample rate harus {SAMPLE_RATE} Hz")
            raw = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV rusak: {exc}") from exc
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def segment_features(
    samples: np.ndarray,
    segment_seconds: float = SEGMENT_SECONDS,
    ignore_seconds: float = STARTUP_IGNORE_SECONDS,
) -> np.ndarray:
    ignore = min(int(ignore_seconds * SAMPLE_RATE), samples.size)
    samples = samples[ignore:]
    segment_size = int(segment_seconds * SAMPLE_RATE)
    count = samples.size // segment_size
    if count < 1:
        raise ValueError(f"rekaman harus minimal {segment_seconds + ignore_seconds:.1f} detik")

    frequencies = np.fft.rfftfreq(N_FFT, d=1.0 / SAMPLE_RATE)
    masks = [(frequencies >= low) & (frequencies < high) for low, high in BANDS_HZ]
    window = np.hanning(N_FFT).astype(np.float32)
    window_power = float(np.sum(window * window))
    df = SAMPLE_RATE / N_FFT
    result = []

    for index in range(count):
        segment = samples[index * segment_size : (index + 1) * segment_size]
        starts = np.arange(0, segment.size - N_FFT + 1, HOP)
        sums = np.zeros(len(BANDS_HZ), dtype=np.float64)
        frames_total = 0
        for offset in range(0, starts.size, 256):
            batch = starts[offset : offset + 256]
            frames = np.stack([segment[start : start + N_FFT] for start in batch])
            spectrum = np.fft.rfft(frames * window, axis=1)
            psd = np.abs(spectrum) ** 2 / (SAMPLE_RATE * window_power)
            psd[:, 1:-1] *= 2.0
            for band_index, mask in enumerate(masks):
                sums[band_index] += float(np.sum(psd[:, mask])) * df
            frames_total += frames.shape[0]
        result.append(10.0 * np.log10(np.maximum(sums / frames_total, 1e-20)))
    return np.asarray(result)


def _contrast(features: np.ndarray) -> np.ndarray:
    """Energi relatif 24-26 kHz terhadap 20-22 kHz dalam dB."""
    return features[:, 2] - features[:, 0]


def _load_folder(folder: Path) -> list[np.ndarray]:
    files = sorted(path for path in folder.rglob("*.wav") if path.is_file())
    if not files:
        raise ValueError(f"tidak ada WAV di {folder}")
    return [segment_features(read_wav(path)) for path in files]


def _model_parts(
    empty_sessions: list[np.ndarray], plant_sessions: list[np.ndarray]
) -> tuple[float, float, float, bool, float]:
    empty_values = np.asarray([np.median(_contrast(session)) for session in empty_sessions])
    plant_values = np.asarray([np.median(_contrast(session)) for session in plant_sessions])
    empty_center = float(np.median(empty_values))
    plant_center = float(np.median(plant_values))
    plant_above = plant_center > empty_center

    # Nol mempunyai arti alami: kedua pita memiliki energi sama. Pakai nol bila
    # seluruh median sesi kedua kelas memang mengapitnya; selain itu gunakan
    # titik tengah antara dua pusat kelas.
    separated_at_zero = (
        np.max(empty_values) < 0.0 < np.min(plant_values)
        if plant_above
        else np.max(plant_values) < 0.0 < np.min(empty_values)
    )
    threshold = 0.0 if separated_at_zero else (empty_center + plant_center) / 2.0
    all_values = np.concatenate((empty_values, plant_values))
    # Zona lemah berada dekat batas keputusan. Setengah jarak sesi referensi
    # terdekat menjaga seluruh referensi tetap di luar zona tersebut.
    confidence_band = max(0.25, 0.5 * float(np.min(np.abs(all_values - threshold))))
    return empty_center, plant_center, threshold, plant_above, confidence_band


def _predict_segments(
    raw_features: np.ndarray,
    threshold: float,
    plant_above: bool,
) -> np.ndarray:
    values = _contrast(raw_features)
    is_plant = values > threshold if plant_above else values < threshold
    return np.where(is_plant, LABEL_PLANT, LABEL_EMPTY)


def _leave_session_out_accuracy(
    empty_sessions: list[np.ndarray], plant_sessions: list[np.ndarray]
) -> float | None:
    if len(empty_sessions) < 2 or len(plant_sessions) < 2:
        return None
    correct = total = 0
    for index, held_out in enumerate(empty_sessions):
        train_empty = [session for i, session in enumerate(empty_sessions) if i != index]
        _, _, threshold, plant_above, _ = _model_parts(train_empty, plant_sessions)
        predictions = _predict_segments(held_out, threshold, plant_above)
        correct += int(np.count_nonzero(predictions == LABEL_EMPTY))
        total += predictions.size
    for index, held_out in enumerate(plant_sessions):
        train_plant = [session for i, session in enumerate(plant_sessions) if i != index]
        _, _, threshold, plant_above, _ = _model_parts(empty_sessions, train_plant)
        predictions = _predict_segments(held_out, threshold, plant_above)
        correct += int(np.count_nonzero(predictions == LABEL_PLANT))
        total += predictions.size
    return correct / total if total else None


def build_calibration(empty_folder: Path, plant_folder: Path) -> Calibration:
    empty_sessions = _load_folder(empty_folder)
    plant_sessions = _load_folder(plant_folder)
    empty_center, plant_center, threshold, plant_above, confidence_band = _model_parts(
        empty_sessions, plant_sessions
    )
    return Calibration(
        empty_center=empty_center,
        plant_center=plant_center,
        decision_threshold=threshold,
        plant_above_threshold=plant_above,
        confidence_band=confidence_band,
        empty_segments=sum(session.shape[0] for session in empty_sessions),
        plant_segments=sum(session.shape[0] for session in plant_sessions),
        empty_files=len(empty_sessions),
        plant_files=len(plant_sessions),
        validation_accuracy=_leave_session_out_accuracy(empty_sessions, plant_sessions),
    )


def classify(features: np.ndarray, calibration: Calibration) -> dict:
    contrasts = _contrast(features)
    predictions = _predict_segments(
        features, calibration.decision_threshold, calibration.plant_above_threshold
    )
    plant_votes = int(np.count_nonzero(predictions == LABEL_PLANT))
    contrast = float(np.median(contrasts))
    is_plant = (
        contrast > calibration.decision_threshold
        if calibration.plant_above_threshold
        else contrast < calibration.decision_threshold
    )
    label = LABEL_PLANT if is_plant else LABEL_EMPTY
    empty_distance = abs(contrast - calibration.empty_center)
    plant_distance = abs(contrast - calibration.plant_center)
    margin = abs(contrast - calibration.decision_threshold) / calibration.confidence_band
    agreement = max(plant_votes, features.shape[0] - plant_votes) / features.shape[0]
    if features.shape[0] < 3:
        quality = "SEMENTARA"
    elif agreement >= 2 / 3 and margin >= 1.0:
        quality = "BAIK"
    else:
        quality = "LEMAH"
    return {
        "label": label,
        "empty_votes": int(features.shape[0] - plant_votes),
        "plant_votes": plant_votes,
        "empty_distance": empty_distance,
        "plant_distance": plant_distance,
        "margin": margin,
        "segments": features.shape[0],
        "agreement": agreement,
        "decision_threshold": calibration.decision_threshold,
        "quality": quality,
        "contrast_db": contrast,
    }
