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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

for _luong in (sys.stdout, sys.stderr):
    if hasattr(_luong, "reconfigure"):
        _luong.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.config import load_env_file  # noqa: E402

load_env_file()

import os  # noqa: E402

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

#: Vài đoạn fanfic tiên hiệp/huyền huyễn NGẮN, KHÔNG bản quyền (tự viết cho
#: mục đích kiểm thử) — đủ đa dạng để lộ ra khác biệt về xưng hô, tên riêng,
#: hội thoại, và đoạn văn tường thuật thuần tuý.
DOAN_MAU = [
    ("hoi_thoai_xung_ho", "萧炎看向药老，微微皱眉，低声道：\"师父，这件事你早就知道了，对不对？\""),
    ("tuong_thuat_dia_danh", "这一日，云澈山下起了大雾，山道两旁的枯树在风中发出低沉的呜咽声。"),
    ("he_thong_thuat_ngu", "叮！恭喜宿主突破至炼气期九层，获得功法《焚天诀》一份，请及时查看。"),
    ("doi_thoai_nhieu_nhan_vat",
     "\"你到底是谁？\"她厉声问道。\n\"我？\"他冷笑一声，\"你很快就会知道了。\""),
]

CONTEXT = TranslationContext(
    vai_tro="translator", quality_mode="van_hoc",
    genre="tien_hiep", naming_mode="han_viet")


@dataclass
class KetQua:
    model_key: str
    display_name: str
    doan_key: str
    trang_thai: str  # "ok" | "loi" | "skipped"
    do_tre_giay: Optional[float] = None
    dau_ra: str = ""
    loi: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


def _thu_cerebras(profile_key: str, api_key: str) -> list[KetQua]:
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
        try:
            dau_ra = provider.translate_segment(van_ban, context=CONTEXT)
            ra.append(KetQua(
                model_key=f"cerebras_{profile_key}",
                display_name=f"Cerebras · {profile.display_name}", doan_key=dk,
                trang_thai="ok", do_tre_giay=time.monotonic() - bat_dau,
                dau_ra=dau_ra,
                input_tokens=(provider.last_usage or {}).get("input_tokens"),
                output_tokens=(provider.last_usage or {}).get("output_tokens")))
        except TranslationProviderError as exc:
            ra.append(KetQua(
                model_key=f"cerebras_{profile_key}",
                display_name=f"Cerebras · {profile.display_name}", doan_key=dk,
                trang_thai="loi", do_tre_giay=time.monotonic() - bat_dau,
                loi=str(exc)[:300]))
    return ra


def _thu_groq(profile_key: str, api_key: str) -> list[KetQua]:
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
            ra.append(KetQua(
                model_key=f"groq_{profile_key}",
                display_name=f"Groq · {profile.display_name}", doan_key=dk,
                trang_thai="ok", do_tre_giay=time.monotonic() - bat_dau,
                dau_ra=dau_ra,
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
        print(f"[{kq.trang_thai.upper():7}] {kq.display_name:24} · {kq.doan_key}")
        if kq.trang_thai == "ok":
            print(f"          độ trễ={kq.do_tre_giay:.2f}s "
                 f"tokens(in/out)={kq.input_tokens}/{kq.output_tokens}")
            print(f"          -> {kq.dau_ra}")
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

    dong_md = ["# Benchmark Cerebras + Groq — dịch fanfic Trung -> Việt", "",
              f"CEREBRAS_API_KEY: {'có' if cerebras_key else 'THIẾU — model Cerebras bị bỏ qua'}",
              f"GROQ_API_KEY: {'có' if groq_key else 'THIẾU — model Groq bị bỏ qua'}", "",
              "| Model | Đoạn | Trạng thái | Độ trễ (s) | Token in/out |",
              "|---|---|---|---|---|"]
    for kq in tat_ca:
        dong_md.append(
            f"| {kq.display_name} | {kq.doan_key} | {kq.trang_thai} | "
            f"{f'{kq.do_tre_giay:.2f}' if kq.do_tre_giay is not None else '—'} | "
            f"{kq.input_tokens}/{kq.output_tokens} |")
    dong_md.append("")
    dong_md.append("## Nội dung dịch (để đối chiếu chất lượng thủ công)")
    for kq in tat_ca:
        if kq.trang_thai == "ok":
            dong_md.append(f"\n**{kq.display_name} · {kq.doan_key}**\n\n{kq.dau_ra}")
    md_path.write_text("\n".join(dong_md), encoding="utf-8")

    print(f"Đã ghi: {json_path}")
    print(f"Đã ghi: {md_path}")


if __name__ == "__main__":
    main()
