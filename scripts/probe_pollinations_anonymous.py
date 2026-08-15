#!/usr/bin/env python3
"""Do tham (discovery probe) — model anh Pollinations nao dung duoc
KHONG CAN api key.

    python scripts/probe_pollinations_anonymous.py

Day CHI la mot cuoc do kham pha. KHONG tich hop gi vao Fanfic World,
KHONG sua bat ky code sinh anh production nao.

AN TOAN — RANG BUOC BAT BUOC (khong duoc vi pham duoi bat ky hinh thuc nao):
- Script nay KHONG bao gio doc POLLINATIONS_API_KEY hay bat ky secret nao —
  khong co dong code nao trong file nay goi os.environ cho muc dich xac
  thuc, va KHONG import server.config.load_env_file (ham do nap .env vao
  tien trinh) de loai tru hoan toan kha nang key bi nap vao roi vo tinh
  dung nham.
- KHONG gui header Authorization o bat ky request nao.
- KHONG gan tham so "?key=..." hay bat ky bien the nao cua no vao URL.
- httpx.Client(trust_env=False) — tu choi doc MOI bien moi truong (ke ca
  proxy), khong chi rieng key, de dam bao moi trung khong the anh huong
  request theo bat ky cach nao.
- Khong bao gio in secret — vi khong doc secret nao ca nen khong co gi de
  lo lot.
- Khong dump toan bo noi dung loi (HTML/JSON dai) hay bat ky header nao
  vao bao cao — chi luu ma trang thai, Content-Type, kich thuoc, do tre,
  va toi da 200 ky tu dau cua thong diep loi.

Chay `python scripts/probe_pollinations_anonymous.py --final-check-only` de
CHI thuc hien buoc xac minh toi thieu bo sung (4 request: khong model,
model=flux, model=zimage, model khong ton tai) — dung de doi chieu voi
phat hien "7 model tra ve anh giong het nhau" ma KHONG lap lai toan bo
25 request cua lan do dau (tranh stress-test dich vu). Buoc nay doc lai
raw JSON da co san tren dia de giu nguyen du lieu vong 1/vong 2 cu, chi
them phan xac minh moi va sua lai cach dien dat bao cao.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

import httpx

for _luong in (sys.stdout, sys.stderr):
    if hasattr(_luong, "reconfigure"):
        _luong.reconfigure(encoding="utf-8", errors="replace")

PROMPT = "a red apple on a white background"
"""Neutral prompt duy nhat, dung cho MOI request trong ca hai vong, ca hai
endpoint — dam bao ket qua giua cac model/lan goi co the so sanh truc tiep."""

MODELS = [
    "flux",
    "zimage",
    "dreamshaper",
    "turbo",
    "gptimage",
    "gpt-image-2",
    "kontext",
    "nanobanana",
    "nanobanana-pro",
    "seedream",
]

LEGACY_BASE = "https://image.pollinations.ai/prompt"
UNIFIED_URL = "https://gen.pollinations.ai/v1/images/generations"
TIMEOUT_SECONDS = 30.0
SEED = 42
SO_LAN_THU_LAI = 2


@dataclass
class KetQua:
    model: str
    endpoint_type: str  # "legacy" | "unified"
    lan_thu: int
    http_status: Optional[int]
    content_type: str
    byte_size: Optional[int]
    do_tre_giay: float
    thanh_cong: bool
    loi: str = ""
    sha256_16: str = ""  # chi de PHAT HIEN trung lap noi dung, khong phai secret


def _client() -> httpx.Client:
    """Client KHONG doc bat ky bien moi truong nao (trust_env=False),
    header mac dinh RONG — khong Authorization o bat ky request nao."""
    return httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, headers={})


def _danh_gia_thanh_cong(resp: httpx.Response) -> bool:
    """Tieu chi thanh cong DUY NHAT duoc chap nhan: HTTP 200 VA Content-Type
    bat dau bang "image/" VA than response khong rong."""
    content_type = resp.headers.get("content-type", "")
    return (
        resp.status_code == 200
        and content_type.startswith("image/")
        and len(resp.content) > 0
    )


def _lam_sach_loi_ngoai_le(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:150]}"


def _lam_sach_loi_http(resp: httpx.Response) -> str:
    try:
        text = resp.text[:200]
    except Exception:
        text = "(khong doc duoc noi dung loi)"
    return f"HTTP {resp.status_code}: {text}"


def _goi_legacy(client: httpx.Client, model: str, lan_thu: int) -> KetQua:
    url = f"{LEGACY_BASE}/{quote(PROMPT)}"
    tham_so = {"model": model, "seed": SEED, "nologo": "true"}
    bat_dau = time.monotonic()
    try:
        resp = client.get(url, params=tham_so)
    except httpx.HTTPError as exc:
        return KetQua(
            model=model, endpoint_type="legacy", lan_thu=lan_thu,
            http_status=None, content_type="", byte_size=None,
            do_tre_giay=time.monotonic() - bat_dau, thanh_cong=False,
            loi=_lam_sach_loi_ngoai_le(exc),
        )
    do_tre = time.monotonic() - bat_dau
    thanh_cong = _danh_gia_thanh_cong(resp)
    return KetQua(
        model=model, endpoint_type="legacy", lan_thu=lan_thu,
        http_status=resp.status_code,
        content_type=resp.headers.get("content-type", ""),
        byte_size=len(resp.content) if thanh_cong else None,
        do_tre_giay=do_tre, thanh_cong=thanh_cong,
        loi="" if thanh_cong else _lam_sach_loi_http(resp),
        sha256_16=hashlib.sha256(resp.content).hexdigest()[:16] if thanh_cong else "",
    )


def _goi_unified(client: httpx.Client, model: str) -> KetQua:
    bat_dau = time.monotonic()
    than = {"prompt": PROMPT, "model": model, "n": 1}
    try:
        resp = client.post(UNIFIED_URL, json=than)
    except httpx.HTTPError as exc:
        return KetQua(
            model=model, endpoint_type="unified", lan_thu=1,
            http_status=None, content_type="", byte_size=None,
            do_tre_giay=time.monotonic() - bat_dau, thanh_cong=False,
            loi=_lam_sach_loi_ngoai_le(exc),
        )
    do_tre = time.monotonic() - bat_dau
    thanh_cong = _danh_gia_thanh_cong(resp)
    return KetQua(
        model=model, endpoint_type="unified", lan_thu=1,
        http_status=resp.status_code,
        content_type=resp.headers.get("content-type", ""),
        byte_size=len(resp.content) if thanh_cong else None,
        do_tre_giay=do_tre, thanh_cong=thanh_cong,
        loi="" if thanh_cong else _lam_sach_loi_http(resp),
    )


def _in_dong(kq: KetQua, nhan: str) -> None:
    trang_thai = "OK" if kq.thanh_cong else f"THAT BAI: {kq.loi}"
    print(
        f"[{nhan:24}] {kq.endpoint_type:8} lan={kq.lan_thu} "
        f"status={kq.http_status} content-type={kq.content_type!r} "
        f"size={kq.byte_size} do_tre={kq.do_tre_giay:.2f}s -> {trang_thai}"
    )


HEADER_KHONG_NHAY_CAM = (
    "content-type", "content-length", "x-cache", "cf-cache-status", "age",
    "server", "x-model", "x-served-by", "via", "x-request-id",
)
"""Danh sach header duoc phep ghi vao bao cao — KHONG bao gio ghi
Authorization, Set-Cookie, hay bat ky header nao khac ngoai danh sach nay."""


@dataclass
class KetQuaXacMinh:
    nhan: str
    tham_so_model: Optional[str]
    http_status: Optional[int]
    content_type: str
    byte_size: Optional[int]
    sha256_16: str
    do_tre_giay: float
    headers_khong_nhay_cam: dict


def _goi_xac_minh(client: httpx.Client, nhan: str, model: Optional[str]) -> KetQuaXacMinh:
    url = f"{LEGACY_BASE}/{quote(PROMPT)}"
    tham_so = {"seed": SEED, "nologo": "true"}
    if model is not None:
        tham_so["model"] = model
    bat_dau = time.monotonic()
    resp = client.get(url, params=tham_so)
    do_tre = time.monotonic() - bat_dau
    content_type = resp.headers.get("content-type", "")
    sha_day_du = hashlib.sha256(resp.content).hexdigest() if content_type.startswith("image/") else ""
    headers_loc = {
        k: v for k, v in resp.headers.items() if k.lower() in HEADER_KHONG_NHAY_CAM
    }
    return KetQuaXacMinh(
        nhan=nhan, tham_so_model=model, http_status=resp.status_code,
        content_type=content_type,
        byte_size=len(resp.content) if content_type.startswith("image/") else None,
        sha256_16=sha_day_du[:16], do_tre_giay=do_tre,
        headers_khong_nhay_cam=headers_loc,
    )


def chay_xac_minh_cuoi_va_cap_nhat_bao_cao() -> None:
    """Buoc xac minh TOI THIEU bo sung — dung DUY NHAT 4 request, khong lap
    lai toan bo cuoc do dau (khong stress-test dich vu)."""
    client = _client()
    print("=== XAC MINH TOI THIEU: khong model / flux / zimage / model khong ton tai ===")
    cac_truong_hop = [
        ("khong_model", None),
        ("model=flux", "flux"),
        ("model=zimage", "zimage"),
        ("model_khong_ton_tai", "this-model-definitely-does-not-exist-xyz123"),
    ]
    ket_qua = []
    for nhan, model in cac_truong_hop:
        kq = _goi_xac_minh(client, nhan, model)
        ket_qua.append(kq)
        print(
            f"[{nhan:20}] status={kq.http_status} content-type={kq.content_type!r} "
            f"size={kq.byte_size} sha256_16={kq.sha256_16 or '—'} "
            f"do_tre={kq.do_tre_giay:.2f}s headers={kq.headers_khong_nhay_cam}"
        )
    client.close()

    cac_hash = {kq.nhan: kq.sha256_16 for kq in ket_qua if kq.sha256_16}
    tat_ca_giong_nhau = len(set(cac_hash.values())) == 1 and len(cac_hash) == len(ket_qua)

    goc = Path(__file__).resolve().parent.parent
    thu_muc = goc / "docs" / "reports"
    raw_path = thu_muc / "pollinations-anonymous-probe-raw.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["xac_minh_toi_thieu_bo_sung"] = {
        "muc_dich": (
            "Kiem tra xem endpoint legacy an danh co thuc su phan biet model "
            "hay khong, bang cach so sanh: khong truyen model, model that "
            "(flux/zimage), va mot ten model khong ton tai."
        ),
        "ket_qua": [asdict(kq) for kq in ket_qua],
        "tat_ca_giong_nhau_byte_for_byte": tat_ca_giong_nhau,
    }
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    _sua_lai_bao_cao_sau_xac_minh(ket_qua, tat_ca_giong_nhau)
    print()
    print(f"Đã cập nhật báo cáo: {thu_muc / 'pollinations-anonymous-probe-summary.md'}")


def _sua_lai_bao_cao_sau_xac_minh(ket_qua: List[KetQuaXacMinh], tat_ca_giong_nhau: bool) -> None:
    goc = Path(__file__).resolve().parent.parent
    thu_muc = goc / "docs" / "reports"
    duong_dan = thu_muc / "pollinations-anonymous-probe-summary.md"
    noi_dung = duong_dan.read_text(encoding="utf-8")

    tieu_de_ket_luan = "## Kết luận cuối cùng — đã xác minh tối thiểu bổ sung\n"
    if tieu_de_ket_luan in noi_dung:
        noi_dung = noi_dung.split(tieu_de_ket_luan)[0].rstrip() + "\n\n"

    dong = [tieu_de_ket_luan]
    dong.append(
        "Bước xác minh bổ sung (4 request, cùng prompt + seed=42, KHÔNG lặp "
        "lại toàn bộ 25 request của lần dò đầu — tránh stress-test dịch vụ):\n"
    )
    dong.append("| Trường hợp | HTTP | Content-Type | Size | SHA256 (16 ký tự) | Header không nhạy cảm |")
    dong.append("|---|---|---|---|---|---|")
    for kq in ket_qua:
        dong.append(
            f"| {kq.nhan} | {kq.http_status} | {kq.content_type or '—'} | "
            f"{kq.byte_size if kq.byte_size is not None else '—'} | "
            f"{kq.sha256_16 or '—'} | `{kq.headers_khong_nhay_cam}` |"
        )
    dong.append("")

    if tat_ca_giong_nhau:
        dong.append(
            "**Xác nhận:** yêu cầu KHÔNG truyền `model`, `model=flux`, "
            "`model=zimage`, và một tên model KHÔNG TỒN TẠI (`this-model-"
            "definitely-does-not-exist-xyz123`) đều trả về **CÙNG MỘT ảnh "
            "byte-for-byte giống hệt nhau**. Điều này chứng minh endpoint "
            "legacy ẩn danh **bỏ qua/chuẩn hoá tham số `model=`** — nó KHÔNG "
            "phân biệt được model hợp lệ với model bịa đặt, nên không thể "
            "coi bất kỳ tên model riêng lẻ nào là \"đã xác nhận hoạt động "
            "ẩn danh\" theo đúng nghĩa của nó.\n"
        )
    else:
        dong.append(
            "**Không xác nhận lại được** hiện tượng trùng lặp byte-for-byte "
            "ở lần chạy xác minh này — xem bảng trên để biết chi tiết từng "
            "trường hợp; cần diễn giải lại kết luận bên dưới cho phù hợp với "
            "dữ liệu thực tế thay vì giữ nguyên kết luận cũ.\n"
        )

    dong.append(
        "**Đối chiếu tài liệu công khai (không dùng thông tin xác thực):** "
        "APIDOCS.md chính thức của Pollinations "
        "([raw.githubusercontent.com/pollinations/pollinations/master/APIDOCS.md]"
        "(https://raw.githubusercontent.com/pollinations/pollinations/master/APIDOCS.md)) "
        "ghi tham số `model` có giá trị mặc định là `flux` — đây là giá trị "
        "MẶC ĐỊNH CỦA THAM SỐ theo tài liệu, KHÔNG phải bằng chứng model nền "
        "thực sự chạy khi ẩn danh (vì cả tên model bịa đặt cũng cho ra ảnh "
        "giống hệt). Tài liệu cũng mô tả hệ thống bậc truy cập: Anonymous → "
        "\"Basic models\", Seed (đăng ký miễn phí) → \"Standard models\", "
        "Flower (trả phí) → \"Advanced models\", Nectar (doanh nghiệp) → "
        "\"All models\" — khớp với việc kontext/nanobanana/seedream bị chặn "
        "kèm thông điệp yêu cầu `enter.pollinations.ai`. Tài liệu KHÔNG mô tả "
        "rõ hành vi chuẩn hoá/bỏ qua tham số model quan sát được ở trên — đây "
        "là phát hiện THỰC NGHIỆM, không phải điều tài liệu xác nhận.\n"
    )

    dong.append("### Kết luận theo đúng yêu cầu\n")
    dong.append(
        "**CONFIRMED:**\n"
        "- Sinh ảnh ẩn danh (không key) qua endpoint legacy hoạt động — trả "
        "về HTTP 200 + ảnh hợp lệ khi gọi endpoint này mà không có bất kỳ "
        "thông tin xác thực nào.\n\n"
        "**NOT CONFIRMED:**\n"
        "- flux hoạt động độc lập/ẩn danh với đúng đặc tính riêng của model này.\n"
        "- zimage hoạt động độc lập/ẩn danh với đúng đặc tính riêng của model này.\n"
        "- gpt-image-2 hoạt động độc lập/ẩn danh với đúng đặc tính riêng của model này.\n"
        "- Bất kỳ model nào khác được đặt tên (dreamshaper, turbo, gptimage, "
        "nanobanana-pro) hoạt động độc lập/ẩn danh với đúng đặc tính riêng "
        "của nó — tham số `model=` bị bỏ qua/chuẩn hoá ẩn danh nên không thể "
        "quy kết ảnh trả về là do model được yêu cầu tạo ra.\n\n"
        "**UNIFIED API:**\n"
        "- Sinh ảnh không key qua `gen.pollinations.ai` (endpoint hợp nhất) "
        "trả về HTTP 401 — yêu cầu xác thực.\n"
    )

    duong_dan.write_text(noi_dung + "\n".join(dong), encoding="utf-8")


def main() -> None:
    if "--final-check-only" in sys.argv:
        chay_xac_minh_cuoi_va_cap_nhat_bao_cao()
        return

    client = _client()
    tat_ca: List[KetQua] = []

    print("=== VONG 1: moi model, endpoint LEGACY, KHONG API key ===")
    vong1 = []
    for model in MODELS:
        kq = _goi_legacy(client, model, lan_thu=1)
        vong1.append(kq)
        tat_ca.append(kq)
        _in_dong(kq, model)

    print()
    print("=== Doi chieu: endpoint UNIFIED (gen.pollinations.ai), KHONG API key ===")
    kq_unified = _goi_unified(client, model="flux")
    tat_ca.append(kq_unified)
    _in_dong(kq_unified, "flux (unified)")

    thanh_cong_models = [kq.model for kq in vong1 if kq.thanh_cong]

    print()
    print(
        f"=== VONG 2: {len(thanh_cong_models)} model thanh cong o vong 1, "
        f"thu lai {SO_LAN_THU_LAI} lan nua moi model (cung prompt) ==="
    )
    vong2 = []
    for model in thanh_cong_models:
        for i in range(SO_LAN_THU_LAI):
            kq = _goi_legacy(client, model, lan_thu=i + 2)
            vong2.append(kq)
            tat_ca.append(kq)
            _in_dong(kq, model)

    client.close()

    _ghi_bao_cao(vong1, kq_unified, vong2, thanh_cong_models)


def _phan_loai(model: str, lan_goi: List[KetQua]) -> str:
    """4 nhom theo yeu cau: (1) confirmed no-key working (2) intermittent/
    capacity limited (3) authentication/payment required (4) unsupported."""
    if not lan_goi:
        return "khong_du_lieu"
    trang_thai_list = [kq.http_status for kq in lan_goi]
    so_thanh_cong = sum(1 for kq in lan_goi if kq.thanh_cong)
    if any(s in (401, 402, 403) for s in trang_thai_list if s is not None):
        return "yeu_cau_xac_thuc_thanh_toan"
    # Pollinations tra ve HTTP 500 kem thong diep "chi co tren
    # enter.pollinations.ai" cho cac model tra phi — day la mot dang
    # xac thuc/thanh toan duoc nguy trang thanh loi server, khong phai
    # "khong ho tro".
    if any(
        "enter.pollinations.ai" in kq.loi for kq in lan_goi
    ):
        return "yeu_cau_xac_thuc_thanh_toan"
    if any(s in (400, 404, 422) for s in trang_thai_list if s is not None) and so_thanh_cong == 0:
        return "khong_ho_tro"
    if so_thanh_cong == len(lan_goi):
        return "xac_nhan_hoat_dong_khong_key"
    if so_thanh_cong > 0:
        return "khong_on_dinh_gioi_han_cong_suat"
    return "khong_ho_tro"


def _ghi_bao_cao(
    vong1: List[KetQua],
    kq_unified: KetQua,
    vong2: List[KetQua],
    thanh_cong_models: List[str],
) -> None:
    goc = Path(__file__).resolve().parent.parent
    thu_muc = goc / "docs" / "reports"
    thu_muc.mkdir(parents=True, exist_ok=True)

    raw = {
        "prompt": PROMPT,
        "vong1_legacy": [asdict(kq) for kq in vong1],
        "doi_chieu_unified": asdict(kq_unified),
        "vong2_legacy_lap_lai": [asdict(kq) for kq in vong2],
    }
    (thu_muc / "pollinations-anonymous-probe-raw.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    nhom: dict[str, List[str]] = {
        "xac_nhan_hoat_dong_khong_key": [],
        "khong_on_dinh_gioi_han_cong_suat": [],
        "yeu_cau_xac_thuc_thanh_toan": [],
        "khong_ho_tro": [],
    }
    chi_tiet_model: dict[str, dict] = {}
    for model in MODELS:
        lan_goi = [kq for kq in vong1 if kq.model == model] + [
            kq for kq in vong2 if kq.model == model
        ]
        loai = _phan_loai(model, lan_goi)
        nhom.setdefault(loai, []).append(model)
        so_thanh_cong = sum(1 for kq in lan_goi if kq.thanh_cong)
        do_tre_tb = (
            sum(kq.do_tre_giay for kq in lan_goi) / len(lan_goi) if lan_goi else 0.0
        )
        chi_tiet_model[model] = {
            "so_lan_thu": len(lan_goi),
            "so_lan_thanh_cong": so_thanh_cong,
            "ty_le_thanh_cong": f"{so_thanh_cong}/{len(lan_goi)}",
            "do_tre_trung_binh_giay": round(do_tre_tb, 2),
            "http_status_vong1": vong1_status_cua(model, vong1),
            "loi_vong1": loi_vong1_cua(model, vong1),
        }

    dong_bang = {
        "xac_nhan_hoat_dong_khong_key": "1. Xác nhận hoạt động KHÔNG cần key",
        "khong_on_dinh_gioi_han_cong_suat": "2. Không ổn định / giới hạn công suất",
        "yeu_cau_xac_thuc_thanh_toan": "3. Yêu cầu xác thực / thanh toán",
        "khong_ho_tro": "4. Model không được hỗ trợ",
    }

    dong = []
    dong.append("# Dò tìm model ảnh Pollinations hoạt động không cần API key\n")
    dong.append(f"Prompt trung tính dùng xuyên suốt: `{PROMPT}`\n")
    dong.append(
        "Tiêu chí thành công: HTTP 200 VÀ Content-Type bắt đầu bằng `image/` "
        "VÀ thân response không rỗng.\n"
    )
    dong.append(
        f"Đối chiếu endpoint UNIFIED (`gen.pollinations.ai`, không key): "
        f"status={kq_unified.http_status}, content-type={kq_unified.content_type!r}, "
        f"kết quả: {'OK' if kq_unified.thanh_cong else 'THẤT BẠI — ' + kq_unified.loi}\n"
    )

    # Phat hien noi dung TRUNG LAP giua cac model "thanh cong" — khong duoc
    # phep che giau phat hien nay du no lam yeu di y nghia cua nhom 1.
    hash_theo_model = {
        kq.model: kq.sha256_16 for kq in vong1 if kq.thanh_cong and kq.sha256_16
    }
    cac_hash_khac_nhau = set(hash_theo_model.values())
    if hash_theo_model and len(cac_hash_khac_nhau) == 1 and len(hash_theo_model) > 1:
        dong.append(
            "## ⚠️ Phát hiện quan trọng — KHÔNG được ẩn giấu\n\n"
            f"Cả **{len(hash_theo_model)} model** trả về HTTP 200 + ảnh hợp lệ "
            f"({', '.join(sorted(hash_theo_model))}) đều cho ra **CÙNG MỘT ảnh "
            f"byte-for-byte giống hệt nhau** (SHA256 rút gọn: "
            f"`{next(iter(cac_hash_khac_nhau))}`), dùng cùng prompt + seed.\n\n"
            "Diễn giải: endpoint legacy ẩn danh (không key) dường như **bỏ qua "
            "tham số `model=`** và luôn phục vụ MỘT model mặc định/dự phòng cố "
            "định, bất kể tên model yêu cầu là gì. Theo tiêu chí thành công "
            "nghiêm ngặt đã định (HTTP 200 + `image/*` + không rỗng), các model "
            "này VẪN được tính là \"thành công\" — nhưng điều đó **không chứng "
            "minh model cụ thể đó thực sự chạy** ở chế độ ẩn danh. Cần xác minh "
            "thêm (có key hoặc qua tài liệu chính thức) trước khi kết luận các "
            "model này thực sự khả dụng ẩn danh với đúng đặc tính riêng của "
            "chúng.\n"
        )
    elif hash_theo_model and len(cac_hash_khac_nhau) > 1:
        dong.append(
            f"Đối chiếu nội dung: {len(cac_hash_khac_nhau)} ảnh khác nhau trong "
            f"số {len(hash_theo_model)} model thành công — không phát hiện "
            "trùng lặp toàn phần.\n"
        )

    dong.append("## Bảng tổng hợp theo 4 nhóm\n")
    for khoa, tieu_de in dong_bang.items():
        dong.append(f"### {tieu_de}\n")
        models_nhom = nhom.get(khoa, [])
        if not models_nhom:
            dong.append("_(không có model nào)_\n")
            continue
        dong.append("| Model | Tỷ lệ thành công | Độ trễ TB (s) | HTTP vòng 1 | Ghi chú lỗi (nếu có) |")
        dong.append("|---|---|---|---|---|")
        for model in models_nhom:
            ct = chi_tiet_model[model]
            dong.append(
                f"| {model} | {ct['ty_le_thanh_cong']} | {ct['do_tre_trung_binh_giay']} "
                f"| {ct['http_status_vong1']} | {ct['loi_vong1']} |"
            )
        dong.append("")

    dong.append("## Chi tiết vòng 1 (tất cả 10 model, legacy endpoint)\n")
    dong.append("| Model | HTTP | Content-Type | Size (byte) | SHA256 (16 ký tự) | Độ trễ (s) | Kết quả |")
    dong.append("|---|---|---|---|---|---|---|")
    for kq in vong1:
        dong.append(
            f"| {kq.model} | {kq.http_status} | {kq.content_type or '—'} | "
            f"{kq.byte_size if kq.byte_size is not None else '—'} | "
            f"{kq.sha256_16 or '—'} | "
            f"{kq.do_tre_giay:.2f} | {'OK' if kq.thanh_cong else 'Thất bại'} |"
        )
    dong.append("")

    if thanh_cong_models:
        dong.append(f"## Vòng 2 — lặp lại {SO_LAN_THU_LAI} lần cho {len(thanh_cong_models)} model thành công ở vòng 1\n")
        dong.append("| Model | Lần | HTTP | Size (byte) | Độ trễ (s) | Kết quả |")
        dong.append("|---|---|---|---|---|---|")
        for kq in vong2:
            dong.append(
                f"| {kq.model} | {kq.lan_thu} | {kq.http_status} | "
                f"{kq.byte_size if kq.byte_size is not None else '—'} | "
                f"{kq.do_tre_giay:.2f} | {'OK' if kq.thanh_cong else 'Thất bại'} |"
            )
        dong.append("")
    else:
        dong.append("## Vòng 2\n\nKhông có model nào thành công ở vòng 1 — bỏ qua vòng 2.\n")

    (thu_muc / "pollinations-anonymous-probe-summary.md").write_text(
        "\n".join(dong), encoding="utf-8"
    )

    print()
    print(f"Đã ghi báo cáo: {thu_muc / 'pollinations-anonymous-probe-summary.md'}")
    print(f"Dữ liệu thô: {thu_muc / 'pollinations-anonymous-probe-raw.json'}")


def vong1_status_cua(model: str, vong1: List[KetQua]) -> str:
    for kq in vong1:
        if kq.model == model:
            return str(kq.http_status)
    return "—"


def loi_vong1_cua(model: str, vong1: List[KetQua]) -> str:
    for kq in vong1:
        if kq.model == model:
            return kq.loi or "—"
    return "—"


if __name__ == "__main__":
    main()
