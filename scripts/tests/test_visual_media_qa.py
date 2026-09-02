"""VisualMediaQA — deterministic-check parsing, cost-aware plan building,
and verdict synthesis.

The ffprobe JSON fixtures below are shaped exactly like a REAL capture
(`wikitongues_henan_rendered.mkv`, a real rendered artifact from a prior
Chinese-media pipeline PASS run — see
docs/reports/watch-visual-qa-integration-2026-09-02.md) — including the
real Matroska quirk that grounds `_stream_duration_seconds()`: only the
subtitle stream carries a top-level `duration` field; video/audio streams
only have it in `tags.DURATION` as an `HH:MM:SS.ffffff` string. These tests
never invoke the real ffprobe/ffmpeg binaries or a model — subprocess calls
are mocked throughout.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import visual_media_qa as vmq  # noqa: E402

# Real shape, trimmed to the fields this module reads — matches the actual
# capture from wikitongues_henan_rendered.mkv.
REAL_SHAPED_FFPROBE = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "vp9",
         "width": 1920, "height": 1080, "display_aspect_ratio": "16:9",
         "tags": {"DURATION": "00:03:37.937000000"}},
        {"index": 1, "codec_type": "audio", "codec_name": "opus", "channels": 2,
         "tags": {"DURATION": "00:03:37.971000000"}},
        {"index": 2, "codec_type": "subtitle", "codec_name": "subrip",
         "duration": "217.971000",
         "tags": {"DURATION": "00:03:37.230000000"}},
        {"index": 3, "codec_type": "audio", "codec_name": "mp3", "channels": 1,
         "tags": {"DURATION": "00:00:32.940000000"}},
    ],
    "format": {"duration": "217.971000", "size": "46699303"},
}

CLEAN_FFPROBE = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264",
         "width": 1280, "height": 720, "display_aspect_ratio": "16:9",
         "duration": "60.0"},
        {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2,
         "duration": "60.0"},
    ],
    "format": {"duration": "60.0", "size": "1000000"},
}


def _fake_ffprobe_run(json_payload):
    def _run(cmd, **kwargs):
        import json as _json
        result = mock.Mock()
        result.returncode = 0
        result.stdout = _json.dumps(json_payload)
        result.stderr = ""
        return result
    return _run


class StreamDurationParsingTest(unittest.TestCase):
    def test_doc_top_level_duration_uu_tien_truoc(self):
        self.assertEqual(vmq._stream_duration_seconds({"duration": "10.5"}), 10.5)

    def test_fallback_ve_tags_duration_khi_thieu_truong_duration(self):
        # The real Matroska case: no top-level `duration`, only tags.DURATION.
        secs = vmq._stream_duration_seconds({"tags": {"DURATION": "00:03:37.937000000"}})
        self.assertAlmostEqual(secs, 217.937, places=2)

    def test_khong_co_ca_hai_tra_ve_none(self):
        self.assertIsNone(vmq._stream_duration_seconds({}))

    def test_gia_tri_duration_hong_khong_lam_crash(self):
        self.assertIsNone(vmq._stream_duration_seconds({"duration": "not-a-number"}))


class DeterministicChecksTest(unittest.TestCase):
    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(vmq, "_find_binary")
    @mock.patch("subprocess.run")
    def test_phat_hien_that_ty_le_dub_thieu(self, mock_run, mock_find, _mock_is_file):
        """The real defect this module is grounded in: a dub track covering
        only 15.1% of the video's duration must be flagged, using the exact
        real ffprobe shape captured from wikitongues_henan_rendered.mkv."""
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = _fake_ffprobe_run(REAL_SHAPED_FFPROBE)
        check = vmq.deterministic_checks(Path("fake.mkv"), run_blackdetect=False)

        self.assertTrue(check.ok)
        self.assertFalse(check.hard_fail)
        self.assertAlmostEqual(check.duration_seconds, 217.971, places=2)
        self.assertTrue(check.has_video_stream)
        self.assertTrue(check.has_audio_stream)
        self.assertTrue(check.has_subtitle_stream)
        matching = [w for w in check.warnings if "covers only" in w]
        self.assertEqual(len(matching), 1)
        self.assertIn("15.1%", matching[0])

    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(vmq, "_find_binary")
    @mock.patch("subprocess.run")
    def test_video_sach_khong_co_canh_bao(self, mock_run, mock_find, _mock_is_file):
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = _fake_ffprobe_run(CLEAN_FFPROBE)
        check = vmq.deterministic_checks(Path("clean.mp4"), run_blackdetect=False)

        self.assertTrue(check.ok)
        self.assertEqual(check.warnings, [])

    @mock.patch.object(vmq, "_find_binary", return_value=None)
    def test_thieu_ffprobe_la_hard_fail(self, _mock_find):
        check = vmq.deterministic_checks(Path("anything.mkv"))
        self.assertTrue(check.hard_fail)
        self.assertFalse(check.ok)

    def test_file_khong_ton_tai_la_hard_fail(self):
        with mock.patch.object(vmq, "_find_binary", return_value="/usr/bin/ffprobe"):
            check = vmq.deterministic_checks(Path("C:/does/not/exist.mkv"))
        self.assertTrue(check.hard_fail)

    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(vmq, "_find_binary")
    @mock.patch("subprocess.run")
    def test_khong_co_video_stream_la_hard_fail(self, mock_run, mock_find, _mock_is_file):
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        audio_only = {"streams": [{"index": 0, "codec_type": "audio",
                                    "codec_name": "mp3", "duration": "10.0"}],
                      "format": {"duration": "10.0"}}
        mock_run.side_effect = _fake_ffprobe_run(audio_only)
        check = vmq.deterministic_checks(Path("audio_only.mkv"), run_blackdetect=False)
        self.assertTrue(check.hard_fail)
        self.assertIn("no video stream present", check.warnings)


class WatchPlanTest(unittest.TestCase):
    def _clean_short_check(self, duration=60.0):
        return vmq.DeterministicCheckResult(
            video_path=Path("x.mp4"), ok=True, hard_fail=False,
            duration_seconds=duration)

    def test_video_ngan_dung_balanced_toan_bo(self):
        plan = vmq.build_watch_plan(self._clean_short_check(duration=90.0))
        self.assertEqual(plan.detail, vmq.SHORT_DETAIL)
        self.assertEqual(plan.windows, [])
        self.assertFalse(plan.skipped)

    def test_video_dai_sach_bi_bo_qua_mac_dinh(self):
        """The core cost-aware requirement: a long video with NO
        deterministic anomalies gets no frames requested by default."""
        check = self._clean_short_check(duration=1200.0)
        plan = vmq.build_watch_plan(check)
        self.assertEqual(plan.detail, vmq.LONG_DETAIL)
        self.assertTrue(plan.skipped)
        self.assertEqual(plan.to_cli_invocations(), [])

    def test_video_dai_sach_force_full_pass(self):
        check = self._clean_short_check(duration=1200.0)
        plan = vmq.build_watch_plan(check, force_full_pass=True)
        self.assertFalse(plan.skipped)
        self.assertEqual(plan.windows, [])
        self.assertEqual(len(plan.to_cli_invocations()), 1)

    def test_video_dai_co_bat_thuong_chi_zoom_vao_do(self):
        """The other core cost-aware requirement: a long video WITH a
        deterministic anomaly gets a focused window, not a full pass."""
        check = vmq.DeterministicCheckResult(
            video_path=Path("long.mkv"), ok=True, hard_fail=False,
            duration_seconds=1200.0,
            warnings=["audio stream #3 covers only 15.1% of video duration "
                      "(32.9s / 217.9s) - likely incomplete narration/dub, "
                      "not a sampling artifact"])
        plan = vmq.build_watch_plan(check)
        self.assertFalse(plan.skipped)
        self.assertEqual(len(plan.windows), 1)
        self.assertAlmostEqual(plan.windows[0].start_seconds, 27.9, places=1)
        self.assertAlmostEqual(plan.windows[0].end_seconds, 37.9, places=1)
        invocations = plan.to_cli_invocations()
        self.assertEqual(len(invocations), 1)
        self.assertIn("--start", invocations[0])
        self.assertIn("--end", invocations[0])

    def test_hard_fail_bo_qua_visual_qa(self):
        check = vmq.DeterministicCheckResult(
            video_path=Path("broken.mkv"), ok=False, hard_fail=True,
            warnings=["no video stream present"])
        plan = vmq.build_watch_plan(check)
        self.assertTrue(plan.skipped)


class VerdictSynthesisTest(unittest.TestCase):
    def test_hard_fail_luon_la_qa_fail(self):
        check = vmq.DeterministicCheckResult(
            video_path=Path("x"), ok=False, hard_fail=True)
        verdict = vmq.synthesize_verdict(check)
        self.assertEqual(verdict, vmq.QAVerdict.QA_FAIL)

    def test_sach_nhung_chua_duoc_xem_visual_la_qa_review(self):
        """Visual QA is optional - the common case. An unreviewed clean
        deterministic pass must not look identical to a reviewed one."""
        check = vmq.DeterministicCheckResult(video_path=Path("x"), ok=True, hard_fail=False)
        verdict = vmq.synthesize_verdict(check, visual=None)
        self.assertEqual(verdict, vmq.QAVerdict.QA_REVIEW)

    def test_sach_va_visual_tich_cuc_la_qa_pass(self):
        check = vmq.DeterministicCheckResult(video_path=Path("x"), ok=True, hard_fail=False)
        visual = vmq.VisualFindings(
            reviewed=True, visual_continuity_ok=True, subtitles_present_readable=True,
            black_or_broken_frames_seen=False, aspect_ratio_ok=True,
            visual_quality_acceptable=True, usable_as_draft=True)
        verdict = vmq.synthesize_verdict(check, visual)
        self.assertEqual(verdict, vmq.QAVerdict.QA_PASS)

    def test_visual_thay_khung_hinh_hong_la_qa_fail_du_deterministic_sach(self):
        check = vmq.DeterministicCheckResult(video_path=Path("x"), ok=True, hard_fail=False)
        visual = vmq.VisualFindings(reviewed=True, black_or_broken_frames_seen=True)
        verdict = vmq.synthesize_verdict(check, visual)
        self.assertEqual(verdict, vmq.QAVerdict.QA_FAIL)

    def test_canh_bao_deterministic_song_sot_qua_visual_tot_van_la_qa_review(self):
        """The real case: dub-coverage warning survives even a fully
        positive visual read (matches the actual wikitongues_henan result)."""
        check = vmq.DeterministicCheckResult(
            video_path=Path("x"), ok=True, hard_fail=False,
            warnings=["audio stream #3 covers only 15.1% of video duration "
                      "(32.9s / 217.9s)"])
        visual = vmq.VisualFindings(
            reviewed=True, visual_continuity_ok=True, subtitles_present_readable=True,
            black_or_broken_frames_seen=False, aspect_ratio_ok=True,
            visual_quality_acceptable=True, usable_as_draft=False)
        verdict = vmq.synthesize_verdict(check, visual)
        self.assertEqual(verdict, vmq.QAVerdict.QA_REVIEW)

    def test_visual_tim_thay_van_de_khac_cung_la_qa_review(self):
        check = vmq.DeterministicCheckResult(video_path=Path("x"), ok=True, hard_fail=False)
        visual = vmq.VisualFindings(reviewed=True, visual_continuity_ok=False)
        verdict = vmq.synthesize_verdict(check, visual)
        self.assertEqual(verdict, vmq.QAVerdict.QA_REVIEW)


class RunQaGateTest(unittest.TestCase):
    """The full stage in one call — the actual integration point a caller
    wires in after a render step."""

    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(vmq, "_find_binary")
    @mock.patch("subprocess.run")
    def test_khong_co_reviewer_tra_ve_qa_review(self, mock_run, mock_find, _mock_is_file):
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = _fake_ffprobe_run(CLEAN_FFPROBE)
        result = vmq.run_qa_gate(Path("clean.mp4"))
        self.assertEqual(result.verdict, vmq.QAVerdict.QA_REVIEW)
        self.assertIsNone(result.visual)

    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(vmq, "_find_binary")
    @mock.patch("subprocess.run")
    def test_reviewer_duoc_goi_va_ket_qua_duoc_dung(self, mock_run, mock_find, _mock_is_file):
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.side_effect = _fake_ffprobe_run(CLEAN_FFPROBE)
        calls = []

        def fake_reviewer(plan):
            calls.append(plan)
            return vmq.VisualFindings(
                reviewed=True, visual_continuity_ok=True, subtitles_present_readable=True,
                black_or_broken_frames_seen=False, aspect_ratio_ok=True,
                visual_quality_acceptable=True, usable_as_draft=True)

        result = vmq.run_qa_gate(Path("clean.mp4"), visual_reviewer=fake_reviewer)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.verdict, vmq.QAVerdict.QA_PASS)

    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(vmq, "_find_binary")
    @mock.patch("subprocess.run")
    def test_reviewer_khong_duoc_goi_khi_plan_bi_skip(self, mock_run, mock_find, _mock_is_file):
        """A long, clean video's plan is skipped by default - the reviewer
        must not be invoked at all, matching the cost-aware contract."""
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        long_clean = {
            "streams": CLEAN_FFPROBE["streams"],
            "format": {"duration": "1200.0", "size": "1"},
        }
        mock_run.side_effect = _fake_ffprobe_run(long_clean)
        calls = []
        result = vmq.run_qa_gate(Path("long.mp4"), visual_reviewer=lambda plan: calls.append(plan))
        self.assertEqual(calls, [])
        self.assertEqual(result.verdict, vmq.QAVerdict.QA_REVIEW)


class ProviderNeutralCliTest(unittest.TestCase):
    """The reuse contract for Router V3/OpenCode/Codex agents: a WatchPlan
    must serialize to a plain argv list any external CLI-capable agent can
    run, with no Claude-Code-specific object involved."""

    def test_cli_invocation_la_list_chuoi_thuan(self):
        check = vmq.DeterministicCheckResult(
            video_path=Path("x.mp4"), ok=True, hard_fail=False, duration_seconds=30.0)
        plan = vmq.build_watch_plan(check)
        invocations = plan.to_cli_invocations()
        self.assertEqual(len(invocations), 1)
        for item in invocations[0]:
            self.assertIsInstance(item, str)


if __name__ == "__main__":
    unittest.main()
