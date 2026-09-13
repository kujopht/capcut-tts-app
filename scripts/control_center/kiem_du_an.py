# -*- coding: utf-8 -*-
"""KHÁM PHÁ PHÉP KIỂM CỦA CHÍNH DỰ ÁN — V1.0.

BẤT BIẾN: **`DONE` nghĩa là mục tiêu gốc CÓ BẰNG CHỨNG KHÁCH QUAN.** Một việc
KHÔNG được `DONE` chỉ vì worker nói nó xong.

KHUYẾT TẬT ĐO ĐƯỢC (RouterDogfood02, 2026-09-13): một việc có tiêu chí "viết
test và verify" được đánh `DONE`, mà bộ kiểm của chính dự án **chưa từng chạy
lần nào** — cổng `tests` của V4 không có lệnh nào để chạy nên nó xanh với
"0 lệnh test xanh". Khi cuối cùng có người chạy, nó đỏ 3/5.

CÁCH CHỮA KHÔNG PHẢI LÀ BỊA MỘT LỆNH. Router đọc BẰNG CHỨNG CÓ THẬT trong
kho — và chỉ những thứ dự án TỰ KHAI:

    1. lệnh kiểm tường minh trong kế hoạch / tiêu chí nghiệm thu
    2. `package.json` -> `scripts.{test,build,typecheck,lint}`
    3. cấu hình pytest (`pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`)
    4. `Makefile` -> target `test` / `check`

Không tìm được gì thì kết luận là **THIẾU BẰNG CHỨNG**, KHÔNG phải `DONE`.
Đó chính là luật V0.9 đã có ("tiêu chí không buộc được vào phép kiểm nào thì
KHÔNG mặc nhiên đạt") — ở đây nó được THI HÀNH cho đường việc thường, nơi nó
chưa từng được thi hành.

BA ĐIỀU TỆP NÀY KHÔNG LÀM:

* **Không bịa lệnh.** Không đoán `npm test` khi `package.json` không khai
  `scripts.test`. Một lệnh bịa hoặc chết (vô ích) hoặc chạy một thứ khác với
  điều dự án định (nguy hiểm).
* **Không chạy thứ ngoài kho.** Mọi lệnh chạy với `cwd` là chính worktree của
  việc, có trần thời gian.
* **Không nới quyền agent.** Đây là Router chạy, không phải agent — cùng mô
  hình với `probe_van_hanh` và `cc_agent_tool`: Router làm phép đo, agent
  nhận bằng chứng.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v3.tien_trinh import an_cua_so


class NguonKiem(str, Enum):
    """Bằng chứng nào cho ra lệnh này. Đi vào báo cáo, không phải trang trí."""

    KE_HOACH = "ke_hoach"            # kế hoạch/tiêu chí nói thẳng
    PACKAGE_JSON = "package.json"
    PYTEST = "pytest"
    MAKEFILE = "Makefile"


class LoaiKiem(str, Enum):
    TEST = "test"
    BUILD = "build"
    TYPECHECK = "typecheck"
    LINT = "lint"


@dataclass(frozen=True)
class LenhKiem:
    argv: Tuple[str, ...]
    nguon: NguonKiem
    loai: LoaiKiem
    #: Bằng chứng NGUYÊN VĂN: khoá/dòng trong tệp cấu hình đã khai nó.
    trich: str = ""

    def to_dict(self) -> Dict:
        return {"argv": list(self.argv), "nguon": self.nguon.value,
                "loai": self.loai.value, "trich": self.trich[:200]}


@dataclass
class KeHoachKiem:
    """Những gì Router SẼ chạy để xác minh — và vì sao đúng những thứ đó."""

    lenh: Tuple[LenhKiem, ...] = ()
    ghi_chu: Tuple[str, ...] = ()

    @property
    def co(self) -> bool:
        return bool(self.lenh)

    def to_dict(self) -> Dict:
        return {"lenh": [x.to_dict() for x in self.lenh],
                "ghi_chu": list(self.ghi_chu), "co": self.co}


#: Khoá `scripts` của npm mà ta CHẤP NHẬN, ánh xạ sang loại kiểm.
#:
#: Danh sách ĐÓNG có chủ đích: `scripts.deploy`, `scripts.start`,
#: `scripts.publish` KHÔNG bao giờ được chạy như một phép kiểm — chúng có
#: hậu quả ra ngoài kho.
_NPM_CHAP_NHAN: Dict[str, LoaiKiem] = {
    "test": LoaiKiem.TEST,
    "test:unit": LoaiKiem.TEST,
    "test:ci": LoaiKiem.TEST,
    "typecheck": LoaiKiem.TYPECHECK,
    "tsc": LoaiKiem.TYPECHECK,
    "lint": LoaiKiem.LINT,
    "build": LoaiKiem.BUILD,
}

#: Target Makefile chấp nhận được. Cùng lý do: danh sách ĐÓNG.
_MAKE_CHAP_NHAN: Dict[str, LoaiKiem] = {
    "test": LoaiKiem.TEST,
    "tests": LoaiKiem.TEST,
    "check": LoaiKiem.TEST,
    "lint": LoaiKiem.LINT,
    "typecheck": LoaiKiem.TYPECHECK,
}

#: Lệnh TUYỆT ĐỐI không chạy như phép kiểm, dù ai khai ở đâu.
#:
#: Một `scripts.test` viết là `npm run deploy && jest` thì cả dòng đó bị từ
#: chối — không cắt bớt, không "chạy phần an toàn". Chặn ở đây là lưới THỨ
#: HAI; lưới thứ nhất là danh sách khoá ĐÓNG ở trên.
_CAM = re.compile(
    r"\b(deploy|publish|release|push|wrangler|cf:deploy|terraform|"
    r"kubectl|docker\s+push|npm\s+publish|pip\s+upload|twine|"
    r"rm\s+-rf|shutdown|reboot|curl|wget)\b", re.I)


#: Đuôi tệp được coi là MÃ NGUỒN/SẢN PHẨM.
#:
#: Cổng kiểm định của dự án chỉ bắt buộc cho những thay đổi NÀY. Một việc chỉ
#: sửa `docs/*.md` cũng là việc GHI, nhưng bắt nó chạy cả bộ test của dự án
#: là đòi một bằng chứng không nói gì về nó — và biến mọi việc tài liệu
#: thành `NEEDS_EVIDENCE` trên một kho không có test.
_DUOI_MA: frozenset = frozenset({
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".java", ".kt", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs",
    ".rb", ".php", ".swift", ".scala", ".sh", ".ps1", ".sql",
    ".html", ".htm", ".css", ".scss", ".less",
})


def co_ma_nguon(duong_dan: Sequence[str]) -> bool:
    """Trong danh sách tệp đã đổi có mã nguồn/sản phẩm không?

    Quyết định bằng ĐUÔI TỆP chứ không bằng thư mục: `docs/vi-du.js` vẫn là
    mã chạy được, còn `src/GHI-CHU.md` thì không.
    """
    for t in duong_dan or ():
        try:
            if Path(str(t)).suffix.lower() in _DUOI_MA:
                return True
        except (OSError, ValueError):
            continue
    return False


def _doc_json(p: Path) -> Optional[Dict]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                         # noqa: BLE001
        return None


def _an_toan(dong: str) -> bool:
    return not _CAM.search(dong or "")


def kham_pha(repo, *, lenh_ke_hoach: Sequence[Sequence[str]] = ()
             ) -> KeHoachKiem:
    """Đọc kho, trả về những phép kiểm dự án TỰ KHAI. Không bịa gì.

    Thứ tự ưu tiên theo đúng yêu cầu chủ sở hữu: kế hoạch/tiêu chí trước,
    rồi manifest, rồi cấu hình test, rồi Makefile.
    """
    goc = Path(repo)
    ra: List[LenhKiem] = []
    chu: List[str] = []
    if not goc.is_dir():
        return KeHoachKiem(ghi_chu=(f"không có thư mục {goc}",))

    # 1. KẾ HOẠCH nói thẳng — thắng mọi thứ khác.
    for a in lenh_ke_hoach:
        argv = tuple(str(x) for x in a if str(x).strip())
        if not argv:
            continue
        if not _an_toan(" ".join(argv)):
            chu.append(f"bỏ lệnh kế hoạch vì chạm danh sách cấm: {' '.join(argv)[:80]}")
            continue
        ra.append(LenhKiem(argv, NguonKiem.KE_HOACH, LoaiKiem.TEST,
                           "lệnh do kế hoạch/tiêu chí khai"))

    # 2. package.json
    pj = goc / "package.json"
    if pj.is_file():
        d = _doc_json(pj) or {}
        sc = d.get("scripts") or {}
        if isinstance(sc, dict):
            co_nao = False
            for khoa, loai in _NPM_CHAP_NHAN.items():
                dong = sc.get(khoa)
                if not isinstance(dong, str) or not dong.strip():
                    continue
                if not _an_toan(dong):
                    chu.append(f"bỏ `scripts.{khoa}` vì chạm danh sách cấm")
                    continue
                npm = shutil.which("npm") or "npm"
                ra.append(LenhKiem((npm, "run", khoa), NguonKiem.PACKAGE_JSON,
                                   loai, f"scripts.{khoa} = {dong[:120]}"))
                co_nao = True
            if not co_nao:
                chu.append("package.json có nhưng không khai script kiểm nào "
                           "dùng được")

    # 3. cấu hình pytest
    dau_pytest = []
    if (goc / "pytest.ini").is_file():
        dau_pytest.append("pytest.ini")
    for ten, khoa in (("pyproject.toml", "[tool.pytest"),
                      ("setup.cfg", "[tool:pytest"),
                      ("tox.ini", "[pytest")):
        p = goc / ten
        if p.is_file():
            try:
                if khoa in p.read_text(encoding="utf-8", errors="replace"):
                    dau_pytest.append(ten)
            except Exception:                                 # noqa: BLE001
                pass
    if dau_pytest:
        # `sys.executable`, KHÔNG phải chuỗi `"python"`.
        #
        # Hai lý do. Thứ nhất: `python` tra qua `PATH`, và `PATH` của tiến
        # trình Router không nhất thiết là thứ người ta nghĩ — một phép kiểm
        # phải chạy trên một trình thông dịch XÁC ĐỊNH. Thứ hai: bài kiểm bất
        # biến V0.4 quét AST tìm những chỗ sinh tiến trình mang tên trình
        # thông dịch, và một hằng chuỗi ở đây trông y hệt một lời gọi
        # `subprocess` thiếu `an_cua_so()` — cảnh báo giả, nhưng nó đúng khi
        # nói rằng gọi tên trần là một thói quen xấu.
        ra.append(LenhKiem((sys.executable, "-m", "pytest", "-q"),
                           NguonKiem.PYTEST, LoaiKiem.TEST,
                           f"cấu hình pytest ở {', '.join(dau_pytest)}"))

    # 4. Makefile
    mk = goc / "Makefile"
    if mk.is_file():
        try:
            van = mk.read_text(encoding="utf-8", errors="replace")
        except Exception:                                     # noqa: BLE001
            van = ""
        make = shutil.which("make")
        for m in re.finditer(r"^([A-Za-z0-9_.-]+):", van, re.M):
            ten = m.group(1)
            loai = _MAKE_CHAP_NHAN.get(ten)
            if loai is None:
                continue
            if not make:
                chu.append(f"Makefile khai `{ten}` nhưng máy này không có "
                           f"`make` — bỏ qua")
                continue
            ra.append(LenhKiem((make, ten), NguonKiem.MAKEFILE, loai,
                               f"Makefile target `{ten}`"))

    if not ra:
        chu.append("KHÔNG tìm được phép kiểm nào dự án tự khai — thiếu bằng "
                   "chứng, KHÔNG được kết luận DONE")
    # Bỏ trùng, GIỮ thứ tự ưu tiên.
    thay: Dict[Tuple[str, ...], LenhKiem] = {}
    for x in ra:
        thay.setdefault(x.argv, x)
    return KeHoachKiem(tuple(thay.values()), tuple(chu))


#: Dấu hiệu LỆNH KIỂM tự nó hỏng — không phải mã sản phẩm sai.
#:
#: Đo được 2026-09-13: `node --test tests/` trên Node 24 + Windows nạp
#: `tests` như một MODULE và chết `MODULE_NOT_FOUND`. `rc=1`, nhưng mã sản
#: phẩm hoàn toàn đúng (chạy lại bằng lệnh đúng: 4/4 đạt). Kết luận "sản
#: phẩm sai" từ `rc != 0` là đi sửa nhầm thứ.
_LENH_HONG = re.compile(
    r"MODULE_NOT_FOUND|Cannot find module|missing script|"
    r"is not recognized as an internal or external command|"
    r"command not found|Unknown command|"
    r"no test files found|0 tests? (found|collected)|"
    r"ERR_UNKNOWN_FILE_EXTENSION|error TS18003|No inputs were found|"
    r"pytest: error: unrecognized arguments|INTERNALERROR", re.I)


@dataclass
class KetQuaChay:
    lenh: LenhKiem
    ma: int = 0
    dat: bool = False
    duoi: str = ""          # đuôi stdout/stderr, đã cắt
    cwd: str = ""
    #: `True` khi bằng chứng cho thấy CHÍNH LỆNH hỏng, không phải sản phẩm.
    lenh_hong: bool = False
    dau_hieu: str = ""      # đoạn văn bản đã khớp, làm bằng chứng

    def to_dict(self) -> Dict:
        return {"lenh": self.lenh.to_dict(), "ma": self.ma, "dat": self.dat,
                "duoi": self.duoi[:600], "cwd": self.cwd,
                "lenh_hong": self.lenh_hong, "dau_hieu": self.dau_hieu[:120]}


@dataclass
class BaoCaoKiem:
    ke_hoach: KeHoachKiem
    ket_qua: Tuple[KetQuaChay, ...] = ()
    #: `True` chỉ khi CÓ phép kiểm VÀ tất cả đều đạt.
    dat: bool = False
    #: `True` khi không có phép kiểm nào để chạy — THIẾU BẰNG CHỨNG.
    thieu_bang_chung: bool = False
    #: `True` khi CHÍNH LỆNH KIỂM hỏng (không phân giải được, không có test
    #: nào được thu…). Khác hẳn "mã sản phẩm sai", và dẫn tới hành động khác.
    ha_tang_hong: bool = False
    ly_do: str = ""

    def to_dict(self) -> Dict:
        return {"ke_hoach": self.ke_hoach.to_dict(),
                "ket_qua": [x.to_dict() for x in self.ket_qua],
                "dat": self.dat, "thieu_bang_chung": self.thieu_bang_chung,
                "ha_tang_hong": self.ha_tang_hong, "ly_do": self.ly_do}


def chay(ke_hoach: KeHoachKiem, repo, *, tran_giay: float = 900.0,
         runner=subprocess.run) -> BaoCaoKiem:
    """Chạy phép kiểm TRONG worktree của việc. Kết quả xấu là DỮ LIỆU.

    `cwd` là chính worktree — cùng bài học với `kiem_dinh.py` của V0.9: chạy
    ở gốc kho thì `git status` thấy một cây SẠCH và mọi bước ghi bị chấm là
    hỏng.
    """
    goc = Path(repo)
    if not ke_hoach.co:
        return BaoCaoKiem(
            ke_hoach=ke_hoach, thieu_bang_chung=True, dat=False,
            ly_do=("dự án không khai phép kiểm nào chạy được — THIẾU BẰNG "
                   "CHỨNG, không đủ để kết luận DONE"))
    ra: List[KetQuaChay] = []
    for l in ke_hoach.lenh:
        try:
            p = runner(list(l.argv), cwd=str(goc), capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=tran_giay, **an_cua_so())
            ma = int(getattr(p, "returncode", 1))
            duoi = ((getattr(p, "stdout", "") or "")
                    + (getattr(p, "stderr", "") or ""))[-800:]
        except subprocess.TimeoutExpired:
            ma, duoi = 124, f"vượt trần {tran_giay:.0f}s"
        except (OSError, ValueError) as exc:
            ma, duoi = 127, f"{type(exc).__name__}: {exc}"
        m = _LENH_HONG.search(duoi or "")
        ra.append(KetQuaChay(l, ma, ma == 0, duoi, cwd=str(goc),
                             lenh_hong=bool(m) and ma != 0,
                             dau_hieu=(m.group(0) if m else "")))

    hong = [x for x in ra if not x.dat]
    ha_tang = [x for x in hong if x.lenh_hong]
    if ha_tang:
        # PHÂN BIỆT HAI THỨ RẤT KHÁC NHAU.
        #
        # "sản phẩm sai" -> đi sửa mã. "lệnh kiểm sai" -> đi sửa lệnh kiểm.
        # Trước đây cả hai đều chỉ là `dat=False`, nên tầng phục hồi không có
        # cách nào chọn đúng hành động.
        return BaoCaoKiem(
            ke_hoach=ke_hoach, ket_qua=tuple(ra), dat=False,
            thieu_bang_chung=False, ha_tang_hong=True,
            ly_do=("LỆNH KIỂM tự nó hỏng, KHÔNG phải mã sản phẩm sai: "
                   + "; ".join(f"{' '.join(x.lenh.argv)} -> rc={x.ma} "
                               f"({x.dau_hieu})" for x in ha_tang[:2])))
    return BaoCaoKiem(
        ke_hoach=ke_hoach, ket_qua=tuple(ra), dat=not hong,
        thieu_bang_chung=False,
        ly_do=("tất cả phép kiểm của dự án đều xanh" if not hong else
               "phép kiểm của dự án KHÔNG đạt: "
               + "; ".join(" ".join(x.lenh.argv) + f" -> rc={x.ma}"
                           for x in hong[:3])))


def xac_minh(repo, *, lenh_ke_hoach: Sequence[Sequence[str]] = (),
             tran_giay: float = 900.0, runner=subprocess.run) -> BaoCaoKiem:
    """Khám phá rồi chạy. Cửa duy nhất người gọi cần biết."""
    return chay(kham_pha(repo, lenh_ke_hoach=lenh_ke_hoach), repo,
                tran_giay=tran_giay, runner=runner)
