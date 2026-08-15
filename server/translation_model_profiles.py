"""
Ho so model Groq + dinh tuyen theo vai tro — overnight Phase 3 (Part R).

XAC MINH TRUC TIEP voi tai lieu Groq hien hanh (console.groq.com/docs/reasoning,
doc lai 2026-08-14) TRUOC khi viet file nay — ca ba model ID va tham so
`reasoning_effort` deu con hieu luc, KHONG phai model da ngung ho tro:

    qwen/qwen3.6-27b     — reasoning_effort: "none" | "default" (mac dinh
                           "default"). CON ho tro `reasoning_format`
                           ("parsed"/"raw"/"hidden") — Qwen RIENG co ca hai.
    openai/gpt-oss-120b  — reasoning_effort: "low" | "medium" | "high".
    openai/gpt-oss-20b   — reasoning_effort: "low" | "medium" | "high".
                           HAI model GPT-OSS KHONG ho tro `reasoning_format`
                           (tai lieu ghi ro "not supported") — gui tham so do
                           cho chung la gui sai, khong phai vo hai.

Day chinh la ly do file nay ton tai thay vi mot `if model_id == ...` rai rac
trong `GroqProvider`: MOI model co dung MOT tap tham so cua RIENG no, va viec
"khong bao gio gui tham so cua model A cho model B" (yeu cau 3C) chi kiem
duoc de dang khi tham so nam trong DU LIEU (ho so), khong nam trong logic re
nhanh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ModelProfile:
    """
    Dac tinh RIENG cua MOT model — CHI chua tham so DA XAC MINH la model do
    ho tro. `extra_payload` duoc gop THANG vao than request chat completions
    (xem `GroqProvider.translate_segment`), khong co logic dieu kien nao
    khac o ben ngoai ho so nay.
    """

    key: str
    model_id: str
    display_name: str
    quality_hint: str
    extra_payload: Dict[str, object] = field(default_factory=dict)


#: BA model curated — MOT credential Groq (`GROQ_API_KEY`) duy nhat, nhieu
#: model (yeu cau 3B). Khoa (`key`) la phan sau cua provider_id
#: (`groq_{key}`, xem `translation_provider_registry.build_provider_registry`).
GROQ_MODEL_PROFILES: Dict[str, ModelProfile] = {
    "qwen": ModelProfile(
        key="qwen", model_id="qwen/qwen3.6-27b", display_name="Qwen 3.6 27B",
        quality_hint="nhanh, miễn phí",
        # 3A: dich thuong KHONG can Qwen tu suy luan hang nghin token truoc
        # khi tra loi — `reasoning_effort: "none"` tat hoan toan buoc do.
        # `reasoning_format: "hidden"` la RAO CHAN THEM: neu mot phien ban
        # model nao đó khong tuan thu `reasoning_effort=none` hoan toan, khoi
        # <think> (neu co) van bi an khoi noi dung tra ve thay vi lan ra
        # thanh "ban dich".
        extra_payload={
            "reasoning_effort": "none",
            "reasoning_format": "hidden",
            "max_completion_tokens": 4096,
        }),
    "gpt_oss_120b": ModelProfile(
        key="gpt_oss_120b", model_id="openai/gpt-oss-120b",
        display_name="GPT-OSS 120B", quality_hint="chất lượng cao, miễn phí",
        extra_payload={
            "reasoning_effort": "low",
            "max_completion_tokens": 4096,
        }),
    "gpt_oss_20b": ModelProfile(
        key="gpt_oss_20b", model_id="openai/gpt-oss-20b",
        display_name="GPT-OSS 20B", quality_hint="nhanh, miễn phí",
        extra_payload={
            "reasoning_effort": "low",
            "max_completion_tokens": 4096,
        }),
}

#: MOT model curated tren Cerebras — MOT credential (`CEREBRAS_API_KEY`)
#: (chien luoc san xuat tam thoi, xem `translation_provider_registry.
#: build_provider_registry`). KHONG co bang dinh tuyen theo vai-tro rieng nhu
#: `ROLE_ROUTING` cua Groq — hien CHI co MOT model nen khong can dinh tuyen
#: noi bo nao ca; du an nay giu cau truc dict (thay vi MOT hang so don) de
#: mo rong lai de dang neu Cerebras them model curated khac sau nay.
#:
#: LICH SU: ban dau co CA `zai-glm-4.7` (uu tien) VA `gpt-oss-120b` (du
#: phong noi bo). Da GO BO `zai-glm-4.7` (2026-08-15, cung ngay phat hien) vi
#: tai lieu Cerebras chinh thuc (inference-docs.cerebras.ai) ghi ro day la
#: model PREVIEW va SE NGUNG HO TRO 2026-08-17 — dua mot model sap ngung ho
#: tro lam LUA CHON MAC DINH cho dinh tuyen san xuat/BYOK la khong an toan,
#: du chi la "tam thoi". KHONG giu lai duoi dang code chet (khong provider
#: nao, khong lua chon frontend nao con tham chieu no) — neu Cerebras phat
#: hanh mot ban GLM on dinh sau nay, them lai nhu MOT muc moi o day, KHONG
#: phuc hoi nguyen ban ghi cu (kiem tra lai extra_payload tu tai lieu MOI).
#:
#: `extra_payload` THEO TAI LIEU CEREBRAS (inference-docs.cerebras.ai, doc
#: 2026-08-15) — CHUA kiem thu song voi API that (khac Groq, noi tham so da
#: duoc xac minh qua request that): `max_completion_tokens` la TEN THAT
#: (giong Groq, khac `max_tokens`); `reasoning_effort` nhan "low"/"medium"/
#: "high" cho `gpt-oss-120b` (mac dinh tai lieu la "medium" — o day chon
#: "low" giong lua chon DA XAC MINH cua Groq cho CUNG model nay, giam rui ro
#: model danh het ngan sach cho suy luan noi bo truoc khi tra loi). Can doi
#: lai neu benchmark thuc te (xem `scripts/benchmark_cerebras_groq_translation.py`)
#: cho thay sai.
CEREBRAS_MODEL_PROFILES: Dict[str, ModelProfile] = {
    "gpt_oss_120b": ModelProfile(
        key="gpt_oss_120b", model_id="gpt-oss-120b",
        display_name="GPT-OSS 120B", quality_hint="chất lượng cao",
        extra_payload={
            "reasoning_effort": "low",
            "max_completion_tokens": 4096,
        }),
}

#: Dinh tuyen vai tro TU DONG (yeu cau 3D) — (che_do, vai_tro) -> THU TU khoa
#: model Groq de thu. CHI liet ke to hop THAT SU xay ra
#: (`translation_service._VAI_TRO_THEO_CHE_DO`: NHANH chi co "translator";
#: CAN_BANG co "translator"/"qa"; VAN_HOC co ca ba) — khong bia them to hop
#: khong bao gio duoc goi toi.
#:
#: Model Groq KHONG nam trong danh sach nay (vi du mot model "legacy" tu
#: `GROQ_MODEL`) van duoc thu — noi vao CUOI nhom Groq, xem
#: `ProviderRegistry._thu_tu_theo_vai_tro`.
ROLE_ROUTING: Dict[Tuple[str, str], List[str]] = {
    ("nhanh", "translator"): ["qwen", "gpt_oss_20b", "gpt_oss_120b"],
    ("can_bang", "translator"): ["qwen", "gpt_oss_120b", "gpt_oss_20b"],
    ("can_bang", "qa"): ["gpt_oss_20b", "gpt_oss_120b", "qwen"],
    ("van_hoc", "translator"): ["qwen"],
    ("van_hoc", "editor"): ["gpt_oss_120b"],
    ("van_hoc", "qa"): ["gpt_oss_20b"],
}


def route_order(quality_mode: str, vai_tro: str) -> List[str]:
    """Thu tu khoa model Groq NEN thu cho (che_do, vai_tro) nay. Danh sach
    rong nghia la "khong dinh tuyen dac biet — giu nguyen thu tu cau hinh"
    (to hop la, chua tung xay ra trong (che_do, vai_tro) hop le nao)."""
    return list(ROLE_ROUTING.get((quality_mode, vai_tro), []))
