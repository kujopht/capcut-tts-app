"""NĂNG LỰC RUNTIME — việc cần gì, chỗ chạy từ chối gì, và ai không hợp ai.

VÌ SAO GÓI NÀY TỒN TẠI — một khuyết tật đo được, `fanfic.t78ce-1`:

    Codex TỪ CHỐI những gói việc "mang hình dạng bảo mật". Phép nhận dạng ở
    `router_v3/pool/adapters.py` là một danh sách TỪ KHOÁ quét trên TOÀN BỘ
    gói việc đã render, và trong danh sách đó có chữ **"quyền"**.

    Lời nhắc công cụ TIÊU CHUẨN mà Router gắn vào MỌI việc có câu:

        "…quyền được khớp theo chuỗi chính xác…"

    Nên MỌI việc đều "mang hình dạng bảo mật", và mọi việc xếp vào Codex đều
    bị từ chối. Lý do từ chối (`codex_security_shaped_refusal`) lại nằm
    trong `engine.KHONG_THU_LAI`, nên việc CHẾT ở `BLOCKED` — dù chính thông
    báo từ chối hứa "định tuyến sang worker khác".

BA SỬA, ở đúng tầng trừu tượng, KHÔNG phải bằng cách thêm/bớt từ khoá:

1. **Năng lực của VIỆC được suy ra có cấu trúc**, và phần dựa vào chữ nghĩa
   chỉ đọc ĐÚNG phần người dùng viết (tiêu đề + mục tiêu gốc) — không đọc
   lời nhắc công cụ, phong bì quyền, hay khối bằng chứng do Router gắn vào.
   Đó là chỗ chữ "quyền" sinh ra, và nó không nói gì về việc cả.

2. **Từ vựng là CỤM TỪ chuyên môn**, không phải từ đơn chung chung.
   "phân quyền" là dấu hiệu; "quyền" một mình thì không.

3. **Chỗ chạy KHAI BÁO thứ nó từ chối**, lấy từ `security.
   security_refusal_family` có sẵn trong `fabric.json` (nơi điều này vốn đã
   được ghi), cộng khoá `refuses` tuỳ chọn cho từng runtime. Xếp chỗ dùng
   khai báo đó làm RÀO CỨNG, không phải một ưu tiên mềm.
"""
from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, Iterable, List, Sequence, Tuple

#: Năng lực ĐÓNG mà tầng này biết. Thêm một năng lực là một quyết định kiến
#: trúc, không phải một lần sửa chuỗi.
SECURITY_REVIEW = "security_review"
NANG_LUC_BIET: FrozenSet[str] = frozenset({SECURITY_REVIEW})

#: Từ vựng "hình dạng bảo mật" nằm ở MỘT chỗ duy nhất: `router_v3.policy`.
#: Hai danh sách song song là đúng cách để chúng lệch nhau trở lại — và lần
#: lệch trước đã làm mọi việc xếp vào Codex đều chết.
from scripts.router_v3.policy import (la_hinh_dang_bao_mat,  # noqa: E402
                                      phan_nguoi_viet)

#: Khoá trong hợp đồng mang văn bản DO NGƯỜI DÙNG/bộ phân rã viết. Mọi khoá
#: khác (mục tiêu đã gắn lời nhắc, phong bì, bằng chứng) KHÔNG được xét.
KHOA_NGUOI_VIET: Tuple[str, ...] = ("title", "tieu_de", "objective_goc",
                                    "muc_tieu_goc")


def van_ban_nguoi_viet(hd: Dict[str, Any]) -> str:
    """Phần văn bản DO NGƯỜI viết trong một hợp đồng.

    `objective` của hợp đồng đã bị Router nối thêm lời nhắc công cụ + phong
    bì quyền + (có thể) khối bằng chứng. Xét cả cục đó là lý do sinh ra
    dương tính giả, nên ở đây chỉ lấy phần đầu — trước dòng "CÔNG CỤ:" —
    cộng với tiêu đề.
    """
    phan: List[str] = []
    for k in KHOA_NGUOI_VIET:
        v = hd.get(k)
        if isinstance(v, str) and v.strip():
            phan.append(v)
    ob = hd.get("objective")
    if isinstance(ob, str) and ob.strip():
        # Cat o dau moc BOILERPLATE dau tien — ranh gioi tin cay giua
        # "nguoi viet" va "may gan". Danh sach moc o `router_v3.policy`.
        phan.append(phan_nguoi_viet(ob))
    return "\n".join(phan)


