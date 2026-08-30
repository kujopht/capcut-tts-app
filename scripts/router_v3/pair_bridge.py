"""Ghép Router với cầu nối worker đã chạy — Router V3.2, Phase 5.

HAI CÁCH, chọn một:

1. Tệp ghép một lần (KHÔNG gõ tay, không qua model context) — worker bên
   kia chạy `run_bridge.py --pairing-file <đường dẫn dùng chung>`:

    python -m scripts.router_v3.pair_bridge --pairing-file C:\\FanficWorkers\\pairing\\AG02.pair

   Đọc cổng+token TỪ TỆP, xác minh bằng một lượt "health" thật, lưu, rồi
   XOÁ AN TOÀN tệp đó — dùng một lần xong là hết. Token không bao giờ đi
   qua đối số dòng lệnh, không bao giờ được in ra.

2. Gõ tay ẩn (dự phòng khi không dùng được tệp dùng chung):

    python -m scripts.router_v3.pair_bridge --worker-id AG02 --port 64689

   Token gõ ẨN (getpass) ngay tại đây.

Cả hai đều XÁC MINH bằng một lượt gọi "health" thật tới cầu nối TRƯỚC khi
lưu — token sai thì không lưu gì cả. Không bao giờ in lại token.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from scripts.router_v3.bridge import BridgeClient
from scripts.router_v3.bridge_store import luu
from scripts.router_v3 import pairing_file


def _ghep_va_luu(worker_id: str, host: str, port: int, token: str,
                 timeout: float) -> tuple:
    """Trả về (rc, thong_bao). KHÔNG BAO GIỜ đưa `token` vào `thong_bao`."""
    client = BridgeClient(port, token, host=host, timeout=timeout)
    r = client.health()

    if r.get("status") != "ok":
        loi = str(r.get("error") or r)
        if loi == "token không hợp lệ":
            return 1, "GHÉP HỎNG — token không hợp lệ (cầu nối từ chối)."
        # Loi khac "token khong hop le" -> nhieu kha nang la CONG sai hoac
        # cau noi da dung, khong phai token sai.
        return 1, (f"GHÉP HỎNG — không liên lạc được với {host}:{port} "
                   f"(cổng có thể sai, hoặc cầu nối đã dừng): {loi}")
    if not r.get("healthy"):
        return 1, f"GHÉP HỎNG — cầu nối trả lời nhưng báo KHÔNG khoẻ: {r}"

    wid_that = str(r.get("worker_id") or "")
    if wid_that and wid_that != worker_id:
        return 1, (f"GHÉP HỎNG — tệp/tham số nói worker_id={worker_id!r} "
                   f"nhưng cầu nối tự nhận là {wid_that!r}. Có thể tệp cũ "
                   f"hoặc trỏ nhầm cầu nối. KHÔNG lưu.")

    p = luu(worker_id, host=host, port=port, token=token)
    return 0, f"GHÉP OK — {worker_id} trả lời khoẻ qua {host}:{port}\nđã lưu tại {p} (không hiện lại token)"


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairing-file", default="",
                    help="đọc worker_id/port/token từ tệp dùng chung, xoá "
                         "an toàn sau khi ghép xong")
    ap.add_argument("--worker-id", default="")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=15.0)
    a = ap.parse_args(argv)

    if a.pairing_file and a.port:
        print("Chỉ dùng MỘT cách: --pairing-file HOẶC --worker-id/--port, không cả hai.")
        return 2

    if a.pairing_file:
        duong = Path(a.pairing_file)
        ban_ghi = pairing_file.read(duong)
        if ban_ghi is None:
            print(f"GHÉP HỎNG — không đọc được tệp ghép ở {duong} "
                 f"(chưa tồn tại, đã bị dùng, hoặc sai định dạng).")
            return 2
        rc, msg = _ghep_va_luu(ban_ghi["worker_id"], a.host, ban_ghi["port"],
                               ban_ghi["token"], a.timeout)
        print(msg)
        if rc == 0:
            da_xoa = pairing_file.secure_delete(duong)
            print(f"tệp ghép {'đã xoá an toàn' if da_xoa else 'không còn (đã bị dọn trước)'}")
        else:
            print(f"tệp ghép GIỮ NGUYÊN ở {duong} — sửa lỗi trên rồi thử lại "
                 f"(không tự xoá khi ghép hỏng, để còn thử lại được).")
        return rc

    if not a.worker_id or not a.port:
        print("Thiếu --pairing-file, hoặc thiếu --worker-id/--port cho cách gõ tay.")
        return 2

    try:
        token = getpass.getpass(
            f"Token cho cầu nối {a.worker_id} (gõ ẩn, Enter để xác nhận): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nHuỷ — không có gì được lưu.")
        return 2
    if not token:
        print("Token rỗng — huỷ, không lưu gì cả.")
        return 2

    rc, msg = _ghep_va_luu(a.worker_id, a.host, a.port, token, a.timeout)
    print(msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
