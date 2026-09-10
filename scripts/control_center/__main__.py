"""Lối vào Control Center — `python -m scripts.control_center`.

Hai chế độ, cùng một bộ máy:

    (mặc định)   mở giao diện Textual
    `--headless` in ảnh chụp trạng thái rồi thoát — dùng cho kiểm tra
                 nhanh, cho CI, và cho lúc chạy qua SSH không có TTY

`--probe` mặc định TẮT. Dò sức khoẻ provider gọi ra `agy`/`codex` thật, mỗi
lệnh vài giây và tốn một lượt; khởi động một bảng điều khiển không được
phép làm điều đó sau lưng người dùng.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.control_center.bootstrap import khoi_tao                # noqa: E402
from scripts.control_center.engine import ControlCenter              # noqa: E402


def _dung(args) -> ControlCenter:
    # GOC DU LIEU CHINH TAC — KHONG `Path.cwd()`; xem `duong_du_lieu.py`.
    from scripts.control_center.duong_du_lieu import dam_bao_kho, goc_du_lieu
    goc = goc_du_lieu(args.root)
    dam_bao_kho(goc, ung_dung="V0.6.1")
    # Xem `desktop.py`: diem vao THAT thi Leader phai bat.
    cc = ControlCenter(root=goc, probe=args.probe,
                       max_parallel=args.max_parallel, leader_bat=True)
    khoi_tao(cc.store, root=goc)
    if not args.no_recover:
        cc.recover()
    return cc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="control-center",
        description="Router Control Center V0.1 — phòng điều khiển Router V4")
    ap.add_argument("--root", default="", help="thư mục gốc giữ sổ .router/")
    ap.add_argument("--project", default="", help="dự án mở sẵn")
    ap.add_argument("--probe", action="store_true",
                    help="dò sức khoẻ provider lúc khởi động (CHẬM, tốn lượt)")
    ap.add_argument("--max-parallel", type=int, default=0,
                    help="trần việc chạy song song; 0 = tự theo bể tài khoản (3..12)")
    ap.add_argument("--refresh-interval", type=float, default=1.0)
    ap.add_argument("--no-recover", action="store_true",
                    help="bỏ qua đối soát phục hồi lúc khởi động")
    ap.add_argument("--headless", action="store_true",
                    help="in ảnh chụp JSON rồi thoát, không mở giao diện")
    ap.add_argument("--chat", default="",
                    help="gửi một câu vào ô chat của dự án rồi thoát")
    ap.add_argument("--remove-worktree", default="", metavar="PATH",
                    help=("GỠ một worktree khỏi đĩa rồi thoát. Chỉ gỡ được "
                          "cây do Router quản lý, có trong sổ, và không còn "
                          "phiên sống nào sở hữu. Dùng để dọn bằng chứng của "
                          "các lượt chứng minh SAU KHI đã ghi lại."))
    ap.add_argument("--list-worktrees", action="store_true",
                    help="liệt kê worktree Router đang biết rồi thoát")
    ap.add_argument("--remove-project", default="", metavar="ID",
                    help=("GỠ một dự án thử nghiệm/demo khỏi sổ rồi thoát. "
                          "Không đụng tới worktree trên đĩa; không gỡ được "
                          "dự án mặc định của bản phát hành."))
    args = ap.parse_args(argv)

    cc = _dung(args)
    pid = args.project or (cc.projects()[0].project_id if cc.projects() else "")

    if args.list_worktrees:
        for p_ in cc.projects():
            for h in cc.store.worktrees(p_.project_id):
                print(f"{p_.project_id:<10} {h['state']:<7} "
                      f"chủ={h['owner_session'] or '-':<14} {h['path']}")
        cc.shutdown()
        return 0

    if args.remove_worktree:
        from scripts.router_v3.worktree import WorktreeError
        got = False
        for p_ in cc.projects():
            if cc.store.worktree(args.remove_worktree) is None:
                continue
            try:
                kq = cc.ctx(p_.project_id).worktrees.go_bo(
                    args.remove_worktree, xac_nhan=True,
                    ly_do="dọn bằng chứng sau khi đã ghi lại")
            except WorktreeError as exc:
                print(str(exc), file=sys.stderr)
                cc.shutdown()
                return 2
            print(f"đã gỡ {kq['path']} (nhánh {kq['branch'] or '-'}, "
                  f"bẩn={kq['was_dirty']})")
            got = True
            break
        if not got:
            print(f"không có worktree {args.remove_worktree!r} trong sổ",
                  file=sys.stderr)
            cc.shutdown()
            return 2
        cc.shutdown()
        return 0

    if args.remove_project:
        try:
            dem = cc.xoa_project(args.remove_project, xac_nhan=True)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            cc.shutdown()
            return 2
        print(f"đã gỡ {args.remove_project!r}: {dem or '(không có gì để gỡ)'}")
        print("worktree trên đĩa KHÔNG bị đụng tới.")
        cc.shutdown()
        return 0

    if args.chat:
        if not pid:
            print("chưa có dự án nào", file=sys.stderr)
            return 2
        kq = cc.chat(pid, args.chat)
        print(kq["reply"])
        cc.shutdown()
        return 0

    if args.headless:
        print(json.dumps(cc.snapshot(pid), ensure_ascii=False, indent=2,
                         default=str))
        cc.shutdown()
        return 0

    try:
        from scripts.control_center.ui.app import ControlCenterApp
    except ModuleNotFoundError as e:
        if e.name not in ("textual", "rich") and not str(e.name or "").startswith(
                ("textual.", "rich.")):
            raise
        sys.stderr.write(
            f"control-center: thiếu gói '{e.name}' — chưa có phụ thuộc TUI.\n"
            f"  Cài đặt:  python -m pip install -r "
            f"requirements-control-room.txt\n")
        return 2

    ControlCenterApp(cc, refresh_interval=max(0.25, args.refresh_interval)).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
