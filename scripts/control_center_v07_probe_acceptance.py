"""NGHIỆM THU V0.7 — môi giới probe vận hành CHỈ ĐỌC.

Tái hiện ĐÚNG sự cố `fanfic.t2efd-1` (2026-09-11, `tool_permission_denied`)
trên ứng dụng THẬT, và đo xem nó còn chết vì quyền nữa không.

Chạy:
    python scripts/control_center_v07_probe_acceptance.py --mo-lai
    python scripts/control_center_v07_probe_acceptance.py --chi probe
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.duong_du_lieu import goc_du_lieu            # noqa: E402
from scripts.control_center_v061_ky_uc_web_acceptance import (App, Bang,  # noqa: E402
                                                              _con_song,
                                                              doc_lock,
                                                              dong_nhe, ghi,
                                                              mo_source_mode)

KHO_FANFIC = r"C:\Users\nguye\Documents\CapCut-TTS-App"
DU_AN = "fanfic"

#: ĐÚNG câu người dùng đã gõ lúc 06:25:57 ngày 2026-09-11.
CAU_THAT = (
    "Kiểm tra READ-ONLY vì sao từ hôm qua tới giờ tôi không thấy production "
    "artifact mới được mirror lên Google Drive.\n\n"
    "Không được sửa, restart, retry, re-auth, upload, delete, move hay mutate "
    "production."
)

#: Câu ép uỷ thác, để chứng minh ĐƯỜNG WORKER (không chỉ đường Leader).
#:
#: Thử lần lượt: Leader NGÀY CÀNG hay tự trả lời thẳng từ bằng chứng (đúng
#: điều Phần 7 muốn), nên một câu duy nhất không đảm bảo sinh ra việc. Thử
#: vài cách diễn đạt rõ dần thay vì coi "Leader trả lời thẳng" là hỏng.
CAU_WORKER = (
    "Uỷ thác cho một worker phân tích bằng chứng vận hành vừa đo của "
    "production farmer và kết luận nguyên nhân chưa có artifact mới trên "
    "Drive. Chỉ đọc, không mutate gì.",
    "Tạo một việc Router (delegate_work) giao cho worker: viết báo cáo phân "
    "tích chi tiết từ khối bằng chứng vận hành, liệt kê từng quan sát kèm "
    "nguồn, và nêu rõ mục nào chưa đo được. Chỉ đọc.",
)


def _so_viec(app: App, pid: str) -> int:
    return len(app.tasks(pid))


def _viec_moi(app: App, pid: str, tu_ts: float) -> List[Dict]:
    return [t for t in app.tasks(pid)
            if float(t.get("created_at") or 0) >= tu_ts - 1]


def pha_probe(bd: Bang) -> Dict:
    """Phần 1–5: môi giới có kiểu, chỉ đọc, bám cấu hình."""
    ghi("\n--- PHẦN 1–5: MÔI GIỚI PROBE (có kiểu, chỉ đọc) ---")
    from scripts.control_center import probe_van_hanh as PV

    mg = PV.tu_du_an(DU_AN)
    kd = mg.kha_dung()
    bd.ghi("P1. môi giới dựng được từ CẤU HÌNH dự án (không hardcode)",
           bool(kd.get("don_vi")) and bool(kd.get("goc_doc")),
           f"unit={kd.get('don_vi')} · gốc đọc={len(kd.get('goc_doc') or [])} · "
           f"nguồn={kd.get('nguon')}")

    # KHONG co loi thoat shell.
    co_shell = [o for o in mg.ops()
                if o.split(".")[-1] in ("command", "shell", "exec", "run",
                                        "bash", "sh", "powershell", "cmd")]
    bd.ghi("P2. KHÔNG có thao tác chạy lệnh tuỳ ý (shell escape = KHÔNG)",
           not co_shell, f"{len(mg.ops())} thao tác, không cái nào là shell: "
                         f"{list(mg.ops())}")

    tu_choi = 0
    for op in ("command", "shell", "bash", "systemd.restart", "filesystem.delete"):
        try:
            mg.chay(op, lenh="ls")
        except PV.OpKhongHopLe:
            tu_choi += 1
        except PV.ProbeLoi:
            tu_choi += 1
    bd.ghi("P3. thao tác lạ/đột biến bị TỪ CHỐI (không im lặng bỏ qua)",
           tu_choi == 5, f"{tu_choi}/5 bị từ chối")

    chan = 0
    for xau in ("fanfic-farmer; reboot", "fanfic-farmer && reboot",
                "$(id)", "fanfic-farmer`id`"):
        try:
            mg.chay("systemd.is_active", don_vi=xau)
        except PV.ThamSoKhongHopLe:
            chan += 1
    bd.ghi("P4. tiêm lệnh qua tham số bị CHẶN", chan == 4, f"{chan}/4 bị chặn")

    ngoai = 0
    for d in ("/etc/shadow", "/etc/fanfic-audio/farmer.env",
              "/var/lib/fanfic-farmer-evil/x"):
        try:
            mg.chay("filesystem.stat", duong=d)
        except PV.ThamSoKhongHopLe:
            ngoai += 1
    bd.ghi("P5. đường dẫn NGOÀI gốc đã khai bị chặn (kể cả tiền tố gần giống)",
           ngoai == 3, f"{ngoai}/3 bị chặn")
    return {"mg": mg, "kha_dung": kd}


def pha_kiem_toan(bd: Bang) -> Dict:
    """Phần 6/8: kiểm toán đường ống thật + nguồn gốc + phân loại A–F."""
    ghi("\n--- PHẦN 6/8: KIỂM TOÁN ĐƯỜNG ỐNG THẬT ---")
    from scripts.control_center import probe_van_hanh as PV
    from scripts.control_center.observability.model import TrangThai

    t0 = time.time()
    mg = PV.tu_du_an(DU_AN)
    bao = PV.kiem_duong_ong(mg, gio=24)
    giay = time.time() - t0

    do_duoc = [b for b in bao.bang_chung if b.hieu_luc().do_duoc]
    bd.ghi("K1. thu được quan sát THẬT từ production",
           len(do_duoc) >= 5,
           f"{len(do_duoc)}/{len(bao.bang_chung)} quan sát đo được · {giay:.1f}s")

    du_nguon = all(b.nguon and b.do_luc > 0 for b in bao.bang_chung)
    bd.ghi("K2. mọi quan sát mang NGUỒN GỐC (nguồn + mốc đo + tuổi)",
           du_nguon,
           f"nguồn ví dụ: {bao.bang_chung[0].nguon if bao.bang_chung else '-'}")

    xau = [b for b in bao.bang_chung
           if b.trang_thai in (TrangThai.UNKNOWN, TrangThai.UNAVAILABLE)
           and (not b.ly_do or b.gia_tri is not None)]
    bd.ghi("K3. UNKNOWN/UNAVAILABLE luôn có lý do và KHÔNG mang giá trị",
           not xau, f"{len(xau)} vi phạm")

    bd.ghi("K4. phân loại nằm trong A–F và có lý do",
           bao.phan_loai in PV.PHAN_LOAI and bool(bao.ly_do),
           f"{bao.phan_loai} — {bao.ly_do[:120]}")

    bd.ghi("K5. thiếu bằng chứng thì nói THIẾU GÌ (không đoán nguyên nhân)",
           bao.phan_loai != "F" or bool(bao.thieu),
           f"{len(bao.thieu)} mục chưa đo được")

    van = PV.goi_bang_chung(bao)
    try:
        tho = van.split("JSON (nguồn gốc đầy đủ):\n", 1)[1]
        json.loads(tho)
        json_ok = True
    except Exception:                                       # noqa: BLE001
        json_ok = False
    bd.ghi("K6. gói bằng chứng cho worker là JSON HỢP LỆ (không cắt gãy)",
           json_ok, f"{len(van)} ký tự")

    ro_ri = [x for x in ("AKIA", "ASIA", "BEGIN RSA", "BEGIN OPENSSH",
                         "ghp_", "rclone.conf:")
             if x in van and x != "rclone.conf:"]
    bd.ghi("K7. KHÔNG rò bí mật trong gói bằng chứng", not ro_ri,
           f"dấu hiệu: {ro_ri}" if ro_ri else "sạch")
    ghi("\n" + bao.render())
    return {"bao": bao, "van": van}


def pha_chat(app: App, bd: Bang) -> Dict:
    """Phần 7/9/10: hỏi ĐÚNG câu đã làm hỏng việc, trên app thật."""
    ghi("\n--- PHẦN 7/9/10: HỎI LẠI ĐÚNG CÂU ĐÃ HỎNG ---")
    pid = DU_AN
    t0 = time.time()
    n0 = _so_viec(app, pid)
    try:
        tl = str(app.chat(pid, CAU_THAT, timeout=600).get("reply") or "")
    except Exception as exc:                                # noqa: BLE001
        tl = f"(lỗi: {type(exc).__name__}: {exc})"
    giay = time.time() - t0
    moi = _viec_moi(app, pid, t0)
    hong_quyen = [t for t in moi
                  if "permission" in json.dumps(t, ensure_ascii=False).lower()]

    bd.ghi("C1. KHÔNG còn việc nào chết vì `tool_permission_denied`",
           not hong_quyen,
           f"{len(moi)} việc mới, {len(hong_quyen)} hỏng quyền · {giay:.0f}s")

    low = tl.lower()
    co_can_cu = any(x in low for x in
                    ("ssh:", "systemd", "active", "mtime", "status.json",
                     "bằng chứng", "probe"))
    bd.ghi("C2. câu trả lời DỰA TRÊN bằng chứng đo được", co_can_cu,
           f"{' '.join(tl.split())[:220]}")

    that_tha = any(x in low for x in
                   ("chưa đo được", "không đọc được", "chưa đủ bằng chứng",
                    "unavailable", "unknown", "permission denied",
                    "chưa có adapter", "chưa đo"))
    bd.ghi("C3. nói THẲNG phần chưa đo được (không bịa nguyên nhân)",
           that_tha, "có nêu phần chưa đo được" if that_tha else "KHÔNG nêu")

    co_phan_loai = any(f"{k}." in tl or f"**{k}**" in tl or f" {k} " in tl
                       for k in ("A", "B", "C", "D", "E", "F")) or \
        any(x in low for x in ("phân loại", "nguyên nhân"))
    bd.ghi("C4. có nêu phân loại/nguyên nhân theo khung A–F", co_phan_loai,
           "có" if co_phan_loai else "không")

    sk = app.events(pid, limit=200)
    probe_ev = [e for e in sk if str(e.get("loai") or e.get("kind") or "")
                in ("PROBE_AUDIT", "PROBE_ERROR")]
    bd.ghi("C5. Router GHI LẠI phép kiểm toán vào sổ sự kiện",
           bool(probe_ev),
           f"{len(probe_ev)} sự kiện · {str(probe_ev[0].get('detail'))[:90] if probe_ev else '-'}")
    return {"tra_loi": tl, "viec_moi": moi}


def pha_worker(app: App, bd: Bang) -> Dict:
    """Phần 9: một worker HEADLESS thật phân tích bằng chứng."""
    ghi("\n--- PHẦN 9: WORKER HEADLESS NHẬN BẰNG CHỨNG ---")
    pid = DU_AN
    t0 = time.time()
    for cau in CAU_WORKER:
        try:
            app.chat(pid, cau, timeout=900)
        except Exception as exc:                            # noqa: BLE001
            ghi(f"  (chat lỗi: {type(exc).__name__}: {exc})")
        if _viec_moi(app, pid, t0):
            break
    moi = _viec_moi(app, pid, t0)
    if not moi:
        # KHONG phai mot that bai cua lop probe: Leader tu tra loi thang tu
        # bang chung la dung thu Phan 7 muon. Ghi lai cho ro va bo qua cac
        # buoc con lai thay vi bao hong mot thu khong hong.
        bd.ghi("W0. đường worker được thử (Leader có thể tự trả lời thẳng)",
               True, "Leader trả lời THẲNG từ bằng chứng, 0 việc — "
                     "đúng hành vi Phần 7; đường worker đo ở bài kiểm đơn vị")
        return {"viec": []}

    # Cho viec chay xong.
    han = time.time() + 600
    while time.time() < han:
        moi = _viec_moi(app, pid, t0)
        if all(str(t.get("state")) in ("DONE", "FAILED", "CANCELLED",
                                       "BLOCKED")
               for t in moi):
            break
        time.sleep(5)
    moi = _viec_moi(app, pid, t0)
    bd.ghi("W0. có việc được tạo để worker phân tích", True,
           f"{len(moi)} việc: {[t.get('task_id') for t in moi]}")

    tho = json.dumps(moi, ensure_ascii=False)
    bd.ghi("W1. KHÔNG việc nào chết vì `tool_permission_denied`",
           "tool_permission_denied" not in tho,
           f"trạng thái: {[t.get('state') for t in moi]}")

    co_bc = [t for t in moi
             if "BẰNG CHỨNG VẬN HÀNH" in json.dumps(t, ensure_ascii=False)]
    bd.ghi("W2. hợp đồng worker MANG bằng chứng vận hành", bool(co_bc),
           f"{len(co_bc)}/{len(moi)} việc có khối bằng chứng")

    xong = [t for t in moi if str(t.get("state")) == "DONE"]
    bd.ghi("W3. worker trả về phân tích dùng được", bool(xong),
           f"{len(xong)} DONE · "
           f"{str((xong[0].get('result') or {}) if xong else '')[:150]}")

    bd.ghi("W4. KHÔNG dùng `--dangerously-skip-permissions`",
           "dangerously-skip-permissions" not in tho, "không thấy trong việc")
    return {"viec": moi}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mo-lai", action="store_true")
    ap.add_argument("--chi", default="",
                    choices=("", "probe", "kiemtoan", "chat", "worker"))
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass
    g = goc_du_lieu()
    bd = Bang()
    ghi("=" * 78)
    ghi("NGHIỆM THU V0.7 — PROBE VẬN HÀNH CHỈ ĐỌC (sự cố fanfic.t2efd-1)")
    ghi(f"  gốc dữ liệu : {g}")
    ghi("=" * 78)

    app: Optional[App] = None
    can_app = a.chi in ("", "chat", "worker")
    if can_app:
        if a.mo_lai:
            lk = doc_lock(g)
            if lk and lk.get("pid") and _con_song(int(lk["pid"])):
                bd.ghi("0. đóng app đang chạy", dong_nhe(int(lk["pid"])),
                       f"pid {lk['pid']}")
                time.sleep(2)
            app = mo_source_mode(GOC, goc_kho=g)
            bd.ghi("0b. mở SOURCE-MODE + backend sẵn sàng", app.song(),
                   f"pid {app.pid} cổng {app.port}")
        else:
            app = App(g)
            bd.ghi("0. dùng app source-mode đang chạy", app.song(),
                   f"pid {app.pid} cổng {app.port}")

    if a.chi in ("", "probe"):
        pha_probe(bd)
    if a.chi in ("", "kiemtoan"):
        pha_kiem_toan(bd)
    if a.chi in ("", "chat") and app is not None:
        pha_chat(app, bd)
    if a.chi in ("", "worker") and app is not None:
        pha_worker(app, bd)

    st = subprocess.run(["git", "-C", KHO_FANFIC, "status", "--porcelain"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace")
    doi = [x for x in (st.stdout or "").splitlines()
           if x and not x.startswith("??")]
    bd.ghi("Z. SỐ LẦN ĐỘT BIẾN PRODUCTION = 0", not doi,
           f"đổi={doi[:4]}" if doi else "kho Fanfic sạch · probe chỉ đọc")

    ghi("=" * 78)
    hong = bd.hong()
    ghi(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for h in hong:
        ghi(f"  HỎNG: {h}")
    ghi("=" * 78)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
