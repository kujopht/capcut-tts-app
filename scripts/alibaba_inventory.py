"""
Công cụ dòng lệnh cho kiểm kê model Alibaba (NGOẠI TUYẾN: chỉ đọc/ghi tệp cục bộ, không mạng, không production, không bí mật).

    python scripts/alibaba_inventory.py validate docs/ai/alibaba_model_inventory.json
    python scripts/alibaba_inventory.py report   docs/ai/alibaba_model_inventory.json
    python scripts/alibaba_inventory.py parse-console docs/ai/alibaba_free_quota_console_paste.txt --into docs/ai/alibaba_model_inventory.json --out moi.json
    python scripts/alibaba_inventory.py candidates docs/ai/alibaba_model_inventory.json --paste docs/ai/alibaba_free_quota_console_paste.txt --md bao_cao.md
    python scripts/alibaba_inventory.py from-csv bang.csv --captured-at 2026-10-04T03:00:00+00:00 > kiem_ke.json
    python scripts/alibaba_inventory.py slot docs/ai/alibaba_model_inventory.json <model_id> --slot-id alibaba-sg-02 \
        --secret-ref ALIBABA_SG_02 --endpoint <endpoint của workspace>
    python scripts/alibaba_inventory.py template

Mã thoát: 0 = ổn; 1 = tệp/CSV không hợp lệ; 2 = model chưa READY nên không xuất payload slot.
`slot` CHỈ in body JSON (luôn enabled=false); việc tạo slot là thao tác riêng của Owner trên /admin/ai.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.ai_assistant.control import alibaba_candidates as cand  # noqa: E402
from server.ai_assistant.control import alibaba_inventory as inv  # noqa: E402
from server.ai_assistant.control.model import CAPABILITY_TIERS, ConfigValidationError  # noqa: E402

#: Với mỗi trường còn thiếu: Owner cần lấy nó ở ĐÂU trên console (để câu trả lời "cần ảnh chụp gì" luôn khớp với mã).
WHERE = {
    "tiers": "Owner/Claude phân loại tầng (FAST/SMART/ADVANCED/TRANSLATION/VISION/EMBEDDING) dựa trên trang chi tiết model",
    "quota_unit": "Model usage > tab Free Quota: ĐƠN VỊ của hạn mức (token / ký tự / giây / ảnh / lần) — bản dán chỉ có con số, không có đơn vị",
    "free_quota_remaining": "Model usage > tab Free Quota: cột số dư còn lại (cả bảng, mọi trang)",
    "free_quota_snapshot_at": "thời điểm chụp ảnh Free Quota (ngày giờ + múi giờ)",
    "free_quota_expires_at": "Model usage > tab Free Quota: cột hạn dùng",
    "rpm": "trang chi tiết model: mục giới hạn tốc độ (RPM)",
    "tpm": "trang chi tiết model: mục giới hạn tốc độ (TPM)",
    "thinking_support": "trang chi tiết model: chế độ thinking (không có / lai bật-tắt được / chỉ-thinking)",
    "thinking_default": "trang chi tiết model: thinking mặc định bật hay tắt",
    "input_modalities": "trang chi tiết model: đầu vào hỗ trợ (văn bản/ảnh/âm thanh/video)",
    "free_quota_only": "Model usage > tab Free Quota: cột/công tắc Free Quota Only của TỪNG model (bật / chưa bật)",
}


def _out(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def _load(path: str):
    try:
        return inv.load_inventory(path)
    except FileNotFoundError:
        _out(f"KHÔNG TÌM THẤY: {path}")
    except json.JSONDecodeError as exc:
        _out(f"JSON hỏng: {exc}")
    except ConfigValidationError as exc:
        _out(f"KHÔNG HỢP LỆ ({len(exc.errors)} lỗi):")
        for e in exc.errors:
            _out(f"  - {e['field'] or '(gốc)'}: {e['message']}")
    return None


def cmd_validate(args: argparse.Namespace) -> int:
    data = _load(args.file)
    if data is None:
        return 1
    _out(f"HỢP LỆ: {len(data.models)} model, nhà cung cấp {data.provider}, vùng {data.region or '(chưa ghi)'}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data = _load(args.file)
    if data is None:
        return 1
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    needed: dict = {}
    counts = {inv.READY: 0, inv.INCOMPLETE: 0, inv.BLOCKED: 0}
    by_category: dict = {}
    for m in data.models:
        state, why = inv.readiness(m, now)
        counts[state] += 1
        by_category[m.console_category or "(không ghi)"] = by_category.get(m.console_category or "(không ghi)", 0) + 1
        if not args.brief:
            _out(f"{m.model_id}  [{m.status}]  tầng={','.join(m.tiers) or '(chưa phân loại)'}  thinking(slot)={m.slot_thinking}  => {state}")
            for w in why:
                _out(f"    - {w}")
            for w in inv.warnings(m):
                _out(f"    ! {w}")
        for g in inv.missing(m):
            needed.setdefault(g, []).append(m.model_id)
    _out(f"Tổng {len(data.models)} model: READY {counts[inv.READY]} · INCOMPLETE {counts[inv.INCOMPLETE]} · BLOCKED {counts[inv.BLOCKED]}")
    _out("Theo danh mục console: " + ", ".join(f"{k} {v}" for k, v in sorted(by_category.items())))
    _out()
    _out("Phủ theo tầng (model READY, hạn dùng sớm nhất trước):")
    cov = inv.tier_coverage(data, now)
    for t in CAPABILITY_TIERS:
        _out(f"  {t:<12} {', '.join(cov[t]) if cov[t] else '(chưa có model đủ dữ liệu để tạo slot)'}")
    if needed:
        _out()
        _out("Dữ liệu còn thiếu (trường -> model -> lấy ở đâu):")
        for k, models in needed.items():
            shown = ", ".join(models[:4]) + (f" … (+{len(models) - 4})" if len(models) > 4 else "")
            _out(f"  {k} [{len(models)} model]: {shown}  <- {WHERE.get(k, '')}")
    return 0


def cmd_from_csv(args: argparse.Namespace) -> int:
    try:
        text = Path(args.csv).read_text(encoding="utf-8-sig")
        raw = inv.from_csv(text, captured_at=args.captured_at, region=args.region)
        inv.parse_inventory(raw)
    except FileNotFoundError:
        _out(f"KHÔNG TÌM THẤY: {args.csv}")
        return 1
    except ValueError as exc:
        if isinstance(exc, ConfigValidationError):
            sys.stderr.write(f"KHÔNG HỢP LỆ ({len(exc.errors)} lỗi):\n")
            for e in exc.errors:
                sys.stderr.write(f"  - {e['field'] or '(gốc)'}: {e['message']}\n")
        else:
            sys.stderr.write(f"CSV lỗi: {exc}\n")
        return 1
    _out(json.dumps(raw, ensure_ascii=False, indent=2))
    return 0


def cmd_parse_console(args: argparse.Namespace) -> int:
    """Đọc văn bản dán từ bảng Free Quota (tiếng Trung) và gộp vào kiểm kê. In JSON mới ra stdout, hoặc ghi vào --out; tóm tắt ra stderr."""
    try:
        text = Path(args.paste).read_text(encoding="utf-8-sig")
        parsed = inv.parse_console_free_quota(text, captured_at=args.captured_at)
        entries, snap = list(parsed.entries), parsed.snapshot_at
        problems = inv.verify_console_counts(text, parsed)
        raw = inv.raw_line_counts(text)
        by_cat: dict = {}
        for e in entries:
            by_cat[e["console_category"]] = by_cat.get(e["console_category"], 0) + 1
        sys.stderr.write("Số model theo danh mục console (thô → đọc được):\n")
        for cat in sorted(set(raw["heads_by_category"]) | set(by_cat)):
            sys.stderr.write(f"  {cat}: {raw['heads_by_category'].get(cat, 0)} → {by_cat.get(cat, 0)}\n")
        sys.stderr.write(f"  Tổng: {sum(raw['heads_by_category'].values())} → {len(entries)} · dòng hạn mức {raw['quota_lines']} · dòng hạn dùng "
                         f"{raw['expiry_lines']} · dòng trạng thái {raw['state_on'] + raw['state_off']} (bật {raw['state_on']}, chưa bật {raw['state_off']}) "
                         f"· khối tiêu đề {raw['header_blocks']}\n")
        sys.stderr.write("Đối chiếu số đếm: " + ("KHỚP" if not problems else "LỆCH") + "\n")
        for p in problems:
            sys.stderr.write(f"  ! {p}\n")
        for i in parsed.errors:
            sys.stderr.write(f"LỖI dòng {i['line']} [{i['code']}]: {i['message']}\n")
        for i in parsed.warnings:
            sys.stderr.write(f"CẢNH BÁO dòng {i['line']} [{i['code']}]: {i['message']}\n")
        sys.stderr.write(f"Thiếu đơn vị hạn mức (quota_unit): {len(entries)}/{len(entries)} model — bảng không có cột đơn vị.\n")
        if parsed.errors or problems:
            sys.stderr.write("Không ghi kết quả vì còn lỗi/lệch ở trên.\n")
            return 1
        base = (json.loads(Path(args.into).read_text(encoding="utf-8")) if args.into else
                {"version": inv.INVENTORY_VERSION, "provider": inv.PROVIDER, "region": args.region, "captured_at": snap, "models": []})
        merged, rep = inv.merge_console(base, entries, snap)
        inv.parse_inventory(merged)
    except FileNotFoundError as exc:
        sys.stderr.write(f"KHÔNG TÌM THẤY: {exc.filename}\n")
        return 1
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"JSON hỏng: {exc}\n")
        return 1
    except ValueError as exc:
        if isinstance(exc, ConfigValidationError):
            sys.stderr.write(f"KHÔNG HỢP LỆ ({len(exc.errors)} lỗi):\n")
            for e in exc.errors:
                sys.stderr.write(f"  - {e['field'] or '(gốc)'}: {e['message']}\n")
        else:
            sys.stderr.write(f"Văn bản dán lỗi: {exc}\n")
        return 1
    body = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)
    sys.stderr.write(f"Đọc {len(entries)} model (chụp {snap}): thêm {len(rep['added'])}, làm mới {len(rep['refreshed'])}, "
                     f"không đổi {len(rep['unchanged'])}.\n")
    return 0


def cmd_candidates(args: argparse.Namespace) -> int:
    """Báo cáo ỨNG VIÊN năng lực (gợi ý, không phải tầng định tuyến; không ghi vào kiểm kê)."""
    data = _load(args.file)
    if data is None:
        return 1
    try:
        paste = Path(args.paste).read_text(encoding="utf-8-sig") if args.paste else None
        rep = cand.build_report(data, paste)
    except FileNotFoundError as exc:
        sys.stderr.write(f"KHÔNG TÌM THẤY: {exc.filename}\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"Bản dán lỗi: {exc}\n")
        return 1
    if args.md:
        Path(args.md).write_text(cand.render_markdown(rep), encoding="utf-8", newline="\n")
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    _out(f"{rep['models']} model, mốc {rep['as_of'][:10]}. Ứng viên theo nhóm (gợi ý, KHÔNG phải tầng định tuyến):")
    for cls in cand.CANDIDATE_CLASSES:
        rows = rep["classes"][cls]
        _out(f"  {cls:<17} {len(rows):>3}  (category {sum(1 for r in rows if r['strength'] == cand.STRONG)}, name {sum(1 for r in rows if r['strength'] == cand.WEAK)})")
    _out(f"  chưa đủ bằng chứng: {len(rep['unclassified'])}")
    p = rep["parse"]
    if p is not None:
        _out(f"Parse nguồn: {'SẠCH' if not p['errors'] and not p['count_problems'] else 'CÓ VẤN ĐỀ'} — {p['rows']} → {p['entries']}, lỗi {len(p['errors'])}, cảnh báo {len(p['warnings'])}")
    return 1 if (p is not None and (p["errors"] or p["count_problems"])) else 0


def cmd_slot(args: argparse.Namespace) -> int:
    data = _load(args.file)
    if data is None:
        return 1
    entry = data.get(args.model_id)
    if entry is None:
        _out(f"Không có model '{args.model_id}' trong kiểm kê (không đoán id).")
        return 1
    try:
        body = inv.to_slot_dict(entry, slot_id=args.slot_id, secret_ref=args.secret_ref, endpoint=args.endpoint,
                                workloads=tuple(w for w in args.workloads.split(",") if w))
    except ConfigValidationError as exc:
        for e in exc.errors:
            sys.stderr.write(f"CHƯA XUẤT ĐƯỢC: {e['field']}: {e['message']}\n")
        return 2
    _out(json.dumps(body, ensure_ascii=False, indent=2))
    return 0


def cmd_template(_: argparse.Namespace) -> int:
    _out(json.dumps(inv.entry_template(), ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("validate"); s.add_argument("file"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("report"); s.add_argument("file"); s.add_argument("--now", default=""); s.add_argument("--brief", action="store_true")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("parse-console"); s.add_argument("paste"); s.add_argument("--into", default=""); s.add_argument("--out", default="")
    s.add_argument("--captured-at", default=""); s.add_argument("--region", default="ap-southeast-1"); s.set_defaults(fn=cmd_parse_console)
    s = sub.add_parser("from-csv"); s.add_argument("csv"); s.add_argument("--captured-at", default=""); s.add_argument("--region", default="")
    s.set_defaults(fn=cmd_from_csv)
    s = sub.add_parser("candidates"); s.add_argument("file"); s.add_argument("--paste", default=""); s.add_argument("--md", default="")
    s.add_argument("--json", default=""); s.set_defaults(fn=cmd_candidates)
    s = sub.add_parser("slot"); s.add_argument("file"); s.add_argument("model_id"); s.add_argument("--slot-id", required=True)
    s.add_argument("--secret-ref", required=True); s.add_argument("--endpoint", required=True); s.add_argument("--workloads", default="general")
    s.set_defaults(fn=cmd_slot)
    s = sub.add_parser("template"); s.set_defaults(fn=cmd_template)
    args = p.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
