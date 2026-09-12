# -*- coding: utf-8 -*-
"""TẠO DỰ ÁN MỚI từ một cái TÊN — V0.9.2.

VẤN ĐỀ: "+ Dự án mới" chỉ nhận MỘT đường dẫn tuyệt đối tới kho ĐÃ CÓ. Tốt
cho việc nhận nuôi một dự án trưởng thành (Fanfic), nhưng để bắt đầu từ số
không thì người dùng phải tự tạo thư mục, tự `git init`, rồi mới quay lại gõ
đường dẫn. Đó là ba bước thủ công cho thứ đáng lẽ là một cái tên.

HAI LUỒNG, TÁCH BẠCH:

    TẠO MỚI      — người dùng gõ TÊN; Router dựng thư mục dưới thư mục dự án
                   mặc định, `git init`, tạo khung tối thiểu, rồi NHẬN nó
                   bằng đúng máy móc sẵn có.
    NHẬP REPO    — hành vi cũ, không đổi một dòng: nhận một kho đã có tại
                   đường dẫn tuyệt đối, KHÔNG di chuyển nó.

BA ĐIỀU FILE NÀY KHÔNG LÀM:

* **Không dựng kiến trúc lưu trữ thứ hai.** Sổ/ký ức canonical vẫn ở gốc dữ
  liệu Router (`duong_du_lieu.py`), KHÔNG nằm trong cây git của dự án. Tạo
  mới chỉ thêm một thư mục làm việc; phần đăng ký đi qua `nhan_du_an()`.
* **Không ghi đè.** Thư mục đích đã tồn tại thì DỪNG kèm lý do, không bao
  giờ trộn vào một thư mục có sẵn.
* **Không xoá thư mục của người dùng khi hoàn tác.** Hoàn tác chỉ gỡ thứ
  CHÍNH NÓ vừa tạo, và chỉ khi thư mục đó trước đó chưa tồn tại.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.router_v3.tien_trinh import an_cua_so

#: Khoá cài đặt: thư mục cha cho dự án TẠO MỚI. Chỉ là MẶC ĐỊNH — dự án nhận
#: nuôi vẫn nằm nguyên chỗ của nó (Fanfic ở `Documents\CapCut-TTS-App`).
KHOA_THU_MUC_GOC = "thu_muc_du_an_mac_dinh"

#: Mặc định trên Windows. Ngắn, không dấu, không đụng OneDrive — `Documents`
#: bị OneDrive chuyển hướng trên máy này và đó là một nguồn lỗi thật.
GOC_MAC_DINH_WIN = r"C:\RouterProjects"

#: Tên Windows CẤM dùng làm thư mục, bất kể phần mở rộng.
_TEN_CAM = frozenset((
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10)),
))

README = """# {ten}

Dự án mới do Router Control Center tạo.

## Trạng thái

- kho git vừa khởi tạo, chưa có commit nội dung
- chưa có dịch vụ production nào
- chưa có gì để triển khai

## Ghi chú

Thư mục `docs/` dành cho tài liệu và báo cáo của dự án.
"""

GITIGNORE = """# Router Control Center
.router/

# Python
__pycache__/
*.py[cod]
.venv/
venv/

# Node
node_modules/
dist/
build/

