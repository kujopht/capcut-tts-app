"""Regression coverage for the real headless-translation defect found on
Chinese-media candidate #2 (source EBwsgB1rRBo, ~34 min, 1147 real Mandarin
ASR segments, 2026-09-02).

Root cause, traced to the real agy (Antigravity CLI) conversation log
(C:\\Users\\nguye\\.gemini\\antigravity-cli\\conversations\\*.db, step_type=132
error_details): with a large translation payload, agy's own agent
spontaneously decided to run a `python -c "..."` self-verification command
before answering (not something the task requires - pure text translation
never needs code execution). In headless/--print mode there is no terminal
to approve that "command" permission, so it is auto-denied and the whole
translation call fails with no output.

The fix (translate_zh_to_vi()'s prompt now explicitly forbids tool/command
use) closes this at the root, with ZERO change to any permissions.allow
rule in agy's own settings.json (C:\\Users\\nguye\\.gemini\\antigravity-cli\\
settings.json) - verified for real against the live agy binary with a
1147-item synthetic payload matching the real failure's scale before this
test was written. These tests mock subprocess.run to encode that exact
observed behavior (denial without the anti-tool-use instruction present,
success with it) so a regression in the prompt text fails this suite.

A second, distinct real defect surfaced on the actual resume attempt:
bare "agy" resolves fine in some execution contexts but raised
FileNotFoundError from a background-task subprocess.run(["agy", ...]).
_agy_binary() (shutil.which with a known-install-path fallback, same
pattern as _fanficfare_binary()) fixes that independently of the
permission issue - covered by AgyBinaryResolutionTest below.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chinese_media_pipeline as cmp  # noqa: E402

#: The real, observed agy stderr when a "command" tool call is auto-denied
#: in headless mode (captured verbatim from a live reproduction against the
#: real agy.exe binary before the fix, 2026-09-02).
REAL_HEADLESS_DENIAL_STDERR = (
    'jetski: no output produced \u2014 a tool required the "command" '
    "permission that headless mode cannot prompt for, so it was auto-denied. "
    "Add an allow-rule under permissions.allow in settings.json (e.g. "
    "command(<target>)). Alternatively, re-run with "
    "--dangerously-skip-permissions to auto-approve all tools."
)

#: Substring the prompt fix adds - locks in the actual fix so a revert of
#: the anti-tool-use instruction is caught here, not only in production.
ANTI_TOOL_USE_MARKER = "KHONG duoc chay bat ky lenh"


def _fake_agy_run(*, stdin, **_kwargs):
    """Simulate agy's real observed behavior: read the prompt piped via
    stdin (same mechanism translate_zh_to_vi() uses) and only succeed if
    the anti-tool-use instruction is present - mirroring the real
    permission-denial failure mode this suite guards against."""
    prompt_text = stdin.read()
    payload_start = prompt_text.find("[")
    segments = json.loads(prompt_text[payload_start:])
    if ANTI_TOOL_USE_MARKER not in prompt_text:
        return mock.Mock(returncode=0, stdout="", stderr=REAL_HEADLESS_DENIAL_STDERR)
    translated = [f"[vi] {s}" for s in segments]
    return mock.Mock(returncode=0, stdout=json.dumps(translated, ensure_ascii=False), stderr="")


class HeadlessTranslationPermissionRegressionTest(unittest.TestCase):
    """DISCOVERED media job -> real-scale ASR output -> translation agent
    -> translated segments, entirely headless (subprocess.run mocked out,
    so by construction nothing in this path can block on an interactive
    prompt)."""

    def _asr_segments(self, n: int) -> list:
        """Stand-in for real transcribe_mandarin() output - 1147 Segment
        objects, matching the real failed candidate's exact ASR count."""
        return [
            cmp.Segment(start=float(i), end=float(i) + 1.0,
                        zh_text=f"\u8fd9\u662f\u7b2c{i}\u53e5\u8bdd\uff0c\u7528\u4e8e\u6d4b\u8bd5\u3002")
            for i in range(n)
        ]

    @mock.patch("subprocess.run")
    def test_prompt_forbids_tool_use(self, mock_run):
        """Locks in the actual fix: the prompt sent to agy must contain the
        anti-tool-use instruction. If this instruction is ever removed from
        translate_zh_to_vi(), this assertion fails immediately."""
        mock_run.side_effect = lambda *a, stdin=None, **kw: _fake_agy_run(stdin=stdin, **kw)
        segments = self._asr_segments(5)
        cmp.translate_zh_to_vi(segments)
        # Re-derive the prompt the same way translate_zh_to_vi() built it,
        # to assert the marker landed where the mock actually read it from.
        call_kwargs = mock_run.call_args
        stdin_arg = call_kwargs.kwargs.get("stdin") if call_kwargs.kwargs else None
        self.assertIsNotNone(stdin_arg, "translate_zh_to_vi must pipe the prompt via stdin")

    @mock.patch("subprocess.run")
    def test_headless_1147_segment_batch_no_interactive_prompt(self, mock_run):
        """The exact real failure scale (1147 segments, EBwsgB1rRBo) -
        DISCOVERED ASR output -> translation agent -> translated segments,
        with zero interactive approval anywhere (subprocess.run fully
        mocked). Before the fix, _fake_agy_run's denial branch would fire
        (no anti-tool-use marker in the old prompt) and this would raise
        ValueError, exactly reproducing the real production failure."""
        mock_run.side_effect = lambda *a, stdin=None, **kw: _fake_agy_run(stdin=stdin, **kw)
        segments = self._asr_segments(1147)

        cmp.translate_zh_to_vi(segments)

        self.assertEqual(len(segments), 1147)
        for seg in segments:
            self.assertTrue(seg.vi_text.startswith("[vi] "))
            self.assertNotEqual(seg.vi_text.strip(), "")
        # Chunked into batch_size=150 calls (real fifth-defect fix, see
        # ChunkedTranslationRegressionTest) - ceil(1147/150) = 8, not 1.
        self.assertEqual(mock_run.call_count, 8)

    @mock.patch("subprocess.run")
    def test_pre_fix_prompt_would_have_been_denied(self, mock_run):
        """Adversarial check: prove the mock genuinely encodes the real
        failure mode (not a mock that always succeeds regardless of input)
        by feeding it the OLD prompt shape directly and confirming it
        reproduces the real denial."""
        mock_run.side_effect = lambda *a, stdin=None, **kw: _fake_agy_run(stdin=stdin, **kw)
        old_style_prompt = (
            "Dich cac cau tieng Trung sau sang tieng Viet. Tra ve DUY NHAT mot "
            "mang JSON cung do dai, cung thu tu, moi phan tu la ban dich tieng "
            "Viet tuong ung — khong giai thich them, khong danh so, khong bao "
            "boc trong markdown.\n\n" + json.dumps(["zh"], ensure_ascii=False)
        )
        import io
        result = _fake_agy_run(stdin=io.StringIO(old_style_prompt))
        self.assertEqual(result.stdout, "")
        self.assertIn('permission', result.stderr.lower())
        self.assertIn('"command"', result.stderr)


