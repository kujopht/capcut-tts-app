"""
Kiem tra CUC BO (khong GPU, khong Beam, khong mang) xem da du dieu kien
de chay proof "Subaru + Anastasia high-fidelity" (mission "Character
LoRA + Controlled Two-Character Cover V1", Track F) hay chua.

VI SAO SCRIPT NAY TON TAI THAY VI MOT SCRIPT PROOF CHAY DUOC NGAY: proof
that can CA HAI dieu kien duoi day, va CA HAI DEU CHUA CO tinh den
2026-09-01 (xem docs/reports/character-lora-architecture-2026-09-01.md
muc 6.3 cho phan tich day du):

  1. It nhat 2 file LoRA THAT da train, kiem chung tuong thich
     animagine-xl-4.0 (`lora_compatible_base_model` phai khop CHINH XAC
     - xem beam_apps/cover_illustrious_logic.py::assert_lora_compatible_with_base_model
     va bang chung that "LoRA V3 khong dung duoc cho V4").
  2. Pipeline "staged regional inpainting" (ControlNet-pose + inpaint
     tung LoRA rieng) phai ton tai trong beam_apps/cover_illustrious_app.py
     - hien CHUA duoc xay dung (chi co txt2img + IP-Adapter reference
     conditioning).

Viet mot script "proof" gia vo san sang trong khi ca hai dieu kien tren
deu thieu se gay hieu lam ve muc do san sang that - thay vao do, script
nay bao cao RO RANG dang thieu gi, giong nguyen tac MORNING_MANUAL_ACTIONS
da dung xuyen suot cac mission truoc.

CACH DUNG:
    .venv\\Scripts\\python.exe scripts/beam_cover_lora_proof_readiness_check.py \\
        --primary-lora-path <duong dan file .safetensors cho Subaru> \\
        --secondary-lora-path <duong dan file .safetensors cho Anastasia> \\
        --primary-compatible-base-model cagliostrolab/animagine-xl-4.0 \\
        --secondary-compatible-base-model cagliostrolab/animagine-xl-4.0

Neu khong truyen tham so nao, script chi kiem tra dieu kien #2 (pipeline
staged-regional-inpainting) va bao cao dieu kien #1 la "khong the kiem
tra - chua cung cap duong dan LoRA".

Script nay KHONG tai file nao, KHONG goi mang, KHONG import torch/
diffusers/beam - chi doc file he thong va grep ma nguon.
"""
from __future__ import annotations

import argparse
import os
import sys

REQUIRED_BASE_MODEL = "cagliostrolab/animagine-xl-4.0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVER_APP_PATH = os.path.join(REPO_ROOT, "beam_apps", "cover_illustrious_app.py")

# Ten ham/marker MA CHUA TON TAI - se duoc them khi pipeline staged
# regional inpainting thuc su duoc xay dung. Cho toi luc do, kiem tra
# nay LUON bao cao "chua san sang" mot cach trung thuc.
STAGED_INPAINTING_MARKERS = (
    "staged_regional_inpaint",
    "StableDiffusionXLControlNetPipeline",
    "StableDiffusionXLInpaintPipeline",
)


def check_lora_asset(label: str, path: str, compatible_base_model: str) -> list:
    """Tra ve danh sach loi (chuoi) cho MOT LoRA duoc de xuat. Danh sach
    rong nghia la LoRA nay du dieu kien."""
    errors = []
    if not path:
        errors.append(f"{label}: chua cung cap --{label}-lora-path")
        return errors
    if not os.path.isfile(path):
        errors.append(f"{label}: khong tim thay file tai '{path}'")
    if not compatible_base_model:
        errors.append(
            f"{label}: thieu --{label}-compatible-base-model - "
            "BAT BUOC de tranh loi khong tuong thich cheo checkpoint "
            "(xem bang chung 'LoRA V3 khong dung duoc cho V4')"
        )
    elif compatible_base_model != REQUIRED_BASE_MODEL:
        errors.append(
            f"{label}: compatible_base_model='{compatible_base_model}' "
            f"khac voi checkpoint production hien tai '{REQUIRED_BASE_MODEL}' "
            "- KHONG duoc dung, se tao anh loi (giong lop loi ViT-bigG/ViT-H)"
        )
    return errors


def check_staged_inpainting_pipeline() -> list:
    """Tra ve danh sach loi neu pipeline staged-regional-inpainting CHUA
    ton tai trong beam_apps/cover_illustrious_app.py."""
    if not os.path.isfile(COVER_APP_PATH):
        return [f"khong tim thay {COVER_APP_PATH}"]
    with open(COVER_APP_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()
    missing = [marker for marker in STAGED_INPAINTING_MARKERS if marker not in source]
    if len(missing) == len(STAGED_INPAINTING_MARKERS):
        return [
            "pipeline 'staged regional inpainting' (ControlNet-pose + "
            "inpaint tung LoRA rieng) CHUA duoc xay dung trong "
            "beam_apps/cover_illustrious_app.py - day la mot pipeline "
            "MOI, khac voi txt2img+IP-Adapter hien co. Xem "
            "docs/reports/character-lora-architecture-2026-09-01.md muc 2."
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-lora-path", default="")
    parser.add_argument("--secondary-lora-path", default="")
    parser.add_argument("--primary-compatible-base-model", default="")
    parser.add_argument("--secondary-compatible-base-model", default="")
    args = parser.parse_args()

    all_errors = []

    if args.primary_lora_path or args.primary_compatible_base_model:
        all_errors += check_lora_asset(
            "primary", args.primary_lora_path, args.primary_compatible_base_model
        )
    else:
        all_errors.append(
            "primary: khong the kiem tra - chua cung cap --primary-lora-path"
        )

    if args.secondary_lora_path or args.secondary_compatible_base_model:
        all_errors += check_lora_asset(
            "secondary", args.secondary_lora_path, args.secondary_compatible_base_model
        )
    else:
        all_errors.append(
            "secondary: khong the kiem tra - chua cung cap --secondary-lora-path"
        )

    all_errors += check_staged_inpainting_pipeline()

    print("=== KIEM TRA SAN SANG PROOF LORA 2 NHAN VAT (CUC BO, KHONG GPU) ===")
    if not all_errors:
        print("SAN SANG: ca 2 LoRA hop le va pipeline staged-regional-inpainting")
        print("da ton tai. CO THE chuan bi mot proof GPU that (van can operator")
        print("thuc thi thu cong, script nay khong bao gio tu goi GPU).")
        return 0

    print(f"CHUA SAN SANG - {len(all_errors)} van de can giai quyet truoc proof that:")
    for i, err in enumerate(all_errors, 1):
        print(f"  {i}. {err}")
    print()
    print("Xem docs/reports/character-lora-architecture-2026-09-01.md")
    print("muc 6 (Track F) cho dac ta dataset + training pipeline day du.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
