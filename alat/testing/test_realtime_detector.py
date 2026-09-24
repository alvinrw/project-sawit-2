from __future__ import annotations

import struct
import sys
import threading
import unittest
from pathlib import Path

import numpy as np

TESTING_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTING_DIR))

from realtime_detector.config import LABEL_EMPTY, LABEL_PLANT, SAMPLE_RATE
from realtime_detector.features import build_calibration, classify, read_wav, segment_features
from realtime_detector.protocol import HEADER, MAGIC, PacketReader


class FakeSerial:
    def __init__(self, payload: bytes):
        self.payload = bytearray(payload)

    def read(self, size: int) -> bytes:
        chunk = bytes(self.payload[:size])
        del self.payload[:size]
        return chunk


class DetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calibration = build_calibration(TESTING_DIR / "kosong", TESTING_DIR / "sawit_sehat")

    def assert_file_label(self, relative_path: str, expected: str):
        features = segment_features(read_wav(TESTING_DIR / relative_path))
        result = classify(features, self.calibration)
        self.assertEqual(result["label"], expected)
        self.assertEqual(result["quality"], "BAIK")

    def test_leave_session_out_validation(self):
        self.assertEqual(self.calibration.validation_accuracy, 1.0)

    def test_all_labeled_sessions(self):
        self.assert_file_label("kosong/Kosong.wav", LABEL_EMPTY)
        self.assert_file_label("kosong/kosong_02.wav", LABEL_EMPTY)
        self.assert_file_label("sawit_sehat/sawit.wav", LABEL_PLANT)
        self.assert_file_label("sawit_sehat/sawit_02.wav", LABEL_PLANT)

    def test_uniform_level_shift_does_not_change_label(self):
        features = segment_features(read_wav(TESTING_DIR / "kosong/Kosong.wav"))[:3]
        original = classify(features, self.calibration)["label"]
        shifted = classify(features + 20.0, self.calibration)["label"]
        self.assertEqual(original, LABEL_EMPTY)
        self.assertEqual(shifted, original)

    def test_new_trials_not_used_for_calibration(self):
        expected = {
            "realtime_kosong.wav": LABEL_EMPTY,
            "realtime_ada.wav": LABEL_PLANT,
            "realtime_ada1.wav": LABEL_PLANT,
            "realtime_ada3.wav": LABEL_PLANT,
        }
        for name, label in expected.items():
            path = TESTING_DIR / name
            if path.exists():
                self.assert_file_label(name, label)

    def test_binary_packet_parser(self):
        pcm = struct.pack("<hhhh", 10, -20, 300, -400)
        header = HEADER.pack(MAGIC, 1, 0, HEADER.size, 7, SAMPLE_RATE, 4, 80, 0)
        reader = PacketReader(FakeSerial(b"noise" + header + pcm), threading.Event())
        sequence, count, gain, dropped, parsed_pcm = reader.read()
        self.assertEqual((sequence, count, gain, dropped), (7, 4, 80, 0))
        self.assertEqual(parsed_pcm, pcm)

    def test_ml_model_matches_reference_files(self):
        from realtime_detector.ml import classify_ml, load_ml_model

        payload, info = load_ml_model(TESTING_DIR)
        if payload is None:
            self.skipTest(info["detail"])
        for name, expected in (
            ("kosong/Kosong.wav", LABEL_EMPTY),
            ("kosong/kosong_02.wav", LABEL_EMPTY),
            ("sawit_sehat/sawit.wav", LABEL_PLANT),
            ("sawit_sehat/sawit_02.wav", LABEL_PLANT),
        ):
            result = classify_ml(segment_features(read_wav(TESTING_DIR / name)), payload)
            self.assertEqual(result["label"], expected)
            self.assertTrue(0.0 <= result["probability"] <= 1.0)

    def test_gui_module_imports(self):
        import realtime_detector.gui  # noqa: F401


if __name__ == "__main__":
    unittest.main()
