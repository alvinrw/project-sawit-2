from __future__ import annotations

from dataclasses import dataclass


APP_TITLE = "PalmSonic — Deteksi Isi Box Real-time"
SAMPLE_RATE = 62_500
N_FFT = 2048
HOP = 512
SEGMENT_SECONDS = 10.0
STABLE_SEGMENTS = 3
STARTUP_IGNORE_SECONDS = 0.1
CLIP_LEVEL = 32_760
RAK_USB_VID = 0x239A
BANDS_HZ = ((20_000, 22_000), (22_000, 24_000), (24_000, 26_000), (26_000, 28_000))

LABEL_EMPTY = "KOSONG"
LABEL_PLANT = "ADA TANAMAN"


@dataclass
class Calibration:
    empty_center: float
    plant_center: float
    decision_threshold: float
    plant_above_threshold: bool
    confidence_band: float
    empty_segments: int
    plant_segments: int
    empty_files: int
    plant_files: int
    validation_accuracy: float | None
