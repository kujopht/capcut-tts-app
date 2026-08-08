#!/usr/bin/env python3
"""
Đo tốc độ tổng hợp của model Piper. **Độc lập với hàng đợi production.**

    python scripts/benchmark_piper.py --models-dir /opt/fanfic-models/nghitts/piper-tts \\
        --voice ngochuyen --repeat 3

Không gọi Appwrite, không gọi R2, không tạo job, không đọc `server/.env*`. Chỉ
nạp model từ đĩa và tổng hợp vào thư mục tạm, rồi xoá. Chạy được trên VM
production mà không chạm dữ liệu production.

VÌ SAO KHÔNG DÙNG HÀNG ĐỢI: đo qua hàng đợi là đo cả Appwrite, mạng, lease và
thời gian chờ — bốn thứ che mất con số ta cần. Ở đây chỉ còn CPU và model.

RTF (real-time factor) = giây tính toán / giây audio. Nhỏ hơn 1 là nhanh hơn
thời gian thực. RTF 0.5 nghĩa là một chương đọc mất 10 phút thì tổng hợp mất 5.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import tempfile
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

for _luong in (sys.stdout, sys.stderr):
    if hasattr(_luong, "reconfigure"):
        _luong.reconfigure(encoding="utf-8", errors="replace")

ONNX_SUFFIX = ".onnx"
CONFIG_SUFFIX = ".onnx.json"

#: Đoạn văn mặc định. Tiếng Việt có dấu, đủ dài để RTF ổn định nhưng không lâu
#: tới mức một lượt đo cả 25 giọng thành cực hình.
VAN_MAC_DINH = (
    "Con thuyền nhỏ trôi giữa màn sương sớm. "
    "Tiếng mái chèo khua nước đều đặn vang lên trong tĩnh lặng. "
    "Phía xa, ngọn hải đăng vẫn kiên nhẫn quét những vòng sáng cuối cùng. "
    "Người lái đò khẽ hát một khúc dân ca quen thuộc."
)

#: Trần concurrency. Cao hơn số này trên máy phát triển chỉ tạo ra số liệu về
#: việc tranh CPU, không phải về model.
CONCURRENCY_TOI_DA = 4


def _ram_dinh_mb() -> Optional[float]:
    """
    RSS đỉnh, hoặc None nếu không đo được.

    KHÔNG thêm `psutil` làm phụ thuộc chỉ để có con số này: nó là phụ thuộc
    nhị phân, phải build trên mọi nền tảng, và bộ nghiệm thu lẫn worker đều
    không cần. Dùng thứ có sẵn: `resource` trên POSIX (VM production là
    Ubuntu), Win32 API qua `ctypes` trên Windows. Không có thì báo None và nói
    thẳng là không đo được.
    """
    try:
        import resource                                    # POSIX
        kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux trả KB, macOS trả byte.
        return kb / 1024 if sys.platform != "darwin" else kb / 1048576
    except ImportError:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(PMC), wintypes.DWORD]
        c = PMC(); c.cb = ctypes.sizeof(c)
        if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return c.PeakWorkingSetSize / 1048576
    except Exception:
        pass
    return None


def tim_giong(thu_muc: Path) -> List[str]:
    if not thu_muc.is_dir():
        return []
    return sorted(p.name[: -len(ONNX_SUFFIX)] for p in thu_muc.glob(f"*{ONNX_SUFFIX}")
                  if not p.name.endswith(CONFIG_SUFFIX))


def _giay_audio(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def mot_lan(pv: Any, module: Any, van: str, ra: Path,
            het_gio: float) -> Dict[str, Any]:
    """Một lần tổng hợp. Không bao giờ ném — lỗi thành một trường."""
    kq: Dict[str, Any] = {"thanh_cong": False, "loi": "",
                          "synth_seconds": None, "audio_seconds": None,
                          "rtf": None, "output_bytes": None}
    cfg = None
    lop = getattr(module, "SynthesisConfig", None)
    if lop is not None:
        try:
            cfg = lop(length_scale=1.0)
        except TypeError:
            cfg = None
    sr = int(getattr(getattr(pv, "config", None), "sample_rate", 22050) or 22050)

    t0 = time.perf_counter()
    try:
        with wave.open(str(ra), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            if cfg is not None:
                pv.synthesize_wav(van, w, syn_config=cfg)
            else:
                pv.synthesize_wav(van, w)
    except Exception as exc:
        kq["loi"] = f"{type(exc).__name__}: {exc}"
        return kq
    kq["synth_seconds"] = round(time.perf_counter() - t0, 4)
    if kq["synth_seconds"] > het_gio:
        kq["loi"] = f"quá {het_gio}s"
    try:
        kq["audio_seconds"] = round(_giay_audio(ra), 4)
        kq["output_bytes"] = ra.stat().st_size
    except Exception as exc:
        kq["loi"] = kq["loi"] or f"không đọc được WAV: {type(exc).__name__}"
        return kq
    if kq["audio_seconds"]:
        kq["rtf"] = round(kq["synth_seconds"] / kq["audio_seconds"], 4)
    kq["thanh_cong"] = not kq["loi"]
    return kq


def do_mot_giong(thu_muc: Path, ten: str, van: str, lap: int, dong_thoi: int,
                 het_gio: float, tam: Path) -> List[Dict[str, Any]]:
    import piper

    onnx = thu_muc / f"{ten}{ONNX_SUFFIX}"
    cfg = thu_muc / f"{ten}{CONFIG_SUFFIX}"
    ban_ghi: List[Dict[str, Any]] = []

    t0 = time.perf_counter()
    try:
        pv = piper.PiperVoice.load(str(onnx), config_path=str(cfg))
    except TypeError:
        pv = piper.PiperVoice.load(str(onnx), str(cfg))
    except Exception as exc:
        return [{"model": ten, "thanh_cong": False, "concurrency": dong_thoi,
                 "loi": f"nạp thất bại: {type(exc).__name__}: {exc}",
                 "load_seconds": None, "synth_seconds": None,
                 "audio_seconds": None, "rtf": None, "output_bytes": None}]
    nap = round(time.perf_counter() - t0, 4)

    # Warm-up: lần đầu luôn chậm hơn (cấp phát, cache, JIT của runtime). Tính nó
    # vào số liệu là bôi bẩn trung vị.
    mot_lan(pv, piper, van, tam / f"{ten}-warmup.wav", het_gio)

    def chay(i: int) -> Dict[str, Any]:
        r = mot_lan(pv, piper, van, tam / f"{ten}-{dong_thoi}-{i}.wav", het_gio)
        r.update({"model": ten, "concurrency": dong_thoi, "load_seconds": nap})
        return r

    if dong_thoi <= 1:
        ban_ghi = [chay(i) for i in range(lap)]
    else:
        # MỘT đối tượng PiperVoice dùng chung, đúng như worker: nó cache theo
        # đường dẫn `.onnx`. Đo concurrency mà mỗi luồng nạp model riêng là đo
        # một hệ thống khác.
        with ThreadPoolExecutor(max_workers=dong_thoi) as ex:
            ban_ghi = list(ex.map(chay, range(lap * dong_thoi)))
    for f in tam.glob(f"{ten}-*.wav"):
        f.unlink(missing_ok=True)
    return ban_ghi


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Đo tốc độ tổng hợp Piper. Độc lập với hàng đợi production.")
    p.add_argument("--models-dir", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--voice", help="một giọng, ví dụ ngochuyen")
    g.add_argument("--all", action="store_true", help="mọi giọng trong thư mục")
    p.add_argument("--text", help="văn bản đo")
    p.add_argument("--text-file", help="tệp chứa văn bản đo")
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--concurrency", type=int, default=1,
                   help=f"số luồng song song (tối đa {CONCURRENCY_TOI_DA})")
    p.add_argument("--timeout", type=float, default=300.0,
                   help="giây tối đa cho MỘT lần tổng hợp")
    p.add_argument("--csv", metavar="FILE")
    p.add_argument("--json", metavar="FILE")
    a = p.parse_args(argv)

    if a.concurrency < 1 or a.concurrency > CONCURRENCY_TOI_DA:
        print(f"--concurrency phải trong khoảng 1..{CONCURRENCY_TOI_DA}")
        return 2

    thu_muc = Path(a.models_dir)
    co = tim_giong(thu_muc)
    if not co:
        print(f"Không có model nào trong {thu_muc}")
        return 2
    if a.all:
        giong = co
    else:
        if a.voice not in co:
            print(f"Không có giọng {a.voice!r}. Có: {', '.join(co)}")
            return 2
        giong = [a.voice]

    van = a.text or (Path(a.text_file).read_text(encoding="utf-8")
                     if a.text_file else VAN_MAC_DINH)

    print(f"Thư mục model : {thu_muc}")
    print(f"Giọng         : {len(giong)}")
    print(f"Văn bản       : {len(van)} ký tự")
    print(f"Lặp / luồng   : {a.repeat} / {a.concurrency}")
    print(f"Hết giờ       : {a.timeout}s mỗi lần\n")

    tam = Path(tempfile.mkdtemp(prefix="bench_piper_"))
    tat_ca: List[Dict[str, Any]] = []
    try:
        for ten in giong:
            r = do_mot_giong(thu_muc, ten, van, a.repeat, a.concurrency,
                             a.timeout, tam)
            tat_ca.extend(r)
            ok = [x for x in r if x["thanh_cong"]]
            if ok:
                rtf = [x["rtf"] for x in ok if x["rtf"] is not None]
                print(f"  [OK  ] {ten:<16} n={len(ok):<3} "
                      f"RTF tv={statistics.median(rtf):.3f} "
                      f"min={min(rtf):.3f} max={max(rtf):.3f}  "
                      f"nạp={ok[0]['load_seconds']}s")
            else:
                print(f"  [HỎNG] {ten:<16} {r[0].get('loi','')[:70]}")
    finally:
        for f in tam.glob("*"):
            f.unlink(missing_ok=True)
        tam.rmdir()

    hong = [x for x in tat_ca if not x["thanh_cong"]]
    rtf = [x["rtf"] for x in tat_ca if x["thanh_cong"] and x["rtf"] is not None]
    ram = _ram_dinh_mb()
    print(f"\n{'=' * 56}")
    print(f"TỔNG: {len(tat_ca) - len(hong)}/{len(tat_ca)} lần thành công")
    if rtf:
        print(f"RTF   trung vị={statistics.median(rtf):.3f}  "
              f"min={min(rtf):.3f}  max={max(rtf):.3f}")
    print(f"RAM đỉnh: {f'{ram:.0f} MB' if ram is not None else 'không đo được'}")

    cot = ["model", "concurrency", "load_seconds", "synth_seconds",
           "audio_seconds", "rtf", "output_bytes", "thanh_cong", "loi"]
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cot, extrasaction="ignore")
            w.writeheader(); w.writerows(tat_ca)
        print(f"Đã ghi CSV : {a.csv}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"models_dir": str(thu_muc), "text_chars": len(van),
                       "repeat": a.repeat, "concurrency": a.concurrency,
                       "peak_rss_mb": ram, "ket_qua": tat_ca},
                      f, ensure_ascii=False, indent=1)
        print(f"Đã ghi JSON: {a.json}")

    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
