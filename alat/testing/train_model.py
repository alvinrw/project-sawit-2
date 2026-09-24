"""Latih model deteksi KOSONG / ADA TANAMAN.

Fitur : kontras relatif energi 24-26 kHz vs 20-22 kHz (1 dimensi, dB).
Model : StandardScaler + LogisticRegression, bobot per sesi seimbang
        (sesi panjang tidak boleh mendominasi — pelajaran dari label terbalik).
Evaluasi: leave-one-session-out (LOSO) — satu WAV = satu sesi; seluruh segmen
        sesi itu hanya diuji, tidak pernah ikut latih.

Varian MFCC 39-dim sempat diuji dan ditolak (LOSO 16,7% segmen — menghafal
gaya rekaman). Lihat laporan hasil di bawah.

Pemakaian:
    python train_model.py
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import joblib
import numpy as np

TESTING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTING_DIR))

from realtime_detector.config import LABEL_EMPTY, LABEL_PLANT
from realtime_detector.features import (
    _leave_session_out_accuracy,
    read_wav,
    segment_features,
)
from realtime_detector.ml import (
    FEATURE_DIM,
    MODEL_FILENAME,
    MODEL_VERSION,
    build_pipeline,
    contrast_features,
    plant_probability,
)

EMPTY_DIR = TESTING_DIR / "kosong"
PLANT_DIR = TESTING_DIR / "sawit_sehat"

MFCC_EXPERIMENT_NOTE = (
    "Eksperimen MFCC 39-dim + LogisticRegression: LOSO 16,7% segmen / 44,4% sesi "
    "— DITOLAK, menghafal gaya rekaman sesi, bukan kelas."
)


def load_sessions() -> list[tuple[int, str, np.ndarray, np.ndarray]]:
    """-> [(label, nama, fitur_kontras per segmen, bobot per segmen)]."""
    sessions: list[tuple[int, str, np.ndarray, np.ndarray]] = []
    for label, folder in ((0, EMPTY_DIR), (1, PLANT_DIR)):
        for path in sorted(folder.glob("*.wav")):
            features = contrast_features(segment_features(read_wav(path)))
            if features.shape[1] != FEATURE_DIM:
                raise ValueError(f"dimensi fitur tak terduga di {path.name}: {features.shape}")
            count = features.shape[0]
            # bobot = 1 jumlah segmen sesi → total bobot per kelas/sumbu = 1
            weights = np.full(count, 1.0 / count)
            sessions.append((label, path.name, features, weights))
    if not sessions:
        raise ValueError("tidak ada WAV kalibrasi")
    return sessions


def loso_ml(
    sessions: list[tuple[int, str, np.ndarray, np.ndarray]],
) -> tuple[float, float, list[str]]:
    rows: list[str] = []
    segment_correct = segment_total = session_correct = 0
    for held_out in range(len(sessions)):
        parts = [s for i, s in enumerate(sessions) if i != held_out]
        train_x = np.vstack([features for _, _, features, _ in parts])
        train_y = np.asarray(
            [label for label, _, features, _ in parts for _ in range(features.shape[0])]
        )
        train_w = np.concatenate([weights for _, _, _, weights in parts])
        train_w = train_w * (train_w.size / train_w.sum())
        pipeline = build_pipeline()
        pipeline.fit(train_x, train_y, clf__sample_weight=train_w)
        label, name, features, _ = sessions[held_out]
        probabilities = plant_probability(pipeline, features)
        predictions = (probabilities >= 0.5).astype(int)
        correct = int(np.count_nonzero(predictions == label))
        segment_correct += correct
        segment_total += predictions.size
        session_prediction = int(np.mean(probabilities) >= 0.5)
        session_correct += int(session_prediction == label)
        truth = LABEL_PLANT if label else LABEL_EMPTY
        guess = LABEL_PLANT if session_prediction else LABEL_EMPTY
        mark = "OK " if session_prediction == label else "SALAH"
        rows.append(
            f"  [{mark}] {name:<24} benar {correct:>2}/{predictions.size:<2} segmen · "
            f"prob rata-rata {np.mean(probabilities):.2f} · {truth} -> {guess}"
        )
    return segment_correct / segment_total, session_correct / len(sessions), rows


def baseline_loso_threshold() -> float | None:
    empty = [segment_features(read_wav(path)) for path in sorted(EMPTY_DIR.glob("*.wav"))]
    plant = [segment_features(read_wav(path)) for path in sorted(PLANT_DIR.glob("*.wav"))]
    return _leave_session_out_accuracy(empty, plant)


def holdout_predictions(pipeline) -> list[str]:
    """Uji file WAV di root testing/ (di luar data latih)."""
    rows = []
    for path in sorted(TESTING_DIR.glob("*.wav")):
        try:
            probabilities = plant_probability(
                pipeline, contrast_features(segment_features(read_wav(path)))
            )
        except ValueError as exc:
            rows.append(f"  {path.name:<28} dilewati: {exc}")
            continue
        mean = float(np.mean(probabilities))
        label = LABEL_PLANT if mean >= 0.5 else LABEL_EMPTY
        rows.append(f"  {path.name:<28} {label:<12} prob {mean:.2f}")
    if not rows:
        rows.append("  (tidak ada file WAV di root testing/)")
    return rows


def main() -> None:
    sessions = load_sessions()
    empty_count = sum(1 for label, _, _, _ in sessions if label == 0)
    plant_count = len(sessions) - empty_count

    segment_acc, session_acc, rows = loso_ml(sessions)
    baseline = baseline_loso_threshold()

    all_x = np.vstack([features for _, _, features, _ in sessions])
    all_y = np.asarray(
        [label for label, _, features, _ in sessions for _ in range(features.shape[0])]
    )
    all_w = np.concatenate([weights for _, _, _, weights in sessions])
    pipeline = build_pipeline()
    pipeline.fit(all_x, all_y, clf__sample_weight=all_w * (all_w.size / all_w.sum()))
    resubstitution = float(np.mean((pipeline.predict_proba(all_x)[:, 1] >= 0.5) == all_y))

    trained_at = dt.datetime.now().isoformat(timespec="seconds")
    meta = {
        "version": MODEL_VERSION,
        "trained_at": trained_at,
        "feature": "kontras 24-26 vs 20-22 kHz (dB)",
        "feature_dim": FEATURE_DIM,
        "sessions": {"empty": empty_count, "plant": plant_count},
        "segments_total": int(all_x.shape[0]),
        "loso_segment_accuracy": segment_acc,
        "loso_session_accuracy": session_acc,
        "baseline_threshold_loso": baseline,
        "resubstitution_accuracy": resubstitution,
    }
    joblib.dump({"pipeline": pipeline, "meta": meta}, TESTING_DIR / MODEL_FILENAME)

    lines = [
        "LAPORAN TRAINING MODEL",
        f"Waktu           : {trained_at}",
        f"Model           : {MODEL_VERSION} (kontras 24-26 vs 20-22 kHz + LogisticRegression)",
        f"Sesi            : {empty_count} kosong + {plant_count} tanaman "
        f"({all_x.shape[0]} segmen latih, bobot per sesi seimbang)",
        "",
        "Validasi LOSO (satu sesi diuji, sisanya latih):",
        *rows,
        "",
        f"Akurasi LOSO segmen : {segment_acc * 100:.1f}%",
        f"Akurasi LOSO sesi   : {session_acc * 100:.1f}% "
        f"({int(session_acc * len(sessions))}/{len(sessions)} sesi benar)",
        f"Baseline ambang lama : "
        + (f"{baseline * 100:.1f}%" if baseline is not None else "tidak tersedia"),
        f"Akurasi data latih   : {resubstitution * 100:.1f}% (bukan bukti generalisasi)",
        "",
        "Catatan eksperimen:",
        f"  - {MFCC_EXPERIMENT_NOTE}",
        "  - Band absolut (dBFS) ditolak juga: LOSO segmen 27-36% (level bervariasi antar sesi).",
        "",
        "File di root testing/ (di luar data latih):",
        *holdout_predictions(pipeline),
        "",
        "Catatan: angka LOSO adalah estimasi internal dengan sesi terbatas,",
        "bukan klaim akurasi lapangan.",
    ]
    report = "\n".join(lines)
    print(report)

    report_dir = TESTING_DIR / "hasil"
    report_dir.mkdir(exist_ok=True)
    (report_dir / "laporan_training_ml.txt").write_text(report, encoding="utf-8")
    print(f"\nModel disimpan: {TESTING_DIR / MODEL_FILENAME}")
    print(f"Laporan disimpan: {report_dir / 'laporan_training_ml.txt'}")


if __name__ == "__main__":
    main()
