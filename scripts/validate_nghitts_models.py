#!/usr/bin/env python3
"""
Kiểm tra thư mục model NghiTTS/Piper. **CHỈ ĐỌC.**

    python scripts/validate_nghitts_models.py --models-dir /opt/fanfic-models/nghitts/piper-tts

Không gọi Appwrite, không gọi R2, không tạo job, không ghi gì vào thư mục model.
Thứ duy nhất nó ghi là tệp báo cáo `--json` nếu bạn yêu cầu.

VÌ SAO CẦN: `PiperLocalProvider` chỉ báo "chưa tải model" khi tổng hợp thất bại,
tức là bạn biết model hỏng vào lúc một người dùng thật đang chờ audio. Script
này hỏi cùng câu hỏi đó trước, ngoài đường chạy production.

Thoát khác 0 khi có model hỏng, để dùng được trong script cài đặt và CI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

for _luong in (sys.stdout, sys.stderr):
    if hasattr(_luong, "reconfigure"):
        _luong.reconfigure(encoding="utf-8", errors="replace")

ONNX_SUFFIX = ".onnx"
CONFIG_SUFFIX = ".onnx.json"

#: Model Piper thật đều lớn hơn ngưỡng này. Nhỏ hơn nghĩa là tải dở hoặc là
#: tệp con trỏ Git LFS chưa được nạp về.
MIN_ONNX_BYTES = 1024 * 1024


def tim_model(thu_muc: Path) -> List[Path]:
    """
    Mọi `*.onnx` trong thư mục, KHÔNG tính `*.onnx.json`.

    `glob("*.onnx")` cũng khớp `x.onnx.json` trên một số nền tảng, nên phải
    loại tường minh chứ không dựa vào hành vi của glob.
    """
    if not thu_muc.is_dir():
        return []
    return sorted(p for p in thu_muc.glob(f"*{ONNX_SUFFIX}")
                  if not p.name.endswith(CONFIG_SUFFIX))


def soi_mot_model(onnx: Path, nap_that: bool) -> Dict[str, Any]:
    """Soi một cặp model. Không bao giờ ném — mọi lỗi thành một trường."""
    ten = onnx.name[: -len(ONNX_SUFFIX)]
    cfg = onnx.with_name(ten + CONFIG_SUFFIX)
    kq: Dict[str, Any] = {
        "voice": ten,
        "voice_id": f"piper:{ten}",
        "onnx": str(onnx),
        "config": str(cfg),
        "onnx_bytes": None,
        "config_target": None,
        "hop_le": False,
        "loi": "",
        "nap_giay": None,
    }
    try:
        kq["onnx_bytes"] = onnx.stat().st_size
    except OSError as exc:
        kq["loi"] = f"không đọc được .onnx: {type(exc).__name__}"
        return kq
    if kq["onnx_bytes"] < MIN_ONNX_BYTES:
        kq["loi"] = (f"tệp .onnx chỉ {kq['onnx_bytes']} byte — nhiều khả năng "
                     "tải dở hoặc là con trỏ Git LFS")
        return kq

    # -- config: symlink phải trỏ tới nơi có thật ---------------------------
    #
    # Bộ NghiTTS dùng MỘT `config.json` chung, mỗi `<voice>.onnx.json` là một
    # symlink trỏ vào đó. `is_file()` đi theo symlink nên trả False cho cả hai
    # trường hợp "không có" và "symlink gãy" — phải phân biệt, vì cách sửa khác
    # hẳn nhau.
    if cfg.is_symlink():
        try:
            kq["config_target"] = os.readlink(cfg)
        except OSError:
            kq["config_target"] = "(không đọc được)"
        if not cfg.resolve().exists():
            kq["loi"] = f"symlink gãy: {cfg.name} -> {kq['config_target']}"
            return kq
    if not cfg.is_file():
        kq["loi"] = f"thiếu {cfg.name}"
        return kq

    try:
        with cfg.open(encoding="utf-8") as f:
            d = json.load(f)
    except Exception as exc:
        kq["loi"] = f"config không phải JSON hợp lệ: {type(exc).__name__}"
        return kq
    thieu = [k for k in ("audio", "phoneme_id_map") if k not in d]
    if thieu:
        kq["loi"] = f"config thiếu khoá {thieu}"
        return kq
    kq["sample_rate"] = (d.get("audio") or {}).get("sample_rate")

    if not nap_that:
        kq["hop_le"] = True
        return kq

    # -- nạp thật bằng chính đường mã mà worker dùng ------------------------
    try:
        import piper
    except ImportError:
        kq["loi"] = "chưa cài gói piper-tts nên không nạp thử được"
        return kq
    t0 = time.perf_counter()
    try:
        piper.PiperVoice.load(str(onnx), config_path=str(cfg))
    except TypeError:
        try:
            piper.PiperVoice.load(str(onnx), str(cfg))
        except Exception as exc:
            kq["loi"] = f"nạp thất bại: {type(exc).__name__}: {exc}"
            return kq
    except Exception as exc:
        kq["loi"] = f"nạp thất bại: {type(exc).__name__}: {exc}"
        return kq
    kq["nap_giay"] = round(time.perf_counter() - t0, 3)
    kq["hop_le"] = True
    return kq


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Kiểm tra thư mục model NghiTTS/Piper. Chỉ đọc.")
    p.add_argument("--models-dir", required=True,
                   help="thư mục chứa các cặp .onnx + .onnx.json")
    p.add_argument("--no-load", action="store_true",
                   help="chỉ kiểm cấu trúc tệp, không nạp model. Nhanh hơn "
                        "nhưng KHÔNG chứng minh model chạy được.")
    p.add_argument("--json", metavar="FILE", help="ghi báo cáo ra tệp JSON")
    a = p.parse_args(argv)

    thu_muc = Path(a.models_dir)
    print(f"Thư mục model : {thu_muc}")
    if not thu_muc.is_dir():
        print("  KHÔNG PHẢI thư mục — dừng.")
        return 2

    models = tim_model(thu_muc)
    print(f"Tìm thấy      : {len(models)} tệp .onnx")
    if not models:
        print("  Không có model nào — dừng.")
        return 2
    print(f"Nạp thử       : {'KHÔNG (--no-load)' if a.no_load else 'có'}\n")

    ket: List[Dict[str, Any]] = []
    for onnx in models:
        r = soi_mot_model(onnx, nap_that=not a.no_load)
        ket.append(r)
        mb = (r["onnx_bytes"] or 0) / 1048576
        dau = "OK  " if r["hop_le"] else "HỎNG"
        them = f"{r['nap_giay']}s" if r.get("nap_giay") is not None else ""
        print(f"  [{dau}] {r['voice']:<16} {mb:7.2f} MB  {them}"
              + (f"  — {r['loi']}" if r["loi"] else ""))

    hong = [r for r in ket if not r["hop_le"]]
    print(f"\n{'=' * 56}")
    print(f"TỔNG: {len(ket) - len(hong)}/{len(ket)} hợp lệ")
    if hong:
        print("HỎNG:")
        for r in hong:
            print(f"  - {r['voice']}: {r['loi']}")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"models_dir": str(thu_muc), "tong": len(ket),
                       "hop_le": len(ket) - len(hong), "chi_tiet": ket},
                      f, ensure_ascii=False, indent=1)
        print(f"\nĐã ghi báo cáo: {a.json}")

    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
