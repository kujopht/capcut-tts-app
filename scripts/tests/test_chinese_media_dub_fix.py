"""dub_segments() — the root-cause fix for the real 15.1% dub-coverage
defect found by VisualMediaQA on wikitongues_henan_rendered.mkv.

The previous version tracked placement using the ASSUMED source-window
length (`seg.end - seg.start`) instead of the synthesized audio's ACTUAL
measured duration, and never checked whether `provider.synthesize()`
produced usable output. These tests exercise the fixed per-segment logic:
natural fit, bounded-rate retry on overrun, spill into adjacent silence,
and flagging a genuine overrun for review — all against mocked Piper/
ffmpeg/ffprobe calls (no real TTS or media processing).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chinese_media_pipeline as cmp  # noqa: E402


def _seg(start, end, text="xin chao"):
    return cmp.Segment(start=start, end=end, zh_text="zh", vi_text=text)


class ProbeAudioDurationTest(unittest.TestCase):
    @mock.patch("subprocess.run")
    def test_doc_duration_that_tu_ffprobe(self, mock_run):
        mock_run.return_value = mock.Mock(stdout="4.500000\n", returncode=0)
        dur = cmp._probe_audio_duration(Path("x.mp3"), "ffmpeg")
        self.assertEqual(dur, 4.5)
        # ffprobe path derived from the ffmpeg path, not hardcoded elsewhere.
        called_bin = mock_run.call_args[0][0][0]
        self.assertIn("ffprobe", called_bin)

    @mock.patch("subprocess.run")
    def test_output_hong_tra_ve_0(self, mock_run):
        mock_run.return_value = mock.Mock(stdout="N/A\n", returncode=0)
        self.assertEqual(cmp._probe_audio_duration(Path("x.mp3"), "ffmpeg"), 0.0)


def _patch_piper(monkeypatch_target_module, *, synth_durations):
    """Patches the lazy-imported Piper chain so dub_segments() never
    touches real models. `synth_durations` maps each synthesize() call
    index (0-based, across ALL calls including retries) to a fake
    rendered-duration float; `_probe_audio_duration` is patched to return
    them in call order."""
    manager = mock.Mock()
    manager.find.return_value = mock.Mock(installed=True)
    provider = mock.Mock()
    calls = []

    def fake_synthesize(*, text, voice, dest, rate="1.0"):
        calls.append(rate)
        Path(dest).write_bytes(b"\x00")  # just needs to exist

    provider.synthesize.side_effect = fake_synthesize

    patches = [
        mock.patch("desktop_app.providers.piper_models.PiperModelManager", return_value=manager),
        mock.patch("desktop_app.providers.piper_provider.PiperLocalProvider", return_value=provider),
        mock.patch("desktop_app.providers.base.Voice", side_effect=lambda **kw: kw),
    ]
    duration_iter = iter(synth_durations)
    patches.append(mock.patch.object(
        cmp, "_probe_audio_duration", side_effect=lambda *a, **k: next(duration_iter, 0.0)))
    return patches, calls


class DubSegmentsPlacementTest(unittest.TestCase):
    def _run(self, segments, synth_durations, max_rate=1.3):
        patches, calls = _patch_piper(cmp, synth_durations=synth_durations)
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            for p in patches:
                p.start()
            try:
                with mock.patch.object(Path, "stat", return_value=mock.Mock(st_size=100)):
                    results = cmp.dub_segments(
                        segments, Path("out.mp3"), "ffmpeg", max_rate=max_rate)
            finally:
                for p in patches:
                    p.stop()
        return results, calls

    def test_khop_vua_khung_khong_can_toc_do_lai(self):
        """Natural fit: rendered duration <= window -> no retry, cursor
        advances by the REAL measured duration (the actual bug fix)."""
        segments = [_seg(0.0, 6.0), _seg(6.0, 10.0)]
        results, calls = self._run(segments, synth_durations=[5.0, 3.0])
        self.assertEqual(calls, ["1.0", "1.0"])  # never retried
        self.assertEqual(results[0].actual_duration, 5.0)
        self.assertEqual(results[0].rate_used, 1.0)
        self.assertFalse(results[0].needs_review)
        self.assertEqual(results[1].actual_duration, 3.0)

    def test_vuot_khung_duoc_tang_toc_trong_gioi_han(self):
        """Overrun that fits within the rate cap: retried once at the
        rate needed to exactly fill the window, not left overrunning."""
        segments = [_seg(0.0, 5.0)]
        # natural=6.0s for a 5.0s window -> needed_rate=1.2, within max_rate=1.3
        results, calls = self._run(segments, synth_durations=[6.0, 5.0], max_rate=1.3)
        self.assertEqual(calls, ["1.0", "1.200"])
        self.assertEqual(results[0].rate_used, 1.2)
        self.assertEqual(results[0].actual_duration, 5.0)
        self.assertFalse(results[0].needs_review)

    def test_khong_bao_gio_vuot_qua_tran_toc_do(self):
        """'Do not create absurdly fast speech' - the retry rate is capped
        at max_rate even when the natural overrun would need much more."""
        segments = [_seg(0.0, 2.0)]
        # natural=10.0s for a 2.0s window -> needed_rate would be 5.0, capped to 1.3
        results, calls = self._run(segments, synth_durations=[10.0, 7.0], max_rate=1.3)
        self.assertEqual(calls, ["1.0", "1.300"])
        self.assertLessEqual(results[0].rate_used, 1.3)

    def test_vuot_khung_tran_ma_van_co_khoang_lang_thi_khong_bi_review(self):
        """Overrun beyond the rate cap that still fits before the next
        segment's start (spills into real silence, no collision) is NOT
        flagged for review."""
        segments = [_seg(0.0, 2.0), _seg(10.0, 14.0)]
        # after rate cap, still 7.0s actual for a 2.0s window -> ends at t=7,
        # next segment starts at t=10 -> 3s of slack, no collision.
        results, calls = self._run(segments, synth_durations=[10.0, 7.0, 4.0], max_rate=1.3)
        self.assertFalse(results[0].needs_review)
        self.assertGreater(results[0].overrun_seconds, 0)
        self.assertIn("spilled", results[0].reason)

    def test_vuot_khung_dung_cham_doan_ke_tiep_thi_bi_danh_dau_review(self):
        """The genuine failure case: even after the rate cap, the segment
        overruns INTO where the next segment must start -> needs_review."""
        segments = [_seg(0.0, 2.0), _seg(3.0, 6.0)]
        # after rate cap, actual=7.0s for a 2.0s window -> ends at t=7, but
        # next segment must start at t=3 -> collision.
        results, calls = self._run(segments, synth_durations=[10.0, 7.0, 2.5], max_rate=1.3)
        self.assertTrue(results[0].needs_review)
        self.assertIn("exceeded available silence", results[0].reason)

    def test_van_ban_rong_bi_bo_qua_khong_goi_tts(self):
        segments = [_seg(0.0, 3.0, text="   "), _seg(3.0, 6.0, text="that")]
        results, calls = self._run(segments, synth_durations=[2.5])
        self.assertFalse(results[0].requested)
        self.assertFalse(results[0].synth_ok)
        self.assertEqual(results[0].reason, "empty translated text")
        # only ONE real synth call, for the second segment.
        self.assertEqual(len(calls), 1)

    def test_synthesize_nem_loi_duoc_ghi_nhan_khong_lam_sap_toan_bo(self):
        """A single segment's synth failure must not crash the whole run
        (the historical bug's most damaging shape: previously an
        unhandled exception here would abort the entire dub) - it's
        recorded and the rest of the segments still get processed."""
        segments = [_seg(0.0, 3.0), _seg(3.0, 6.0)]
        patches, calls = _patch_piper(cmp, synth_durations=[2.5])
        provider_patch = patches[1]
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            for p in patches:
                p.start()
            try:
                real_provider = mock.Mock()
                call_count = {"n": 0}

                def flaky_synthesize(*, text, voice, dest, rate="1.0"):
                    call_count["n"] += 1
                    if call_count["n"] == 1:
                        raise RuntimeError("piper crashed")
                    Path(dest).write_bytes(b"\x00")

                real_provider.synthesize.side_effect = flaky_synthesize
                with mock.patch("desktop_app.providers.piper_provider.PiperLocalProvider",
                                return_value=real_provider), \
                     mock.patch.object(Path, "stat", return_value=mock.Mock(st_size=100)):
                    results = cmp.dub_segments(segments, Path("out.mp3"), "ffmpeg")
            finally:
                for p in patches:
                    p.stop()
        self.assertFalse(results[0].synth_ok)
        self.assertTrue(results[0].needs_review)
        self.assertIn("synthesize() raised", results[0].reason)
        self.assertTrue(results[1].synth_ok)


if __name__ == "__main__":
    unittest.main()
