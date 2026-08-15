#!/usr/bin/env python3
"""
So sánh CÙNG một số đoạn fanfic Trung -> Việt qua Cerebras (gpt-oss-120b) và
Groq (qwen/qwen3.6-27b) — chiến lược sản xuất tạm thời
(`feature/cerebras-groq-translation`).

KHÔNG benchmark `zai-glm-4.7`: tài liệu Cerebras (kiểm tra 2026-08-15) ghi
model này là Preview và sẽ ngừng hỗ trợ 2026-08-17 — đã bị gỡ khỏi
`CEREBRAS_MODEL_PROFILES`, không còn nằm trong định tuyến sản xuất/BYOK.

    python scripts/benchmark_cerebras_groq_translation.py

Đọc `CEREBRAS_API_KEY`/`GROQ_API_KEY` từ `server/.env` (qua
`server.config.load_env_file`) — model NÀO thiếu key sẽ được BỎ QUA rõ ràng
("SKIPPED — thiếu ..."), KHÔNG bịa kết quả. Không tạo job/project/store nào —
gọi thẳng `CerebrasProvider`/`GroqProvider`, độc lập với web/API.

QUAN TRỌNG (sau khi thêm kiểm tra tính vẹn): script này gọi CÙNG cơ chế
tích vẹn + sửa lỗi mà `TranslationService._goi_dich_mot_doan` dùng thật
(`translation_integrity.kiem_tra_tinh_ven` + `CHI_DAN_SUA_LOI_CEREBRAS`) —
KHÔNG chỉ gọi provider thô. Nếu không làm vậy, benchmark sẽ chỉ tái hiện lại
lỗi gốc (còn sót tiếng Trung) mà không bao giờ chứng minh được cơ chế sửa
lỗi mới có tác dụng thật.

KHÔNG tự động đổi thứ tự provider chỉ vì độ trễ — script này CHỈ in số liệu
(độ trễ, số token, nội dung dịch) để NGƯỜI đọc và quyết định; không có logic
"model nhanh nhất thắng" nào ở đây.

Ghi kết quả thô (JSON) VÀ bản tóm tắt đọc được (Markdown) vào
`docs/reports/`, tách biệt — JSON để đối chiếu lại sau, Markdown để đọc nhanh.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

for _luong in (sys.stdout, sys.stderr):
    if hasattr(_luong, "reconfigure"):
        _luong.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.config import load_env_file  # noqa: E402

load_env_file()

import os  # noqa: E402

from server.translation_integrity import kiem_tra_tinh_ven, tom_tat_van_de  # noqa: E402
from server.translation_model_profiles import (  # noqa: E402
    CEREBRAS_MODEL_PROFILES,
    GROQ_MODEL_PROFILES,
)
from server.translation_provider_registry import (  # noqa: E402
    CerebrasProvider,
    GroqProvider,
    TranslationProviderError,
)
from server.translation_providers import TranslationContext  # noqa: E402
from server.translation_service import CHI_DAN_SUA_LOI_CEREBRAS  # noqa: E402

#: Vài đoạn fanfic tiên hiệp/huyền huyễn NGẮN, KHÔNG bản quyền (tự viết cho
#: mục đích kiểm thử) — đủ đa dạng để lộ ra khác biệt về xưng hô, tên riêng,
#: hội thoại, và đoạn văn tường thuật thuần tuý.
#:
#: `nhac_lai_duoc_lao` THÊM sau khi phát hiện benchmark thật dịch "药老"
#: không nhất quán giữa hai lần gọi ("Dược Lão" vs "Yêu Lão") — đoạn này
#: nhắc lại CÙNG nhân vật để chứng minh glossary tường minh giữ nhất quán
#: XUYÊN SUỐT nhiều lần gọi (mô phỏng nhiều chunk của cùng một job).
DOAN_MAU = [
    ("hoi_thoai_xung_ho", "萧炎看向药老，微微皱眉，低声道：\"师父，这件事你早就知道了，对不对？\""),
    ("tuong_thuat_dia_danh", "这一日，云澈山下起了大雾，山道两旁的枯树在风中发出低沉的呜咽声。"),
    ("he_thong_thuat_ngu", "叮！恭喜宿主突破至炼气期九层，获得功法《焚天诀》一份，请及时查看。"),
    ("doi_thoai_nhieu_nhan_vat",
     "\"你到底是谁？\"她厉声问道。\n\"我？\"他冷笑一声，\"你很快就会知道了。\""),
    ("nhac_lai_duoc_lao", "药老转过身，对萧炎说了几句话，随后又望向远方的天际。"),
]

#: Novel Bible / glossary GIẢ ĐỊNH đã chốt cho dự án này (thực tế sẽ do
#: người dùng cấu hình qua `TranslationService.add_glossary_entry` — script
#: này gọi thẳng provider, không qua project/store, nên khai báo trực tiếp
#: ở đây để mô phỏng ĐÚNG những gì một dự án thật đã có sẵn).
GLOSSARY_DU_AN = {"药老": "Dược Lão"}

CONTEXT = TranslationContext(
    vai_tro="translator", quality_mode="van_hoc",
    genre="tien_hiep", naming_mode="han_viet", glossary=GLOSSARY_DU_AN)


@dataclass
class KetQua:
    model_key: str
    display_name: str
    doan_key: str
    #: "ok" (dat tinh ven) | "loi_tinh_ven" (API thanh cong nhung van khong
    #: dat tinh ven sau khi da thu moi cach) | "loi" (API that bai) |
    #: "skipped" (thieu key).
    trang_thai: str
    do_tre_giay: Optional[float] = None
    #: Ket qua CUOI CUNG (sau sua loi neu co) — day la thu duoc dua vao
    #: file/hien thi chinh.
    dau_ra: str = ""
    loi: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    #: True neu lan dau KHONG dat tinh ven va da phai goi sua loi (repair
    #: retry) — cho biet co che sua loi co THAT SU can dung hay khong.
    da_sua_loi: bool = False
    #: Ban dich THO lan dau (CHI dien khi `da_sua_loi=True`) — giu lai de
    #: doi chieu truoc/sau sua loi.
    dau_ra_lan_dau: str = ""
    #: Mo ta van de tinh ven phat hien o lan dau (rong = khong co van de).
    van_de_lan_dau: str = ""


def _thu_cerebras(profile_key: str, api_key: str) -> list[KetQua]:
    """
    Goi Cerebras qua CUNG co che tich ven + sua loi that su dung trong san
    xuat (`TranslationService._sua_loi_cerebras_roi_du_phong_groq`, don gian
    hoa cho MOT provider — khong co Groq du phong o day, script nay muon
    thay RIENG kha nang tu sua cua Cerebras).
    """
    profile = CEREBRAS_MODEL_PROFILES[profile_key]
    if not api_key:
        return [KetQua(model_key=f"cerebras_{profile_key}",
                       display_name=f"Cerebras · {profile.display_name}",
                       doan_key=dk, trang_thai="skipped",
                       loi="thiếu CEREBRAS_API_KEY")
                for dk, _ in DOAN_MAU]
    provider = CerebrasProvider(api_key=api_key, profile=profile)
    ra = []
    for dk, van_ban in DOAN_MAU:
        bat_dau = time.monotonic()
        ten = f"cerebras_{profile_key}"
        hien_thi = f"Cerebras · {profile.display_name}"
        try:
            dau_ra_1 = provider.translate_segment(van_ban, context=CONTEXT)
        except TranslationProviderError as exc:
            ra.append(KetQua(model_key=ten, display_name=hien_thi, doan_key=dk,
                             trang_thai="loi", do_tre_giay=time.monotonic() - bat_dau,
                             loi=str(exc)[:300]))
            continue

        van_de_1 = kiem_tra_tinh_ven(van_ban, dau_ra_1, glossary=GLOSSARY_DU_AN)
        da_sua = False
        dau_ra_cuoi = dau_ra_1
        loi_sua = ""
        if van_de_1:
            ctx_sua = replace(CONTEXT, chi_dan_sua_loi=CHI_DAN_SUA_LOI_CEREBRAS)
            try:
                dau_ra_2 = provider.translate_segment(van_ban, context=ctx_sua)
                da_sua = True
                dau_ra_cuoi = dau_ra_2
            except TranslationProviderError as exc:
                loi_sua = f" (lần sửa lỗi cũng thất bại: {str(exc)[:200]})"

        van_de_cuoi = kiem_tra_tinh_ven(van_ban, dau_ra_cuoi, glossary=GLOSSARY_DU_AN)
        ra.append(KetQua(
            model_key=ten, display_name=hien_thi, doan_key=dk,
            trang_thai="ok" if not van_de_cuoi else "loi_tinh_ven",
            do_tre_giay=time.monotonic() - bat_dau,
            dau_ra=dau_ra_cuoi,
            loi=(tom_tat_van_de(van_de_cuoi) + loi_sua) if van_de_cuoi else "",
            input_tokens=(provider.last_usage or {}).get("input_tokens"),
            output_tokens=(provider.last_usage or {}).get("output_tokens"),
            da_sua_loi=da_sua,
            dau_ra_lan_dau=dau_ra_1 if da_sua else "",
            van_de_lan_dau=tom_tat_van_de(van_de_1) if van_de_1 else ""))
    return ra


def _thu_groq(profile_key: str, api_key: str) -> list[KetQua]:
    """Groq KHONG co buoc sua loi rieng (dung theo so do yeu cau goc — chi
    Cerebras moi "sua loi", Groq la du phong cuoi) — CHI kiem tra tinh ven
    de BAO CAO (khong remediation nao duoc thuc hien tren ket qua cua no)."""
    profile = GROQ_MODEL_PROFILES[profile_key]
    if not api_key:
        return [KetQua(model_key=f"groq_{profile_key}",
                       display_name=f"Groq · {profile.display_name}",
                       doan_key=dk, trang_thai="skipped",
                       loi="thiếu GROQ_API_KEY")
                for dk, _ in DOAN_MAU]
    provider = GroqProvider(api_key=api_key, profile=profile)
    ra = []
    for dk, van_ban in DOAN_MAU:
        bat_dau = time.monotonic()
        try:
            dau_ra = provider.translate_segment(van_ban, context=CONTEXT)
            van_de = kiem_tra_tinh_ven(van_ban, dau_ra, glossary=GLOSSARY_DU_AN)
            ra.append(KetQua(
                model_key=f"groq_{profile_key}",
                display_name=f"Groq · {profile.display_name}", doan_key=dk,
                trang_thai="ok" if not van_de else "loi_tinh_ven",
                do_tre_giay=time.monotonic() - bat_dau,
                dau_ra=dau_ra, loi=tom_tat_van_de(van_de) if van_de else "",
                input_tokens=(provider.last_usage or {}).get("input_tokens"),
                output_tokens=(provider.last_usage or {}).get("output_tokens")))
        except TranslationProviderError as exc:
            ra.append(KetQua(
                model_key=f"groq_{profile_key}",
                display_name=f"Groq · {profile.display_name}", doan_key=dk,
                trang_thai="loi", do_tre_giay=time.monotonic() - bat_dau,
                loi=str(exc)[:300]))
    return ra


def main() -> None:
    cerebras_key = os.environ.get("CEREBRAS_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    print(f"CEREBRAS_API_KEY present: {bool(cerebras_key)}")
    print(f"GROQ_API_KEY present: {bool(groq_key)}")
    print()

    tat_ca: list[KetQua] = []
    tat_ca += _thu_cerebras("gpt_oss_120b", cerebras_key)
    tat_ca += _thu_groq("qwen", groq_key)

    for kq in tat_ca:
        print(f"[{kq.trang_thai.upper():13}] {kq.display_name:24} · {kq.doan_key}")
        if kq.trang_thai in ("ok", "loi_tinh_ven"):
            print(f"          độ trễ={kq.do_tre_giay:.2f}s "
                 f"tokens(in/out)={kq.input_tokens}/{kq.output_tokens}")
            if kq.da_sua_loi:
                print(f"          [LẦN ĐẦU, KHÔNG ĐẠT: {kq.van_de_lan_dau}]")
                print(f"          -> {kq.dau_ra_lan_dau}")
                print("          [SAU KHI SỬA LỖI]")
            print(f"          -> {kq.dau_ra}")
            if kq.trang_thai == "loi_tinh_ven":
                print(f"          VẪN KHÔNG ĐẠT TÍNH VẸN: {kq.loi}")
        elif kq.trang_thai == "loi":
            print(f"          lỗi: {kq.loi}")
        else:
            print(f"          {kq.loi}")
        print()

    thu_muc = Path(__file__).resolve().parent.parent / "docs" / "reports"
    thu_muc.mkdir(parents=True, exist_ok=True)
    json_path = thu_muc / "cerebras-groq-benchmark-raw.json"
    md_path = thu_muc / "cerebras-groq-benchmark-summary.md"

    json_path.write_text(json.dumps(
        [kq.__dict__ for kq in tat_ca], ensure_ascii=False, indent=2),
        encoding="utf-8")

    cerebras_ket_qua = [kq for kq in tat_ca if kq.model_key.startswith("cerebras")]
    cerebras_dat_het = (bool(cerebras_ket_qua)
                        and all(kq.trang_thai == "ok" for kq in cerebras_ket_qua))

    dong_md = ["# Benchmark Cerebras + Groq — dịch fanfic Trung -> Việt", "",
              f"CEREBRAS_API_KEY: {'có' if cerebras_key else 'THIẾU — model Cerebras bị bỏ qua'}",
              f"GROQ_API_KEY: {'có' if groq_key else 'THIẾU — model Groq bị bỏ qua'}", ""]
    if cerebras_key:
        dong_md.append(
            "**Tiêu chí thành công** (Cerebras cho ra bản dịch tiếng Việt "
            "đầy đủ cho cả 4 mẫu sau khi qua cơ chế tích vẹn/sửa lỗi, "
            "không còn sót tiếng Trung): "
            + ("ĐẠT ✓" if cerebras_dat_het else "CHƯA ĐẠT ✗ — xem chi tiết bên dưới"))
        dong_md.append("")

    dong_md += [
        "| Model | Đoạn | Trạng thái | Đã sửa lỗi? | Độ trễ (s) | Token in/out |",
        "|---|---|---|---|---|---|"]
    for kq in tat_ca:
        dong_md.append(
            f"| {kq.display_name} | {kq.doan_key} | {kq.trang_thai} | "
            f"{'có' if kq.da_sua_loi else '—'} | "
            f"{f'{kq.do_tre_giay:.2f}' if kq.do_tre_giay is not None else '—'} | "
            f"{kq.input_tokens}/{kq.output_tokens} |")
    dong_md.append("")
    dong_md.append("## Nội dung dịch (để đối chiếu chất lượng thủ công)")
    for kq in tat_ca:
        if kq.trang_thai in ("ok", "loi_tinh_ven"):
            dong_md.append(f"\n**{kq.display_name} · {kq.doan_key}**")
            if kq.da_sua_loi:
                dong_md.append(
                    f"\n_Lần đầu (KHÔNG đạt: {kq.van_de_lan_dau}):_ {kq.dau_ra_lan_dau}")
                dong_md.append("\n_Sau khi sửa lỗi:_")
            dong_md.append(f"\n{kq.dau_ra}")
            if kq.trang_thai == "loi_tinh_ven":
                dong_md.append(f"\n_⚠ Vẫn không đạt tính vẹn: {kq.loi}_")
    md_path.write_text("\n".join(dong_md), encoding="utf-8")

    print(f"Đã ghi: {json_path}")
    print(f"Đã ghi: {md_path}")


if __name__ == "__main__":
    main()