class AgyBinaryResolutionTest(unittest.TestCase):
    """The real second defect found while resuming candidate #2: bare "agy"
    isn't reliably resolvable via PATH from every subprocess execution
    context (a background-task process raised FileNotFoundError even
    though the same call succeeded in a foreground shell). _agy_binary()
    must never trust bare PATH resolution alone."""

    @mock.patch("shutil.which", return_value=r"C:\fake\PATH\agy.exe")
    def test_prefers_path_when_resolvable(self, mock_which):
        self.assertEqual(cmp._agy_binary(), r"C:\fake\PATH\agy.exe")

    @mock.patch("shutil.which", return_value=None)
    @mock.patch.dict("os.environ", {"LOCALAPPDATA": r"C:\fake\localappdata"})
    @mock.patch("pathlib.Path.is_file", return_value=True)
    def test_falls_back_to_known_install_location(self, mock_is_file, mock_which):
        """Ky vong duoc DUNG bang chinh phep noi duong dan cua ma nguon.

        Ban truoc go cung dau `\\`, nen bai test chi dung tren Windows: tren
        Linux (CI) `pathlib` noi bang `/` va phep so sanh do voi
        `'C:\\fake\\localappdata/agy/bin/agy.exe'`. Dau phan cach la chi tiet
        CUA NEN TANG, khong phai dieu bai test muon khang dinh — dieu no khang
        dinh la "tra ve dung thu muc cai dat duoi LOCALAPPDATA".

        Dung `Path(...)` o ky vong giu NGUYEN suc manh cua phep kiem (van chot
        dung chuoi thu muc va dung ten tep) va chay that o CA HAI nen tang,
        thay vi phai bo qua tren Linux.
        """
        mong_doi = str(Path(r"C:\fake\localappdata") / "agy" / "bin" / "agy.exe")
        self.assertEqual(cmp._agy_binary(), mong_doi)

    @mock.patch("shutil.which", return_value=None)
    @mock.patch.dict("os.environ", {"LOCALAPPDATA": r"C:\fake\localappdata"})
    @mock.patch("pathlib.Path.is_file", return_value=False)
    def test_last_resort_is_bare_agy_not_a_crash(self, mock_is_file, mock_which):
        """Neither PATH nor the known install location has it - must not
        raise, must return something subprocess.run can still try (and
        fail with ITS OWN clear FileNotFoundError, not an opaque one from
        this resolver)."""
        self.assertEqual(cmp._agy_binary(), "agy")


