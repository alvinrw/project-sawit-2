from __future__ import annotations

import importlib.util
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rekam.py"
SPEC = importlib.util.spec_from_file_location("rekam_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
rekam = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rekam)


class PartialFileHelpersTests(unittest.TestCase):
    def test_partial_path_marks_in_progress_capture(self) -> None:
        self.assertEqual(
            rekam.partial_path(Path("hasil.wav")),
            Path("hasil.wav.partial"),
        )

    def test_find_partial_files_returns_sorted_partial_wavs_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "z.wav.partial").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "a.wav.partial").touch()
            (root / "normal.wav").touch()

            self.assertEqual(
                rekam.find_partial_files(root),
                [nested / "a.wav.partial", root / "z.wav.partial"],
            )

    def test_delete_capture_file_removes_existing_failed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            failed_file = Path(temp_dir) / "gagal.wav"
            failed_file.write_bytes(b"failed capture")

            ok, detail = rekam.delete_capture_file(failed_file)

            self.assertTrue(ok)
            self.assertEqual(detail, "")
            self.assertFalse(failed_file.exists())

    def test_delete_capture_file_reports_permission_error_without_false_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            failed_file = Path(temp_dir) / "gagal.wav"
            failed_file.write_bytes(b"failed capture")

            with patch.object(Path, "unlink", side_effect=PermissionError("ditolak")):
                ok, detail = rekam.delete_capture_file(failed_file)

            self.assertFalse(ok)
            self.assertIn("ditolak", detail)
            self.assertTrue(failed_file.exists())


class PacketTimeoutTests(unittest.TestCase):
    def test_read_packet_times_out_when_serial_stays_silent(self) -> None:
        class SilentSerial:
            def read(self, _size: int) -> bytes:
                return b""

        with patch.object(rekam.time, "monotonic", return_value=10.0):
            with self.assertRaisesRegex(TimeoutError, "tidak mengirim audio"):
                rekam._read_packet(
                    SilentSerial(),
                    bytearray(),
                    threading.Event(),
                    no_data_deadline=9.0,
                )

    def test_record_to_keeps_partial_when_audio_stops_mid_capture(self) -> None:
        pcm = struct.pack("<" + "h" * 256, *([0] * 256))
        header = rekam.sawt.HEADER.pack(
            rekam.sawt.MAGIC,
            rekam.sawt.PROTOCOL_VERSION,
            0,
            rekam.sawt.HEADER.size,
            0,
            62500,
            256,
            80,
            0,
        )

        class OnePacketThenSilentSerial:
            def __init__(self) -> None:
                self.started = False
                self.payload = bytearray(header + pcm)
                self.writes: list[bytes] = []

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def set_buffer_size(self, **_kwargs) -> None:
                return None

            def reset_input_buffer(self) -> None:
                return None

            def write(self, data: bytes) -> int:
                self.writes.append(data)
                if data == b"R":
                    self.started = True
                return len(data)

            def flush(self) -> None:
                return None

            def read(self, size: int) -> bytes:
                if not self.started or not self.payload:
                    return b""
                result = bytes(self.payload[:size])
                del self.payload[:size]
                return result

        fake_serial = OnePacketThenSilentSerial()
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "putus.wav"
            with patch("serial.Serial", return_value=fake_serial), patch.object(rekam.time, "sleep"):
                with self.assertRaisesRegex(TimeoutError, "tidak mengirim audio"):
                    rekam.record_to(
                        0.01,
                        "COM15",
                        out,
                        threading.Event(),
                        no_audio_timeout=0.01,
                    )

            self.assertFalse(out.exists())
            self.assertTrue(rekam.partial_path(out).exists())
            self.assertIn(b"S", fake_serial.writes)


