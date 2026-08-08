"""
Thu vien ket qua: doc lai cac lan chay truoc trong thu muc outputs.

Chi DOC, khong bao gio sua/xoa ket qua cu.
Nguon du lieu: report.json cua moi lan chay, va manifest.json cua tung job;
neu thieu file JSON thi van liet ke duoc tu cac file MP3 co tren dia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from desktop_app.output_manager import MANIFEST_NAME, REPORT_NAME, load_manifest


@dataclass
class LibraryAudio:
    """Mot file audio trong thu vien."""

    path: str
    name: str
    size: int = 0
    is_full: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "size": self.size,
            "is_full": self.is_full,
        }


@dataclass
class LibraryJob:
    """Mot job (input x voice) trong mot lan chay."""

    job_dir: str
    input_name: str
    voice_label: str
    voice_type: str = ""
    state: str = ""
    message: str = ""
    total_parts: int = 0
    done_parts: int = 0
    full_audio: Optional[str] = None
    merge_note: str = ""
    error_kind: str = ""
    audios: List[LibraryAudio] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_dir": self.job_dir,
            "input_name": self.input_name,
            "voice_label": self.voice_label,
            "voice_type": self.voice_type,
            "state": self.state,
            "message": self.message,
            "total_parts": self.total_parts,
            "done_parts": self.done_parts,
            "full_audio": self.full_audio,
            "merge_note": self.merge_note,
            "error_kind": self.error_kind,
            "audios": [a.to_dict() for a in self.audios],
        }


@dataclass
class LibraryRun:
    """Mot lan chay (mot thu muc dau thoi gian)."""

    run_dir: str
    name: str
    started_at: str = ""
    modified_at: str = ""
    jobs: List[LibraryJob] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    has_report: bool = False

    @property
    def audio_count(self) -> int:
        return sum(len(job.audios) for job in self.jobs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "name": self.name,
            "started_at": self.started_at,
            "modified_at": self.modified_at,
            "summary": self.summary,
            "has_report": self.has_report,
            "audio_count": self.audio_count,
            "jobs": [job.to_dict() for job in self.jobs],
        }


def _list_audios(job_dir: Path, full_name: Optional[str] = None) -> List[LibraryAudio]:
    audios: List[LibraryAudio] = []
    try:
        for path in sorted(job_dir.glob("*.mp3")):
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            is_full = path.name.endswith("_full.mp3") or (
                full_name is not None and path.name == Path(full_name).name
            )
            audios.append(
                LibraryAudio(path=str(path), name=path.name, size=size, is_full=is_full)
            )
    except OSError:
        return audios
    # File full len dau danh sach
    audios.sort(key=lambda a: (not a.is_full, a.name))
    return audios


def _job_from_manifest(job_dir: Path, data: Dict[str, Any]) -> LibraryJob:
    full_audio = data.get("full_audio")
    if full_audio and not Path(full_audio).is_file():
        # Ket qua co the da bi di chuyen: thu tim theo ten trong chinh thu muc
        candidate = job_dir / Path(str(full_audio)).name
        full_audio = str(candidate) if candidate.is_file() else None

    return LibraryJob(
        job_dir=str(job_dir),
        input_name=str(data.get("input_name") or job_dir.parent.name),
        voice_label=str(data.get("voice_display_name") or data.get("voice_type") or job_dir.name),
        voice_type=str(data.get("voice_type") or ""),
        state=str(data.get("state") or ""),
        message=str(data.get("message") or ""),
        total_parts=int(data.get("total_parts") or 0),
        done_parts=int(data.get("done_parts") or 0),
        full_audio=full_audio,
        merge_note=str(data.get("merge_note") or ""),
        error_kind=str(data.get("error_kind") or ""),
        audios=_list_audios(job_dir, full_audio),
    )


def _job_from_disk(job_dir: Path) -> Optional[LibraryJob]:
    """Du phong khi khong co manifest.json: dung lai tu file tren dia."""
    audios = _list_audios(job_dir)
    if not audios:
        return None
    full = next((a.path for a in audios if a.is_full), None)
    parts = [a for a in audios if not a.is_full]
    return LibraryJob(
        job_dir=str(job_dir),
        input_name=job_dir.parent.name,
        voice_label=job_dir.name,
        state="unknown",
        message="Không có manifest.json — dựng lại từ file trên đĩa",
        total_parts=len(parts),
        done_parts=len(parts),
        full_audio=full,
        audios=audios,
    )


def scan_run(run_dir: Path | str) -> Optional[LibraryRun]:
    """Doc mot thu muc lan chay. Tra None neu khong co gi ben trong."""
    root = Path(run_dir)
    if not root.is_dir():
        return None

    try:
        modified = datetime.fromtimestamp(root.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        modified = ""

    run = LibraryRun(run_dir=str(root), name=root.name, modified_at=modified)

    report = load_manifest(root / REPORT_NAME)
    if report:
        run.has_report = True
        run.started_at = str(report.get("started_at") or "")
        summary = report.get("summary")
        if isinstance(summary, dict):
            run.summary = {
                str(k): int(v) for k, v in summary.items() if isinstance(v, (int, float))
            }

    # Quet <run>/<input>/<voice>/
    try:
        input_dirs = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        input_dirs = []

    for input_dir in input_dirs:
        try:
            voice_dirs = sorted(p for p in input_dir.iterdir() if p.is_dir())
        except OSError:
            continue
        for voice_dir in voice_dirs:
            data = load_manifest(voice_dir / MANIFEST_NAME)
            if data:
                run.jobs.append(_job_from_manifest(voice_dir, data))
            else:
                fallback = _job_from_disk(voice_dir)
                if fallback:
                    run.jobs.append(fallback)

    if not run.jobs and not run.has_report:
        return None
    return run


def scan_runs(outputs_root: Path | str, limit: int = 200) -> List[LibraryRun]:
    """
    Liet ke cac lan chay, moi nhat truoc.
    Bo qua thu muc khong doc duoc thay vi nem exception.
    """
    root = Path(outputs_root)
    if not root.is_dir():
        return []

    try:
        candidates = sorted(
            (p for p in root.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return []

    runs: List[LibraryRun] = []
    for path in candidates[:limit]:
        try:
            run = scan_run(path)
        except Exception:
            continue
        if run is not None:
            runs.append(run)
    return runs
