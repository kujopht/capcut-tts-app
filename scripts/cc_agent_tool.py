"""Công cụ CỐ ĐỊNH cho agent do Router quản lý — tập động từ HỮU HẠN.

VÌ SAO TỆP NÀY TỒN TẠI:

Quyền `command(...)` của `agy` khớp **CHUỖI LỆNH CHÍNH XÁC**. Đã đo trên máy
này (2026-09-08): `command(git)` và `command(git *)` đều KHÔNG cho chạy
`git status --porcelain`; chỉ chuỗi khớp từng ký tự mới qua. Không có glob,
không có tiền tố.

Hệ quả: một thao tác có THAM SỐ THAY ĐỔI không biểu diễn được bằng một
allow-rule an toàn. Hai lối thoát, và chỉ một lối chấp nhận được:

    command(*)          -> mọi lệnh chạy được, tức là truy cập hệ tệp tuỳ ý
                           bằng shell. BỊ CẤM.
    một WRAPPER cố định -> hữu hạn động từ, mỗi động từ là MỘT chuỗi lệnh
                           chính xác. Đây là thứ đang đọc.

BA ĐỘNG TỪ, mỗi cái ánh xạ 1-1 tới một lệnh ĐÃ ĐỊNH NGHĨA SẴN trong kho —
không phát minh lệnh mới. Nhưng CHỈ HAI được cấp cho agent; xem `tests`:

    changes  git status --porcelain -uall
             (agent PHẢI khai đúng đường dẫn đã sửa vào `changes`; cổng
             `diff` của `router_v3/pool/validation.py` đối chiếu lời khai
             với `git` thật, và một lượt làm ĐÚNG từng bị đánh HỎNG chỉ vì
             agent để `changes` rỗng — xem CONTROL_CENTER_V01_PROOF §4 #10)

    compile  python -m compileall -q server scripts
             (đúng lệnh CI chạy — `.github/workflows/ci.yml`)

    tests    python -m unittest discover -s scripts/tests -t .
             (đúng lệnh CI chạy — `.github/workflows/ci.yml`)

             KHÔNG CẤP CHO AGENT. Chỉ Control Center — vốn đã tin cậy — gọi
             động từ này; không mục `command(...)` nào cấp nó cho agent, và
             `planner.KHONG_CAP_CHO_AGENT` khoá ranh giới đó bằng bài kiểm.

             Vì sao: worktree của việc là nơi agent ĐƯỢC PHÉP GHI, còn
             `unittest discover -s scripts/tests` NẠP RỒI CHẠY mọi `test_*.py`
             tìm thấy ở đó. Agent chỉ cần ghi `scripts/tests/test_x.py` vào
             cây của chính nó rồi gọi đúng chuỗi lệnh đã duyệt — mã chạy ngay,
             với toàn quyền tiến trình. Các cổng `scope`/`diff`/`security`
             chạy SAU lượt nên thấy tệp lạ quá muộn. Rào `cwd` bên dưới không
             cứu được: cây độc hại chính là cây hợp lệ.

             Đó là thực thi mã tuỳ ý qua một allow-rule hẹp — đúng thứ tệp này
             dựng lên để chặn. Nên nó ở lại đây, nhưng không ở trong allowlist.

RÀO CHỐNG ĐI VÒNG BẰNG `cwd`, và đây là phần quan trọng nhất:

Một lệnh như `python -m unittest discover -s scripts/tests -t .` giải đường
dẫn TƯƠNG ĐỐI theo `cwd`. Nếu agent đổi `cwd` sang một cây khác có
`scripts/tests/` của riêng nó, cùng một chuỗi lệnh "đã được duyệt" sẽ NẠP VÀ
CHẠY mã tuỳ ý ở đó. Đó là biến một allow-rule hẹp thành thực thi tuỳ ý.

Chặn bằng hai lớp:

  1. Đường dẫn tới CHÍNH TỆP NÀY được ghim TUYỆT ĐỐI trong allow-rule, nên
     `cwd` không đổi được *script nào* chạy.
  2. `_kiem_cwd()` bắt buộc `cwd` phải là gốc kho này, hoặc nằm trong
     `.router/worktrees/` của chính nó. Ngoài ra: TỪ CHỐI, thoát 2.

FAIL CLOSED ở mọi nhánh: không đọc được `cwd`, không phân giải được đường
dẫn, động từ lạ — đều từ chối, không "đoán rồi chạy".

KHÔNG BAO GIỜ: `shell=True`, tham số tuỳ ý từ dòng lệnh, thao tác phá huỷ,
in bí mật (mọi đầu ra đi qua `packet.redact`).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

#: Goc kho SUY RA TU CHINH TEP NAY, khong tu `cwd` va khong tu bien moi
#: truong. Allow-rule ghim duong dan tuyet doi toi tep nay, nen day la mot
#: neo khong doi duoc tu ben ngoai.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Noi Router V4 dat worktree co lap (`router_v3/worktree.ROOT_DIR`).
WORKTREE_ROOT = REPO_ROOT / ".router" / "worktrees"

#: Tran thoi gian cho MOI dong tu. Huu han co chu dich: mot lenh treo trong
#: che do headless se an het tran cua ca luot agent.
TIMEOUT = {"changes": 60.0, "compile": 300.0, "tests": 1800.0}

#: Dong tu -> argv CO DINH. Khong mot phan tu nao den tu dong lenh.
DONG_TU: dict = {
    "changes": ["git", "status", "--porcelain", "-uall"],
    "compile": [sys.executable, "-m", "compileall", "-q", "server", "scripts"],
    "tests": [sys.executable, "-m", "unittest", "discover",
              "-s", "scripts/tests", "-t", "."],
}


class TuChoi(RuntimeError):
    """Từ chối chạy. Luôn kèm lý do đọc được; không bao giờ im lặng."""


def _kiem_cwd() -> Path:
    """`cwd` phải nằm TRONG kho này. Ngoài ra: từ chối.

    Đây là rào chống biến một allow-rule hẹp thành thực thi tuỳ ý. Không có
    nó, `cwd=C:\\` cộng một `scripts/tests/` giả sẽ khiến động từ `tests`
    nạp và chạy mã của người khác dưới đúng chuỗi lệnh đã được duyệt.
    """
    try:
        cwd = Path(os.getcwd()).resolve()
    except OSError as exc:                      # thu muc bi xoa giua chung
        raise TuChoi(f"không đọc được thư mục hiện tại: {exc}") from exc

    if cwd == REPO_ROOT:
        return cwd
    try:
        cwd.relative_to(WORKTREE_ROOT.resolve())
        return cwd
    except (ValueError, OSError):
        pass
    # WORKTREE CUA MOT DU AN KHAC cung hop le.
    #
    # `REPO_ROOT` suy ra tu vi tri cua tep nay, tuc kho control-center. Nhung
    # du an `fanfic` tro toi KHO CHINH (thu muc khac), nen worktree cua no
    # nam o `<kho chinh>/.router/worktrees/...`. Ban truoc chi chap nhan cay
    # duoi `REPO_ROOT`, nen CA BA dong tu bi tu choi 100% tren dung du an
    # MAC DINH cua ban phat hanh — chuoi cong cu hong tu dau toi cuoi ma bai
    # kiem nao cung xanh.
    #
    # Dieu kien thay the van chat: duong dan phai co mot doan `.router` roi
    # `worktrees` ke nhau trong to tien da RESOLVE. Junction khong lach duoc
    # (da resolve), va no van giam trong cay do Router quan ly.
    doan = [x.lower() for x in cwd.parts]
    for i in range(len(doan) - 1):
        if doan[i] == ".router" and doan[i + 1] == "worktrees":
            return cwd
    raise TuChoi(
        f"TỪ CHỐI: thư mục hiện tại nằm ngoài kho do Router quản lý.\n"
        f"  cwd đang là : {cwd}\n"
        f"  chỉ chấp nhận: {REPO_ROOT}\n"
        f"               hoặc bên trong {WORKTREE_ROOT}\n"
        f"Công cụ này chỉ chạy trong cây làm việc của chính việc bạn đang "
        f"làm. Đổi `cwd` KHÔNG mở rộng được phạm vi của nó.")


def _loc(van_ban: str) -> str:
    """Lọc bí mật trước khi in. Đầu ra này đi vào nhật ký và báo cáo."""
    try:
        # `python scripts/cc_agent_tool.py` dat `sys.path[0]` = `scripts/`,
        # khong phai goc kho, nen `scripts.router_v3` khong nap duoc neu
        # khong them goc vao. Them REPO_ROOT (da suy ra tu chinh tep nay,
        # khong tu `cwd`) chu KHONG them `cwd` — them `cwd` se cho phep mot
        # cay khac tiem `scripts/router_v3/packet.py` gia.
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from scripts.router_v3.packet import redact
        return redact(van_ban or "")
    except Exception:                           # noqa: BLE001
        # Khong nap duoc bo loc thi KHONG in tho — fail closed.
        return "(không nạp được bộ lọc bí mật; đầu ra bị giữ lại)"


def chay(dong_tu: str) -> Tuple[int, str]:
    """Chạy MỘT động từ trong `cwd` đã kiểm. Trả `(mã thoát, đầu ra)`."""
    if dong_tu not in DONG_TU:
        raise TuChoi(f"động từ lạ {dong_tu!r} — chỉ có {sorted(DONG_TU)}")
    cwd = _kiem_cwd()
    argv: List[str] = list(DONG_TU[dong_tu])
    try:
        p = subprocess.run(
            argv, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=TIMEOUT.get(dong_tu, 300.0),
            # shell=False la MAC DINH va phai giu nguyen: `shell=True` bien
            # moi phan tu argv thanh mot chuoi shell dien giai duoc.
            shell=False)
    except FileNotFoundError as exc:
        raise TuChoi(f"không tìm thấy chương trình cho {dong_tu!r}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TuChoi(f"{dong_tu!r} quá {TIMEOUT.get(dong_tu)}s — đã cắt") from exc
    return p.returncode, _loc((p.stdout or "") + (p.stderr or ""))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cc_agent_tool",
        description=("Công cụ cố định cho agent do Router quản lý. Tập động "
                     "từ hữu hạn; không nhận tham số tuỳ ý."))
    # `choices` la rao thu nhat: argparse tu tu choi dong tu la truoc khi
    # mot dong ma nao cua ta chay.
    ap.add_argument("verb", choices=sorted(DONG_TU),
                    help="thao tác cần chạy")
    a = ap.parse_args(argv)
    try:
        ma, ra = chay(a.verb)
    except TuChoi as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    sys.stdout.write(ra)
    if a.verb == "changes" and not ra.strip():
        sys.stdout.write("(không có tệp nào thay đổi)\n")
    return ma


if __name__ == "__main__":
    sys.exit(main())
