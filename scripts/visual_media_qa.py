#!/usr/bin/env python3
"""VisualMediaQA — provider-neutral post-render QA stage for the content
factory's rendered video drafts.

    RENDERED -> deterministic_checks() -> [watch() by ANY agent] ->
    synthesize_verdict() -> QA_PASS / QA_REVIEW / QA_FAIL -> DRAFT_READY

Real proof this module is grounded in: `/watch` (bradautomates/claude-video,
installed as a Claude Code plugin) was run against a real rendered artifact
from a prior Chinese-media pipeline PASS run
(`wikitongues_henan_rendered.mkv`) — see
`docs/reports/watch-visual-qa-integration-2026-09-02.md` for the full
comparison of what ffprobe caught vs what frame-reading added.

Design principles, each enforced by what this module does and does NOT do:

1. **Deterministic checks never depend on an LLM.** `deterministic_checks()`
   below is pure ffprobe/ffmpeg — same input, same output, every time. It is
   the ONLY thing this module trusts for hard facts (durations, codecs,
   stream presence, black frames). Real proof: it caught a genuine defect
   (dub audio track 32.9s long inside a 217.9s video — 85% of the runtime
   has no narration) with zero model cost, before any frame was ever read.

2. **Visual judgment (`/watch`) is optional and never authoritative on its
   own.** This module NEVER calls out to an LLM itself — `build_watch_plan()`
   only decides WHETHER a visual pass is warranted and WHAT it should look
   at (whole-video sample vs a focused window around a deterministic
   anomaly), returning a plan the CALLING AGENT executes with its own model.
   This is what makes the stage provider-neutral: a Router V3 worker, an
   OpenCode agent, a Codex agent, or Claude Code itself can all consume the
   same `WatchPlan` and run it through their own `/watch`-compatible
   invocation, feeding results back into `synthesize_verdict()`.

3. **Cost-aware by construction, not by convention.** `build_watch_plan()`
   picks `efficient` detail for anything over `LONG_VIDEO_SECONDS`,
   `balanced` for anything shorter, and — the real point of "only zoom into
   suspicious timestamps" — narrows to a `--start`/`--end` window around
   each deterministic anomaly instead of sampling the whole timeline once a
   long video already has a concrete lead. A video with zero deterministic
   anomalies over `LONG_VIDEO_SECONDS` gets NO frames requested by default;
   the caller has to explicitly ask for a full pass (`force_full_pass=True`)
   — never token-burn a long clean-looking video by default.

4. **`synthesize_verdict()` never lets visual opinion overrule a
   deterministic hard-fail**, and a missing visual pass (the common case,
   since it's optional) degrades to QA_REVIEW rather than silently
   upgrading to QA_PASS — an un-reviewed draft is never indistinguishable
   from a reviewed-and-clean one.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: Above this, default to `efficient` detail and a focused (not full) watch
#: pass — matches the "long video: efficient first, only zoom into
#: suspicious timestamps" requirement.
LONG_VIDEO_SECONDS = 600.0
SHORT_DETAIL = "balanced"
LONG_DETAIL = "efficient"

#: A narration/dub track covering less than this fraction of the video's
#: own duration is flagged as a real anomaly worth zooming into — chosen
#: from the real case that grounds this module: 32.9s / 217.9s ≈ 15%, an
#: unambiguous defect, not sampling noise from encoder rounding.
DUB_COVERAGE_WARN_RATIO = 0.85

#: Minimum black-segment length ffmpeg's blackdetect reports (seconds) —
#: below this, a genuine fade transition looks identical to a real black
#: frame, so keep the floor at "clearly not just a cut fade".
BLACKDETECT_MIN_DURATION = 0.5
BLACKDETECT_PIX_THRESHOLD = 0.10


class QAVerdict(str, Enum):
    QA_PASS = "QA_PASS"
    QA_REVIEW = "QA_REVIEW"
    QA_FAIL = "QA_FAIL"


@dataclass
class StreamSummary:
    index: int
    codec_type: str
    codec_name: str
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    display_aspect_ratio: Optional[str] = None
    channels: Optional[int] = None


@dataclass
class BlackSegment:
    start_seconds: float
    end_seconds: float


@dataclass
class DeterministicCheckResult:
    video_path: Path
    ok: bool
    hard_fail: bool
    warnings: List[str] = field(default_factory=list)
    streams: List[StreamSummary] = field(default_factory=list)
    duration_seconds: float = 0.0
    black_segments: List[BlackSegment] = field(default_factory=list)
    raw_ffprobe: Optional[Dict[str, Any]] = None

    @property
    def has_video_stream(self) -> bool:
        return any(s.codec_type == "video" for s in self.streams)

    @property
    def has_audio_stream(self) -> bool:
        return any(s.codec_type == "audio" for s in self.streams)

    @property
    def has_subtitle_stream(self) -> bool:
        return any(s.codec_type == "subtitle" for s in self.streams)


def _find_binary(name: str) -> Optional[str]:
    return shutil.which(name)


_TAG_DURATION_RE = re.compile(r"^(\d+):(\d{2}):(\d{2}(?:\.\d+)?)$")


def _stream_duration_seconds(stream: Dict[str, Any]) -> Optional[float]:
    """ffprobe's per-stream `duration` field is frequently absent for
    Matroska/MKV containers — real, measured behavior (see
    docs/reports/watch-visual-qa-integration-2026-09-02.md): only the
    subtitle stream carried a top-level `duration` in the file this module
    is grounded in, while video/audio only had it in `tags.DURATION` as an
    `HH:MM:SS.ffffff` string. Falls back to that tag before giving up."""
    raw = stream.get("duration")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    tag = (stream.get("tags") or {}).get("DURATION")
    if isinstance(tag, str):
        m = _TAG_DURATION_RE.match(tag.strip())
        if m:
            hours, minutes, seconds = m.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return None


def _run_ffprobe(video_path: Path, ffprobe_bin: str) -> Dict[str, Any]:
    proc = subprocess.run(
        [ffprobe_bin, "-v", "error", "-show_format", "-show_streams",
         "-print_format", "json", str(video_path)],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr[:500]}")
    return json.loads(proc.stdout)


def _detect_black_segments(
    video_path: Path, ffmpeg_bin: str, *, max_duration_seconds: Optional[float] = None,
) -> List[BlackSegment]:
    """Real ffmpeg `blackdetect` pass — deterministic, no model involved.
    Skipped entirely by the caller for very long videos where a full decode
    pass is not worth the CPU time (see `deterministic_checks()`'s
    `skip_blackdetect_over_seconds`), same cost-aware spirit as the visual
    stage but for CPU time rather than tokens.
    """
    args = [ffmpeg_bin, "-hide_banner"]
    if max_duration_seconds is not None:
        args += ["-t", f"{max_duration_seconds:.3f}"]
    args += [
        "-i", str(video_path),
        "-vf", f"blackdetect=d={BLACKDETECT_MIN_DURATION}:pix_th={BLACKDETECT_PIX_THRESHOLD}",
        "-an", "-f", "null", "-",
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=300)
    segments: List[BlackSegment] = []
    start_re = re.compile(r"black_start:([\d.]+)")
    end_re = re.compile(r"black_end:([\d.]+)")
    pending_start: Optional[float] = None
    for line in proc.stderr.splitlines():
        m_start = start_re.search(line)
        m_end = end_re.search(line)
        if m_start:
            pending_start = float(m_start.group(1))
        if m_end and pending_start is not None:
            segments.append(BlackSegment(start_seconds=pending_start,
                                          end_seconds=float(m_end.group(1))))
            pending_start = None
    return segments


def deterministic_checks(
    video_path: Path, *,
    run_blackdetect: bool = True,
    skip_blackdetect_over_seconds: float = 1800.0,
) -> DeterministicCheckResult:
    """The ONLY authoritative stage in this module — pure ffprobe/ffmpeg,
    zero LLM involvement (principle 1 in the module docstring). Real facts
    only: stream presence/codecs/durations, a whole-vs-audio duration
    mismatch (the real defect this module is grounded in), and black-frame
    segments. Never guesses; a warning is only emitted when the underlying
    ffprobe/ffmpeg data unambiguously supports it.
    """
    video_path = Path(video_path)
    warnings: List[str] = []

    ffprobe_bin = _find_binary("ffprobe")
    if not ffprobe_bin:
        return DeterministicCheckResult(
            video_path=video_path, ok=False, hard_fail=True,
            warnings=["ffprobe binary not found — cannot run deterministic checks"])
    if not video_path.is_file():
        return DeterministicCheckResult(
            video_path=video_path, ok=False, hard_fail=True,
            warnings=[f"file not found: {video_path}"])

    try:
        raw = _run_ffprobe(video_path, ffprobe_bin)
    except Exception as exc:
        return DeterministicCheckResult(
            video_path=video_path, ok=False, hard_fail=True,
            warnings=[f"ffprobe error: {exc}"])

    streams: List[StreamSummary] = []
    for s in raw.get("streams", []):
        duration_f = _stream_duration_seconds(s)
        streams.append(StreamSummary(
            index=s.get("index", -1), codec_type=s.get("codec_type", "?"),
            codec_name=s.get("codec_name", "?"), duration_seconds=duration_f,
            width=s.get("width"), height=s.get("height"),
            display_aspect_ratio=s.get("display_aspect_ratio"),
            channels=s.get("channels")))

    fmt = raw.get("format", {})
    try:
        total_duration = float(fmt.get("duration", 0.0))
    except (TypeError, ValueError):
        total_duration = 0.0

    hard_fail = False
    result_streams = streams
    has_video = any(s.codec_type == "video" for s in result_streams)
    has_audio = any(s.codec_type == "audio" for s in result_streams)

    if total_duration <= 0.0:
        hard_fail = True
        warnings.append("zero or unreadable total duration")
    if not has_video:
        hard_fail = True
        warnings.append("no video stream present")
    if not has_audio:
        warnings.append("no audio stream present")

    video_durations = [s.duration_seconds for s in result_streams
                        if s.codec_type == "video" and s.duration_seconds]
    audio_durations = [(s.index, s.duration_seconds) for s in result_streams
                        if s.codec_type == "audio" and s.duration_seconds]
    if video_durations and audio_durations:
        video_dur = max(video_durations)
        for idx, audio_dur in audio_durations:
            ratio = audio_dur / video_dur if video_dur else 0.0
            if ratio < DUB_COVERAGE_WARN_RATIO:
                warnings.append(
                    f"audio stream #{idx} covers only {ratio:.1%} of video "
                    f"duration ({audio_dur:.1f}s / {video_dur:.1f}s) — "
                    f"likely incomplete narration/dub, not a sampling artifact")

    black_segments: List[BlackSegment] = []
    ffmpeg_bin = _find_binary("ffmpeg")
    if run_blackdetect and ffmpeg_bin and total_duration <= skip_blackdetect_over_seconds:
        try:
            black_segments = _detect_black_segments(video_path, ffmpeg_bin)
        except Exception as exc:
            warnings.append(f"blackdetect pass failed (non-fatal): {exc}")
    elif run_blackdetect and total_duration > skip_blackdetect_over_seconds:
        warnings.append(
            f"blackdetect skipped: video is {total_duration:.0f}s, over the "
            f"{skip_blackdetect_over_seconds:.0f}s cost-aware ceiling")

    if black_segments:
        total_black = sum(b.end_seconds - b.start_seconds for b in black_segments)
        warnings.append(
            f"{len(black_segments)} black segment(s) detected, "
            f"{total_black:.1f}s total")

    return DeterministicCheckResult(
        video_path=video_path, ok=not hard_fail, hard_fail=hard_fail,
        warnings=warnings, streams=result_streams, duration_seconds=total_duration,
        black_segments=black_segments, raw_ffprobe=raw)


@dataclass
class WatchWindow:
    start_seconds: float
    end_seconds: float
    reason: str


@dataclass
class WatchPlan:
    """What a `/watch`-compatible agent (Claude Code, a Router V3 worker,
    an OpenCode/Codex agent — anything that can shell out to the same
    `watch.py` CLI or an equivalent) should actually run. This module never
    executes it — see module docstring principle 2."""

    video_path: Path
    detail: str
    windows: List[WatchWindow] = field(default_factory=list)
    skip_reason: str = ""

    @property
    def skipped(self) -> bool:
        return not self.windows and bool(self.skip_reason)

    def to_cli_invocations(self, watch_py_path: str = "watch.py") -> List[List[str]]:
        """Real, ready-to-run argv lists for `scripts/watch.py` (the
        installed plugin's entry point) — one per window, or one whole-video
        call when `windows` is empty and not skipped."""
        base = ["python3", watch_py_path, str(self.video_path), "--detail", self.detail,
                "--no-whisper"]
        if not self.windows:
            return [] if self.skipped else [base]
        invocations = []
        for w in self.windows:
            invocations.append(
                base + ["--start", f"{w.start_seconds:.0f}", "--end", f"{w.end_seconds:.0f}"])
        return invocations


def build_watch_plan(
    check: DeterministicCheckResult, *,
    force_full_pass: bool = False,
    focus_window_padding_seconds: float = 5.0,
) -> WatchPlan:
    """Decide whether/how to run visual QA — cost-aware per module
    docstring principle 3. Pure decision logic, no model call.

    - Deterministic hard-fail: skip visual QA entirely (nothing to look at,
      or looking won't change a verdict that's already QA_FAIL).
    - Short video (<= LONG_VIDEO_SECONDS): balanced detail, whole video.
    - Long video with NO deterministic anomalies and no forced full pass:
      skip — never token-burn a long clean-looking video by default.
    - Long video WITH deterministic anomalies (duration mismatch, black
      segments): efficient detail, windows focused on each anomaly instead
      of the whole timeline.
    - Long video with force_full_pass=True: efficient detail, whole video.
    """
    if check.hard_fail:
        return WatchPlan(video_path=check.video_path, detail=LONG_DETAIL,
                          skip_reason="deterministic hard-fail — visual pass would not change the verdict")

    is_long = check.duration_seconds > LONG_VIDEO_SECONDS
    detail = LONG_DETAIL if is_long else SHORT_DETAIL

    if not is_long:
        return WatchPlan(video_path=check.video_path, detail=detail, windows=[])

    anomaly_windows: List[WatchWindow] = []
    for w in check.warnings:
        m = re.search(r"covers only ([\d.]+)% of video duration \(([\d.]+)s / ([\d.]+)s\)", w)
        if m:
            audio_end = float(m.group(2))
            anomaly_windows.append(WatchWindow(
                start_seconds=max(0.0, audio_end - focus_window_padding_seconds),
                end_seconds=audio_end + focus_window_padding_seconds,
                reason="dub/narration duration mismatch boundary"))
    for seg in check.black_segments:
        anomaly_windows.append(WatchWindow(
            start_seconds=max(0.0, seg.start_seconds - focus_window_padding_seconds),
            end_seconds=seg.end_seconds + focus_window_padding_seconds,
            reason="black segment"))

    if force_full_pass:
        return WatchPlan(video_path=check.video_path, detail=detail, windows=[])
    if anomaly_windows:
        return WatchPlan(video_path=check.video_path, detail=detail, windows=anomaly_windows)
    return WatchPlan(
        video_path=check.video_path, detail=detail, windows=[],
        skip_reason=(f"long video ({check.duration_seconds:.0f}s) with no deterministic "
                     f"anomalies — full pass not run by default, pass force_full_pass=True "
                     f"to override"))


@dataclass
class VisualFindings:
    """What the calling agent reports back after actually running a
    `WatchPlan` through its own model. Every field is the agent's honest
    read — this module does not second-guess it, only combines it with the
    deterministic facts in `synthesize_verdict()`."""

    reviewed: bool
    visual_continuity_ok: Optional[bool] = None
    subtitles_present_readable: Optional[bool] = None
    black_or_broken_frames_seen: Optional[bool] = None
    aspect_ratio_ok: Optional[bool] = None
    visual_quality_acceptable: Optional[bool] = None
    usable_as_draft: Optional[bool] = None
    notes: str = ""


#: The other half of the recurrence-prevention gate (mission "FIX REAL
#: CHINESE DUB COVERAGE", section 6) — even 100% segment coverage can hide
#: one large hole (a whole scene with no dub), so a big enough single gap
#: fails the gate on its own regardless of the aggregate ratio.
MAX_UNEXPLAINED_MISSING_GAP_SECONDS = 15.0


# ---------------------------------------------------------------------------
# Speech/dub coverage — the deterministic metric the wikitongues_henan
# defect exposed a gap in. `dub_duration / full_video_duration` alone is
# the WRONG metric (mission "FIX REAL CHINESE DUB COVERAGE", section 3):
# a video can legitimately have long non-speech stretches, so what matters
# is how much of the SOURCE SPEECH TIME actually got a matching dub, not
# how much of the raw video runtime did. Interval-based, not a single
# duration ratio — generic enough that it takes plain (start, end) tuples,
# not this repo's own Segment/DubSegmentResult types, so it composes with
# any pipeline's own data shapes rather than importing them. Defined here,
# ahead of `synthesize_verdict()`, because that function takes
# `MIN_SEGMENT_COVERAGE_RATIO` as a default parameter value — module-level
# names must exist before the `def` that references them as a default.
# ---------------------------------------------------------------------------

#: Production default per the mission — a caller may pass a different
#: threshold for a source explicitly excluded by QA policy.
MIN_SEGMENT_COVERAGE_RATIO = 0.95


@dataclass
class SpeechCoverageMetrics:
    source_segment_count: int
    dub_segment_count: int
    segment_count_ratio: float
    source_speech_duration: float
    dub_speech_duration: float
    speech_coverage_ratio: float
    first_dubbed_timestamp: Optional[float]
    last_dubbed_timestamp: Optional[float]
    largest_missing_gap: float
    largest_missing_gap_window: Optional[Tuple[float, float]]

    def passes(self, min_ratio: float = MIN_SEGMENT_COVERAGE_RATIO) -> bool:
        return self.segment_count_ratio >= min_ratio


#: Two interval boundaries this close are "touching", not a real gap.
#: Guards against floating-point noise: two segments computed as
#: `start + duration` vs `start_of_next` via a different arithmetic path
#: (e.g. one via repeated addition, the other via multiplication) can
#: differ by a few ULPs even when mathematically adjacent — real,
#: reproduced case, not theoretical (see test suite). Real SRT-derived
#: timestamps are millisecond-quantized (>= 0.001s apart when genuinely
#: distinct), so this is far below any real gap that should count.
INTERVAL_ADJACENCY_EPSILON = 1e-6


def _merge_intervals(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Sorted, non-overlapping union — the shared primitive both duration
    sums and gap-finding are built on."""
    if not intervals:
        return []
    ordered = sorted((max(0.0, s), max(0.0, e)) for s, e in intervals if e > s)
    merged: List[Tuple[float, float]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + INTERVAL_ADJACENCY_EPSILON:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _interval_duration(intervals: List[Tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def _covered_duration(
    source: List[Tuple[float, float]], dub: List[Tuple[float, float]],
) -> float:
    """Total time inside `source`'s union that overlaps `dub`'s union —
    the numerator for `speech_coverage_ratio`."""
    covered = 0.0
    for s_start, s_end in source:
        for d_start, d_end in dub:
            overlap = min(s_end, d_end) - max(s_start, d_start)
            if overlap > 0:
                covered += overlap
    return covered


def compute_speech_coverage(
    source_intervals: List[Tuple[float, float]],
    dub_intervals: List[Tuple[float, float]],
) -> SpeechCoverageMetrics:
    """The real metric the mission asked for, in place of the naive
    `dub_duration / full_video_duration`:

        source_speech_duration = union of source ASR/SRT speech intervals
        dub_speech_duration    = union of placed dub intervals
        speech_coverage_ratio  = time-overlap(source, dub) / source_speech_duration
        segment_count_ratio    = (# source segments with ANY dub overlap) / (# source segments)

    Also reports first/last dubbed timestamp and the single largest
    contiguous gap in source speech time that has no dub coverage at all —
    the number an operator actually needs to answer "is the ending cut
    off?" or "is there one big silent hole in the middle?".
    """
    merged_source = _merge_intervals(source_intervals)
    merged_dub = _merge_intervals(dub_intervals)

    source_duration = _interval_duration(merged_source)
    dub_duration = _interval_duration(merged_dub)
    covered = _covered_duration(merged_source, merged_dub)
    coverage_ratio = (covered / source_duration) if source_duration > 0 else 0.0

    covered_source_segments = sum(
        1 for s_start, s_end in source_intervals
        if any(min(s_end, d_end) - max(s_start, d_start) > 0 for d_start, d_end in merged_dub))
    count_ratio = (
        covered_source_segments / len(source_intervals) if source_intervals else 0.0)

    first_ts = merged_dub[0][0] if merged_dub else None
    last_ts = merged_dub[-1][1] if merged_dub else None

    largest_gap = 0.0
    largest_gap_window: Optional[Tuple[float, float]] = None
    for s_start, s_end in merged_source:
        cursor = s_start
        for d_start, d_end in merged_dub:
            if d_end <= cursor or d_start >= s_end:
                continue
            gap = max(0.0, min(d_start, s_end) - cursor)
            if gap > largest_gap:
                largest_gap, largest_gap_window = gap, (cursor, min(d_start, s_end))
            cursor = max(cursor, d_end)
        tail_gap = max(0.0, s_end - cursor)
        if tail_gap > largest_gap:
            largest_gap, largest_gap_window = tail_gap, (cursor, s_end)

    return SpeechCoverageMetrics(
        source_segment_count=len(source_intervals),
        dub_segment_count=len(dub_intervals),
        segment_count_ratio=count_ratio,
        source_speech_duration=source_duration,
        dub_speech_duration=dub_duration,
        speech_coverage_ratio=coverage_ratio,
        first_dubbed_timestamp=first_ts,
        last_dubbed_timestamp=last_ts,
        largest_missing_gap=largest_gap,
        largest_missing_gap_window=largest_gap_window)


def synthesize_verdict(
    check: DeterministicCheckResult, visual: Optional[VisualFindings] = None, *,
    speech_coverage: Optional["SpeechCoverageMetrics"] = None,
    min_coverage_ratio: float = MIN_SEGMENT_COVERAGE_RATIO,
    max_missing_gap_seconds: float = MAX_UNEXPLAINED_MISSING_GAP_SECONDS,
) -> QAVerdict:
    """Combine deterministic facts with an optional visual pass — module
    docstring principle 4. A deterministic hard-fail always wins. A clean
    deterministic pass with NO visual review (the common case, since visual
    QA is optional) is QA_REVIEW, not QA_PASS: an unreviewed draft must
    never look identical to a reviewed-and-clean one. QA_PASS requires both
    a clean deterministic pass AND an explicit, positive visual read.

    `speech_coverage`, if given, is the OTHER hard gate this function
    enforces (mission section 6 — "prevent recurrence" of the real
    wikitongues_henan defect): segment coverage below `min_coverage_ratio`
    or a single missing-speech gap above `max_missing_gap_seconds` is
    QA_FAIL regardless of how clean the visual read was — a beautiful-
    looking video that is 85% silent must never reach DRAFT_READY.
    """
    if check.hard_fail:
        return QAVerdict.QA_FAIL

    if speech_coverage is not None:
        if not speech_coverage.passes(min_coverage_ratio):
            return QAVerdict.QA_FAIL
        if speech_coverage.largest_missing_gap > max_missing_gap_seconds:
            return QAVerdict.QA_FAIL

    if visual is None or not visual.reviewed:
        return QAVerdict.QA_REVIEW

    visual_flags = [
        visual.visual_continuity_ok, visual.subtitles_present_readable,
        visual.aspect_ratio_ok, visual.visual_quality_acceptable,
        visual.usable_as_draft,
    ]
    if visual.black_or_broken_frames_seen is True:
        return QAVerdict.QA_FAIL
    if any(flag is False for flag in visual_flags):
        return QAVerdict.QA_REVIEW
    if check.warnings:
        # Deterministic warnings survived even a positive visual read (e.g.
        # the dub-coverage gap itself, which is real regardless of how
        # clean the video looks) — still needs a human decision, not a
        # silent pass.
        return QAVerdict.QA_REVIEW
    if all(flag is True for flag in visual_flags):
        return QAVerdict.QA_PASS
    return QAVerdict.QA_REVIEW


@dataclass
class QAGateResult:
    verdict: QAVerdict
    check: DeterministicCheckResult
    plan: WatchPlan
    visual: Optional[VisualFindings]
    speech_coverage: Optional[SpeechCoverageMetrics] = None


def run_qa_gate(
    video_path: Path, *,
    visual_reviewer: Optional[Any] = None,
    force_full_pass: bool = False,
    speech_coverage: Optional[SpeechCoverageMetrics] = None,
    min_coverage_ratio: float = MIN_SEGMENT_COVERAGE_RATIO,
    max_missing_gap_seconds: float = MAX_UNEXPLAINED_MISSING_GAP_SECONDS,
) -> QAGateResult:
    """The full stage in one call:

        RENDERED -> deterministic_checks() -> build_watch_plan()
                  -> [visual_reviewer(plan) if given] -> synthesize_verdict()

    This is the integration point a caller wires in right after a render
    step (e.g. `chinese_media_pipeline.py::compose_with_source()`) and right
    before shipping a draft (`ship_draft()`) — intentionally NOT wired into
    any existing pipeline `main()` here (see module docstring: this stage is
    optional and additive, not a pipeline redesign).

    `visual_reviewer`, if given, is any callable `(WatchPlan) ->
    VisualFindings` — the ONLY model-touching seam in this entire module.
    Passing None (the default) runs deterministic-only and returns
    QA_REVIEW for anything that isn't a hard fail, per
    `synthesize_verdict()`'s documented behavior. A Router V3/OpenCode/
    Codex agent supplies its own reviewer here; Claude Code supplies one
    that shells out to the installed `/watch` plugin and reads frames with
    the Read tool, exactly as done for the real proof this module is
    grounded in.

    `speech_coverage`, if given (a caller-computed `compute_speech_coverage()`
    result — this module has no ASR/dub-timing knowledge of its own, so it
    never computes this itself), is the recurrence-prevention gate from
    mission "FIX REAL CHINESE DUB COVERAGE" section 6: coverage below
    `min_coverage_ratio` or a missing-speech gap above
    `max_missing_gap_seconds` forces QA_FAIL regardless of the visual read.
    """
    check = deterministic_checks(video_path)
    plan = build_watch_plan(check, force_full_pass=force_full_pass)
    visual: Optional[VisualFindings] = None
    if visual_reviewer is not None and not plan.skipped:
        visual = visual_reviewer(plan)
    verdict = synthesize_verdict(
        check, visual, speech_coverage=speech_coverage,
        min_coverage_ratio=min_coverage_ratio,
        max_missing_gap_seconds=max_missing_gap_seconds)
    return QAGateResult(verdict=verdict, check=check, plan=plan, visual=visual,
                        speech_coverage=speech_coverage)


