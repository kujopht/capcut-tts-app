# -*- coding: utf-8 -*-
"""VIÊN NANG DỰ ÁN (Project Capsule) V0.7 — mô hình trí nhớ gọn, CÓ NGUỒN GỐC.

Viên nang KHÔNG thay ký ức thô. Nó là bản đồ nhỏ, có phiên bản, để Leader nạp
RẺ mỗi lượt: "dự án này là gì, đang ở đâu, quyết định gì đang hiệu lực, chỗ nào
chưa biết". Ký ức L0/L1 vẫn là nơi tra chi tiết.

BỐN LUẬT (mỗi cái ứng với một cách nói dối mà lớp này phải chặn)

1. **Mỗi mục có NGUỒN.** `nguon` nói điều này biết từ đâu và `bang_chung` cho
   mã/đường dẫn lần về được. Không có bằng chứng thì mục đó là `khong_ro` —
   **UNKNOWN là một giá trị hợp lệ**, bịa cho đủ ô thì không.
2. **Thứ tự nguồn** (Phần D): quyết định/ràng buộc/yêu cầu TƯỜNG MINH > trạng
   thái kho hiện tại > ký ức độ tin cao > tài liệu/HANDOFF/báo cáo > lịch sử
   git > suy luận (và suy luận phải TỰ DÁN NHÃN `suy_luan`).
3. **Giá trị SỐNG không bị đóng băng vào viên nang.** "farmer đang ACTIVE" là
   một phép ĐO, không phải một sự thật vĩnh viễn. Viên nang chỉ giữ THAM CHIẾU
   ("dịch vụ `fanfic-farmer`, provider quan sát: ssh_service") — câu hỏi hiện
   tại vẫn phải đi đo. Bậc thẩm quyền V0.5/V0.6 giữ nguyên:
   SỐNG > KHO/SỔ > KÝ ỨC > SUY LUẬN.
4. **Có phiên bản, không ghi đè.** Bảng `vien_nang` đã tự tăng `phien_ban` và
   giữ lịch sử; ta chỉ lưu bản mới KHI CÓ MỤC ĐỔI THẬT (tránh sinh phiên bản
   cho tiếng ồn hội thoại), kèm `ly_do` + `bang_chung` của lần cập nhật.

Lưu trữ: dùng ĐÚNG bảng `vien_nang` của v0.6 (nội dung là MỘT khối JSON), nên
không đổi lược đồ SQL và bản cũ đọc được bình thường. Trường mới: `muc`.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: (khoá, nhãn hiển thị, nhóm UI). Nhóm dùng cho tab Tổng quan (Phần H).
SO_MUC: Tuple[Tuple[str, str, str], ...] = (
    ("danh_tinh",          "Danh tính",                      "tong_quan"),
    # BẢN ĐỒ THÀNH PHẦN đứng ngay sau danh tính: nó trả lời "dự án này GỒM
    # NHỮNG GÌ", và thiếu nó thì `muc_tieu` (một câu chép từ `CLAUDE.md`) trở
    # thành định nghĩa duy nhất về phạm vi dự án — đo được là nó lạc hậu.
    ("thanh_phan",         "Bản đồ thành phần",              "tong_quan"),
    ("muc_tieu",           "Mục tiêu / nhiệm vụ",            "tong_quan"),
    ("moc_hien_tai",       "Mốc hiện tại",                   "tong_quan"),
    ("kien_truc",          "Kiến trúc hiện tại",             "kien_truc"),
    ("luu_tru",            "Kiến trúc lưu trữ",              "kien_truc"),
    ("topo_production",    "Topology production",            "production"),
    ("dich_vu",            "Dịch vụ quan trọng",             "production"),
    ("quyet_dinh",         "Quyết định đang hiệu lực",       "quyet_dinh"),
    ("rang_buoc",          "Ràng buộc cứng",                 "rang_buoc"),
    ("yeu_cau",            "Yêu cầu",                        "rang_buoc"),
    ("su_co",              "Sự cố đã biết",                  "su_co"),
    ("gioi_han",           "Giới hạn đã biết",               "su_co"),
    ("issue_mo",           "Issue đang mở",                  "issue"),
    ("no_ky_thuat",        "Nợ kỹ thuật",                    "issue"),
    ("roadmap",            "Roadmap",                        "roadmap"),
    ("tai_nguyen_agent",   "Tài nguyên agent / provider",    "tai_nguyen"),
    ("lich_su_quan_trong", "Bối cảnh lịch sử quan trọng",    "lich_su"),
    ("thay_doi_gan_day",   "Thay đổi gần đây",               "lich_su"),
    ("tham_chieu_song",    "Tham chiếu trạng thái SỐNG",     "song"),
)
KHOA_MUC = tuple(k for k, _n, _g in SO_MUC)
NHAN_MUC = {k: n for k, n, _g in SO_MUC}
NHOM_MUC = {k: g for k, _n, g in SO_MUC}

#: Trạng thái một mục.
CO, KHONG_RO, CU = "co", "khong_ro", "cu"

#: Thứ tự ưu tiên nguồn (Phần D) — số NHỎ là mạnh hơn.
UU_TIEN_NGUON = {"quyet_dinh": 1, "kho": 2, "ky_uc": 3, "tai_lieu": 4,
                 "git": 5, "suy_luan": 6, "song": 2}

#: Mẫu TÊN TỆP tài liệu -> mục. Cố ý bám vào TÊN (ổn định, đọc rẻ) chứ không
#: đoán nghĩa nội dung; đường dẫn tệp chính là bằng chứng.
_MAU_TAI_LIEU: Tuple[Tuple[str, str], ...] = (
    ("kien_truc",       r"ARCH|KIEN_TRUC|SCHEMA|DESIGN|CONTROL_CENTER|AI_ROUTER"),
    ("luu_tru",         r"STORAGE|LUU_TRU|R2|DRIVE|APPWRITE|BACKUP|ARCHIVE|RESTORE|DR_"),
    ("topo_production", r"PRODUCTION|CUTOVER|DEPLOY|TOPOLOGY|AWS|GCE|STAGING|INFRA"),
    ("dich_vu",         r"FARMER|WORKER|SERVICE|ORCHESTRATOR|QUEUE|DAEMON"),
    ("roadmap",         r"ROADMAP|HANDOFF|NEXT|PLAN|MILESTONE|PHASE"),
    ("gioi_han",        r"LIMIT|GIOI_HAN|CAPACITY|NPLUS1|PERF|SCALE|AUDIT"),
    ("no_ky_thuat",     r"DEBT|TODO|CLEANUP|REFACTOR|LEGACY"),
)

#: Câu truy hồi FTS cho từng mục (chạy trên ký ức ĐÃ NHẬP của chính dự án).
_TRUY_HOI: Dict[str, str] = {
    "kien_truc": "kiến trúc architecture module service",
    "luu_tru": "lưu trữ storage bucket database backup archive",
    "topo_production": "production deploy cutover server host",
    "dich_vu": "service worker farmer systemd unit",
    "gioi_han": "giới hạn limitation không thể chưa hỗ trợ",
    "roadmap": "kế hoạch bước tiếp theo roadmap phase",
    "no_ky_thuat": "nợ kỹ thuật cần dọn refactor tạm thời",
}


#: Lưu ý khi đọc mục nào cũng vậy: giá trị của nhiều mục là TÊN TÀI LIỆU +
#: trích đoạn ký ức — tức là CHỖ ĐỂ TRA, không phải câu trả lời. Luật tương
#: ứng cho Leader nằm ở `leader.LUAT_NANG` ("mục CÓ MẶT nhưng MỎNG cũng là
#: chưa có bằng chứng"), vì đo được là nó lấp chỗ trống bằng kiến thức chung.
#:
#: TỪ KHOÁ NẠP — dùng lúc DỰNG NHẮC NHỞ (khác `_TRUY_HOI`, thứ dùng lúc DỰNG
#: viên nang). Tách đôi có lý do: đổi từ khoá nạp KHÔNG được đổi nội dung viên
#: nang đã lưu. Phủ cả 19 mục, vì mục nào cũng có thể là mục bị hỏi.
_TU_KHOA_NAP: Dict[str, str] = {
    "danh_tinh": "tên dự án repo kho branch nhánh remote identity",
    "thanh_phan": ("thành phần component phần module gồm những gì hệ thống "
                   "web frontend scraper cạo cào thu thập tts audio farmer "
                   "duyệt review appwrite r2 drive triển khai deploy router"),
    "muc_tieu": "mục tiêu nhiệm vụ mission để làm gì tại sao",
    "moc_hien_tai": "tiến độ mốc trạng thái hiện tại đang ở đâu milestone",
    "kien_truc": "kiến trúc architecture module service tầng thiết kế",
    "luu_tru": ("lưu trữ storage bucket database backup archive r2 s3 drive "
                "google object sqlite d1 kv blob audio tệp file"),
    "topo_production": ("production deploy cutover server host topology aws "
                        "ec2 cloudflare worker domain vps máy chủ"),
    "dich_vu": ("dịch vụ service worker farmer systemd unit daemon process "
                "tiến trình chạy gì"),
    "quyet_dinh": "quyết định decision chốt đã chọn adr chính sách policy",
    "rang_buoc": "ràng buộc constraint không được cấm bắt buộc phải",
    "yeu_cau": "yêu cầu requirement cần phải có tính năng",
    "su_co": ("sự cố incident lỗi rò rỉ leak ssh key bảo mật security vụ "
              "hỏng outage postmortem"),
    "gioi_han": "giới hạn limitation không thể chưa hỗ trợ bug chapter scale",
    "issue_mo": "issue đang mở open ticket việc chưa xong tồn đọng",
    "no_ky_thuat": "nợ kỹ thuật debt cần dọn refactor tạm thời workaround",
    "roadmap": "kế hoạch bước tiếp theo roadmap phase lộ trình sắp tới",
    "tai_nguyen_agent": ("tài khoản account agent provider antigravity ag "
                         "runtime khe slot quota claude codex gemini bể pool "
                         "bao nhiêu"),
    "lich_su_quan_trong": "lịch sử history bối cảnh trước đây từng đã validate",
    "thay_doi_gan_day": "thay đổi gần đây recent commit vừa sửa mới nhất",
    "tham_chieu_song": "sống live đang chạy hiện tại trạng thái probe đo",
}

#: Số mục ĐẦU BẢNG luôn nạp bất kể câu hỏi (danh tính → tham chiếu sống).
#: Đây là thứ Leader cần ở MỌI lượt; phần đuôi mới chọn theo liên quan.
_DAU_LUON: int = 6

#: Chỗ NHƯỜNG SẴN cho dòng "còn các mục chưa nạp" (nêu tên nên nó không rẻ).
#: Chỉ trừ khi THẬT SỰ có mục bị cắt — viên nang vừa trần thì không mất gì.
_CHO_CHAN: int = 110


def _bo_dau(s: str) -> str:
    """Bỏ dấu + hạ chữ, để 'Antigravity account' khớp 'tài khoản antigravity'."""
    x = unicodedata.normalize("NFD", (s or "").lower())
    x = "".join(c for c in x if not unicodedata.combining(c))
    return x.replace("đ", "d")


def _tach_tu(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", _bo_dau(s)))


def thu_tu_nap(cau_hoi: str = "") -> List[str]:
    """Thứ tự nạp mục cho MỘT câu hỏi cụ thể.

    Vì sao không dùng một bảng ưu tiên cố định: đo được ở nghiệm thu v0.7 —
    bảng cố định nào cũng cắt mất đúng mục đang bị hỏi, và Leader lấp chỗ
    trống bằng cách BỊA (hỏi số account → "5" trong khi sổ ghi 8; đổi thứ tự
    thì hỏng sang câu R2/Drive). Nên: đầu bảng giữ nguyên, phần đuôi xếp theo
    ĐỘ LIÊN QUAN với câu đang hỏi. Tất định, không LLM, không mạng.
    """
    if not cau_hoi:
        return list(UU_TIEN_NAP)
    tq = _tach_tu(cau_hoi)
    if not tq:
        return list(UU_TIEN_NAP)

    def diem(k: str) -> int:
        vom = _tach_tu(_TU_KHOA_NAP.get(k, "") + " " + NHAN_MUC.get(k, k))
        return len(vom & tq)

    dau = list(UU_TIEN_NAP[:_DAU_LUON])
    duoi = sorted(UU_TIEN_NAP[_DAU_LUON:],
                  key=lambda k: (-diem(k), UU_TIEN_NAP.index(k)))
    #: Khi ngân sách chật, đầu bảng ăn hết trần và mục ĐANG BỊ HỎI vẫn bị cắt
    #: (bài kiểm `test_dong_CAT_khong_duoc_hy_sinh_muc_LIEN_QUAN_NHAT` bắt
    #: được). Mục khớp mạnh nhất CHÍNH LÀ thứ "cần ở lượt này", nên nó chen
    #: lên ngay sau danh tính — chỉ MỘT mục, để không phá đầu bảng.
    if duoi and diem(duoi[0]) > 0:
        return dau[:1] + [duoi[0]] + dau[1:] + duoi[1:]
    return dau + duoi


def _muc(gia_tri: Any, *, nguon: str, bang_chung: Sequence[str] = (),
         trang_thai: str = "", ghi_chu: str = "") -> Dict:
    """Dựng MỘT mục. Rỗng -> tự thành `khong_ro` (không bao giờ bịa)."""
    rong = (gia_tri is None or gia_tri == "" or gia_tri == [] or gia_tri == ())
    return {"gia_tri": ([] if rong and isinstance(gia_tri, (list, tuple)) else gia_tri),
            "trang_thai": (trang_thai or (KHONG_RO if rong else CO)),
            "nguon": ("" if rong else nguon),
            "bang_chung": [str(x) for x in (bang_chung or ())][:12],
            "ghi_chu": ghi_chu, "ts": time.time()}


def _khong_ro(ly_do: str = "chưa có bằng chứng đủ") -> Dict:
    return {"gia_tri": "", "trang_thai": KHONG_RO, "nguon": "",
            "bang_chung": [], "ghi_chu": ly_do, "ts": time.time()}


# ------------------------------------------------------------ dung nang -----

def dung_muc(cc, project_id: str, *, kho=None, gioi_han_doc: int = 6) -> Dict[str, Dict]:
    """Dựng TOÀN BỘ các mục của viên nang từ nguồn CÓ THẬT.

    Không ném: mỗi nhánh nguồn tự bọc, hỏng thì mục đó thành `khong_ro` kèm lý
    do — một nguồn chết không được biến viên nang thành lời bịa.
    """
    from scripts.control_center.nhan_du_an import kham_pha_kho, kham_pha_nguon
    muc: Dict[str, Dict] = {}
    kc = getattr(cc, "ky_uc", None)
    try:
        pj = cc.store.project(project_id)
    except Exception:                                       # noqa: BLE001
        pj = None
    repo = getattr(pj, "repo_path", "") or ""
    d = kho or (kham_pha_kho(repo) if repo else None)

    # ---- 1. DANH TÍNH: từ sổ Router + kho (nguồn `kho`) -------------------
    if d is not None and d.goc_worktree:
        dt = [f"project_id: {project_id}",
              f"tên: {getattr(pj, 'name', '') or project_id}",
              f"kho: {d.goc_worktree}"]
        if d.la_git:
            dt.append(f"nhánh hiện tại: {d.nhanh or '?'} · HEAD {(d.head or '')[:8]}")
            dt.append(f"{d.so_commit} commit"
                      + (f" · gốc: {d.commit_dau_tien}" if d.commit_dau_tien else ""))
            if d.remote_url:
                dt.append(f"remote: {d.remote_url}")
        else:
            dt.append("KHÔNG phải kho git — phần lịch sử git là UNKNOWN")
        # ---- BẢN ĐỒ THÀNH PHẦN: suy TỪ KHO, không từ một câu mô tả -------
        #
        # Đo được (dogfood 2026-09-12): `muc_tieu` lấy từ `CLAUDE.md` nói dự
        # án là "Fanfic Audio Studio — pipeline TTS", nên Leader khung hẹp và
        # không biết `server/scraper` tồn tại cho tới khi có tra cứu lúc-hỏi.
        # Một câu mô tả lạc hậu thì cả viên nang lạc hậu theo; bản đồ suy từ
        # tệp THẬT thì tự đúng theo kho.
        try:
            from scripts.control_center import tim_thanh_phan as _TTP
            topo = _TTP.topo_thanh_phan(Path(d.goc_worktree))
            if topo:
                muc["thanh_phan"] = _muc(
                    _TTP.goi_topo(topo), nguon="kho",
                    bang_chung=[b for t in topo for b in t["bang_chung"]][:8],
                    ghi_chu=("vai trò chỉ hiện khi có tệp CHỨNG MINH — "
                             "không suy diễn từ tên dự án"))
        except Exception as exc:                              # noqa: BLE001
            muc["thanh_phan"] = _khong_ro(f"không dựng được bản đồ: {exc}")

        muc["danh_tinh"] = _muc(dt, nguon="kho",
                                bang_chung=[f"repo:{d.goc_worktree}"],
                                ghi_chu=("danh tính KHÔNG suy từ nhánh: nhánh/HEAD "
                                         "chỉ là trạng thái hiện tại"))
    else:
        muc["danh_tinh"] = _khong_ro("dự án chưa có repo_path dùng được")

    # ---- 2. QUYẾT ĐỊNH / RÀNG BUỘC / YÊU CẦU: TƯỜNG MINH, ưu tiên cao nhất -
    for khoa, loai in (("quyet_dinh", "decision"), ("rang_buoc", "constraint"),
                       ("yeu_cau", "requirement")):
        muc[khoa] = _tu_ky_uc_theo_loai(kc, project_id, loai, khoa)

    # ---- 3. SỰ CỐ + bối cảnh lịch sử --------------------------------------
    muc["su_co"] = _tu_ky_uc_theo_loai(kc, project_id, "incident", "su_co",
                                       limit=8)
    muc["lich_su_quan_trong"] = _lich_su_quan_trong(kc, project_id)

    # ---- 4. Mục dựa TÀI LIỆU + ký ức đã nhập ------------------------------
    tl = _quet_tai_lieu(Path(d.goc_worktree)) if (d and d.goc_worktree) else {}
    for khoa in ("kien_truc", "luu_tru", "topo_production", "dich_vu",
                 "roadmap", "gioi_han", "no_ky_thuat"):
        muc[khoa] = _tu_tai_lieu_va_ky_uc(kc, project_id, khoa, tl,
                                          gioi_han_doc=gioi_han_doc)

    # ---- 5. MỐC HIỆN TẠI: điểm dừng gần nhất (đo từ sổ) -------------------
    muc["moc_hien_tai"] = _moc_hien_tai(kc, project_id)

    # ---- 6. MỤC TIÊU: người khai tường minh > tài liệu gốc của kho --------
    muc["muc_tieu"] = _muc_tieu(kc, project_id, tl,
                                Path(d.goc_worktree) if (d and d.goc_worktree)
                                else None)

    # ---- 7. ISSUE ĐANG MỞ: việc BLOCKED/FAILED còn treo trong sổ ----------
    muc["issue_mo"] = _issue_mo(cc, project_id)

    # ---- 8. THAY ĐỔI GẦN ĐÂY: git log (nguồn `git`) ----------------------
    muc["thay_doi_gan_day"] = _thay_doi_gan_day(d)

    # ---- 9. TÀI NGUYÊN AGENT + THAM CHIẾU SỐNG ---------------------------
    ng = {}
    try:
        ng = kham_pha_nguon(cc, d.goc_worktree if d else "", project_id)
    except Exception:                                       # noqa: BLE001
        ng = {}
    muc["tai_nguyen_agent"] = _tai_nguyen(ng)
    muc["tham_chieu_song"] = _tham_chieu_song(ng)

    for k in KHOA_MUC:
        muc.setdefault(k, _khong_ro())
    return muc


def _tu_ky_uc_theo_loai(kc, pid: str, loai: str, khoa: str,
                        limit: int = 12) -> Dict:
    """Bản ghi L1 TƯỜNG MINH theo loại — nguồn mạnh nhất (Phần D mục 1)."""
    if kc is None:
        return _khong_ro("ký ức không sẵn")
    try:
        r = kc.liet_ke(pid, loai, limit=limit)
        ds = [x for x in (r.get("ket_qua") or [])]
    except Exception as exc:                                # noqa: BLE001
        return _khong_ro(f"đọc ký ức hỏng: {type(exc).__name__}")
    if not ds:
        return _khong_ro(f"chưa có bản ghi loại {loai!r}")
    dong, bc = [], []
    for x in ds:
        k = x.get("ky_uc") or x        # decision -> {quyet_dinh..., ky_uc:{}}
        ma = x.get("ma") or k.get("ma") or ""
        tt = (k.get("trang_thai") or "hieu_luc")
        if tt not in ("hieu_luc", "", None):
            continue                   # BỎ bản đã bị thay thế/hết hiệu lực
        noi = (k.get("tieu_de") or "").strip() or (k.get("noi_dung") or "")[:120]
        auth = k.get("tin_cay") or ""
        dong.append(f"[{ma}] {noi}" + (f" · {auth}" if auth else ""))
        bc.append(ma)
    if not dong:
        return _khong_ro(f"có bản ghi {loai!r} nhưng không bản nào còn hiệu lực")
    m = _muc(dong, nguon="quyet_dinh" if loai in ("decision", "constraint",
                                                  "requirement") else "ky_uc",
             bang_chung=bc)
    # SỐ BẢN GHI THẬT lúc dựng. Cần cho phép so "cũ" (Phần J): mục cố ý CẮT
    # còn `limit` dòng, nên "sổ có nhiều bản ghi hơn danh sách" là BÌNH THƯỜNG
    # — bản đầu so với `len(bang_chung)` nên báo CŨ oan mọi lần.
    m["so_ban_ghi"] = len(dong)
    m["so_ban_ghi_tong"] = _dem_loai(kc, pid, loai)
    return m


def _dem_loai(kc, pid: str, loai: str) -> int:
    """Tổng bản ghi CÒN HIỆU LỰC của một loại (để so mốc cũ/mới)."""
    if kc is None:
        return 0
    try:
        r = kc.liet_ke(pid, loai, limit=1000)
        return sum(1 for x in (r.get("ket_qua") or [])
                   if ((x.get("ky_uc") or x).get("trang_thai") or "hieu_luc")
                   == "hieu_luc")
    except Exception:                                       # noqa: BLE001
        return 0


def _lich_su_quan_trong(kc, pid: str) -> Dict:
    """Bối cảnh lịch sử: bản ghi quan trọng nhất, ưu tiên thẩm quyền cao."""
    if kc is None:
        return _khong_ro("ký ức không sẵn")
    dong, bc = [], []
    try:
        for loai in ("incident", "architecture", "procedural", "fact"):
            r = kc.liet_ke(pid, loai, limit=6)
            for x in (r.get("ket_qua") or []):
                if (x.get("trang_thai") or "hieu_luc") != "hieu_luc":
                    continue
                if int(x.get("quan_trong") or 0) < 6:
                    continue
                ma = x.get("ma", "")
                dong.append(f"[{ma}] {loai}: "
                            + ((x.get("tieu_de") or "").strip()
                               or (x.get("noi_dung") or "")[:110]))
                bc.append(ma)
    except Exception as exc:                                # noqa: BLE001
        return _khong_ro(f"đọc ký ức hỏng: {type(exc).__name__}")
    if not dong:
        return _khong_ro("chưa có bản ghi lịch sử quan trọng")
    return _muc(dong[:10], nguon="ky_uc", bang_chung=bc)


def _quet_tai_lieu(goc: Path) -> Dict[str, List[str]]:
    """Tài liệu dự án khớp mẫu tên -> mục. CHỈ liệt kê đường dẫn (bằng chứng).

    Không đọc cả 249 tệp: tên tệp là tín hiệu rẻ và ổn định, còn nội dung để
    truy hồi FTS trên ký ức ĐÃ NHẬP lo.
    """
    ra: Dict[str, List[str]] = {k: [] for k, _p in _MAU_TAI_LIEU}
    try:
        ung: List[Path] = []
        for thu in (goc / "docs", goc):
            if not thu.is_dir():
                continue
            for f in sorted(thu.glob("*.md")):
                ung.append(f)
            d2 = thu / "reports"
            if d2.is_dir():
                for f in sorted(d2.glob("*.md")):
                    ung.append(f)
        for f in ung:
            ten = f.name.upper()
            for khoa, mau in _MAU_TAI_LIEU:
                if re.search(mau, ten):
                    try:
                        rel = str(f.relative_to(goc))
                    except ValueError:
                        rel = f.name
                    if rel not in ra[khoa]:
                        ra[khoa].append(rel)
    except OSError:
        pass
    return ra


def _tu_tai_lieu_va_ky_uc(kc, pid: str, khoa: str, tl: Dict[str, List[str]],
                          *, gioi_han_doc: int = 6) -> Dict:
    """Mục ghép từ TÀI LIỆU (đường dẫn) + KÝ ỨC khớp truy hồi (trích đoạn).

    Nói đúng những gì có: "các tài liệu này mô tả X" + trích đoạn ký ức có mã.
    Không tổng hợp thành một câu khẳng định mới — đó là việc của Leader, và nó
    sẽ thấy cả bằng chứng.
    """
    doc = (tl.get(khoa) or [])[:gioi_han_doc]
    dong: List[str] = []
    bc: List[str] = []
    if doc:
        dong.append("tài liệu: " + ", ".join(doc))
        bc += [f"doc:{x}" for x in doc]
    cau = _TRUY_HOI.get(khoa, "")
    if kc is not None and cau:
        try:
            r = kc.tim(pid, cau, limit=4)
            for m in (r.get("ket_qua") or [])[:4]:
                if (m.get("trang_thai") or "hieu_luc") != "hieu_luc":
                    continue
                ma = m.get("ma", "")
                t = (m.get("tieu_de") or "").strip() or (m.get("noi_dung") or "")[:110]
                t = re.sub(r"\s+", " ", t)[:130]
                if t and t not in ("```bash",):
                    dong.append(f"[{ma}] {t}")
                    bc.append(ma)
        except Exception:                                   # noqa: BLE001
            pass
    if not dong:
        return _khong_ro("không có tài liệu khớp và ký ức chưa đủ bằng chứng")
    return _muc(dong, nguon=("tai_lieu" if doc else "ky_uc"), bang_chung=bc)


def _moc_hien_tai(kc, pid: str) -> Dict:
    """Mốc hiện tại = điểm dừng gần nhất (dựng từ SỔ THẬT, không từ lời kể)."""
    if kc is None:
        return _khong_ro("ký ức không sẵn")
    try:
        tt = kc.tiep_tuc(pid)
    except Exception as exc:                                # noqa: BLE001
        return _khong_ro(f"đọc điểm dừng hỏng: {type(exc).__name__}")
    dd = (tt or {}).get("diem_dung")
    if not dd:
        return _khong_ro("chưa có điểm dừng nào")
    dong = [f"[{dd.get('ma','')}] {dd.get('ly_do','')}"]
    if dd.get("muc_tieu"):
        dong.append(f"đang làm: {dd['muc_tieu']}")
    if dd.get("chua_xong"):
        dong.append("chưa xong: " + "; ".join(list(dd["chua_xong"])[:4]))
    return _muc(dong, nguon="ky_uc", bang_chung=[dd.get("ma", "")])


def _muc_tieu(kc, pid: str, tl: Dict[str, List[str]],
              goc: Optional[Path] = None) -> Dict:
    """Mục tiêu dự án. Thứ tự: người/Leader KHAI TƯỜNG MINH > tài liệu gốc
    của chính kho (`CLAUDE.md` / `README.md`).

    Đọc tài liệu gốc là GROUNDING, không phải bịa: giá trị là chữ TRÍCH từ tệp
    và `bang_chung` là đường dẫn tệp đó — người đọc lần về được. Không có tệp
    nào nói mục tiêu thì để UNKNOWN.
    """
    if kc is not None:
        try:
            tt = kc.tiep_tuc(pid) or {}
            vn = tt.get("vien_nang") or {}
            cu = (vn.get("muc_tieu") or "").strip()
            # Bo qua gia tri do CHINH ta guong tu tai lieu o lan truoc, de
            # khong tu bien "trich tai lieu" thanh "nguoi da khai".
            if cu and not cu.startswith("(theo "):
                return _muc(cu, nguon="ky_uc",
                            bang_chung=[f"vien_nang:v{vn.get('phien_ban','?')}"])
        except Exception:                                   # noqa: BLE001
            pass
    if goc is not None:
        for ten in ("CLAUDE.md", "README.md", "docs/README.md"):
            f = goc / ten
            if not f.is_file():
                continue
            try:
                van = f.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                continue
            tieu_de = ""
            doan: List[str] = []
            for dong in van.splitlines():
                s = dong.strip()
                if not s:
                    if doan:
                        break
                    continue
                if s.startswith("#"):
                    if not tieu_de:
                        tieu_de = s.lstrip("#").strip()
                    continue
                if s.startswith(("|", "```", "<!--", ">")):
                    continue
                doan.append(s)
                if len(" ".join(doan)) > 300:
                    break
            mo = " ".join(doan)[:320].strip()
            if tieu_de or mo:
                gt = f"(theo {ten}) " + (f"{tieu_de} — {mo}" if tieu_de and mo
                                         else (tieu_de or mo))
                return _muc(gt.strip(), nguon="tai_lieu",
                            bang_chung=[f"doc:{ten}"],
                            ghi_chu=("trích từ tài liệu gốc của kho; người dùng "
                                     "có thể khai lại tường minh để thay"))
    return _khong_ro("chưa ai khai mục tiêu dự án và không có CLAUDE.md/README.md "
                     "nào nói nhiệm vụ (dùng `record_memory` để khai)")


def _issue_mo(cc, pid: str) -> Dict:
    """Issue đang mở = việc BLOCKED/FAILED/PAUSED còn treo trong SỔ Router."""
    try:
        ts = cc.store.tasks(pid, limit=500)
    except Exception as exc:                                # noqa: BLE001
        return _khong_ro(f"đọc sổ hỏng: {type(exc).__name__}")
    mo = [t for t in ts if t.state.value in ("BLOCKED", "FAILED", "PAUSED",
                                             "WAITING")]
    if not mo:
        return _muc([], nguon="kho", trang_thai=CO,
                    ghi_chu="không có việc nào đang treo trong sổ Router")
    dong = [f"[{t.task_id}] {t.state.value}: "
            + ((t.blocked_reason or t.title or "")[:110]) for t in mo[:10]]
    return _muc(dong, nguon="kho", bang_chung=[t.task_id for t in mo[:10]])


def _thay_doi_gan_day(d) -> Dict:
    """Thay đổi gần đây = commit mới nhất (nguồn `git`, chỉ đọc)."""
    if d is None or not d.la_git or not d.goc_worktree:
        return _khong_ro("không phải kho git")
    try:
        from scripts.control_center.nhan_du_an import _git, _ra
        van = _ra(_git(Path(d.goc_worktree), "log", "-n8",
                       "--format=%h %ad %s", "--date=short", han=45.0))
    except Exception as exc:                                # noqa: BLE001
        return _khong_ro(f"git log hỏng: {type(exc).__name__}")
    if not van:
        return _khong_ro("git log rỗng")
    dong = [x.strip()[:150] for x in van.splitlines() if x.strip()][:8]
    return _muc(dong, nguon="git",
                bang_chung=[f"git:{d.head[:8]}" if d.head else "git"])


def _tai_nguyen(ng: Dict) -> Dict:
    p = (ng or {}).get("provider") or {}
    if p.get("loi") or not p:
        return _khong_ro("chưa đọc được fabric")
    ag = p.get("tai_khoan_ag") or []
    dong = [f"runtime đã cấp phát: {p.get('runtime', 0)}",
            f"Antigravity: {p.get('antigravity', 0)} runtime"
            + (f" · tài khoản: {', '.join(ag)}" if ag else ""),
            f"nhà cung cấp: {', '.join(p.get('provider') or []) or '—'}"]
    return _muc(dong, nguon="kho", bang_chung=["fabric"])


def _tham_chieu_song(ng: Dict) -> Dict:
    """CHỈ THAM CHIẾU, không giá trị đo.

    Đây là chỗ dễ sai nhất của cả lớp này: nhét "farmer ACTIVE" vào viên nang
    là biến một phép đo 10 giây thành một "sự thật" sống mãi. Nên mục này chỉ
    nói CÁI GÌ ĐO ĐƯỢC và BẰNG PROVIDER NÀO.
    """
    q = (ng or {}).get("quan_sat") or {}
    if q.get("loi"):
        return _khong_ro(f"đọc cấu hình quan sát hỏng: {q['loi']}")
    prov = q.get("probe") or []
    if not prov:
        return _khong_ro("dự án chưa khai provider quan sát riêng — câu hỏi "
                         "hiện tại sẽ dùng quan sát chung")
    dong = [f"{x.get('loai','?')} · id={x.get('id','?')}"
            + (f" · unit={x['unit']}" if x.get("unit") else "")
            + (" · host đã khai" if x.get("host") else "")
            for x in prov]
    return _muc(dong, nguon="song", bang_chung=["observability.json"],
                ghi_chu=("THAM CHIẾU, không phải giá trị: trạng thái hiện tại "
                         "PHẢI đo lại qua provider trên"))


# ------------------------------------------------------ phien ban / cu ------

def _chuan(v: Any) -> Any:
    """Chuẩn hoá giá trị để SO SÁNH (bỏ `ts` và nhiễu thứ tự)."""
    if isinstance(v, dict):
        return {k: _chuan(x) for k, x in sorted(v.items())
                if k not in ("ts",)}
    if isinstance(v, (list, tuple)):
        return [_chuan(x) for x in v]
    return v


def so_sanh(cu: Optional[Dict], moi: Dict) -> List[str]:
    """Các KHOÁ MỤC đổi thật giữa hai bản. Bỏ qua `ts` (nhiễu mỗi lần dựng)."""
    cu = cu or {}
    ra = []
    for k in KHOA_MUC:
        if _chuan(cu.get(k)) != _chuan(moi.get(k)):
            ra.append(k)
    return ra


def dau_hieu_cu(cc, project_id: str, vn_muc: Dict) -> Dict[str, str]:
    """Mục nào có thể ĐÃ CŨ (Phần J) — trả `{khoa: lý do}`.

    ĐÁNH DẤU, không tự viết lại: một mục cũ được nói rõ là cũ còn tốt hơn một
    mục mới bịa. Không đo thứ đắt ở đây (không `git log` toàn kho, không đọc
    tài liệu) — chỉ so vài mốc rẻ.
    """
    ra: Dict[str, str] = {}
    from scripts.control_center.nhan_du_an import kham_pha_kho
    try:
        pj = cc.store.project(project_id)
        repo = getattr(pj, "repo_path", "") or ""
    except Exception:                                       # noqa: BLE001
        repo = ""
    if repo:
        d = kham_pha_kho(repo)
        dt = (vn_muc.get("danh_tinh") or {}).get("gia_tri") or []
        van = " ".join(dt) if isinstance(dt, list) else str(dt)
        if d.la_git and d.head and d.head[:8] not in van:
            ra["danh_tinh"] = f"HEAD đã đổi (nay {d.head[:8]})"
            ra["thay_doi_gan_day"] = "HEAD đã đổi — commit gần đây cần dựng lại"
        if d.la_git and d.nhanh and f"nhánh hiện tại: {d.nhanh}" not in van:
            ra["danh_tinh"] = (ra.get("danh_tinh", "")
                               + f"; nhánh nay là {d.nhanh}").strip("; ")
    kc = getattr(cc, "ky_uc", None)
    if kc is not None:
        for khoa, loai in (("quyet_dinh", "decision"), ("rang_buoc", "constraint"),
                           ("su_co", "incident"), ("yeu_cau", "requirement")):
            m = vn_muc.get(khoa) or {}
            # So voi TONG luc dung, khong voi so dong da CAT.
            truoc = m.get("so_ban_ghi_tong")
            if truoc is None:
                continue                # ban cu chua ghi moc -> khong doan
            nay = _dem_loai(kc, project_id, loai)
            if nay > int(truoc):
                ra[khoa] = (f"sổ có {nay} bản ghi {loai} (viên nang dựng lúc "
                            f"{truoc}) — có bản mới chưa vào")
    return ra


def uoc_token(muc: Dict) -> int:
    """Ước token của viên nang khi render (đo bằng byte UTF-8, như `memory`)."""
    from scripts.control_center.memory.model import uoc_token as _ut
    return _ut(render(muc))


#: Thứ tự NẠP cho Leader khi phải cắt theo trần token (Phần I). Mục đầu bảng
#: là thứ Leader cần ở MỌI lượt; mục cuối là thứ tra khi cần.
#: Chỉ còn là thứ tự MẶC ĐỊNH (khi không có câu hỏi) và thứ tự PHÁ HOÀ cho
#: phần đuôi — `thu_tu_nap()` mới là thứ quyết định lượt cụ thể nạp mục nào.
UU_TIEN_NAP: Tuple[str, ...] = (
    # `thanh_phan` nằm trong ĐẦU BẢNG (luôn nạp): câu hỏi rộng nào cũng cần
    # biết dự án GỒM NHỮNG GÌ, và đó chính là thứ đã thiếu khi Leader trả lời
    # hẹp về "pipeline TTS".
    "danh_tinh", "thanh_phan", "moc_hien_tai", "muc_tieu", "quyet_dinh",
    "rang_buoc", "tham_chieu_song", "issue_mo", "kien_truc",
    "topo_production", "su_co", "gioi_han", "luu_tru", "dich_vu", "roadmap",
    "tai_nguyen_agent", "yeu_cau", "no_ky_thuat", "thay_doi_gan_day",
    "lich_su_quan_trong",
)


def render_gon(muc: Dict, *, tran_token: int = 900, tran_dong: int = 3,
               cau_hoi: str = "") -> str:
    """Bản GỌN có TRẦN TOKEN cho nhắc nhở Leader (Phần I).

    Viên nang đầy của một dự án thật ~3.8k token — nạp nguyên si mỗi lượt là
    đúng thứ "ảo hoá ngữ cảnh" của V0.6 tồn tại để tránh. Nên: nạp theo
    `thu_tu_nap(cau_hoi)` tới khi hết trần, và NÓI RÕ đã cắt NHỮNG MỤC NÀO.

    Hai điều đo được ở nghiệm thu v0.7, cả hai đổi thiết kế:

    * Thứ tự cố định luôn cắt mất đúng mục đang bị hỏi → chọn theo câu hỏi.
    * Dòng cắt chỉ ĐẾM ("còn 10 mục nữa") thì Leader không phân biệt được
      "không có bằng chứng" với "có mà lượt này chưa nạp", nên nó BỊA. Nêu
      TÊN mục bị cắt tốn ~40 token và biến câu bịa thành câu "chưa nạp".

    Trần là THẬT, với đúng một ngoại lệ đã biết và cố ý: luôn giữ ÍT NHẤT
    MỘT mục cộng dòng cắt. Nếu một mục đơn lẻ đã lớn hơn cả trần (trần bệnh
    lý, hoặc mục khổng lồ bất thường) thì khối trả về sẽ vượt trần — vì bỏ
    nốt dòng cắt để cho vừa lại chính là bỏ đúng thứ ngăn Leader đoán. Ở
    trần thật 900 với viên nang thật, khối đo được 759–897 token.
    """
    from scripts.control_center.memory.model import uoc_token as _ut
    thu_tu = thu_tu_nap(cau_hoi)

    def mot_luot(tran: int) -> Tuple[List[str], List[str], int]:
        d: List[str] = []
        ten_bo: List[str] = []
        dung = 0
        for khoa in thu_tu:
            m = muc.get(khoa) or {}
            nhan = NHAN_MUC.get(khoa, khoa)
            tt = m.get("trang_thai")
            if tt == KHONG_RO:
                khoi = f"{nhan}: UNKNOWN"
            else:
                gt = m.get("gia_tri")
                if isinstance(gt, (list, tuple)):
                    lay = list(gt)[:tran_dong]
                    khoi = (f"{nhan}" + (" [CŨ]" if tt == CU else "") + ":\n"
                            + "\n".join(f"  - {x}" for x in lay)
                            + (f"\n  … còn {len(gt) - len(lay)}"
                               if len(gt) > len(lay) else ""))
                else:
                    khoi = f"{nhan}" + (" [CŨ]" if tt == CU else "") + f": {gt}"
            t = _ut(khoi)
            if dung + t > tran and d:
                ten_bo.append(nhan)
                continue
            d.append(khoi)
            dung += t
        return d, ten_bo, dung

    def chan(ten_bo: Sequence[str], so_ten: int) -> str:
        lay = list(ten_bo)[:max(0, so_ten)]
        con = len(ten_bo) - len(lay)
        if not lay:                       # trần quá chật để nêu nổi một tên
            ke = f"{con} mục"
        else:
            ke = ", ".join(lay) + (f", +{con} mục" if con > 0 else "")
        return ("(viên nang CÒN các mục CHƯA NẠP lượt này: " + ke
                + " — có dữ liệu, chỉ là chưa nạp; cần thì HỎI, đừng đoán)")

    d, ten_bo, dung = mot_luot(tran_token)
    if not ten_bo:
        return "\n".join(d)

    #: Dòng chân CŨNG tốn token, nên phải NHƯỜNG CHỖ TRƯỚC, không trừ sau.
    #: Đo được ở nghiệm thu v0.7: bản trừ-sau đuổi đúng mục LIÊN QUAN NHẤT ra
    #: để lấy chỗ cho dòng chân (câu R2/Drive mất mục "Kiến trúc lưu trữ" vừa
    #: mới được xếp lên đầu đuôi), rồi tên nó rơi vào phần "+N mục" nên Leader
    #: không thấy cả nội dung lẫn tên → lại BỊA. Thứ được phép hy sinh là TÊN
    #: trong dòng chân, không bao giờ là MỤC.
    d, ten_bo, dung = mot_luot(max(1, tran_token - _CHO_CHAN))
    so_ten = 10
    while so_ten > 0 and dung + _ut(chan(ten_bo, so_ten)) > tran_token:
        so_ten -= 1
    d.append(chan(ten_bo, so_ten))
    return "\n".join(d)


def luu_neu_dang(cc, project_id: str, muc: Dict, *, ly_do: str = "",
                 bang_chung: Sequence[str] = ()) -> Dict:
    """Lưu MỘT PHIÊN BẢN MỚI chỉ khi có mục ĐỔI THẬT (Phần E).

    Không ghi đè lịch sử: bảng `vien_nang` tự tăng `phien_ban`, bản cũ còn
    nguyên. Không sinh phiên bản cho tiếng ồn: `so_sanh()` bỏ qua `ts`.
    """
    kc = getattr(cc, "ky_uc", None)
    if kc is None:
        return {"luu": False, "ly_do": "ký ức không sẵn"}
    p = kc.provider(project_id)
    if p is None:
        return {"luu": False, "ly_do": "provider ký ức không sẵn"}
    cu = None
    try:
        cu = p.vien_nang()
    except Exception:                                       # noqa: BLE001
        cu = None
    muc_cu = dict(getattr(cu, "muc", None) or {}) if cu is not None else {}
    doi = so_sanh(muc_cu, muc)
    if cu is not None and not doi:
        return {"luu": False, "phien_ban": getattr(cu, "phien_ban", 0),
                "doi": [], "ly_do": "không có mục nào đổi — không sinh phiên bản"}
    from scripts.control_center.memory.model import VienNang
    vn = cu if cu is not None else VienNang(project_id=project_id)
    vn.muc = muc
    # GƯƠNG sang các trường V0.6 để bản đọc cũ (`goi_ngu_canh`) vẫn thấy nội
    # dung, không phải một viên nang trống.
    vn.muc_tieu = _mot_dong(muc.get("muc_tieu"))
    vn.kien_truc = _mot_dong(muc.get("kien_truc"))
    vn.moc_hien_tai = _mot_dong(muc.get("moc_hien_tai"))
    vn.rang_buoc = tuple(_ds(muc.get("rang_buoc"))[:8])
    vn.van_de_da_biet = tuple((_ds(muc.get("su_co")) + _ds(muc.get("gioi_han")))[:8])
    vn.moc_gan_day = tuple(_ds(muc.get("thay_doi_gan_day"))[:6])
    vn.ly_do = (ly_do or ("dựng lại Viên nang — đổi: " + ", ".join(doi[:6])))[:400]
    if bang_chung:
        vn.bang_chung = tuple(dict.fromkeys(list(vn.bang_chung) + list(bang_chung)))[:24]
    try:
        ra = p.cap_nhat_vien_nang(vn)
    except Exception as exc:                                # noqa: BLE001
        return {"luu": False, "ly_do": f"{type(exc).__name__}: {exc}"[:200]}
    if ra is None:
        return {"luu": False, "ly_do": p.loi_cuoi or "không lưu được"}
    try:
        cc.store.ghi_su_kien(
            "MEMORY_CAPSULE", project_id=project_id,
            detail=f"Viên nang v{ra.phien_ban}: {vn.ly_do}"[:400],
            meta={"phien_ban": ra.phien_ban, "doi": doi,
                  "so_muc_co": sum(1 for k in KHOA_MUC
                                   if (muc.get(k) or {}).get("trang_thai") == CO)})
    except Exception:                                       # noqa: BLE001
        pass
    return {"luu": True, "phien_ban": ra.phien_ban, "doi": doi}


def _ds(m: Optional[Dict]) -> List[str]:
    gt = (m or {}).get("gia_tri")
    if isinstance(gt, (list, tuple)):
        return [str(x) for x in gt]
    return [str(gt)] if gt else []


def _mot_dong(m: Optional[Dict]) -> str:
    ds = _ds(m)
    return " · ".join(ds)[:1200] if ds else ""


def dung_va_luu(cc, project_id: str, *, ly_do: str = "") -> Dict:
    """Dựng viên nang từ nguồn rồi lưu nếu đổi. Trả báo cáo gọn."""
    muc = dung_muc(cc, project_id)
    kq = luu_neu_dang(cc, project_id, muc, ly_do=ly_do)
    kq["so_muc"] = len(KHOA_MUC)
    kq["so_muc_co"] = sum(1 for k in KHOA_MUC
                          if muc[k].get("trang_thai") == CO)
    kq["so_khong_ro"] = sum(1 for k in KHOA_MUC
                            if muc[k].get("trang_thai") == KHONG_RO)
    kq["token_day"] = uoc_token(muc)
    kq["token_gon"] = _ut_gon(muc)
    kq["muc"] = muc
    return kq


def _ut_gon(muc: Dict) -> int:
    from scripts.control_center.memory.model import uoc_token as _ut
    return _ut(render_gon(muc))


def nap(cc, project_id: str) -> Tuple[Dict, int]:
    """Đọc viên nang ĐANG LƯU + đánh dấu mục CŨ. `({muc}, phien_ban)`.

    Không dựng lại (đắt): chỉ đọc bản đã lưu rồi gắn cờ `cu` cho mục mà dấu
    hiệu rẻ cho thấy đã lạc hậu — Phần J: đánh dấu, không im lặng.
    """
    kc = getattr(cc, "ky_uc", None)
    if kc is None:
        return {}, 0
    p = kc.provider(project_id)
    if p is None:
        return {}, 0
    try:
        vn = p.vien_nang()
    except Exception:                                       # noqa: BLE001
        return {}, 0
    if vn is None:
        return {}, 0
    muc = dict(getattr(vn, "muc", None) or {})
    if not muc:
        return {}, int(getattr(vn, "phien_ban", 0) or 0)
    try:
        cu = dau_hieu_cu(cc, project_id, muc)
    except Exception:                                       # noqa: BLE001
        cu = {}
    for k, ly in (cu or {}).items():
        if k in muc and muc[k].get("trang_thai") == CO:
            muc[k] = dict(muc[k])
            muc[k]["trang_thai"] = CU
            muc[k]["ghi_chu"] = (muc[k].get("ghi_chu") or "") + f" [CŨ: {ly}]"
    return muc, int(getattr(vn, "phien_ban", 0) or 0)


def render(muc: Dict, *, bo_khong_ro: bool = False, tran_dong: int = 6) -> str:
    """Viên nang thành CHỮ gọn cho nhắc nhở Leader / UI.

    `khong_ro` được IN RA có chủ đích (trừ khi gọi bỏ): Leader phải biết chỗ
    nào dự án chưa có bằng chứng, để nó HỎI thay vì đoán.
    """
    d: List[str] = []
    for khoa, nhan, _g in SO_MUC:
        m = muc.get(khoa) or {}
        tt = m.get("trang_thai")
        if tt == KHONG_RO:
            if not bo_khong_ro:
                d.append(f"{nhan}: UNKNOWN ({m.get('ghi_chu') or 'chưa có bằng chứng'})")
            continue
        gt = m.get("gia_tri")
        dau = f"{nhan}" + (" [CŨ]" if tt == CU else "") + ":"
        if isinstance(gt, (list, tuple)):
            if not gt:
                d.append(f"{dau} (rỗng)")
                continue
            d.append(dau)
            for x in list(gt)[:tran_dong]:
                d.append(f"  - {x}")
            if len(gt) > tran_dong:
                d.append(f"  … còn {len(gt) - tran_dong} dòng")
        else:
            d.append(f"{dau} {gt}")
        if m.get("nguon"):
            bc = ", ".join((m.get("bang_chung") or [])[:4])
            d.append(f"    (nguồn: {m['nguon']}"
                     + (f" · bằng chứng: {bc}" if bc else "") + ")")
    return "\n".join(d)
