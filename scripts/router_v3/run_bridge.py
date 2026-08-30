"""Chạy cầu nối worker AG0x — Router V3.2, Phase 5.

CHẠY LỆNH NÀY TRONG PHIÊN WINDOWS CỦA CHÍNH TÀI KHOẢN ĐÓ, sau khi đã đăng
nhập `agy` một lần bằng tài khoản Google riêng của nó.

    python -m scripts.router_v3.run_bridge --worker-id AG02

Nó in ra CỔNG và TOKEN. Chép hai giá trị đó sang phiên Router chính. Token
này chỉ cho phép **gửi việc** tới cầu nối; nó không mở được gì thuộc về
Google, và Router không bao giờ thấy credential của tài khoản.

Cầu nối chỉ nghe trên 127.0.0.1.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3.bridge import BridgeConfig, WorkerBridge
from scripts.router_v3.native_worker import find_agy
from scripts.router_v3 import pairing_file, worker_identity
from scripts.router_v3.warm_pool import RecyclePolicy, WarmAgyWorker


def main(argv=None) -> int:
    # PHAI o TRUOC parse_args: console Windows mac dinh dung code page ANSI
    # (vd cp1252), khong ma hoa duoc dau tieng Viet. `--help`/loi cu phap goi
    # `print_help()` NGAY TRONG luc parse — dat reconfigure sau parse_args thi
    # `--help` vo tinh vo` UnicodeEncodeError truoc khi kip chay toi day.
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker-id", default="AG02")
    ap.add_argument("--model", default="gemini-3.7-flash-low")
    ap.add_argument("--port", type=int, default=0, help="0 = HĐH tự chọn")
    ap.add_argument("--workspace", default="", help="thư mục cho --add-dir")
    ap.add_argument("--allow-edits", action="store_true")
    ap.add_argument("--dangerously-skip-permissions", action="store_true",
                    help="tự duyệt MỌI quyền (gồm lệnh shell) — chỉ dùng khi "
                         "việc chạy trong worktree cô lập, có write_scope "
                         "và verify_scope() chặn sau")
    ap.add_argument("--pairing-file", default="",
                    help="ghi cổng+token vào tệp dùng chung MỘT LẦN thay vì "
                         "in ra màn hình để gõ tay — vd C:\\FanficWorkers\\"
                         "pairing\\AG02.pair. Thư mục cha phải đã có ACL "
                         "siết (setup_shared_root.py). pair_bridge.py đọc "
                         "và xoá tệp này sau khi ghép xong.")
    ap.add_argument("--no-persist-identity", action="store_true",
                    help="KHÔNG lưu cổng+token để dùng lại lần sau — mỗi lần "
                         "khởi động sinh danh tính MỚI (hành vi cũ, buộc "
                         "ghép lại mỗi lần). Mặc định: dùng lại nếu có, cho "
                         "phép khởi động lại bình thường mà không cần ghép "
                         "lại phía Router.")
    a = ap.parse_args(argv)

    exe = find_agy()
    if not exe:
        print("KHÔNG tìm thấy `agy` trong hồ sơ người dùng này.")
        print("Cài/kiểm tra Antigravity CLI rồi chạy lại.")
        return 2

    worker = WarmAgyWorker(
        a.worker_id, model=a.model,
        workspace=a.workspace or None, allow_edits=a.allow_edits,
        dangerously_skip_permissions=a.dangerously_skip_permissions,
        policy=RecyclePolicy())

    print(f"agy      : {exe}")
    print(f"worker   : {a.worker_id}  model={a.model}")
    print("Đang khởi động tiến trình ấm...", flush=True)
    if not worker.start():
        print("KHỞI ĐỘNG HỎNG. Nhiều khả năng tài khoản này CHƯA đăng nhập.")
        print("Chạy `agy` một lần ở chế độ tương tác và đăng nhập, rồi thử lại.")
        return 3
    print(f"tiến trình ấm SẴN SÀNG (khởi động {worker.cold_start_seconds:.2f}s)\n")

    def chay(prompt: str, family: str) -> dict:
        t = worker.send(prompt, family=family)
        ra = {"ok": t.ok, "response": t.response, "error": t.error,
             "seconds": round(t.seconds, 2), "turns": worker.stats.turns}
        # Chi kem stderr khi co van de ro rang — "ok" ma response RONG van la
        # dau hieu dang ngo, vi mot luot that thanh cong khong bao gio rong.
        if not t.ok or not t.response.strip():
            ra["stderr_tail"] = worker.stderr_tail[-2000:]
        return ra

    if a.no_persist_identity:
        cfg = BridgeConfig(worker_id=a.worker_id, port=a.port)
    else:
        danh_tinh = worker_identity.doc_hoac_tao(a.worker_id)
        cfg = BridgeConfig(worker_id=a.worker_id, port=danh_tinh["port"],
                           token=danh_tinh["token"])
        if danh_tinh["port"]:
            print(f"dùng lại danh tính đã lưu (cổng {danh_tinh['port']}) — "
                 f"Router không cần ghép lại nếu vẫn còn pairing cũ.")

    try:
        bridge = WorkerBridge(cfg, chay,
                              health_fn=lambda: worker.state.value != "failed",
                              state_fn=lambda: worker.state.value)
    except OSError as exc:
        if a.no_persist_identity or not cfg.port:
            raise
        # Cong da luu khong bind duoc (vd bi chiem boi tien trinh khac) —
        # roi ve danh tinh MOI thay vi treo hoan toan. Buoc ghep lai LAN
        # NAY, nhung khong lam hong ca lan khoi dong.
        print(f"cổng đã lưu {cfg.port} không bind được ({exc}) — "
             f"sinh danh tính MỚI, cần ghép lại.")
        danh_tinh = worker_identity.xoay_token(a.worker_id)
        cfg = BridgeConfig(worker_id=a.worker_id, port=danh_tinh["port"],
                           token=danh_tinh["token"])
        bridge = WorkerBridge(cfg, chay,
                              health_fn=lambda: worker.state.value != "failed",
                              state_fn=lambda: worker.state.value)
    bridge.start()
    if not a.no_persist_identity:
        worker_identity.ghi_cong_that_su(a.worker_id, bridge.port)

    print("=" * 58)
    print(f"  CẦU NỐI {a.worker_id} ĐÃ SẴN SÀNG")
    print(f"  cổng  : {bridge.port}")
    if a.pairing_file:
        duong = pathlib.Path(a.pairing_file)
        try:
            pairing_file.write(duong, worker_id=a.worker_id, port=bridge.port,
                               token=bridge.token)
            print(f"  token : đã ghi vào {duong} (KHÔNG hiện ở đây)")
        except FileNotFoundError as exc:
            print(f"  token : GHI TỆP HỎNG — {exc}")
            print(f"  token : {bridge.token}  (rơi về gõ tay do lỗi trên)")
    else:
        print(f"  token : {bridge.token}")
    print("=" * 58)
    if a.pairing_file:
        print("\nBên Router chạy: python -m scripts.router_v3.pair_bridge "
             f"--pairing-file {a.pairing_file}")
    else:
        print("\nChép CỔNG và TOKEN sang phiên Router chính.")
    print("Cầu nối chỉ nghe trên 127.0.0.1. Ctrl+C để dừng.\n")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nĐang dừng...")
    finally:
        bridge.stop()
        worker.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
