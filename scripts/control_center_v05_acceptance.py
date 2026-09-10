"""Nghiệm thu V0.5 trên BẢN EXE ĐÓNG GÓI — chín tình huống của mục 13.

Chạy trên CHÍNH cửa sổ WebView2 của bản đã đóng gói, mở qua
`ShellExecuteW` (đúng API Explorer gọi), và giám sát cửa sổ console suốt
phiên bằng `giam_sat_cua_so`. Dùng lại hạ tầng của bộ nghiệm thu V0.4
thay vì viết lại.

    python scripts/control_center_v05_acceptance.py \
        --exe "dist-v05/Router Control Center/Router Control Center.exe"

TÌNH HUỐNG 6 (giả lập provider hỏng) làm bằng cách ghi một cấu hình quan
sát RIÊNG CỦA BẢN CÀI (`<gốc>/.router/observability.json`) trỏ vào một
host không tồn tại. An toàn: không chạm production, và nó đi đúng đường
mà một người dùng thật sẽ dùng để khai máy của họ.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.ghi_utf8 import GhiUTF8  # noqa: E402
from scripts.control_center_desktop_acceptance import (  # noqa: E402
    CDP, Bang, _dem_so, _mo_qua_explorer, _ta_vi_pham, kho_git_tam)
from scripts.giam_sat_cua_so import (GiamSatCuaSo,  # noqa: E402
                                     vi_pham_cua_app)

ghi = GhiUTF8()
NL = chr(10)
Q = chr(39)

#: Cau hoi CHINH cua muc 13.2 — nguyen van cau da lam Leader tra loi sai.
CAU_HOI = "production farmer còn chạy không?"


def _gieo(goc: Path) -> None:
    """Dự án `fanfic` (có adapter riêng) + `router` (chỉ quan sát chung)."""
    from scripts.control_center.bootstrap import khoi_tao
    from scripts.control_center.engine import ControlCenter
    from scripts.control_center.model import Project
    cc = ControlCenter(root=goc, probe=False)
    try:
        khoi_tao(cc.store, root=goc)
        cc.them_project(Project(project_id="fanfic",
                                name="Fanfic Audio Studio",
                                repo_path=str(goc)))
        cc.them_project(Project(project_id="router",
                                name="Router Control Center",
                                repo_path=str(goc)))
    finally:
        cc.store.close()


def _live(cdp: CDP, pid: str, refresh: bool = False) -> dict:
    return json.loads(cdp.js(
        "const t=sessionStorage.getItem('cc_token');"
        + NL + f"const r=await fetch('/api/live?project={pid}"
        + ("&refresh=1" if refresh else "") + "',"
        + NL + "  {headers:{'X-CC-Token':t}});"
        + NL + "return JSON.stringify(await r.json());") or "{}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--cdp", type=int, default=9701)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    bd = Bang()
    goc = kho_git_tam()
    _gieo(goc)
    p_exe = Path(a.exe)
    if not p_exe.is_absolute():
        p_exe = (GOC / a.exe).resolve()

    ghi("=" * 78)
    ghi("NGHIỆM THU V0.5 — QUAN SÁT SỐNG, trên BẢN EXE ĐÓNG GÓI")
    ghi(f"  exe : {p_exe}")
    ghi(f"  gốc : {goc}")
    ghi("=" * 78)

    gs = GiamSatCuaSo()
    gs.__enter__()
    ph = None
    try:
        # -- 13.1 mo app, chon du an Fanfic --------------------------------
        gs.dat_pha("mở app")
        ph = _mo_qua_explorer(p_exe, goc, a.cdp)
        gs.theo(ph.pid)
        cdp = CDP(a.cdp)
        cdp.cho("return !!document.querySelector('#o-soan')", han=45)
        cdp.dua_len_truoc()
        chon = cdp.cho(
            "const li=document.querySelector("
            + NL + f"  {Q}#ds-project li[data-pid=\"fanfic\"]{Q});"
            + NL + "if (li) li.click();"
            + NL + "const m=document.querySelector("
            + NL + f"  {Q}#ds-project li.dang-mo{Q});"
            + NL + "return !!(m && m.dataset.pid === 'fanfic');", han=40)
        bd.ghi("1. mở EXE và chọn được dự án Fanfic", bool(chon),
               f"pid {ph.pid}")

        # -- 13.3/13.4/13.5 probe SONG, doc lap voi so viec Router ---------
        gs.dat_pha("probe SỐNG (Fanfic)")
        d = _live(cdp, "fanfic", refresh=True)
        svc = (d.get("dich_vu") or {}).get("fanfic_farmer") or {}
        qs = {q["khoa"]: q for q in (svc.get("quan_sat") or [])}
        rt = ((d.get("router") or {}).get("router") or {})
        rqs = {q["khoa"]: q for q in (rt.get("quan_sat") or [])}
        so_viec = rqs.get("running_tasks", {}).get("gia_tri")
        bd.ghi("3. probe SỐNG chạy thật và có nguồn gốc",
               bool(qs) and qs.get("ssh", {}).get("nguon", "").startswith(
                   "ssh:"),
               f"farmer={svc.get('trang_thai')} · "
               f"ssh={qs.get('ssh', {}).get('trang_thai')} · "
               f"nguồn={qs.get('ssh', {}).get('nguon')}")
        bd.ghi("4. trạng thái dịch vụ NGOÀI tách riêng khỏi Router",
               "router" in (d.get("router") or {})
               and "router" not in (d.get("dich_vu") or {}),
               f"nhóm ngoài={sorted((d.get('dich_vu') or {}).keys())} · "
               f"nhóm router={sorted((d.get('router') or {}).keys())}")
        khoe_song = svc.get("trang_thai") in ("ACTIVE", "DEGRADED")
        bd.ghi("5. Router tasks = 0 mà farmer VẪN có thể ACTIVE",
               (so_viec == 0 and khoe_song
                and d.get("trang_thai_chung") in ("ACTIVE", "DEGRADED")),
               f"Router tasks={so_viec} · farmer={svc.get('trang_thai')} · "
               f"tổng thể NGOÀI={d.get('trang_thai_chung')}")
        bd.ghi("5b. và các số thật đã đo được hiện ra",
               all(qs.get(k, {}).get("gia_tri") is not None
                   for k in ("main_pid", "restarts")),
               "; ".join(f"{k}={qs.get(k, {}).get('gia_tri')}"
                         for k in ("service_state", "main_pid", "restarts",
                                   "disk")))

        # -- 13.2 Leader DOI trang thai song ------------------------------
        gs.dat_pha("Leader chat: câu hỏi hiện tại")
        n0 = len(json.loads(cdp.js(
            "const t=sessionStorage.getItem('cc_token');"
            + NL + "const r=await fetch('/api/state?project=fanfic',"
            + NL + "  {headers:{'X-CC-Token':t}});"
            + NL + "const j=await r.json();"
            + NL + "return JSON.stringify((j.events||[]).filter("
            + NL + "  e => e.kind === 'LIVE_PROBE'));") or "[]"))
        cdp.js("const o=document.querySelector('#o-soan'); o.focus();"
               + NL + f"o.value={json.dumps(CAU_HOI)};"
               + NL + "return 1;")
        cdp.phim("Enter", 13)
        # O soan phai trong NGAY (hoi quy V0.4).
        ngay = json.loads(cdp.js(
            "return JSON.stringify([document.querySelector('#o-soan').value,"
            + NL + " document.querySelector('#nut-gui').disabled]);")
            or '["?",false]')
        bd.ghi("2b. hồi quy V0.4: ô soạn trống NGAY khi gửi",
               ngay[0] == "" and ngay[1] is True,
               f"value={ngay[0]!r} đang-gửi={ngay[1]}")
        xong = cdp.cho("return !document.querySelector('#nut-gui').disabled",
                       han=300)
        sk = json.loads(cdp.js(
            "const t=sessionStorage.getItem('cc_token');"
            + NL + "const r=await fetch('/api/state?project=fanfic',"
            + NL + "  {headers:{'X-CC-Token':t}});"
            + NL + "const j=await r.json();"
            + NL + "return JSON.stringify((j.events||[]).filter("
            + NL + "  e => e.kind === 'LIVE_PROBE'));") or "[]")
        bd.ghi("2. câu hỏi HIỆN TẠI khiến Leader đòi trạng thái SỐNG",
               len(sk) > n0,
               f"sự kiện LIVE_PROBE: {n0} -> {len(sk)}"
               + (f" · {sk[0].get('detail')}" if sk else "")
               + ("" if xong else " · (lượt chưa xong trong 300s)"))
        tin = cdp.js(
            "return JSON.stringify([...document.querySelectorAll("
            + NL + f"  {Q}#ds-tin .tin{Q})].slice(-2).map("
            + NL + "  e => (e.textContent||'').slice(0,300)));")
        bd.ghi("2c. và có câu trả lời trong ô chat (không chỉ badge)",
               bool(json.loads(tin or "[]")),
               (json.loads(tin or '[""]')[-1] or "")[:150])

        # -- 13.9 du an KHONG co adapter rieng ----------------------------
        gs.dat_pha("dự án chung (Router)")
        d2 = _live(cdp, "router", refresh=True)
        bd.ghi("9. dự án không có adapter riêng vẫn được quan sát chung",
               "router" in (d2.get("router") or {})
               and "git" in (d2.get("kho") or {}),
               f"nhóm={[k for k in ('router', 'kho', 'dich_vu') if (d2.get(k) or {})]}"
               f" · tổng thể={d2.get('trang_thai_chung')}")
        bd.ghi("9b. và KHÔNG kết luận DOWN khi chỉ thiếu probe",
               d2.get("trang_thai_chung") != "DOWN",
               f"tổng thể={d2.get('trang_thai_chung')}")

        # -- 13.7 khong nhap cua so console -------------------------------
        kq = gs.ket_qua
        cua_ta = vi_pham_cua_app(kq.vi_pham)
        bd.ghi("7. không cửa sổ console nào DO APP nhấp lên", not cua_ta,
               kq.tom_tat()
               + (NL + "      " + _ta_vi_pham(kq.vi_pham)
                  if kq.vi_pham else ""))

        truoc = _dem_so(goc)
        cdp.dong()

        # -- 13.6 gia lap provider HONG (an toan) -------------------------
        # Ghi cau hinh RIENG CUA BAN CAI tro vao mot host khong ton tai.
        # KHONG cham production; va day dung la duong mot nguoi dung that
        # dung de khai may cua ho.
        ghi_de = goc / ".router" / "observability.json"
        ghi_de.parent.mkdir(parents=True, exist_ok=True)
        ghi_de.write_text(json.dumps({
            "projects": {"fanfic": {"providers": [{
                "type": "ssh_service", "id": "fanfic_farmer",
                "label": "AWS farmer (host giả lập hỏng)",
                "group": "dich_vu",
                "host": "10.255.255.1", "user": "ubuntu",
                "unit": "fanfic-farmer",
                "status_file": "/var/lib/fanfic-farmer/status.json",
                "key_path": "C:/khong/ton/tai.pem",
                "timeout": 6, "max_age": 120}]}}
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        ph.terminate()
        try:
            ph.wait(timeout=30)
        except subprocess.TimeoutExpired:
            ph.kill()
        time.sleep(2)

        gs2 = GiamSatCuaSo()
        gs2.__enter__()
        gs2.dat_pha("mở lại + provider hỏng")
        ph2 = _mo_qua_explorer(p_exe, goc, a.cdp + 1)
        gs2.theo(ph2.pid)
        try:
            cdp2 = CDP(a.cdp + 1)
            cdp2.cho("return !!document.querySelector('#o-soan')", han=45)
            cdp2.cho(
                "const li=document.querySelector("
                + NL + f"  {Q}#ds-project li[data-pid=\"fanfic\"]{Q});"
                + NL + "if (li) li.click(); return !!li;", han=40)
            d3 = _live(cdp2, "fanfic", refresh=True)
            s3 = (d3.get("dich_vu") or {}).get("fanfic_farmer") or {}
            cfg3 = next((x for x in (d3.get("nhat_ky_provider") or [])
                         if x.get("provider") == "config"), {})
            bd.ghi("6z. bản cài đọc ĐÚNG cấu hình ghi đè",
                   bool(cfg3.get("ghi_de")),
                   f"đường={cfg3.get('duong')}"
                   f" · ghi_đè={cfg3.get('ghi_de')}"
                   f" · nhãn={s3.get('nhan')!r}")
            bd.ghi("6. provider hỏng -> UNKNOWN/UNAVAILABLE, KHÔNG phải DOWN",
                   s3.get("trang_thai") in ("UNKNOWN", "UNAVAILABLE"),
                   f"trạng thái={s3.get('trang_thai')} · "
                   f"lý do={(s3.get('ly_do') or '')[:110]}")
            bd.ghi("6b. và tổng thể cũng KHÔNG thành DOWN",
                   d3.get("trang_thai_chung") != "DOWN"
                   and d3.get("co_bang_chung_song") is False,
                   f"tổng thể={d3.get('trang_thai_chung')} · "
                   f"bằng chứng sống={d3.get('co_bang_chung_song')}")
            # Router VAN doc duoc — mot probe ngoai hong khong lam vo
            # phan noi bo.
            bd.ghi("6c. Router vẫn quan sát được dù probe ngoài hỏng",
                   "router" in (d3.get("router") or {}),
                   f"router={sorted((d3.get('router') or {}).keys())}")
            bd.ghi("6d. giao diện hiện CHỮ trạng thái, không hiện số bịa",
                   bool(cdp2.cho(
                       "const t=(document.querySelector('#insp-song')"
                       ".textContent||'');"
                       + NL + "return t.includes('UNKNOWN') "
                       + NL + "  || t.includes('UNAVAILABLE');", han=40)),
                   (cdp2.js("return (document.querySelector('#insp-song')"
                            ".textContent||'')"
                            r".replace(/\s+/g,' ').slice(0,160)") or ""))

            # -- 13.8 dong/mo lai: trang thai khong hong ------------------
            sau = _dem_so(goc)
            dem = [k for k, v in truoc.items() if isinstance(v, int)]
            bd.ghi("8. đóng/mở lại: sổ không mất bản ghi nào",
                   all(sau[k] >= truoc[k] for k in dem),
                   "trước=" + ",".join(f"{k}:{truoc[k]}" for k in dem)
                   + " | sau=" + ",".join(f"{k}:{sau[k]}" for k in dem))
            bd.ghi("8b. sổ SQLite lành", sau["nguyen_ven"] == "ok",
                   str(sau["nguyen_ven"]))
            kq2 = gs2.ket_qua
            bd.ghi("7b. lần mở thứ hai cũng không nhấp cửa sổ console",
                   not vi_pham_cua_app(kq2.vi_pham), kq2.tom_tat())
            cdp2.dong()
        finally:
            ph2.terminate()
            try:
                ph2.wait(timeout=30)
            except subprocess.TimeoutExpired:
                ph2.kill()
            gs2.dung()
    finally:
        gs.dung()
        if ph is not None and ph.poll() is None:
            ph.terminate()
            try:
                ph.wait(timeout=25)
            except subprocess.TimeoutExpired:
                ph.kill()
        if a.keep:
            ghi(f"{NL}  (giữ lại {goc})")
        else:
            shutil.rmtree(goc, ignore_errors=True)

    ghi(NL + "=" * 78)
    hong = bd.hong()
    ghi(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for b in hong:
        ghi(f"  HỎNG: {b}")
    ghi("=" * 78)
    return 1 if hong else 0


if __name__ == "__main__":
    raise SystemExit(main())
