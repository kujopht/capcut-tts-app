"""Đưa Router vào một kho khác — Router LTS Phase 13.

VÌ SAO: `WorktreeManager`, `routing_history.py`, `checkpoint.py` đều đã
mặc định dùng `<kho>/.router/...` — quy ước đó CHƯA từng được một lệnh
nào dựng sẵn, người dùng phải tự biết cấu trúc đúng. `router init` dựng
đúng cấu trúc đó một lần, ở kho MỤC TIÊU (không phải kho của Router).

    python -m scripts.router_v3.router_init C:\\du-an-khac

Runtime Router (mã trong `scripts/router_v3/`) VẪN nằm trong kho NÀY —
lệnh này không sao chép mã Router sang kho khác, nó chỉ dựng THƯ MỤC
TRẠNG THÁI (`.router/`) mà runtime Router sẽ ghi vào KHI CHẠY NHẮM VÀO
kho đó. Chính sách riêng của dự án (danh sách worker, ngưỡng rủi ro...)
nằm TRONG `.router/config.json` của chính dự án đó — không nằm trong mã
Router dùng chung.

KHÔNG BAO GIỜ di chuyển bí mật của dự án hiện tại — lệnh này không đọc,
không sao chép bất kỳ tệp nào ngoài việc tạo thư mục rỗng + một tệp cấu
hình mặc định.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

THU_MUC_CON = ("config", "state", "worktrees", "telemetry", "checkpoints")

CAU_HINH_MAC_DINH = {
    "speed_mode": "normal",
    "max_parallel_ceiling": 6,
    "note": "Chính sách RIÊNG của dự án này. Không ảnh hưởng dự án khác "
           "dùng chung mã Router.",
}

DONG_GITIGNORE = (
    "\n# Router (router_init) — trạng thái cục bộ, không commit.\n.router/\n"
)


def dung(goc_du_an: Path, *, ghi_de_cau_hinh: bool = False) -> dict:
    """Trả về {"đã_tạo": [...], "đã_có": [...]}."""
    goc_router = goc_du_an / ".router"
    da_tao, da_co = [], []

    for ten in THU_MUC_CON:
        p = goc_router / ten
        if p.exists():
            da_co.append(str(p))
        else:
            p.mkdir(parents=True, exist_ok=True)
            da_tao.append(str(p))

    tep_cfg = goc_router / "config" / "config.json"
    if tep_cfg.exists() and not ghi_de_cau_hinh:
        da_co.append(str(tep_cfg))
    else:
        tep_cfg.write_text(json.dumps(CAU_HINH_MAC_DINH, ensure_ascii=False,
                                      indent=2), encoding="utf-8")
        da_tao.append(str(tep_cfg))

    gi = goc_du_an / ".gitignore"
    if gi.exists():
        noi_dung = gi.read_text(encoding="utf-8")
        if ".router/" not in noi_dung:
            with open(gi, "a", encoding="utf-8") as f:
                f.write(DONG_GITIGNORE)
            da_tao.append(f"{gi} (thêm dòng .router/)")
        else:
            da_co.append(str(gi))
    else:
        gi.write_text(DONG_GITIGNORE.lstrip("\n"), encoding="utf-8")
        da_tao.append(str(gi))

    return {"đã_tạo": da_tao, "đã_có": da_co}


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", help="đường dẫn kho MỤC TIÊU (không phải kho Router)")
    ap.add_argument("--force-config", action="store_true",
                    help="ghi đè config.json nếu đã có (mặc định: giữ nguyên)")
    a = ap.parse_args(argv)

    goc = Path(a.repo).resolve()
    if not goc.is_dir():
        print(f"{goc} không phải thư mục — chưa tạo gì cả.")
        return 2
    if not (goc / ".git").exists():
        print(f"CẢNH BÁO: {goc} không có .git — vẫn tạo .router/ ở đây, "
             f"nhưng WorktreeManager cần một kho git thật để hoạt động.")

    kq = dung(goc, ghi_de_cau_hinh=a.force_config)
    print(f"Router đã sẵn sàng cho {goc}\n")
    for p in kq["đã_tạo"]:
        print(f"  tạo mới : {p}")
    for p in kq["đã_có"]:
        print(f"  đã có   : {p}")
    print(f"\nChạy Router NHẮM VÀO kho này bằng cách trỏ "
         f"WorktreeManager(repo_root={goc!s}) — mã Router vẫn ở kho hiện tại.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
