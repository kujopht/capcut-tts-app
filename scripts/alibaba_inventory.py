"""
Công cụ dòng lệnh cho kiểm kê model Alibaba (NGOẠI TUYẾN: chỉ đọc/ghi tệp cục bộ, không mạng, không production, không bí mật).

    python scripts/alibaba_inventory.py validate docs/ai/alibaba_model_inventory.json
    python scripts/alibaba_inventory.py report   docs/ai/alibaba_model_inventory.json
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

from server.ai_assistant.control import alibaba_inventory as inv  # noqa: E402
from server.ai_assistant.control.model import CAPABILITY_TIERS, ConfigValidationError  # noqa: E402

#: Với mỗi trường còn thiếu: Owner cần lấy nó ở ĐÂU trên console (để câu trả lời "cần ảnh chụp gì" luôn khớp với mã).
WHERE = {
    "tiers": "Owner/Claude phân loại tầng (FAST/SMART/ADVANCED/TRANSLATION/VISION/EMBEDDING) dựa trên trang chi tiết model",
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
    for m in data.models:
        state, why = inv.readiness(m, now)
        _out(f"{m.model_id}  [{m.status}]  tầng={','.join(m.tiers) or '(chưa phân loại)'}  thinking(slot)={m.slot_thinking}  => {state}")
        for w in why:
            _out(f"    - {w}")
        for w in inv.warnings(m):
            _out(f"    ! {w}")
        for g in inv.missing(m):
            needed.setdefault(g, []).append(m.model_id)
    _out()
    _out("Phủ theo tầng (model READY, hạn dùng sớm nhất trước):")
    cov = inv.tier_coverage(data, now)
    for t in CAPABILITY_TIERS:
        _out(f"  {t:<12} {', '.join(cov[t]) if cov[t] else '(chưa có model đủ dữ liệu để tạo slot)'}")
    if needed:
        _out()
        _out("Dữ liệu còn thiếu (trường -> model -> lấy ở đâu):")
        for k, models in needed.items():
            _out(f"  {k}: {', '.join(models)}  <- {WHERE.get(k, '')}")
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
    s = sub.add_parser("report"); s.add_argument("file"); s.add_argument("--now", default=""); s.set_defaults(fn=cmd_report)
    s = sub.add_parser("from-csv"); s.add_argument("csv"); s.add_argument("--captured-at", default=""); s.add_argument("--region", default="")
    s.set_defaults(fn=cmd_from_csv)
    s = sub.add_parser("slot"); s.add_argument("file"); s.add_argument("model_id"); s.add_argument("--slot-id", required=True)
    s.add_argument("--secret-ref", required=True); s.add_argument("--endpoint", required=True); s.add_argument("--workloads", default="general")
    s.set_defaults(fn=cmd_slot)
    s = sub.add_parser("template"); s.set_defaults(fn=cmd_template)
    args = p.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
