"""Cấp phát gốc worker dùng chung — Router V3.2.

VÌ SAO CẦN: worker AG02 chạy trong một hồ sơ Windows khác và **không** đọc
được `C:\\Users\\nguye`. Nó cần một nơi cả hai bên đều với tới được, nhưng chỉ
hai bên đó thôi.

VÌ SAO KHÔNG CHỈ LÀ MỘT THƯ MỤC: một `git worktree` chỉ chứa tệp `.git` trỏ
NGƯỢC về `.git/worktrees/<tên>` của kho mẹ. Chuyển worktree sang thư mục chung
mà vẫn tạo từ kho mẹ thì AG02 đọc được cây làm việc nhưng không đọc được con
trỏ — hỏng ở mọi lệnh git. Nên gốc dùng chung phải chứa một **bản sao bare**,
và worktree được tạo TỪ bản sao đó.

    python -m scripts.router_v3.setup_shared_root --accounts AG02
    python -m scripts.router_v3.setup_shared_root --accounts AG02,AG03 --check

CHẠY LẠI ĐƯỢC: mỗi bước đều kiểm trước khi làm.
KHÔNG cấp quyền nào trên hồ sơ chính. KHÔNG đụng credential.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

MAC_DINH_GOC = r"C:\FanficWorkers"
MIRROR = "repo.git"

#: Chủ thể LUÔN cần, kèm quyền. Ít nhất có thể mà vẫn dùng được:
#: SYSTEM/Administrators để HĐH và người quản trị còn cứu được thư mục;
#: người dùng Router toàn quyền; mỗi tài khoản worker chỉ MODIFY — đủ để tạo
#: và sửa worktree, KHÔNG đủ để đổi ACL.
QUYEN_HE_THONG = (
    (r"NT AUTHORITY\SYSTEM", "(OI)(CI)(F)"),
    (r"BUILTIN\Administrators", "(OI)(CI)(F)"),
)

#: Chủ thể phải BIẾN MẤT khỏi ACL. Thừa kế mặc định của `C:\` cho
#: `BUILTIN\Users` quyền đọc và `Authenticated Users` quyền sửa — nghĩa là MỌI
#: tài khoản trên máy, đúng thứ gốc dùng chung sinh ra để tránh.
CAM = ("BUILTIN\\Users", "Authenticated Users", "Everyone")


def _chay(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def _icacls(*args) -> subprocess.CompletedProcess:
    moi = dict(os.environ)
    # Git Bash bien `/grant` thanh mot duong dan Windows. Tat chuyen doi.
    moi["MSYS_NO_PATHCONV"] = "1"
    return _chay(["icacls", *args], env=moi)


def sieu_quyen(goc: str, tai_khoan, may: str) -> list:
    """Đặt ACL ít quyền nhất. Trả về danh sách việc đã làm."""
    lam = []
    cap = [f"{chu}:{q}" for chu, q in QUYEN_HE_THONG]
    cap.append(f"{may}\\{os.environ.get('USERNAME', 'nguye')}:(OI)(CI)(F)")
    for tk in tai_khoan:
        cap.append(f"{may}\\{tk}:(OI)(CI)(M)")

    args = [goc]
    for c in cap:
        args += ["/grant", c]
    r = _icacls(*args)
    if r.returncode != 0:
        raise SystemExit(f"icacls /grant hỏng: {r.stdout or r.stderr}")
    lam.append(f"cấp quyền cho {len(cap)} chủ thể")

    # BO THUA KE — phai lam SAU khi cap, neu khong co the tu khoa chinh minh.
    r = _icacls(goc, "/inheritance:r")
    if r.returncode != 0:
        raise SystemExit(f"icacls /inheritance:r hỏng: {r.stdout or r.stderr}")
    lam.append("bỏ thừa kế (gỡ Users/Authenticated Users)")
    return lam


def kiem_acl(goc: str) -> list:
    """Trả về danh sách VẤN ĐỀ. Rỗng = đạt."""
    r = _icacls(goc)
    van_ban = r.stdout or ""
    van_de = []
    for chu in CAM:
        if chu.lower() in van_ban.lower():
            van_de.append(f"ACL vẫn còn {chu!r} — mọi tài khoản trên máy đọc được")
    return van_de


def kiem_ho_so_chinh(may: str, tai_khoan) -> list:
    """Hồ sơ chính KHÔNG được mở quyền cho worker."""
    ho_so = pathlib.Path.home()
    r = _icacls(str(ho_so))
    van_ban = (r.stdout or "").lower()
    return [f"{tk} CÓ quyền trên {ho_so} — không được phép"
            for tk in tai_khoan if f"\\{tk.lower()}:" in van_ban]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=MAC_DINH_GOC)
    ap.add_argument("--accounts", default="AG02",
                    help="tài khoản worker, phân tách bằng dấu phẩy")
    ap.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[2]))
    ap.add_argument("--check", action="store_true", help="chỉ kiểm, không sửa")
    a = ap.parse_args(argv)

    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    may = os.environ.get("COMPUTERNAME", "").strip() or "."
    tk = [x.strip() for x in a.accounts.split(",") if x.strip()]
    goc = pathlib.Path(a.root)
    bare = goc / MIRROR

    print(f"gốc dùng chung : {goc}")
    print(f"tài khoản      : {', '.join(tk)}")
    print(f"kho nguồn      : {a.repo}\n")

    if a.check:
        van_de = kiem_acl(str(goc)) + kiem_ho_so_chinh(may, tk)
        if not goc.exists():
            van_de.append(f"{goc} chưa tồn tại")
        if not bare.exists():
            van_de.append(f"{bare} chưa tồn tại")
        for v in van_de:
            print(f"  VẤN ĐỀ: {v}")
        print("\nĐẠT" if not van_de else f"\n{len(van_de)} vấn đề")
        return 0 if not van_de else 1

    if not goc.exists():
        goc.mkdir(parents=True)
        print(f"  đã tạo {goc}")
    else:
        print(f"  {goc} đã có")

    for viec in sieu_quyen(str(goc), tk, may):
        print(f"  {viec}")

    #: `git clone --bare` KHÔNG tự đặt refspec fetch — `git fetch --all` sau đó
    #: chỉ tải object mới chứ KHÔNG cập nhật `main` cục bộ. Bản sao trông như
    #: "đã cập nhật" (thoát mã 0) nhưng vẫn đứng yên ở commit lúc clone — âm
    #: thầm cho AG02 chạy mã cũ. Phải đặt refspec tường minh.
    REFSPEC = "+refs/heads/*:refs/heads/*"
    if bare.exists():
        _chay(["git", "-C", str(bare), "config", "remote.origin.fetch", REFSPEC])
        r = _chay(["git", "-C", str(bare), "fetch", "origin", REFSPEC, "--quiet"])
        moi = _chay(["git", "-C", str(bare), "log", "-1", "--format=%h %s", "main"])
        print(f"  cập nhật bản sao bare ({'ok' if r.returncode == 0 else 'hỏng'})"
              f" -> main = {moi.stdout.strip()}")
    else:
        r = _chay(["git", "clone", "--bare", "--quiet", a.repo, str(bare)])
        if r.returncode != 0:
            raise SystemExit(f"clone bare hỏng: {r.stderr[:300]}")
        _chay(["git", "-C", str(bare), "config", "remote.origin.fetch", REFSPEC])
        print(f"  đã tạo bản sao bare {bare} (đặt refspec fetch tường minh)")

    print("\n--- KIỂM LẠI ---")
    van_de = kiem_acl(str(goc)) + kiem_ho_so_chinh(may, tk)
    for v in van_de:
        print(f"  VẤN ĐỀ: {v}")
    if van_de:
        return 1
    print("  ACL đạt: không có Users/Authenticated Users/Everyone")
    print(f"  hồ sơ chính không mở quyền cho: {', '.join(tk)}")
    print(f"\nDùng: WorktreeManager(repo, git_dir={bare!s}, "
          f"worktree_root={goc / 'workers'!s})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