def nang_luc_viec(hd: Dict[str, Any]) -> FrozenSet[str]:
    """Năng lực mà MỘT việc đòi hỏi. Tất định, không LLM.

    Thứ tự: khai báo tường minh > kiểu việc > dấu hiệu chữ nghĩa (chỉ trên
    phần người viết). Khai báo tường minh thắng để bộ phân rã/người dùng có
    đường nói thẳng "đây là việc bảo mật" mà không phải trông vào máy đoán.
    """
    if not isinstance(hd, dict):
        return frozenset()
    ra = set()

    khai = hd.get("required_capabilities") or hd.get("nang_luc")
    if isinstance(khai, (list, tuple)):
        ra |= {str(x) for x in khai if str(x) in NANG_LUC_BIET}

    loai = str(hd.get("type") or hd.get("loai") or "")
    if SECURITY_REVIEW in loai:
        ra.add(SECURITY_REVIEW)

    if la_hinh_dang_bao_mat(van_ban_nguoi_viet(hd)):
        ra.add(SECURITY_REVIEW)
    return frozenset(ra)


def tu_choi_theo_runtime(fab, cau_hinh: Dict[str, Any] | None = None
                         ) -> Dict[str, FrozenSet[str]]:
    """`{runtime_id: {năng lực nó TỪ CHỐI}}`.

    Nguồn khai báo, theo thứ tự:

    * `runtimes[*].refuses` — khai riêng cho một chỗ chạy (tuỳ chọn);
    * `security.security_refusal_family` — họ nhà cung cấp từ chối review
      bảo mật. Khoá này ĐÃ CÓ SẴN trong `fabric.json` và vốn đã ghi đúng
      điều này, nên ở đây chỉ THI HÀNH nó chứ không phát minh thêm.
    """
    ra: Dict[str, FrozenSet[str]] = {}
    cfg = cau_hinh or {}
    ho = str((cfg.get("security") or {}).get("security_refusal_family") or "")
    khai_rieng: Dict[str, Sequence[str]] = {}
    for r in (cfg.get("runtimes") or []):
        if isinstance(r, dict) and r.get("refuses"):
            khai_rieng[str(r.get("runtime_id"))] = r["refuses"]

    runtimes = getattr(fab, "runtimes", {}) or {}
    for rid, r in runtimes.items():
        tu: set = set()
        if ho and str(getattr(r, "provider", "")).lower() == ho.lower():
            tu.add(SECURITY_REVIEW)
        for x in khai_rieng.get(str(rid), ()):
            if str(x) in NANG_LUC_BIET:
                tu.add(str(x))
        if tu:
            ra[str(rid)] = frozenset(tu)
    return ra


def runtime_khong_tuong_thich(fab, yeu_cau: Iterable[str],
                              cau_hinh: Dict[str, Any] | None = None
                              ) -> Tuple[str, ...]:
    """Runtime KHÔNG được nhận việc đòi `yeu_cau`. Rào CỨNG.

    Rỗng khi việc không đòi năng lực đặc biệt nào — trường hợp thường gặp,
    và nó phải không tốn gì.
    """
    can = {str(x) for x in (yeu_cau or ())}
    if not can:
        return ()
    tu = tu_choi_theo_runtime(fab, cau_hinh)
    return tuple(sorted(rid for rid, bo in tu.items() if bo & can))


def ly_do_khong_hop(rid: str, yeu_cau: Iterable[str]) -> str:
    return (f"runtime {rid} khai báo TỪ CHỐI năng lực "
            f"{sorted(str(x) for x in yeu_cau)} — không xếp việc vào đó")
