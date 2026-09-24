from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np

from .config import LABEL_EMPTY, LABEL_PLANT

MODEL_FILENAME = "model.pkl"
# Varian MFCC 39-dim pernah diuji dan DITOLAK: LOSO hanya 16,7% segmen pada
# data 9 sesi (menghafal gaya rekaman, bukan kelas). Fitur kontras 24-26 vs
# 20-22 kHz dengan bobot sesi seimbang terbukti jauh lebih kuat dan jujur.
MODEL_VERSION = "kontras-logreg-v1"
FEATURE_DIM = 1


def contrast_features(band_features: np.ndarray) -> np.ndarray:
    """Fitur model: kontras relatif energi 24-26 kHz terhadap 20-22 kHz (dB)."""
    return (band_features[:, 2] - band_features[:, 0]).reshape(-1, 1)


def build_pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    C=1.0, max_iter=2000, class_weight="balanced", random_state=0
                ),
            ),
        ]
    )


def plant_probability(pipeline, features: np.ndarray) -> np.ndarray:
    plant_index = int(np.flatnonzero(pipeline.classes_ == 1)[0])
    return pipeline.predict_proba(features)[:, plant_index]


def load_ml_model(base_dir: Path) -> tuple[dict | None, dict]:
    path = Path(base_dir) / MODEL_FILENAME
    if not path.exists():
        return None, {"loaded": False, "detail": "model.pkl belum ada — jalankan train_model.py"}
    try:
        payload = joblib.load(path)
        if not isinstance(payload, dict) or "pipeline" not in payload:
            raise ValueError("format model tidak dikenal")
    except Exception as exc:
        return None, {"loaded": False, "detail": f"model gagal dimuat: {exc}"}
    meta = payload.get("meta", {})
    loso = meta.get("loso_session_accuracy")
    detail = f"model {MODEL_VERSION} aktif"
    if loso is not None:
        detail += f" · akurasi LOSO sesi {loso * 100:.0f}%"
    return payload, {"loaded": True, "detail": detail, "meta": meta}


def classify_ml(band_features: np.ndarray, payload: dict) -> dict:
    """Keputusan biner dari probabilitas model; kontras tetap ditampilkan."""
    probabilities = plant_probability(payload["pipeline"], contrast_features(band_features))
    plant_mean = float(np.mean(probabilities))
    plant_votes = int(np.count_nonzero(probabilities >= 0.5))
    empty_votes = int(probabilities.size - plant_votes)
    label = LABEL_PLANT if plant_mean >= 0.5 else LABEL_EMPTY
    contrasts = band_features[:, 2] - band_features[:, 0]
    contrast = float(np.median(contrasts))
    agreement = max(plant_votes, empty_votes) / probabilities.size
    margin = abs(plant_mean - 0.5) * 2.0
    if probabilities.size < 3:
        quality = "SEMENTARA"
    elif agreement >= 2 / 3 and margin >= 0.4:
        quality = "BAIK"
    else:
        quality = "LEMAH"
    return {
        "ml": True,
        "label": label,
        "probability": plant_mean,
        "empty_votes": empty_votes,
        "plant_votes": plant_votes,
        "segments": int(probabilities.size),
        "agreement": agreement,
        "margin": margin,
        "quality": quality,
        "contrast_db": contrast,
    }
