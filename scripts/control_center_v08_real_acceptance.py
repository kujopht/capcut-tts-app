"""NGHIỆM THU THẬT V0.8 — vai suy luận chạy trên MODEL THẬT.

Đây là bài lấp đúng một lỗ hổng mà báo cáo v0.8 tự nêu: *"chưa có lượt model
THẬT nào của Strategist/Reviewer được đo — chất lượng nội dung chưa có số
liệu."* Mọi thứ khác của v0.8 đã kiểm được tất định; cái này thì không.

NÓ CHẠY ỨNG DỤNG THẬT, KHÔNG MÔ PHỎNG:

* `python -m scripts.control_center.webmain --khong-mo` — ĐÚNG điểm vào mà
  `router-cc-web.cmd` dùng, nên `leader_bat=True`, `khoi_tao`, `recover()`
  và vòng điều phối đều giống hệt một lần bấm đôi;
* **sổ CHÍNH TẮC** (`%LOCALAPPDATA%\\RouterControlCenter`), không phải một
  SQLite tạm — vì viên nang, ký ức và quyết định `qd_0001` của Fanfic chỉ
  tồn tại ở đó, và một bản sao rỗng sẽ chứng minh nhầm thứ;
* **dự án `fanfic` thật**.

NGÂN SÁCH LÀ MỘT RÀNG BUỘC THẬT, KHÔNG PHẢI LỜI KHUYÊN. Bể Claude+GPT của
Antigravity đo được **10% hạn mức tuần** (2026-09-11). Nên kịch bản chạy
**số lượt model THẬT tối thiểu** để chứng minh kiến trúc — bốn tình huống,
chế độ AUTO, không lặp lại cho từng chế độ. Các chế độ được chứng minh bằng
phép định tuyến TẤT ĐỊNH (`--che-do`), không bằng bốn lần gọi model.

KHÔNG ĐỘNG VÀO PRODUCTION. Không việc nào được tạo trong các tình huống thảo
luận, và kịch bản đếm số việc TRƯỚC/SAU để chứng minh điều đó chứ không hứa.

    python scripts/control_center_v08_real_acceptance.py
    python scripts/control_center_v08_real_acceptance.py --chi 1,2
    python scripts/control_center_v08_real_acceptance.py --khong-ui
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from scripts.control_center.duong_du_lieu import goc_du_lieu        # noqa: E402
from scripts.control_center.ghi_utf8 import duong_nhat_ky           # noqa: E402

DU_AN = "fanfic"

#: Bốn tình huống, NGUYÊN VĂN câu người dùng.
TINH_HUONG: Tuple[Dict, ...] = (
    {"so": 1, "cau": "ê bro",
     "mong": "Leader một mình · không Strategist · không Reviewer · không worker",
     "vai_mong": {"leader"}, "viec_moi": 0},
    {"so": 2, "cau": "vụ SSH key fanficappwrite trước đây bị gì?",
     "mong": "trả lời TỪ KÝ ỨC · không worker đi khám phá lại",
     "vai_mong": {"leader"}, "viec_moi": 0},
    {"so": 3,
     "cau": ("theo trạng thái hiện tại của Fanfic.world, m nghĩ tôi nên ưu "
             "tiên phát triển phần nào tiếp theo và tại sao?"),
     "mong": "Strategist THAM GIA · không tự tạo việc · khuyến nghị cụ thể",
     "vai_mong": {"leader", "strategist"}, "viec_moi": 0},
    {"so": 4,
     "cau": ("hãy đề xuất một redesign lớn cho kiến trúc production của "
             "Fanfic.world để scale tốt hơn, sau đó tự phản biện đề xuất đó "
             "và nói tôi có nên làm ngay không."),
     "mong": "Strategist + Reviewer THẬT · Reviewer khác họ · Leader tổng hợp",
     "vai_mong": {"leader", "strategist", "reviewer"}, "viec_moi": 0},
)


class Bang:
    def __init__(self) -> None:
        self.hang: List[Dict] = []

    def them(self, muc: str, dat: bool, ct: str = "") -> bool:
        self.hang.append({"muc": muc, "dat": bool(dat), "chi_tiet": ct})
        print(f"  [{'ĐẠT ' if dat else 'HỎNG'}] {muc}"
              + (f"\n         {ct}" if ct else ""))
        return bool(dat)

    @property
    def so_dat(self) -> int:
        return sum(1 for h in self.hang if h["dat"])

    @property
    def tat_ca_dat(self) -> bool:
        return all(h["dat"] for h in self.hang)


# --------------------------------------------------------------- ung dung --

class UngDungThat:
    """Tiến trình `webmain` THẬT + một client HTTP mang token phiên.

    TOKEN KHÔNG BAO GIỜ ĐƯỢC IN. Nó nằm trong nhật ký của chính ứng dụng
    (đó là cách người dùng thật lấy nó), được đọc vào bộ nhớ rồi dùng làm
    header — không đi vào stdout, không vào tệp kết quả.
    """

    def __init__(self, *, cong: int = 0, timeout: float = 900.0):
        self.goc = goc_du_lieu()
        self.cong = cong
        self.timeout = timeout
        self._p: Optional[subprocess.Popen] = None
        self._token = ""
        self.dia = ""

    def mo(self) -> bool:
        from scripts.control_center.webmain import cong_rong

        self.cong = self.cong or cong_rong()
        nk = duong_nhat_ky(self.goc)
        # MỐC TÍNH BẰNG KÝ TỰ, không phải byte.
        #
        # `stat().st_size` là số BYTE; `read_text()` trả về một chuỗi đã giải
        # mã. Nhật ký này toàn tiếng Việt có dấu (UTF-8 nhiều byte mỗi ký
        # tự), nên số byte LỚN HƠN số ký tự và `van[st_size:]` luôn cắt quá
        # đuôi -> rỗng -> không bao giờ tìm thấy token. Đã vấp thật.
        moc = len(nk.read_text(encoding="utf-8", errors="replace")) \
            if nk.exists() else 0
        self._p = subprocess.Popen(
            [sys.executable, "-m", "scripts.control_center.webmain",
             "--khong-mo", "--port", str(self.cong)],
            cwd=str(GOC), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**_moi_truong()})
        self.dia = f"http://127.0.0.1:{self.cong}"
        # Doc token tu nhat ky UNG DUNG TU GHI — dung duong ma nguoi dung
        # that dung, thay vi tiem mot token tu ngoai vao.
        for _ in range(600):
            if nk.exists():
                van = nk.read_text(encoding="utf-8", errors="replace")[moc:]
                # GHIM ĐÚNG CỔNG ta vừa cấp: nhật ký là tệp GHI THÊM và đã
                # chứa URL của những lần chạy trước. Không ghim cổng thì một
                # token CŨ có thể được nhặt lên, rồi mọi request trả 401.
                m = re.search(
                    rf"http://127\.0\.0\.1:{self.cong}/\?t=([A-Za-z0-9_\-]+)",
                    van)
                if m:
                    self._token = m.group(1)
                    break
            if self._p.poll() is not None:
                return False
            time.sleep(0.2)
        if not self._token:
            return False
        for _ in range(300):
            try:
                self.get("/api/state")
                return True
            except Exception:                               # noqa: BLE001
                time.sleep(0.2)
        return False

    def _goi(self, duong: str, *, data: Optional[Dict] = None,
             timeout: Optional[float] = None):
        req = urllib.request.Request(
            self.dia + duong,
            data=(json.dumps(data).encode("utf-8") if data is not None else None),
            headers={"X-CC-Token": self._token,
                     "Content-Type": "application/json"},
            method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=timeout or 30.0) as r:
            return json.loads(r.read().decode("utf-8"))

    def get(self, duong: str, **kw):
        return self._goi(duong, **kw)

    def post(self, duong: str, data: Dict, **kw):
        return self._goi(duong, data=data, **kw)

    def url_co_token(self) -> str:
        """Chỉ dùng để đưa cho Chrome. KHÔNG in ra."""
        return f"{self.dia}/?t={self._token}"

    def dong(self) -> None:
        if self._p is not None:
            try:
                self._p.terminate()
                self._p.wait(timeout=20)
            except Exception:                               # noqa: BLE001
                try:
                    self._p.kill()
                except Exception:                           # noqa: BLE001
                    pass
            self._p = None


def _moi_truong() -> Dict[str, str]:
    import os
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    return e


# ------------------------------------------------------------------- pha 1 --

def pha_ui(bd: Bang, app: UngDungThat) -> Dict:
    """§1 — giao diện THẬT phơi ra và GIỮ BỀN bốn chế độ + nguồn gốc."""
    print("\n--- PHẦN 1: GIAO DIỆN THẬT (Chrome qua CDP) ---")
    ra: Dict = {}
    try:
        from scripts.control_center_web_smoke import CDP, cong_rong, tim_chrome
    except Exception as exc:                                # noqa: BLE001
        bd.them("giao diện: mở được Chrome", False, f"{exc}")
        return ra
    import tempfile

    cong_cdp = cong_rong()
    prof = Path(tempfile.mkdtemp(prefix="v08-real-prof-"))
    ch = subprocess.Popen(
        [tim_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", f"--user-data-dir={prof}",
         f"--remote-debugging-port={cong_cdp}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    for _ in range(150):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{cong_cdp}/json/list", timeout=1) as r:
                ds = json.load(r)
            ws = next((t["webSocketDebuggerUrl"] for t in ds
                       if t.get("type") == "page"), None)
            if ws:
                break
        except Exception:                                   # noqa: BLE001
            pass
        time.sleep(0.2)
    if not ws:
        bd.them("giao diện: nối được CDP", False, "không thấy trang nào")
        ch.terminate()
        return ra

    cdp = CDP(ws)
    try:
        cdp.goi("Runtime.enable")
        cdp.goi("Page.enable")
        cdp.goi("Page.navigate", url=app.url_co_token())
        time.sleep(5.0)
        # Chon du an fanfic trong sidebar.
        cdp.js("""
          const li = [...document.querySelectorAll('#ds-project li')]
            .find(x => x.textContent.includes('fanfic'));
          if (li) li.click();
          return !!li;
        """)
        time.sleep(3.0)

        opts = cdp.js("[...document.querySelectorAll('#chon-che-do option')]"
                      ".map(o=>o.value)")
        ra["che_do_trong_ui"] = opts
        bd.them("UI phơi ra ECO/AUTO/STRONG/MAX",
                opts == ["ECO", "AUTO", "STRONG", "MAX"], str(opts))

        cu = app.get(f"/api/reasoning?project={DU_AN}")["che_do"]
        ra["che_do_truoc"] = cu
        cdp.js("""
          const s = document.querySelector('#chon-che-do');
          s.value = 'STRONG';
          s.dispatchEvent(new Event('change', {bubbles: true}));
          return true;
        """)
        time.sleep(3.0)
        sau = app.get(f"/api/reasoning?project={DU_AN}")["che_do"]
        bd.them("đổi chế độ qua UI -> BỀN ở sổ server", sau == "STRONG",
                f"{cu} -> {sau}")
        # Tra ve AUTO: moi tinh huong that chay o AUTO.
        app.post("/api/reasoning/mode", {"project": DU_AN, "che_do": "AUTO"})
        time.sleep(2.0)
        chip = cdp.js("document.querySelector('#chip-che-do').textContent.trim()")
        bd.them("UI đồng bộ lại chế độ từ server", chip == "AUTO", f"chip={chip!r}")

        the = cdp.js("!!document.querySelector('#the-suy-luan')")
        bd.them("UI có thẻ nguồn gốc định tuyến", bool(the))

        loi = cdp.js("(window.__loi||[]).length")
        bd.them("không lỗi JavaScript", not loi, f"{loi} lỗi")
        ra["cdp_ok"] = True
    finally:
        try:
            cdp.dong()
        finally:
            ch.terminate()
    return ra


# ------------------------------------------------------------------- pha 2 --

def _dem_viec(app: UngDungThat) -> int:
    return len(app.get(f"/api/state?project={DU_AN}").get("tasks") or [])


def pha_tinh_huong(bd: Bang, app: UngDungThat, chon: List[int],
                   han: float) -> Dict:
    """§2 — bốn tình huống, MODEL THẬT, chế độ AUTO."""
    print("\n--- PHẦN 2: TÌNH HUỐNG THẬT (model thật, AUTO) ---")
    ra: Dict[str, Dict] = {}
    for th in TINH_HUONG:
        if th["so"] not in chon:
            continue
        print(f"\n  === TÌNH HUỐNG {th['so']} ===")
        print(f"  người dùng: {th['cau']}")
        print(f"  mong đợi  : {th['mong']}")
        truoc = _dem_viec(app)
        t0 = time.perf_counter()
        try:
            kq = app.post("/api/chat", {"project_id": DU_AN, "text": th["cau"]},
                          timeout=han)
        except Exception as exc:                            # noqa: BLE001
            bd.them(f"TH{th['so']}: gọi được", False,
                    f"{type(exc).__name__}: {exc}"[:200])
            ra[str(th["so"])] = {"loi": str(exc)[:300]}
            continue
        giay = round(time.perf_counter() - t0, 1)
        sau = _dem_viec(app)
        sl = app.get(f"/api/reasoning?project={DU_AN}").get("nguon_goc") or {}
        vai = set((sl.get("ke_hoach") or {}).get("vai") or [])
        pl = sl.get("phan_loai") or {}
        so = sl.get("so") or {}

        print(f"  -> {giay}s · phân loại {pl.get('bac')}/{pl.get('tac_dong')} "
              f"(tin {pl.get('do_tin')}) · vai {sorted(vai)} "
              f"· việc mới {sau - truoc}")
        for d in (sl.get("dong_nguon_goc") or []):
            print(f"     {d}")
        tra_loi = (kq.get("reply") or "").strip()
        print(f"  --- TRẢ LỜI CỦA LEADER ({len(tra_loi)} ký tự) ---")
        print("  " + tra_loi.replace("\n", "\n  ")[:2600])

        ra[str(th["so"])] = {
            "cau": th["cau"], "giay": giay, "vai": sorted(vai),
            "phan_loai": pl, "so": so, "viec_moi": sau - truoc,
            "dong": sl.get("dong_nguon_goc") or [],
            "nguon_goc": sl.get("nguon_goc") or [],
            "chien_luoc": sl.get("chien_luoc"),
            "phan_bien": sl.get("phan_bien"),
            "chinh_sach": sl.get("chinh_sach"),
            "suy_giam": sl.get("suy_giam"),
            "reply": tra_loi,
            "reply_len": len(tra_loi),
            "tasks": [t.get("task_id") for t in (kq.get("tasks") or [])],
        }
        bd.them(f"TH{th['so']}: vai đúng kỳ vọng ({sorted(th['vai_mong'])})",
                vai == th["vai_mong"], f"thực tế {sorted(vai)}")
        bd.them(f"TH{th['so']}: KHÔNG tạo việc nào",
                (sau - truoc) == th["viec_moi"] and not kq.get("tasks"),
                f"việc mới = {sau - truoc}")
        bd.them(f"TH{th['so']}: Leader có trả lời", bool(tra_loi),
                f"{len(tra_loi)} ký tự")
    return ra


# ------------------------------------------------------------------- pha 3 --

def pha_che_do(bd: Bang, app: UngDungThat) -> Dict:
    """§5 — bốn chế độ, chứng minh TẤT ĐỊNH (không gọi model lần nào)."""
    print("\n--- PHẦN 3: BỐN CHẾ ĐỘ (tất định, 0 lượt model) ---")
    from scripts.control_center.reasoning import chinh_sach as CS
    from scripts.control_center.reasoning.dinh_tuyen import (BoDinhTuyenVai,
                                                             KhongCoCho)
    from scripts.control_center.reasoning.phan_loai import (lap_ke_hoach_vai,
                                                            phan_loai_luot)
    from scripts.control_center.reasoning.vai import VaiTro
    from scripts.control_center.memory.service import DichVuKyUc
    from scripts.control_center.store import ControlStore
    from scripts.control_center.duong_du_lieu import duong_control_db
    from scripts.router_v4 import fabric_config as FC
    from scripts.router_v4.premium import CheDo

    fab, w, _ = FC.nap(probe=True)
    st = ControlStore(duong_control_db())
    dv = DichVuKyUc(st, goc_du_lieu())
    cs = CS.doc_chinh_sach(dv, DU_AN, ten_model=CS.ten_model_cao_cap(fab))
    ra: Dict = {"chinh_sach": cs.to_dict(), "theo_che_do": {}}
    kho = phan_loai_luot(TINH_HUONG[3]["cau"])
    de = phan_loai_luot("ê bro")

    for cd in CheDo:
        bdt = BoDinhTuyenVai(fab, weights=w, chinh_sach=cs)
        try:
            s = bdt.chon(VaiTro.STRATEGIST, kho, cd,
                         nguoi_yeu_cau_cao_cap=(cd is CheDo.MAX))
            mo = f"{s.runtime_id}/{s.model_id} [{s.bac_gia.value}]"
            astra, ly = s.astra, s.astra_ly_do
        except KhongCoCho as exc:
            mo, astra, ly = "(KHÔNG CÓ CHỖ)", False, str(exc)[:200]
        ra["theo_che_do"][cd.value] = {
            "strategist": mo, "astra": astra, "ly_do_astra": ly,
            "vai_cau_de": [v.value for v in lap_ke_hoach_vai(de, cd).vai]}
        print(f"  {cd.value:<7} câu RẤT KHÓ -> {mo}  astra={astra}")

    t = ra["theo_che_do"]
    bd.them("ECO: chặn bậc cao cấp tuyệt đối",
            not t["ECO"]["astra"] and "ECO" in t["ECO"]["ly_do_astra"],
            t["ECO"]["ly_do_astra"][:120])
    bd.them("AUTO: chỉ leo thang khi có lý do, và ghi lại lý do",
            bool(t["AUTO"]["ly_do_astra"]), t["AUTO"]["ly_do_astra"][:120])
    bd.them("STRONG mạnh hơn ECO cho cùng câu",
            t["STRONG"]["strategist"] != t["ECO"]["strategist"],
            f"ECO={t['ECO']['strategist']} STRONG={t['STRONG']['strategist']}")
    bd.them("MAX ≠ 'luôn dùng Astra' — vẫn qua chính sách + GacAstra",
            not t["MAX"]["astra"], t["MAX"]["ly_do_astra"][:140])
    bd.them("Mọi chế độ: câu tầm thường KHÔNG gọi vai nào",
            all(v["vai_cau_de"] == ["leader"] for v in t.values()))
    bd.them("Chính sách cao cấp đến từ KÝ ỨC dự án",
            cs.nguon == "ky_uc" and bool(cs.ma),
            f"nguồn={cs.nguon} mã={cs.ma!r}")
    st.close()
    return ra


# ------------------------------------------------------------------- pha 4 --

def pha_lich_su(bd: Bang) -> Dict:
    """§7 — lượt vai THẬT đã vào kho lịch sử/benchmark chưa."""
    print("\n--- PHẦN 4: VÒNG PHẢN HỒI (lịch sử vai) ---")
    from scripts.router_v4.history import BenchmarkStore, duong_vai

    p = duong_vai(goc_du_lieu())
    ls = BenchmarkStore(path=p)
    ds = ls.all()
    print(f"  tệp: {p}")
    print(f"  bản ghi: {len(ds)}")
    for r in ds[-8:]:
        print(f"    {r.task_type:<22} {r.provider}/{r.model_id:<28} "
              f"{r.wall_seconds:6.1f}s ok={r.success} verdict={r.verdict or '—'} "
              f"proj={r.project}")
    bd.them("Lượt vai THẬT được ghi vào lịch sử benchmark", bool(ds),
            f"{len(ds)} bản ghi ở {p.name}")
    if ds:
        bd.them("Bản ghi mang đủ nhãn (vai/provider/model/dự án)",
                all(r.task_type and r.provider and r.model_id and r.project
                    for r in ds))
        bd.them("KHÔNG bịa usage: tokens/cost là None",
                all(r.tokens is None and r.cost_usd is None for r in ds))
    tong = {}
    for r in ds:
        s = ls.summary_for(model_id=r.model_id, task_type=r.task_type)
        if s:
            tong[f"{r.model_id}|{r.task_type}"] = s
    print(f"  tổng hợp ĐO ĐƯỢC (≥3 mẫu): {len(tong)}")
    for k, v in tong.items():
        print(f"    {k}: samples={v['samples']} quality={v['quality']} "
              f"success={v['success_rate']}")
    return {"duong": str(p), "so_ban_ghi": len(ds),
            "ban_ghi": [r.to_dict() for r in ds],
            "tong_hop_do_duoc": tong}


# ------------------------------------------------------------------- main --

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chi", default="1,2,3,4",
                    help="tình huống chạy (mặc định tất cả)")
    ap.add_argument("--khong-ui", action="store_true",
                    help="bỏ qua phần Chrome")
    ap.add_argument("--han", type=float, default=900.0,
                    help="trần giây cho MỘT lượt chat")
    ap.add_argument("--do-han-muc", action="store_true",
                    help="đo hạn mức thật một lần trước các tình huống")
    ap.add_argument("--ra", default="", help="ghi kết quả JSON ra tệp")
    a = ap.parse_args(argv)
    chon = [int(x) for x in a.chi.split(",") if x.strip().isdigit()]

    print("=" * 76)
    print("NGHIỆM THU THẬT V0.8 — vai suy luận trên MODEL THẬT")
    print(f"sổ chính tắc: {goc_du_lieu()}")
    print(f"dự án       : {DU_AN}   ·   tình huống: {chon}")
    print("=" * 76)

    bd = Bang()
    kq: Dict = {}
    app = UngDungThat()
    print("\nđang mở ứng dụng THẬT (webmain, Leader BẬT)…")
    if not app.mo():
        print("KHÔNG mở được ứng dụng — dừng.")
        return 2
    print(f"  server 127.0.0.1:{app.cong} · token đọc từ nhật ký ứng dụng")
    try:
        kq["so_viec_truoc"] = _dem_viec(app)
        if a.do_han_muc:
            # ĐO hạn mức THẬT một lần, TRƯỚC các tình huống — để phép định
            # tuyến của chúng thật sự nhận biết hạn mức thay vì đọc con số
            # `declared` mặc định. `/usage` và `/credits` là lệnh gạch chéo
            # của CLI, không phải một lượt model.
            print("\nđo hạn mức thật (agy --print /usage)…")
            d = app.get(f"/api/reasoning?project={DU_AN}&refresh=1",
                        timeout=180.0)
            kq["han_muc"] = {"do_duoc": d.get("han_muc_do_duoc"),
                             "da_ap": d.get("han_muc_da_ap")}
            print(f"  {json.dumps(kq['han_muc'], ensure_ascii=False)}")
            bd.them("Hạn mức ĐO ĐƯỢC từ nhà cung cấp (§4 usage thật)",
                    bool(d.get("han_muc_do_duoc")),
                    f"đã áp cho: {d.get('han_muc_da_ap')}")
        if not a.khong_ui:
            kq["ui"] = pha_ui(bd, app)
        kq["tinh_huong"] = pha_tinh_huong(bd, app, chon, a.han)
        kq["che_do"] = pha_che_do(bd, app)
        kq["so_viec_sau"] = _dem_viec(app)
        bd.them("TỔNG: không việc nào được tạo trong cả phiên nghiệm thu",
                kq["so_viec_sau"] == kq["so_viec_truoc"],
                f"{kq['so_viec_truoc']} -> {kq['so_viec_sau']}")
    finally:
        app.dong()
    kq["lich_su"] = pha_lich_su(bd)

    print("\n" + "=" * 76)
    print(f"KẾT QUẢ: {bd.so_dat}/{len(bd.hang)} ĐẠT")
    print("=" * 76)
    for h in bd.hang:
        if not h["dat"]:
            print(f"  HỎNG: {h['muc']} — {h['chi_tiet']}")
    kq["bang"] = bd.hang
    if a.ra:
        Path(a.ra).write_text(json.dumps(kq, ensure_ascii=False, indent=2,
                                         default=str), encoding="utf-8")
        print(f"\nJSON: {a.ra}")
    return 0 if bd.tat_ca_dat else 1


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
