"""
Giao dien dong lenh (headless) cua Fanfic Audio Studio.

Muc dich: Claude Code — hoac bat ky cong cu tu dong hoa nao — co the tao audio
cho mot arc DA HOAN TAT ma khong can mo giao dien.

    FanficAudioStudio.exe generate-arc --input <arc-file> --output <output-dir> \
        --voice "Ngọc Huyền"

Cac lenh:
    init-arc        tao manifest cho mot arc (trang thai `draft`)
    finalize-arc    danh dau arc da hoan tat (`finalized`) va chot hash ban thao
    generate-arc    tao audio — CHI khi manifest ghi `status: finalized`
    arc-status      xem trang thai arc va trang thai audio
    list-voices     liet ke giong kha dung (de biet dung id giong)

Toan bo viec tao audio di qua `desktop_app.arc_pipeline`, tuc la qua dung
`ProviderRegistry` + `QueueManager` ma giao dien dang dung. Khong co logic
provider nao duoc viet lai o day.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from desktop_app import APP_NAME, APP_VERSION
from desktop_app.arc_manifest import (
    AUDIO_COMPLETED,
    DEFAULT_RATE,
    DEFAULT_VOICE_ID,
    STATUS_DRAFT,
    STATUS_FINALIZED,
    ArcManifest,
    ArcManifestError,
    audio_relative_path,
    find_manifest,
    manifest_path_for,
    safe_name_component,
)
from desktop_app.arc_pipeline import (
    EXIT_MANIFEST,
    EXIT_MANUSCRIPT,
    EXIT_OK,
    EXIT_USAGE,
    RESULT_SKIPPED,
    ArcError,
    build_headless_registry,
    generate_arc_audio,
    is_up_to_date,
    write_report,
)
from desktop_app.models import content_hash, human_duration, human_size

#: Ten cac lenh con — `app.py` dung danh sach nay de biet khi nao phai chay o
#: che do dong lenh thay vi mo cua so.
COMMANDS = (
    "generate-arc",
    "finalize-arc",
    "init-arc",
    "arc-status",
    "list-voices",
)

PROG = "FanficAudioStudio"


# -----------------------------------------------------------------------------
# In ra man hinh
# -----------------------------------------------------------------------------


def _reconfigure_streams() -> None:
    """
    Bat buoc stdout/stderr dung UTF-8.

    Ten giong va thong bao deu co dau tieng Viet; console Windows mac dinh dung
    cp1252/cp437 nen se nem UnicodeEncodeError neu khong doi.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _out(message: str = "") -> None:
    try:
        print(message, flush=True)
    except Exception:
        pass


def _err(message: str) -> None:
    try:
        print(message, file=sys.stderr, flush=True)
    except Exception:
        pass


def _fail(exit_code: int, message: str, hint: str = "") -> int:
    _err(f"LỖI: {message}")
    if hint:
        _err(f"→ {hint}")
    return exit_code


# -----------------------------------------------------------------------------
# Parser
# -----------------------------------------------------------------------------


