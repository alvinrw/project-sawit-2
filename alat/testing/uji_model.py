"""Uji model MFCC pada file WAV mana pun.

Pemakaian:
    python uji_model.py                      # semua WAV di testing/ dan subfoldernya
    python uji_model.py path\\ke\\file.wav    # file tertentu saja

Keputusan: probabilitas rata-rata model per segmen.
>= 0.5 = ADA TANAMAN, < 0.5 = KOSONG.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

TESTING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTING_DIR))

from realtime_detector.config import LABEL_EMPTY, LABEL_PLANT
from realtime_detector.features import build_calibration, classify, read_wav, segment_features
from realtime_detector.ml import classify_ml, load_ml_model


def quality_of(probability: float, agreement: float, segments: int) -> str:
    if segments < 3:
        return "SEMENTARA"
    margin = abs(probability - 0.5) * 2.0
    return "BAIK" if agreement >= 2 / 3 and margin >= 0.4 else "LEMAH"


def truth_from_path(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "kosong" in parts:
        return LABEL_EMPTY
    if "sawit_sehat" in parts:
        return LABEL_PLANT
    return "?"


def default_files() -> list[Path]:
    files = sorted(TESTING_DIR.glob("*.wav"))
    files += sorted((TESTING_DIR / "kosong").glob("*.wav"))
    files += sorted((TESTING_DIR / "sawit_sehat").glob("*.wav"))
    return files


def main() -> None:
    payload, info = load_ml_model(TESTING_DIR)
    if payload is None:
        print(f"GAGAL: {info['detail']}")
        sys.exit(1)
    print(f"Model: {info['detail']}")
    if info.get("meta"):
        meta = info["meta"]
        print(
            f"Latih : {meta.get('trained_at')} · LOSO segmen "
            f"{(meta.get('loso_segment_accuracy') or 0) * 100:.1f}% · "
            f"LOSO sesi {(meta.get('loso_session_accuracy') or 0) * 100:.1f}%"
        )

    try:
        calibration = build_calibration(TESTING_DIR / "kosong", TESTING_DIR / "sawit_sehat")
    except ValueError:
        calibration = None

    args = [Path(arg) for arg in sys.argv[1:]]
    files = args if args else default_files()
    if not files:
        print("Tidak ada file WAV ditemukan.")
        sys.exit(1)

    print(f"\n{'FILE':<30} {'ASLI':<12} {'MODEL':<12} {'PROB':>5} {'KUALITAS':<11} {'AMBANG':<12}")
    print("-" * 88)
    correct = judged = 0
    for path in files:
        if not path.exists():
            print(f"{path.name:<30} tidak ditemukan")
            continue
        bands = segment_features(read_wav(path))
        result = classify_ml(bands, payload)
        label = result["label"]
        probability = result["probability"]
        agreement = result["agreement"]
        quality = result["quality"]
        truth = truth_from_path(path.resolve())
        if truth != "?":
            judged += 1
            correct += int(truth == label)
        threshold_label = "-"
        if calibration is not None:
            threshold_label = classify(bands, calibration)["label"]
        mark = "" if truth == "?" else ("[OK ]" if truth == label else "[SALAH]")
        print(
            f"{path.name:<30} {truth + mark:<12} {label:<12} {probability:>5.2f} "
            f"{quality:<11} {threshold_label:<12}"
        )

    print("-" * 88)
    if judged:
        print(
            f"Cocok label asli: {correct}/{judged} file "
            f"(file di folder = data latih; angka ini optimis, bukan bukti lapangan)"
        )
    print("AMBANG = keputusan metode kontras lama, untuk perbandingan.")


if __name__ == "__main__":
    main()