# Bí mật — KHÔNG BAO GIỜ commit
.env
.env.*
*.pem
*.key
"""


class TaoDuAnLoi(ValueError):
    """Không tạo được dự án. Luôn kèm lý do người đọc hiểu được."""


@dataclass
class KetQuaTao:
    ok: bool = False
    project_id: str = ""
    ten: str = ""
    duong: str = ""
    ly_do: str = ""
    da_tao: List[str] = field(default_factory=list)
    ghi_chu: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"ok": self.ok, "project_id": self.project_id, "ten": self.ten,
                "duong": self.duong, "ly_do": self.ly_do,
                "da_tao": list(self.da_tao), "ghi_chu": list(self.ghi_chu)}


def slug(ten: str) -> str:
    """Tên người gõ -> tên thư mục AN TOÀN. Tất định.

    Bỏ dấu tiếng Việt, hạ chữ, gom mọi thứ không phải chữ/số thành `-`. Kết
    quả rỗng hoặc trùng tên cấm của Windows thì TỪ CHỐI ở `kiem_ten`, không
    tự bịa một tên thay thế — người dùng phải biết tên mình gõ không dùng
    được.
    """
    x = unicodedata.normalize("NFD", (ten or "").strip())
    x = "".join(c for c in x if not unicodedata.combining(c))
    x = x.replace("đ", "d").replace("Đ", "D")
    x = re.sub(r"[^A-Za-z0-9._-]+", "-", x).strip("-._")
    return x[:64]


def kiem_ten(ten: str) -> str:
    """Tên hợp lệ -> slug. Không hợp lệ -> `TaoDuAnLoi` nói RÕ vì sao."""
    if not (ten or "").strip():
        raise TaoDuAnLoi("Tên dự án không được để trống.")
    s = slug(ten)
    if not s:
        raise TaoDuAnLoi(
            f"Tên {ten!r} không tạo được tên thư mục hợp lệ — hãy dùng chữ "
            f"và số.")
    if s.lower() in _TEN_CAM:
        raise TaoDuAnLoi(f"{s!r} là tên dành riêng của Windows — chọn tên khác.")
    if s in (".", ".."):
        raise TaoDuAnLoi("Tên dự án không hợp lệ.")
    return s


def thu_muc_goc(store=None) -> Path:
    """Thư mục dự án mặc định: cài đặt của người dùng, hoặc mặc định."""
    if store is not None:
        try:
            d = (store.cai_dat_ui() or {}).get(KHOA_THU_MUC_GOC)
            if isinstance(d, str) and d.strip():
                return Path(d.strip())
        except Exception:                                     # noqa: BLE001
            pass
    return Path(GOC_MAC_DINH_WIN)


def kiem_thu_muc_goc(d: str) -> str:
    """Giá trị người dùng gõ vào ô «Thư mục dự án mặc định» -> giá trị lưu.

    Rỗng là HỢP LỆ và có nghĩa "bỏ thiết lập, quay về mặc định" — không phải
    lỗi. Ngoài ra đây là cài đặt DUY NHẤT quyết định Router tạo thư mục ở
    ĐÂU, nên nó được kiểm ở một chỗ chứ không phải ở mỗi người gọi:

    * phải TUYỆT ĐỐI — đường tương đối sẽ giải theo thư mục làm việc của
      tiến trình server, một khái niệm người dùng không nhìn thấy và không
      điều khiển được;
    * không có đoạn `..` — gốc phải là một chỗ nói thẳng ra được, vì mọi
      phép kiểm containment về sau đều đo từ nó;
    * không được là gốc ổ đĩa — một gốc như `C:\\` biến `_trong_goc()` thành
      phép kiểm luôn đúng;
    * không được trỏ vào một TỆP đang tồn tại.

    Thư mục chưa tồn tại thì CHẤP NHẬN: `tao_du_an()` tự tạo khi cần, và bắt
    người dùng đi tạo tay trước là đúng cái phiền mà V0.9.2 xoá đi.
    """
    x = (d or "").strip().strip('"')
    if not x:
        return ""
    if len(x) > 240:
        raise TaoDuAnLoi("Đường dẫn quá dài.")
    p = Path(x)
    if not p.is_absolute():
        raise TaoDuAnLoi(
            f"{x!r} là đường dẫn tương đối — hãy gõ đường dẫn đầy đủ, "
            f"ví dụ {GOC_MAC_DINH_WIN}.")
    if ".." in p.parts:
        raise TaoDuAnLoi("Đường dẫn không được chứa `..`.")
    if p.parent == p:
        raise TaoDuAnLoi(
            f"{x!r} là gốc ổ đĩa — hãy chọn một thư mục con, "
            f"ví dụ {GOC_MAC_DINH_WIN}.")
    if p.is_file():
        raise TaoDuAnLoi(f"{x!r} là một tệp, không phải thư mục.")
    return str(p)


def duong_xem_truoc(ten: str, store=None) -> str:
    """Chỗ dự án SẼ nằm — để UI hiện trước khi người dùng bấm."""
    try:
        return str(thu_muc_goc(store) / kiem_ten(ten))
    except TaoDuAnLoi:
        return ""


def _trong_goc(goc: Path, dich: Path) -> bool:
    """`dich` có nằm THẬT SỰ trong `goc` không? So sau `resolve()`.

    Chặn `../`, đường dẫn tuyệt đối lén, và junction trỏ ra ngoài — cùng
    luật `attachments.py` và `worktrees.go_bo` đã dùng.
    """
    try:
        dich.resolve().relative_to(goc.resolve())
        return True
    except (ValueError, OSError):
        return False


def _git(goc: Path, *a: str) -> Tuple[int, str]:
    try:
        r = subprocess.run(["git", *a], cwd=str(goc), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=60, **an_cua_so())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return int(r.returncode), ((r.stdout or "") + (r.stderr or "")).strip()


def tao_du_an(cc, ten: str, *, goc: Optional[object] = None,
              project_id: str = "") -> KetQuaTao:
    """TẠO một dự án mới từ TÊN, rồi nhận nó bằng máy móc sẵn có.

    Thứ tự có nghĩa: kiểm HẾT rồi mới chạm đĩa, và mọi thứ chạm đĩa đều được
    ghi lại để hoàn tác được. Đăng ký Router đi SAU cùng — một dự án đăng ký
    xong mà thư mục hỏng thì tệ hơn là không đăng ký.
    """
    kq = KetQuaTao(ten=(ten or "").strip())
    try:
        s = kiem_ten(ten)
    except TaoDuAnLoi as exc:
        kq.ly_do = str(exc)
        return kq

    goc_p = Path(goc) if goc is not None else thu_muc_goc(
        getattr(cc, "store", None))
    dich = goc_p / s
    if not _trong_goc(goc_p, dich):
        kq.ly_do = (f"Tên dự án {ten!r} trỏ ra ngoài thư mục dự án "
                    f"({goc_p}) — từ chối.")
        return kq
    if dich.exists():
        kq.ly_do = (f"Đã có thư mục {dich} rồi. Router KHÔNG ghi đè — hãy "
                    f"chọn tên khác, hoặc dùng tab «Nhập repo» nếu đó chính "
                    f"là dự án bạn muốn.")
        return kq

    goc_co_san = goc_p.exists()
    da_tao: List[Path] = []
    try:
        goc_p.mkdir(parents=True, exist_ok=True)
        if not goc_co_san:
            da_tao.append(goc_p)
        dich.mkdir()
        da_tao.append(dich)
        (dich / "docs").mkdir()
        (dich / "README.md").write_text(README.format(ten=kq.ten),
                                        encoding="utf-8")
        (dich / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
        ma, ra = _git(dich, "init", "-q")
        if ma != 0:
            raise TaoDuAnLoi(f"`git init` hỏng: {ra[:200]}")
        # COMMIT ĐẦU TIÊN — V0.9.3, và nó KHÔNG phải thứ làm cho đẹp.
        #
        # `git init` trần để lại một kho KHÔNG CÓ `HEAD`, và `git rev-parse
        # HEAD` trên kho đó hỏng. Tầng worktree của Router gọi đúng lệnh ấy
        # để lấy `base_sha`, nên MỌI việc GHI trên một dự án vừa tạo đều
        # chết ngay lúc xin cây làm việc:
        #
        #     không cấp được cây làm việc: git rev-parse HEAD thất bại:
        #     fatal: ambiguous argument 'HEAD': unknown revision
        #
        # Đo được trên RouterDogfood02 (2026-09-13), NGAY SAU khi V0.9.3 đã
        # sửa xong phạm vi ghi: gói việc đúng rồi mà vẫn không chạy được.
        # Đây là cái ngõ cụt THỨ HAI của cùng một dự án mới.
        #
        # Sâu hơn một lỗi git: toàn bộ mô hình kiểm định của Router là SO
        # VỚI MỘT MỐC (`base_sha`, `git status` trong worktree). Một dự án
        # không có commit nào thì không có mốc để so — nên "kho vừa tạo"
        # phải có một mốc, đúng như mọi kho thật đều có.
        #
        # `-c user.*` đặt TẠI LỆNH: máy chưa cấu hình `user.email` toàn cục
        # là chuyện thường, và một dự án mới không được hỏng vì điều đó.
        ma, ra = _git(dich, "add", "-A")
        if ma != 0:
            raise TaoDuAnLoi(f"`git add` hỏng: {ra[:200]}")
        ma, ra = _git(dich, "-c", "user.name=Router Control Center",
                      "-c", "user.email=router@localhost",
                      "commit", "-q", "-m",
                      "chore: khung dự án do Router Control Center tạo")
        if ma != 0:
            raise TaoDuAnLoi(f"commit đầu tiên hỏng: {ra[:200]}")
        kq.ghi_chu.append("đã khởi tạo kho git kèm commit đầu tiên")
    except (OSError, TaoDuAnLoi) as exc:
        kq.ly_do = f"Không tạo được dự án: {exc}"
        _hoan_tac(da_tao)
        return kq

    # ĐĂNG KÝ bằng ĐÚNG máy móc nhận nuôi — không có đường thứ hai.
    try:
        from scripts.control_center.nhan_du_an import nhan_du_an
        nhan = nhan_du_an(cc, dich, ten=kq.ten, project_id=project_id)
    except Exception as exc:                                  # noqa: BLE001
        kq.ly_do = f"Tạo thư mục xong nhưng đăng ký hỏng: {exc}"
        _hoan_tac(da_tao)
        return kq
    if not nhan.ok:
        kq.ly_do = f"Tạo thư mục xong nhưng đăng ký hỏng: {nhan.ly_do}"
        _hoan_tac(da_tao)
        return kq

    kq.ok = True
    kq.project_id = nhan.project_id
    kq.duong = str(dich)
    kq.da_tao = [str(p) for p in da_tao]
    kq.ly_do = f"đã tạo dự án {nhan.project_id!r} tại {dich}"
    try:
        cc.store.ghi_su_kien(
            "PROJECT_CREATED", project_id=nhan.project_id,
            detail=f"tạo dự án MỚI {kq.ten!r} tại {dich}"[:300],
            meta={"duong": str(dich), "goc": str(goc_p), "slug": s})
    except Exception:                                         # noqa: BLE001
        pass
    return kq


def _hoan_tac(da_tao: List[Path]) -> None:
    """Gỡ ĐÚNG thứ ta vừa tạo, theo thứ tự ngược.

    Chỉ xoá thư mục CHÍNH HÀM NÀY đã tạo trong lần gọi này — thư mục có sẵn
    của người dùng không bao giờ nằm trong danh sách, nên không có đường nào
    để một lần tạo hỏng làm mất dữ liệu đã có.
    """
    for p in reversed(da_tao):
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception:                                     # noqa: BLE001
            pass
