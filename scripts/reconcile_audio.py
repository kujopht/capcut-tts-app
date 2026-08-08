"""
Doi soat object audio voi ban ghi metadata.

MAC DINH CHI DOC. Muon xoa thi phai truyen `--delete --yes-really-delete`, hai co
chu khong phai mot.

    # xem co gi lech (khong xoa gi)
    .venv\\Scripts\\python.exe scripts\\reconcile_audio.py

    # ghi bao cao ra file
    .venv\\Scripts\\python.exe scripts\\reconcile_audio.py --json bao-cao.json

    # xoa that (can CA HAI co)
    .venv\\Scripts\\python.exe scripts\\reconcile_audio.py --delete --yes-really-delete

Script nay KHONG bao gio duoc goi tu luc backend khoi dong. Bo quet job ket va
cong cu nay la hai viec tach roi: mot cai chi doi trang thai job, cai kia moi
cham vao file.

KHONG in secret: chi in object key, kich thuoc va moc thoi gian.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")   # Windows console mac dinh la cp1252

from server.adapters import build_metadata_store, build_storage   # noqa: E402
from server.config import get_settings                            # noqa: E402
from server.reconcile import DEFAULT_GRACE_HOURS, purge, scan     # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Đối soát object audio với bản ghi metadata.")
    parser.add_argument("--delete", action="store_true",
                        help="Xoá object mồ côi. Cần thêm --yes-really-delete.")
    parser.add_argument("--yes-really-delete", action="store_true",
                        help="Xác nhận lần hai. Không có cờ này thì không xoá gì.")
    parser.add_argument("--grace-hours", type=int, default=DEFAULT_GRACE_HOURS,
                        help=f"Thời gian ân hạn, mặc định {DEFAULT_GRACE_HOURS} giờ.")
    parser.add_argument("--json", metavar="FILE",
                        help="Ghi báo cáo dạng JSON ra file.")
    args = parser.parse_args()

    settings = get_settings()
    store = build_metadata_store(settings)
    storage = build_storage(settings)

    print(f"Kho metadata : {getattr(store, 'mode', '?')}")
    print(f"Kho file     : {getattr(storage, 'mode', '?')}")
    print(f"Ân hạn       : {args.grace_hours} giờ")

    if args.delete and not args.yes_really_delete:
        print("\nTừ chối xoá: có --delete nhưng thiếu --yes-really-delete.")
        print("Đây là cố ý — xoá file cần hai cờ, không phải một.")
        return 2

    if args.delete:
        print("Chế độ      : XOÁ\n")
        report = purge(store, storage, confirm=True, grace_hours=args.grace_hours)
    else:
        print("Chế độ      : chỉ đọc (dry-run)\n")
        report = scan(store, storage, grace_hours=args.grace_hours)

    print(f"Tổng object            : {report.tong_object}")
    print(f"  đã được tham chiếu   : {report.da_tham_chieu}")
    print(f"  đang xử lý           : {len(report.dang_xu_ly)}")
    print(f"  còn trong ân hạn     : {len(report.con_moi)}")
    print(f"  MỒ CÔI               : {len(report.mo_coi)}")
    print(f"Bản ghi thiếu file     : {len(report.ban_ghi_thieu_file)}")
    if args.delete:
        print(f"Đã xoá                 : {len(report.da_xoa)}")
        print(f"Bỏ qua khi xoá         : {len(report.bo_qua_khi_xoa)}")
    print(f"Lỗi                    : {len(report.loi)}")

    if report.mo_coi:
        print("\nObject mồ côi:")
        for item in report.mo_coi:
            print(f"  {item['key']}  {item['size_bytes']} byte  {item['modified_at']}")
    if report.ban_ghi_thieu_file:
        print("\nBản ghi trỏ tới object không tồn tại (MẤT DỮ LIỆU — không tự xoá):")
        for item in report.ban_ghi_thieu_file:
            print(f"  {item['track_id']}  ->  {item['object_key']}")
    if report.bo_qua_khi_xoa:
        print("\nBỏ qua khi xoá:")
        for item in report.bo_qua_khi_xoa:
            print(f"  {item['key']}  ({item['vi_sao']})")
    if report.loi:
        print("\nLỗi:")
        for item in report.loi:
            print(f"  {item['khi']}: {item['loi']}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\nĐã ghi báo cáo: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