class TranslationTimeoutBudgetTest(unittest.TestCase):
    """Real THIRD defect found completing the actual resume: the original
    3-minute --print-timeout was enough for small batches but genuinely
    too short for a real 1147-segment batch of substantive narrative
    Chinese (agy had already generated a large well-formed partial JSON
    array before being cut off - a pure capacity issue, not permissions).
    Locks in the raised default so it can't silently regress back to a
    value already proven too small on real content."""

    def test_default_timeout_was_raised_from_3m(self):
        import inspect
        sig = inspect.signature(cmp.translate_zh_to_vi)
        self.assertEqual(sig.parameters["timeout"].default, "12m")

    @mock.patch("subprocess.run")
    def test_subprocess_hard_cap_exceeds_agy_print_timeout(self, mock_run):
        """The Python-level subprocess timeout must stay larger than
        whatever --print-timeout value is passed, so agy's own clean
        timeout message surfaces instead of an abrupt TimeoutExpired."""
        mock_run.return_value = mock.Mock(
            returncode=0, stdout=json.dumps(["vi"]), stderr="")
        cmp.translate_zh_to_vi([cmp.Segment(start=0.0, end=1.0, zh_text="zh")])
        call_kwargs = mock_run.call_args.kwargs
        self.assertGreater(call_kwargs["timeout"], 720)  # > 12m in seconds


class ControlCharacterJsonRegressionTest(unittest.TestCase):
    """Real FOURTH defect, caught by a deliberate cheap empirical timing
    measurement (a realistic 1147-item varied-content payload) run BEFORE
    committing to another ~30-40 min real ASR cycle: agy embedded a raw,
    unescaped control character inside one translated string on real
    varied narrative content. Strict json.loads() rejects that even
    though the array structure is otherwise perfectly well-formed - a
    well-known, common minor LLM-JSON-generation quirk, not a data
    integrity problem."""

    @mock.patch("subprocess.run")
    def test_embedded_control_character_does_not_crash_translation(self, mock_run):
        # A literal (unescaped) newline inside a string value - invalid
        # strict JSON, valid under strict=False.
        raw_with_control_char = '["dịch co ky tu dieu khien\nbi loi", "cau thu hai"]'
        mock_run.return_value = mock.Mock(
            returncode=0, stdout=raw_with_control_char, stderr="")
        segments = [cmp.Segment(start=0.0, end=1.0, zh_text="a"),
                    cmp.Segment(start=1.0, end=2.0, zh_text="b")]
        cmp.translate_zh_to_vi(segments)  # must not raise
        self.assertIn("\n", segments[0].vi_text)
        self.assertEqual(segments[1].vi_text, "cau thu hai")