class DurationOptionTests(unittest.TestCase):
    def test_offered_durations_include_ten_minutes(self) -> None:
        self.assertEqual(
            rekam.DURASI,
            ["10", "15", "20", "25", "30", "60", "120", "300", "600"],
        )

    def test_duration_field_accepts_a_manually_typed_value(self) -> None:
        self.assertEqual(rekam.parse_duration("10"), 10.0)
        self.assertEqual(rekam.parse_duration("600"), 600.0)
        self.assertEqual(rekam.parse_duration(" 45 "), 45.0)
        self.assertEqual(rekam.parse_duration("90.5"), 90.5)

    def test_duration_rejects_blank_and_non_numeric_input(self) -> None:
        for bad in ("", "   ", "abc", "10abc", "-5", "1,5"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    rekam.parse_duration(bad)

    def test_duration_label_reads_as_minutes_above_sixty_seconds(self) -> None:
        self.assertEqual(rekam.duration_label(20), "20 detik")
        self.assertEqual(rekam.duration_label(60), "1 menit")
        self.assertEqual(rekam.duration_label(120), "2 menit")
        self.assertEqual(rekam.duration_label(600), "10 menit")

    def test_duration_suffix_keeps_file_names_in_seconds(self) -> None:
        self.assertEqual(rekam.duration_suffix(20), "20s")
        self.assertEqual(rekam.duration_suffix(600), "600s")
        self.assertEqual(rekam.duration_suffix(90.5), "90.5s")


class MissingControlPromptTests(unittest.TestCase):
    META = {"mode": "data", "jenis": "kosong", "plant": "1",
            "hari": "1", "sesi": "1", "posisi": "-"}

    def test_default_prompt_returns_a_bare_string_the_caller_can_unpack(self) -> None:
        # A GUI override that returned a tuple here caused
        # "too many values to unpack" at record time, so the contract is pinned.
        result = rekam.prompt_missing_control("kosong", "1", "1")
        self.assertIsInstance(result, str)
        self.assertIn(result, rekam.CONTROL_CHOICES)

    def test_every_documented_choice_is_accepted(self) -> None:
        self.assertEqual(
            sorted(rekam.CONTROL_CHOICES),
            ["cancel", "continue", "control"],
        )

    def control_exists(self, root: Path) -> bool:
        controls = root / "controls" / "kosong" / "hari-1"
        return any(controls.glob("kontrol-sesi1_hari1_*.wav")) if controls.is_dir() else False

    def test_recording_is_refused_when_the_operator_cancels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(rekam, "prompt_missing_control",
                              return_value="cancel") as prompt:
                with self.assertRaises(rekam.CancelRecording):
                    rekam.resolve_data_target(root, self.META, 20.0, "20260928_080000")
            prompt.assert_called_once()

    def test_recording_proceeds_when_the_operator_continues_without_control(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(rekam, "prompt_missing_control",
                              return_value="continue"):
                out, meta = rekam.resolve_data_target(root, self.META, 20.0, "20260928_080000")
            self.assertTrue(out.name.startswith("kosong_P1_hari1_sesi1_20s_"))
            self.assertEqual(meta["jenis"], "kosong")

    def test_recording_proceeds_without_asking_when_the_control_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            controls = root / "controls" / "kosong" / "hari-1"
            controls.mkdir(parents=True)
            (controls / "kontrol-sesi1_hari1_20s_20260928_080000.wav").touch()

            with patch.object(rekam, "prompt_missing_control") as prompt:
                out, _ = rekam.resolve_data_target(root, self.META, 20.0, False)

            prompt.assert_not_called()
            self.assertTrue(out.name.startswith("kosong_P1_hari1_sesi1_20s_"))

    def test_recording_jumps_to_the_control_target_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(rekam, "prompt_missing_control",
                              return_value="control"):
                out, meta = rekam.resolve_data_target(root, self.META, 20.0, "20260928_080000")

            self.assertEqual(meta["mode"], "kontrol")
            self.assertEqual(meta["plant"], "-")
            self.assertEqual(meta["posisi"], "awal")
            self.assertEqual(out.parent.parent.parent, root / "controls")
            self.assertIn("kontrol-sesi1_hari1_20s_", out.name)

    def test_control_target_keeps_jenis_hari_sesi_and_uses_ten_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(rekam, "prompt_missing_control",
                              return_value="continue"):
                out, _ = rekam.resolve_data_target(root, self.META, 600.0, "20260928_080000")

            self.assertIn("600s_", out.name)

    def test_ten_minute_file_name_stays_in_seconds_not_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            out, _ = rekam.data_target(root, "kosong", "1", "1", "1", 600.0, "20260928_080000")
            self.assertIn("600s_", out.name)
            self.assertNotIn("10m", out.name)


class OperationButtonStateTests(unittest.TestCase):
    def test_idle_enables_start_only(self) -> None:
        self.assertEqual(
            rekam.operation_button_states("idle"),
            {"start": "normal", "stop": "disabled"},
        )

    def test_recording_disables_start(self) -> None:
        self.assertEqual(
            rekam.operation_button_states("recording"),
            {"start": "disabled", "stop": "normal"},
        )

    def test_tool_disables_both_controls(self) -> None:
        self.assertEqual(
            rekam.operation_button_states("tool"),
            {"start": "disabled", "stop": "disabled"},
        )

    def test_unknown_operation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "operasi tidak dikenal"):
            rekam.operation_button_states("unknown")

    def test_window_can_close_directly_only_when_idle(self) -> None:
        self.assertTrue(rekam.can_close_window("idle"))
        self.assertFalse(rekam.can_close_window("recording"))
        self.assertFalse(rekam.can_close_window("tool"))


class CaptureFailurePayloadTests(unittest.TestCase):
    def test_failure_payload_shows_existing_partial_and_allows_its_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "putus.wav"
            partial = rekam.partial_path(out)
            partial.write_bytes(b"unfinished wav")

            payload = rekam.capture_failure_payload(out, TimeoutError("tidak mengirim audio"))

            self.assertEqual(payload["path"], partial)
            self.assertTrue(payload["can_delete"])
            self.assertEqual(payload["reason"], "tidak mengirim audio")
            self.assertIn("TimeoutError", payload["message"])

    def test_failure_payload_does_not_allow_deleting_existing_final_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "sudah-ada.wav"
            out.write_bytes(b"valid earlier capture")

            payload = rekam.capture_failure_payload(out, FileExistsError("tolak overwrite"))

            self.assertEqual(payload["path"], out)
            self.assertFalse(payload["can_delete"])

    def test_failure_status_keeps_action_and_explicit_reason(self) -> None:
        self.assertEqual(
            rekam.failure_status("gagal-dihapus", "gap 1"),
            "gagal-dihapus: gap 1",
        )


class FailureGuidanceTests(unittest.TestCase):
    def test_transport_failure_guidance_mentions_usb_checks(self) -> None:
        guidance = rekam.failure_guidance("blok hilang (drop 0 gap 1)")
        self.assertIn("kabel USB", guidance)
        self.assertIn("Serial Monitor", guidance)

    def test_signal_failure_guidance_mentions_box_cleaning_and_waiting(self) -> None:
        guidance = rekam.failure_guidance("clipping 0.12%")
        self.assertIn("box", guidance)
        self.assertIn("serangga", guidance)
        self.assertIn("2 menit", guidance)

    def test_guidance_covers_both_problem_kinds_in_one_failure(self) -> None:
        guidance = rekam.failure_guidance("blok hilang (drop 0 gap 1), clipping 0.02%")
        self.assertIn("kabel USB", guidance)
        self.assertIn("serangga", guidance)


class FailureRowContractTests(unittest.TestCase):
    META = {"mode": "data", "jenis": "kosong", "plant": "1",
            "hari": "1", "sesi": "1", "posisi": "-"}

    def test_relative_capture_path_uses_recorder_relative_path(self) -> None:
        inside = rekam.ROOT / "data" / "raw_audio" / "kosong" / "hari-1" / "a.wav"
        self.assertEqual(
            rekam.relative_capture_path(inside),
            "data/raw_audio/kosong/hari-1/a.wav",
        )

    def test_relative_capture_path_survives_a_path_outside_the_project(self) -> None:
        outside = Path("D:/lain/hasil.wav.partial")
        self.assertEqual(rekam.relative_capture_path(outside), "D:/lain/hasil.wav.partial")

    def test_failure_row_fills_exactly_the_csv_header_columns(self) -> None:
        row = rekam.build_failure_row(self.META, 20.0, "-", Path("data/x.wav.partial"))
        self.assertEqual(set(row), set(rekam.CSV_HEADER))
        self.assertEqual(row["file"], "data/x.wav.partial")
        self.assertEqual(row["sha256"], "")
        self.assertEqual(row["status"], "")

    def test_capture_error_payload_always_carries_a_loggable_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "putus.wav"
            rekam.partial_path(out).write_bytes(b"unfinished wav")

            payload = rekam.build_capture_error(
                out, self.META, 20.0, "-", TimeoutError("tidak mengirim audio")
            )

            self.assertTrue(payload["can_delete"])
            self.assertEqual(set(payload["row"]), set(rekam.CSV_HEADER))
            self.assertIn("tidak mengirim audio", payload["reason"])


class CsvWriteSafetyTests(unittest.TestCase):
    def test_log_row_reports_success(self) -> None:
        with patch.object(rekam, "log_csv") as log_csv:
            ok, detail = rekam.log_row({"status": "bersih"})
        self.assertTrue(ok)
        self.assertEqual(detail, "")
        log_csv.assert_called_once()

    def test_log_row_reports_disk_failure_instead_of_raising(self) -> None:
        with patch.object(rekam, "log_csv", side_effect=OSError("disk penuh")):
            ok, detail = rekam.log_row({"status": "putus-dihapus:Dhentikan"})
        self.assertFalse(ok)
        self.assertIn("disk penuh", detail)


class StartupPartialScanTests(unittest.TestCase):
    def test_find_startup_partials_scans_only_recording_data_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir) / "data"
            raw = data_root / "raw_audio" / "air-normal"
            controls = data_root / "controls" / "air-normal"
            pilot = data_root / "pilot_test"
            ignored = data_root / "other"
            for folder in (raw, controls, pilot, ignored):
                folder.mkdir(parents=True)

            raw_partial = raw / "raw.wav.partial"
            control_partial = controls / "control.wav.partial"
            pilot_partial = pilot / "pilot.wav.partial"
            ignored_partial = ignored / "ignore.wav.partial"
            for path in (raw_partial, control_partial, pilot_partial, ignored_partial):
                path.touch()

            self.assertEqual(
                rekam.find_startup_partials(data_root),
                sorted([raw_partial, control_partial, pilot_partial]),
            )

    def test_first_startup_step_offers_the_first_leftover_partial(self) -> None:
        first = Path("data/a.wav.partial")
        second = Path("data/b.wav.partial")
        self.assertEqual(rekam.pending_startup_partial([first, second], 0), first)
        self.assertEqual(rekam.pending_startup_partial([first, second], 1), second)
        self.assertIsNone(rekam.pending_startup_partial([first, second], 2))
        self.assertIsNone(rekam.pending_startup_partial([], 0))