def _add_common_tts_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--voice", help='Giọng đọc, ví dụ "Ngọc Huyền" hoặc piper:ngochuyen')
    parser.add_argument("--rate", help="Hệ số tốc độ đọc, ví dụ 1.0 hoặc 1.15")
    parser.add_argument("--chunk-chars", type=int, help="Số ký tự tối đa mỗi phần")
    parser.add_argument("--ffmpeg", help="Đường dẫn ffmpeg.exe (nếu không có trong PATH)")
    parser.add_argument("--device-json", help="device.json cho nguồn CapCut")
    parser.add_argument("--catalog", help="Đường dẫn Voice.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=f"{APP_NAME} — giao diện dòng lệnh tạo audio cho arc đã hoàn tất.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ví dụ:\n"
            f"  {PROG} init-arc --manuscript arc-01.md --arc-id arc-01 --output D:\\audio\n"
            f"  {PROG} finalize-arc --input arc-01.arc.json\n"
            f'  {PROG} generate-arc --input arc-01.arc.json --output D:\\audio --voice "Ngọc Huyền"\n'
            f"  {PROG} arc-status --input arc-01.arc.json\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    subs = parser.add_subparsers(dest="command", metavar="<lệnh>")

    # -- init-arc ------------------------------------------------------------
    init = subs.add_parser(
        "init-arc",
        help="Tạo manifest cho một arc (trạng thái draft)",
        description=(
            "Tạo manifest cho một arc. Manifest luôn bắt đầu ở trạng thái 'draft' — "
            "chưa được tạo audio."
        ),
    )
    init.add_argument("--manuscript", required=True, help="File bản thảo (.txt/.md/.docx)")
    init.add_argument("--arc-id", help="Mã arc (mặc định: lấy từ tên file bản thảo)")
    init.add_argument("--title", help="Tên arc để hiển thị")
    init.add_argument("--output", help="Thư mục xuất audio")
    init.add_argument("--manifest", help="Nơi ghi manifest (mặc định: <tên bản thảo>.arc.json)")
    init.add_argument("--force", action="store_true", help="Ghi đè manifest đã có")
    _add_common_tts_args(init)

    # -- finalize-arc --------------------------------------------------------
    final = subs.add_parser(
        "finalize-arc",
        help="Đánh dấu arc đã hoàn tất (chỉ chạy sau khi người dùng xác nhận)",
        description=(
            "Đặt status = finalized và chốt hash nội dung bản thảo hiện tại. "
            "CHỈ chạy lệnh này sau khi người dùng đã xác nhận arc hoàn tất — "
            "đây chính là mốc cho phép tạo audio."
        ),
    )
    final.add_argument("--input", required=True, help="Manifest, hoặc bản thảo có manifest bên cạnh")
    final.add_argument("--output", help="Cập nhật thư mục xuất audio")
    final.add_argument("--voice", help="Cập nhật giọng mặc định của arc")
    final.add_argument("--title", help="Cập nhật tên arc")

    # -- generate-arc --------------------------------------------------------
    gen = subs.add_parser(
        "generate-arc",
        help="Tạo audio cho arc đã hoàn tất",
        description=(
            "Tạo audio cho arc. Chỉ chạy khi manifest ghi status: finalized. "
            "Chạy lại với cùng nội dung/giọng/thiết lập thì không tạo lại."
        ),
    )
    gen.add_argument("--input", required=True, help="Manifest, hoặc bản thảo có manifest bên cạnh")
    gen.add_argument("--output", help="Thư mục xuất audio (ghi đè giá trị trong manifest)")
    _add_common_tts_args(gen)
    gen.add_argument("--report", help="Ghi report JSON của lần chạy ra file này")
    gen.add_argument("--force", action="store_true", help="Tạo lại dù đã có bản audio đúng")
    gen.add_argument(
        "--keep-work",
        action="store_true",
        help="Giữ thư mục làm việc tạm sau khi thành công (để tra cứu từng phần)",
    )
    gen.add_argument(
        "--work-dir",
        help=(
            "Gốc thư mục làm việc tạm (mặc định: "
            "%LOCALAPPDATA%\\FanficAudioStudio\\arc-work). Hãy chọn đường dẫn NGẮN."
        ),
    )
    gen.add_argument(
        "--gap-between-parts",
        type=float,
        help="Số giây nghỉ giữa các phần (mặc định: 0 với giọng cục bộ, 2 với giọng qua mạng)",
    )
    gen.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    # -- arc-status ----------------------------------------------------------
    status = subs.add_parser(
        "arc-status",
        help="Xem trạng thái arc và trạng thái audio",
    )
    status.add_argument("--input", required=True, help="Manifest, hoặc bản thảo có manifest bên cạnh")
    status.add_argument("--output", help="Thư mục xuất audio để kiểm tra file kết quả")
    status.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    # -- list-voices ---------------------------------------------------------
    voices = subs.add_parser("list-voices", help="Liệt kê giọng khả dụng")
    voices.add_argument("--provider", help="Chỉ hiện một nguồn: capcut | edge | piper")
    voices.add_argument("--query", help="Từ khoá tìm kiếm")
    voices.add_argument("--installed-only", action="store_true", help="Chỉ giọng đã sẵn sàng")
    voices.add_argument("--catalog", help="Đường dẫn Voice.json")
    voices.add_argument("--ffmpeg", help="Đường dẫn ffmpeg.exe")
    voices.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    return parser


# -----------------------------------------------------------------------------
# init-arc
# -----------------------------------------------------------------------------


def cmd_init_arc(args: argparse.Namespace) -> int:
    manuscript = Path(args.manuscript).expanduser()
    if not manuscript.is_file():
        return _fail(EXIT_MANUSCRIPT, f"Không tìm thấy bản thảo: {manuscript}")

    manifest_path = (
        Path(args.manifest).expanduser() if args.manifest else manifest_path_for(manuscript)
    )
    if manifest_path.exists() and not args.force:
        return _fail(
            EXIT_MANIFEST,
            f"Manifest đã tồn tại: {manifest_path}",
            "Dùng --force nếu bạn thực sự muốn ghi đè.",
        )

    arc_id = safe_name_component(args.arc_id or manuscript.stem, fallback="arc")

    # Duong dan ban thao duoc ghi TUONG DOI khi cung nam trong thu muc manifest,
    # nho vay ca thu muc arc co the di chuyen ma manifest van dung.
    try:
        rel = manuscript.resolve().relative_to(manifest_path.expanduser().resolve().parent)
        manuscript_value = rel.as_posix()
    except (ValueError, OSError):
        manuscript_value = str(manuscript.resolve())

    manifest = ArcManifest(
        arc_id=arc_id,
        manuscript=manuscript_value,
        title=args.title or manuscript.stem,
        status=STATUS_DRAFT,
        voice=(args.voice or DEFAULT_VOICE_ID).strip(),
        output_dir=str(Path(args.output).expanduser()) if args.output else "",
        rate=(args.rate or DEFAULT_RATE).strip(),
        path=manifest_path,
    )
    if args.chunk_chars is not None:
        manifest.chunk_chars = args.chunk_chars

    try:
        written = manifest.save()
    except ArcManifestError as exc:
        return _fail(EXIT_MANIFEST, str(exc))

    _out(f"Đã tạo manifest: {written}")
    _out(f"  arc_id     : {manifest.arc_id}")
    _out(f"  bản thảo   : {manifest.manuscript_path()}")
    _out(f"  giọng      : {manifest.voice}")
    _out(f"  output     : {manifest.resolved_output_dir()}")
    _out(f"  status     : {manifest.status}  (chưa được tạo audio)")
    _out("")
    _out(
        "Bước tiếp theo: sau khi người dùng xác nhận arc đã hoàn tất, chạy "
        f"'{PROG} finalize-arc --input {written.name}'."
    )
    return EXIT_OK


# -----------------------------------------------------------------------------
# finalize-arc
# -----------------------------------------------------------------------------


def cmd_finalize_arc(args: argparse.Namespace) -> int:
    from desktop_app.text_importer import import_file

    try:
        manifest_path = find_manifest(args.input)
        manifest = ArcManifest.load(manifest_path)
    except ArcManifestError as exc:
        return _fail(EXIT_MANIFEST, str(exc))

    manuscript = manifest.manuscript_path()
    item = import_file(manuscript)
    if item.error:
        return _fail(
            EXIT_MANUSCRIPT,
            f"Không đọc được bản thảo '{manuscript}': {item.error}",
            "Hãy lưu bản cuối của arc rồi chạy lại.",
        )

    new_hash = content_hash(item.text)
    was_finalized = manifest.is_finalized
    changed = manifest.content_sha256 != new_hash

    if args.output:
        manifest.output_dir = str(Path(args.output).expanduser())
    if args.voice:
        manifest.voice = args.voice.strip()
    if args.title:
        manifest.title = args.title

    manifest.status = STATUS_FINALIZED
    manifest.content_sha256 = new_hash
    manifest.finalized_at = datetime.now().isoformat(timespec="seconds")

    try:
        manifest.save()
    except ArcManifestError as exc:
        return _fail(EXIT_MANIFEST, str(exc))

    _out(f"Đã đánh dấu HOÀN TẤT: {manifest.arc_id}")
    _out(f"  manifest   : {manifest.path}")
    _out(f"  bản thảo   : {manuscript}")
    _out(f"  số ký tự   : {len(item.text):,}")
    _out(f"  hash       : {new_hash}")
    _out(f"  giọng      : {manifest.voice}")
    _out(f"  output     : {manifest.resolved_output_dir()}")
    if was_finalized and changed:
        _out(
            "  lưu ý      : nội dung đã thay đổi so với lần hoàn tất trước — "
            "lần tạo audio tới sẽ tạo lại và thay thế an toàn file cũ."
        )
    elif was_finalized and not changed:
        _out("  lưu ý      : nội dung không đổi so với lần hoàn tất trước.")
    _out("")
    _out(f"Bước tiếp theo: '{PROG} generate-arc --input {Path(manifest.path).name}'.")
    return EXIT_OK


# -----------------------------------------------------------------------------
# generate-arc
# -----------------------------------------------------------------------------


def _report_target(args: argparse.Namespace) -> Optional[Path]:
    if not getattr(args, "report", None):
        return None
    return Path(args.report).expanduser()


def cmd_generate_arc(args: argparse.Namespace) -> int:
    try:
        manifest_path = find_manifest(args.input)
        manifest = ArcManifest.load(manifest_path)
    except ArcManifestError as exc:
        return _fail(EXIT_MANIFEST, str(exc))

    report_path = _report_target(args)
    quiet = bool(args.json)

    def log(message: str) -> None:
        if not quiet:
            _out(message)

    try:
        outcome = generate_arc_audio(
            manifest,
            output_dir=Path(args.output).expanduser() if args.output else None,
            voice_query=args.voice,
            rate=args.rate,
            chunk_chars=args.chunk_chars,
            ffmpeg_path=args.ffmpeg,
            device_path=args.device_json,
            catalog_path=args.catalog,
            force=bool(args.force),
            keep_work=bool(args.keep_work),
            work_dir=Path(args.work_dir).expanduser() if args.work_dir else None,
            gap_between_parts=args.gap_between_parts,
            log=log,
        )
    except ArcError as exc:
        if report_path is not None:
            write_report(
                report_path,
                {
                    "app": {"name": APP_NAME, "version": APP_VERSION},
                    "status": "failed",
                    "exit_code": exc.exit_code,
                    "arc_id": manifest.arc_id,
                    "manifest": str(manifest_path),
                    "error_message": exc.message,
                    "hint": exc.hint,
                    "written_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        return _fail(exc.exit_code, exc.message, exc.hint)
    except Exception as exc:  # lop bao ve cuoi: khong bao gio in traceback tho
        import traceback

        detail = traceback.format_exc()[-1500:]
        if report_path is not None:
            write_report(
                report_path,
                {
                    "app": {"name": APP_NAME, "version": APP_VERSION},
                    "status": "failed",
                    "exit_code": 1,
                    "arc_id": manifest.arc_id,
                    "manifest": str(manifest_path),
                    "error_message": f"{type(exc).__name__}: {exc}",
                    "detail": detail,
                    "written_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        _err(detail)
        return _fail(1, f"Lỗi ngoài dự kiến: {type(exc).__name__}: {exc}")

    data = outcome.to_dict()
    data["written_at"] = datetime.now().isoformat(timespec="seconds")
    written_report = write_report(report_path, data) if report_path is not None else None
    if written_report:
        data["report"] = written_report

    if args.json:
        _out(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _print_outcome(outcome, written_report)

    return outcome.exit_code


def _print_outcome(outcome, report: Optional[str]) -> None:
    _out("")
    if outcome.ok:
        headline = (
            "ĐÃ CÓ SẴN (không tạo lại)"
            if outcome.status == RESULT_SKIPPED
            else "TẠO AUDIO THÀNH CÔNG"
        )
        _out(f"=== {headline} ===")
    else:
        _out("=== TẠO AUDIO THẤT BẠI ===")

    _out(f"  arc          : {outcome.arc_id}")
    _out(f"  giọng        : {outcome.voice_label} ({outcome.voice_id})")
    _out(f"  nguồn TTS    : {outcome.provider_label}")
    if outcome.ok:
        _out(f"  file audio   : {outcome.output_path}")
        _out(
            "  thời lượng   : "
            + (
                human_duration(outcome.duration_seconds)
                if outcome.duration_seconds is not None
                else "chưa đo được (thiếu ffprobe)"
            )
        )
        _out(f"  kích thước   : {human_size(outcome.size_bytes)} ({outcome.size_bytes:,} byte)")
        if outcome.total_parts:
            _out(f"  số phần      : {outcome.done_parts}/{outcome.total_parts}")
        if outcome.elapsed_seconds:
            _out(f"  thời gian chạy: {human_duration(outcome.elapsed_seconds)}")
    else:
        _out(f"  loại lỗi     : {outcome.error_kind or '—'}")
        _out(f"  lỗi          : {outcome.error_message}")
        if outcome.work_dir:
            _out(f"  thư mục tạm  : {outcome.work_dir}")
        _out("  file audio cũ (nếu có) KHÔNG bị thay đổi.")
    _out(f"  manifest     : {outcome.manifest_path}")
    if report:
        _out(f"  report       : {report}")


# -----------------------------------------------------------------------------
# arc-status
# -----------------------------------------------------------------------------


def cmd_arc_status(args: argparse.Namespace) -> int:
    from desktop_app.text_importer import import_file

    try:
        manifest_path = find_manifest(args.input)
        manifest = ArcManifest.load(manifest_path)
    except ArcManifestError as exc:
        return _fail(EXIT_MANIFEST, str(exc))

    manuscript = manifest.manuscript_path()
    item = import_file(manuscript)
    current_hash = "" if item.error else content_hash(item.text)

    out_dir = manifest.resolved_output_dir(
        Path(args.output).expanduser() if args.output else None
    )
    audio = manifest.audio
    target = Path(audio.output_path) if audio.output_path else None
    if target is None and audio.voice_label:
        target = out_dir / audio_relative_path(manifest.arc_id, safe_name_component(audio.voice_label))

    file_exists = bool(target and target.is_file())
    file_size = target.stat().st_size if file_exists else 0

    up_to_date = bool(
        current_hash
        and target is not None
        and is_up_to_date(
            audio, current_hash, audio.voice_id, audio.rate, audio.chunk_chars, target
        )
    )
    content_changed = bool(
        current_hash and manifest.content_sha256 and manifest.content_sha256 != current_hash
    )

    data: Dict[str, Any] = {
        "arc_id": manifest.arc_id,
        "title": manifest.title,
        "manifest": str(manifest_path),
        "status": manifest.status,
        "finalized": manifest.is_finalized,
        "finalized_at": manifest.finalized_at,
        "manuscript": str(manuscript),
        "manuscript_readable": not bool(item.error),
        "manuscript_error": item.error or "",
        "manuscript_chars": len(item.text or ""),
        "manifest_content_sha256": manifest.content_sha256,
        "current_content_sha256": current_hash,
        "content_changed_since_finalize": content_changed,
        "voice": manifest.voice,
        "rate": manifest.rate,
        "chunk_chars": manifest.chunk_chars,
        "output_dir": str(out_dir),
        "audio": audio.to_dict(),
        "audio_file_exists": file_exists,
        "audio_file_size": file_size,
        "audio_up_to_date": up_to_date,
    }

    if args.json:
        _out(json.dumps(data, ensure_ascii=False, indent=2))
        return EXIT_OK

    _out(f"=== ARC {manifest.arc_id} ===")
    _out(f"  tên          : {manifest.title or '—'}")
    _out(f"  manifest     : {manifest_path}")
    _out(
        "  trạng thái   : "
        + (f"{manifest.status} (ĐÃ HOÀN TẤT)" if manifest.is_finalized
           else f"{manifest.status or '(trống)'} — CHƯA hoàn tất, không được tạo audio")
    )
    if manifest.finalized_at:
        _out(f"  hoàn tất lúc : {manifest.finalized_at}")
    _out(f"  bản thảo     : {manuscript}")
    if item.error:
        _out(f"  đọc bản thảo : LỖI — {item.error}")
    else:
        _out(f"  số ký tự     : {len(item.text):,}")
    if content_changed:
        _out(
            "  CẢNH BÁO     : bản thảo đã thay đổi sau khi đánh dấu hoàn tất — "
            "cần chạy lại 'finalize-arc'."
        )
    _out(f"  giọng        : {manifest.voice}")
    _out(f"  output       : {out_dir}")
    _out("")
    _out(f"  audio state  : {audio.state}")
    if audio.voice_id:
        _out(f"  audio giọng  : {audio.voice_label} ({audio.voice_id})")
    if audio.output_path:
        _out(f"  audio file   : {audio.output_path}")
        _out(f"  file tồn tại : {'có' if file_exists else 'KHÔNG'}")
    if audio.state == AUDIO_COMPLETED and file_exists:
        _out(f"  kích thước   : {human_size(file_size)}")
        if audio.duration_seconds is not None:
            _out(f"  thời lượng   : {human_duration(audio.duration_seconds)}")
    if audio.error_message:
        _out(f"  lỗi lần trước: [{audio.error_kind}] {audio.error_message}")
    _out(
        "  cần tạo lại  : "
        + ("KHÔNG — đã có bản đúng" if up_to_date else "CÓ")
    )
    return EXIT_OK


# -----------------------------------------------------------------------------
# list-voices
# -----------------------------------------------------------------------------


def cmd_list_voices(args: argparse.Namespace) -> int:
    from desktop_app.providers.base import provider_label

    registry = build_headless_registry(
        catalog_path=args.catalog, ffmpeg_path=args.ffmpeg
    )
    try:
        voices = registry.filter_voices(query=args.query or "", provider=args.provider or None)
        if args.installed_only:
            voices = [v for v in voices if v.installed]

        rows: List[Dict[str, Any]] = []
        for voice in voices:
            info = registry.status_of(voice)
            rows.append(
                {
                    "id": voice.id,
                    "display_name": voice.display_name,
                    "provider": voice.provider,
                    "provider_label": provider_label(voice.provider),
                    "language": voice.language,
                    "installed": voice.installed,
                    "status": info.status.value,
                    "status_reason": info.reason,
                    "is_default": voice.id == DEFAULT_VOICE_ID,
                }
            )

        if args.json:
            _out(json.dumps({"count": len(rows), "voices": rows}, ensure_ascii=False, indent=2))
            return EXIT_OK

        if not rows:
            _out("Không có giọng nào khớp điều kiện.")
            return EXIT_OK

        _out(f"{len(rows)} giọng:")
        for row in rows:
            mark = " ← mặc định" if row["is_default"] else ""
            ready = "sẵn sàng" if row["installed"] else f"chưa dùng được ({row['status_reason']})"
            _out(
                f"  {row['id']:<34} {row['display_name'] or '—':<34} "
                f"{row['provider_label']:<12} {row['language'] or '—':<7} {ready}{mark}"
            )
        return EXIT_OK
    finally:
        try:
            registry.close()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Dieu phoi
# -----------------------------------------------------------------------------

_HANDLERS = {
    "init-arc": cmd_init_arc,
    "finalize-arc": cmd_finalize_arc,
    "generate-arc": cmd_generate_arc,
    "arc-status": cmd_arc_status,
    "list-voices": cmd_list_voices,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    _reconfigure_streams()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.command:
        parser.print_help()
        return EXIT_USAGE

    handler = _HANDLERS.get(args.command)
    if handler is None:  # pragma: no cover - argparse da chan truoc
        return _fail(EXIT_USAGE, f"Lệnh không hợp lệ: {args.command}")

    try:
        return int(handler(args))
    except ArcError as exc:
        return _fail(exc.exit_code, exc.message, exc.hint)
    except KeyboardInterrupt:
        _err("Đã dừng theo yêu cầu (Ctrl+C).")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