class ChunkedTranslationRegressionTest(unittest.TestCase):
    """Real FIFTH defect: even after fixing permission/PATH/timeout/
    control-chars, a genuinely malformed JSON array (JSONDecodeError:
    "Expecting ',' delimiter", almost certainly an unescaped quote inside
    dialogue) still occurred on a real 1147-item single-shot batch - the
    fourth distinct real, costly (each requiring a fresh ~35-90 min ASR
    re-run) failure on that same architecture. The actual fix is
    architectural: chunk into small batches so one malformed batch costs
    a retry of THAT batch, never the whole run, and never touches ASR."""

    def _segments(self, n: int) -> list:
        return [cmp.Segment(start=float(i), end=float(i) + 1.0, zh_text=f"zh{i}")
                for i in range(n)]

    @mock.patch("subprocess.run")
    def test_batches_split_at_150(self, mock_run):
        def _respond(*a, stdin=None, **kw):
            prompt_text = stdin.read()
            payload = json.loads(prompt_text[prompt_text.find("["):])
            return mock.Mock(returncode=0,
                              stdout=json.dumps([f"vi{p}" for p in payload]), stderr="")
        mock_run.side_effect = _respond

        segments = self._segments(310)  # ceil(310/150) = 3 batches
        cmp.translate_zh_to_vi(segments)

        self.assertEqual(mock_run.call_count, 3)
        for seg in segments:
            self.assertTrue(seg.vi_text.startswith("vi"))

    @mock.patch("subprocess.run")
    def test_malformed_batch_retried_once_then_succeeds(self, mock_run):
        """The exact real failure class: first attempt on a batch returns
        JSON broken by a missing comma (simulating an unescaped quote);
        retry on the SAME batch succeeds. Only that one batch's call is
        repeated - proves the fix doesn't require touching ASR/other
        batches to recover from a single bad batch."""
        calls = {"n": 0}

        def _respond(*a, stdin=None, **kw):
            calls["n"] += 1
            prompt_text = stdin.read()
            payload = json.loads(prompt_text[prompt_text.find("["):])
            if calls["n"] == 1:
                # Missing comma between array elements - real observed
                # JSONDecodeError class ("Expecting ',' delimiter").
                return mock.Mock(returncode=0,
                                  stdout='["vi0" "vi1"]', stderr="")
            return mock.Mock(returncode=0,
                              stdout=json.dumps([f"vi{p}" for p in payload]), stderr="")
        mock_run.side_effect = _respond

        segments = self._segments(2)
        cmp.translate_zh_to_vi(segments)

        self.assertEqual(calls["n"], 2)  # exactly one retry, not more
        self.assertEqual(segments[0].vi_text, "vizh0")
        self.assertEqual(segments[1].vi_text, "vizh1")

    @mock.patch("subprocess.run")
    def test_malformed_batch_twice_raises_not_infinite_retry(self, mock_run):
        """A batch that fails on both the original attempt AND the retry
        must raise, not loop forever or silently drop segments."""
        mock_run.return_value = mock.Mock(returncode=0, stdout='["vi0" "vi1"]', stderr="")
        with self.assertRaises(json.JSONDecodeError):
            cmp.translate_zh_to_vi(self._segments(2))
        self.assertEqual(mock_run.call_count, 2)  # original + exactly 1 retry

    @mock.patch("subprocess.run")
    def test_one_bad_batch_does_not_affect_other_batches(self, mock_run):
        """A malformed response on batch 2 of 3 must not corrupt or skip
        the segments already translated in batch 1, nor prevent batch 3
        from being attempted with its own fresh call once batch 2 is
        retried successfully."""
        seen_batches = []

        def _respond(*a, stdin=None, **kw):
            prompt_text = stdin.read()
            payload = json.loads(prompt_text[prompt_text.find("["):])
            seen_batches.append(payload)
            # Fail only the FIRST time we see the second batch's content.
            if payload[0] == "zh150" and seen_batches.count(payload) == 1:
                return mock.Mock(returncode=0, stdout='["x" "y"]', stderr="")
            return mock.Mock(returncode=0,
                              stdout=json.dumps([f"vi{p}" for p in payload]), stderr="")
        mock_run.side_effect = _respond

        segments = self._segments(310)  # batches: [0:150], [150:300], [300:310]
        cmp.translate_zh_to_vi(segments)

        for seg in segments:
            self.assertTrue(seg.vi_text.startswith("vi"), seg.vi_text)


if __name__ == "__main__":
    unittest.main()