class StandaloneProtocolTests(unittest.TestCase):
    """rekam-new harus jalan tanpa clone referensi eksternal."""

    def setUp(self) -> None:
        self.protocol = rekam.sawt

    def test_header_layout_matches_firmware_header_size(self) -> None:
        header_text = (rekam.ROOT / "src" / "firmware" / "RawSawitRecorder"
                       / "sawt_protocol.h").read_text(encoding="utf-8")
        self.assertIn(f"SAWT_HEADER_SIZE = {self.protocol.HEADER.size}", header_text)
        self.assertIn(f"SAWT_PROTOCOL_VERSION = {self.protocol.PROTOCOL_VERSION}", header_text)
        self.assertIn(f"SAWT_SAMPLE_RATE_HZ = {rekam.RATE}", header_text)

    def test_header_packs_the_exact_wire_bytes(self) -> None:
        packed = self.protocol.HEADER.pack(
            self.protocol.MAGIC, 1, 0, 24, 0x01020304, 62500, 256, 80, 7,
        )
        # 62500 == 0xF424 little-endian; 256 == 0x0100; 24 == 0x18; gain 80 == 0x50.
        self.assertEqual(
            packed,
            b"SAWT" b"\x01" b"\x00" b"\x18\x00" b"\x04\x03\x02\x01"
            b"\x24\xf4\x00\x00" b"\x00\x01" b"\x50\x00" b"\x07\x00\x00\x00",
        )
        self.assertEqual(len(packed), 24)

    def test_recorder_source_has_no_dependency_on_the_reference_clone(self) -> None:
        source = (rekam.ROOT / "scripts" / "rekam.py").read_text(encoding="utf-8")
        self.assertNotIn(".reference-project-sawit-2", source)
        self.assertNotIn("arduino-cli", source)

    def test_recorder_source_has_no_windows_only_folder_opening(self) -> None:
        source = (rekam.ROOT / "scripts" / "rekam.py").read_text(encoding="utf-8")
        # os.startfile only exists inside the Windows branch of open_in_file_manager.
        self.assertEqual(source.count("os.startfile"), 1)
        self.assertIn('sys.platform.startswith("win")', source)

    def test_open_in_file_manager_creates_missing_folder_and_reports_errors(self) -> None:
        import sys as _sys
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "belum" / "ada"
            with patch.object(_sys, "platform", "linux"), \
                    patch("subprocess.run", side_effect=FileNotFoundError("xdg-open tidak ada")):
                ok, detail = rekam.open_in_file_manager(missing)
            self.assertFalse(ok)
            self.assertIn("xdg-open", detail)
            self.assertTrue(missing.is_dir())

    def test_open_in_file_manager_uses_xdg_open_on_linux(self) -> None:
        import sys as _sys
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "hasil"
            with patch.object(_sys, "platform", "linux"), \
                    patch("subprocess.run") as run:
                ok, detail = rekam.open_in_file_manager(folder)
            self.assertTrue(ok, detail)
            self.assertEqual(run.call_args.args[0][0], "xdg-open")

    def test_open_in_file_manager_uses_open_on_macos(self) -> None:
        import sys as _sys
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "hasil"
            with patch.object(_sys, "platform", "darwin"), \
                    patch("subprocess.run") as run:
                ok, detail = rekam.open_in_file_manager(folder)
            self.assertTrue(ok, detail)
            self.assertEqual(run.call_args.args[0][0], "open")

    def test_only_rekam_and_berhenti_remain_as_lockable_controls(self) -> None:
        self.assertEqual(
            rekam.operation_button_states("recording"),
            {"start": "disabled", "stop": "normal"},
        )
        self.assertEqual(
            rekam.operation_button_states("idle"),
            {"start": "normal", "stop": "disabled"},
        )


if __name__ == "__main__":
    unittest.main()
