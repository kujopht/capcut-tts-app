#!/usr/bin/env python3
"""
So sánh Pollinations (deepseek, deepseek-pro) với Groq hiện có trên CÙNG một
tập đoạn văn fanfic mẫu — feature/pollinations-translation.

    python scripts/benchmark_pollinations_translation.py
    python scripts/benchmark_pollinations_translation.py --groq-model gpt_oss_120b
    python scripts/benchmark_pollinations_translation.py --repeat 3 --json out.json

Đọc `POLLINATIONS_API_KEY`/`GROQ_API_KEY` từ biến môi trường. THIẾU credential
nào thì BỎ QUA cột đó (in rõ "bỏ qua — thiếu <BIẾN>"), không làm sập script —
script này PHẢI chạy được để so sánh MỘT PHẦN (ví dụ chỉ có Groq) mà không cần
đủ cả hai bên.

KHÔNG tự động kết luận "Pollinations tốt hơn" từ tên model — script này CHỈ đo
độ trễ và in NGUYÊN VĂN bản dịch của cả ba model để người đọc tự so sánh:
chất lượng dịch, nhất quán tên riêng, nhất quán xưng hô, tự nhiên của hội
thoại. Xem hướng dẫn đọc kết quả ở cuối output.

Không import `server.main` (tránh nạp FastAPI/toàn bộ app chỉ để đo một hàm) —
chỉ dùng `server.translation_provider_registry`/`server.translation_providers`
trực tiếp, độc lập với web server đang chạy hay không.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _luong in (sys.stdout, sys.stderr):
    if hasattr(_luong, "reconfigure"):
        _luong.reconfigure(encoding="utf-8", errors="replace")

from server.translation_model_profiles import GROQ_MODEL_PROFILES  # noqa: E402
from server.translation_provider_registry import (  # noqa: E402
    GroqProvider,
    PollinationsProvider,
)
from server.translation_providers import (  # noqa: E402
    TranslationContext,
    TranslationProviderError,
)

#: Ba đoạn văn MẪU, đại diện cho ba tình huống dịch fanfic khác nhau — chọn
#: có CHỦ ĐÍCH để lộ ra đúng những điều yêu cầu gốc quan tâm:
#:   1. Hội thoại + xưng hô thay đổi theo người nói (nam/nữ, vai vế).
#:   2. Miêu tả thuần tuý, không hội thoại — đo độ tự nhiên của văn phong.
#:   3. Ba nhân vật CÙNG xuất hiện, có kính xưng ("师兄"/"前辈") — đo nhất
#:      quán TÊN RIÊNG khi cùng một tên xuất hiện nhiều lần.
DOAN_MAU = [
    (
        "hoi_thoai_xung_ho",
        "萧炎看向药老，低声道：“师父，你说这药方当真有效？”\n"
        "药老捋了捋胡须，笑道：“为师行走多年，何时骗过你？”\n"
        "萧炎苦笑一声，没有再说话，只是将手中的药瓶握得更紧了。",
    ),
    (
        "mieu_ta_thuan_tuy",
        "夜色渐深，乌坦城的灯火一盏盏熄灭下去。远处的山峦在月光下勾勒出一道"
        "模糊的轮廓，山间的雾气缓缓流动，像是活物一般缠绕在树梢之间。城墙上的"
        "巡逻兵靴声回荡在寂静的街道中，偶尔传来几声犬吠，随即又归于平静。",
    ),
    (
        "ba_nhan_vat_kinh_xung",
        "“师兄，前辈找你。”云韵匆匆跑来，脸上带着几分焦急。\n"
        "萧炎皱了皱眉：“药老找我做什么？”\n"
        "“这我哪知道。”云韵白了他一眼，“药老前辈的脾气你又不是不知道，还不"
        "快去。”\n"
        "萧炎无奈地叹了口气，转身朝药老的院子走去。",
    ),
]


@dataclass
class KetQuaMoHinh:
    ten_model: str
    thanh_cong: bool
    do_tre_ms: List[int]
    ban_dich: List[str]
    loi: str = ""

    def do_tre_trung_vi(self) -> Optional[float]:
        return statistics.median(self.do_tre_ms) if self.do_tre_ms else None


def _dich_qua_nhieu_lan(provider, doan: List[str], repeat: int) -> KetQuaMoHinh:
    do_tre: List[int] = []
    ban_dich: List[str] = []
    ctx = TranslationContext(vai_tro="translator", quality_mode="nhanh",
                             genre="auto", naming_mode="auto")
    try:
        for text in doan:
            for _ in range(repeat):
                bat_dau = time.monotonic()
                ket_qua = provider.translate_segment(text, context=ctx)
                do_tre.append(round((time.monotonic() - bat_dau) * 1000))
            ban_dich.append(ket_qua)
        return KetQuaMoHinh(provider.name, True, do_tre, ban_dich)
    except TranslationProviderError as exc:
        return KetQuaMoHinh(provider.name, False, do_tre, ban_dich, str(exc))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repeat", type=int, default=1,
                    help="Số lần dịch LẶP LẠI mỗi đoạn (đo độ trễ ổn định hơn, "
                         "mặc định 1 — chỉ dịch một lần, không tốn thêm hạn mức).")
    ap.add_argument("--groq-model", default="qwen", choices=list(GROQ_MODEL_PROFILES),
                    help="Model Groq curated dùng để so sánh (mặc định 'qwen' — "
                         "model AUTO mặc định cho chế độ NHANH hiện tại).")
    ap.add_argument("--json", default="", help="Ghi kết quả thô (kèm bản dịch) "
                    "ra một tệp JSON, ngoài phần in ra màn hình.")
    args = ap.parse_args()

    pollinations_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()

    ket_qua_theo_model = {}

    if pollinations_key:
        for model_id, nhan in (("deepseek", "pollinations_deepseek"),
                               ("deepseek-pro", "pollinations_deepseek_pro")):
            provider = PollinationsProvider(api_key=pollinations_key, model=model_id)
            provider.name = nhan
            print(f"Đang chạy {nhan}...", file=sys.stderr)
            ket_qua_theo_model[nhan] = _dich_qua_nhieu_lan(
                provider, [d for _, d in DOAN_MAU], args.repeat)
    else:
        print("Bỏ qua Pollinations — thiếu POLLINATIONS_API_KEY.", file=sys.stderr)

    if groq_key:
        profile = GROQ_MODEL_PROFILES[args.groq_model]
        provider = GroqProvider(api_key=groq_key, profile=profile)
        nhan = f"groq_{args.groq_model}"
        provider.name = nhan
        print(f"Đang chạy {nhan}...", file=sys.stderr)
        ket_qua_theo_model[nhan] = _dich_qua_nhieu_lan(
            provider, [d for _, d in DOAN_MAU], args.repeat)
    else:
        print("Bỏ qua Groq — thiếu GROQ_API_KEY.", file=sys.stderr)

    if not ket_qua_theo_model:
        print("\nKhông có credential nào (POLLINATIONS_API_KEY/GROQ_API_KEY) — "
              "không có gì để so sánh. Đặt ít nhất một biến môi trường rồi "
              "chạy lại.", file=sys.stderr)
        return 1

    print("\n" + "=" * 78)
    print("ĐỘ TRỄ (median, mili-giây) — thấp hơn = nhanh hơn")
    print("=" * 78)
    for nhan, kq in ket_qua_theo_model.items():
        if not kq.thanh_cong:
            print(f"  {nhan:28s} THẤT BẠI: {kq.loi[:80]}")
            continue
        print(f"  {nhan:28s} {kq.do_tre_trung_vi():>8.0f} ms "
              f"(n={len(kq.do_tre_ms)})")

    print("\n" + "=" * 78)
    print("BẢN DỊCH — TỰ SO SÁNH chất lượng/tên riêng/xưng hô/hội thoại")
    print("(script KHÔNG tự chấm điểm chất lượng — chỉ đo được độ trễ/thành "
          "công một cách khách quan; chất lượng dịch cần người đọc tiếng "
          "Việt đánh giá trực tiếp trên văn bản dưới đây)")
    print("=" * 78)
    for i, (khoa, nguon) in enumerate(DOAN_MAU):
        print(f"\n--- Đoạn {i + 1}: {khoa} ---")
        print(f"[Nguồn] {nguon}")
        for nhan, kq in ket_qua_theo_model.items():
            if not kq.thanh_cong or i >= len(kq.ban_dich):
                continue
            print(f"[{nhan}] {kq.ban_dich[i]}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fp:
            json.dump({
                nhan: {
                    "thanh_cong": kq.thanh_cong, "loi": kq.loi,
                    "do_tre_ms": kq.do_tre_ms, "ban_dich": kq.ban_dich,
                }
                for nhan, kq in ket_qua_theo_model.items()
            }, fp, ensure_ascii=False, indent=2)
        print(f"\nĐã ghi kết quả thô vào {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
