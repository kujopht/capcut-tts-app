"""Nghiệm thu V0.6.1 trên BẢN EXE ĐÓNG GÓI — đề bạt ký ức, nhập lịch sử, provider + kho bí mật.

    python scripts/control_center_v061_acceptance.py \
        --exe "dist-v061/Router Control Center/Router Control Center.exe"

HAI PHIÊN, MỘT GỐC (dùng lại hạ tầng V0.4/V0.5/V0.6). Phiên A: người dùng GÕ
đúng câu đã lộ khuyết tật V0.6 vào ô chat ("hãy ghi nhớ đây là một quyết định
của project: GPT-6 Astra…") — không qua API; rồi gõ câu THAY THẾ; rồi nhập
lịch sử của CHÍNH kho này qua một dự án trỏ vào kho; rồi thêm một provider
OpenAI-compatible trỏ vào MÁY CHỦ GIẢ trên 127.0.0.1 với một KHOÁ GIẢ (chuỗi
ngẫu nhiên có hình dạng `sk-…`), thử kết nối, hỏi thử; tắt như người dùng.
Phiên B: tiến trình MỚI — quyết định/thay thế/nhập/provider sống sót; Leader
mới trả lời từ ký ức; xoá tài khoản → credential biến mất khỏi Windows
Credential Manager.

KHOÁ GIẢ KHÔNG BAO GIỜ được in ra. Bài chỉ in ĐÃ/CHƯA tìm thấy nó ở đâu.
Không kho thật nào bị sửa: nhập lịch sử chỉ ĐỌC; máy chủ giả không phải API
trả tiền; không dispatch tự động nào tới provider ngoài (V0.6.1 tắt cứng).
"""
from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.ghi_utf8 import BoDocUTF8, GhiUTF8  # noqa: E402
from scripts.control_center_desktop_acceptance import (  # noqa: E402
    Bang, _dem_so, _ta_vi_pham, kho_git_tam)
from scripts.control_center_v05_acceptance import _gieo  # noqa: E402
from scripts.control_center_v06_acceptance import (  # noqa: E402
    _api, _chon_du_an, _dong_nhe, _gui_chat, _mo, _so_ky_uc, _tat)
from scripts.giam_sat_cua_so import (GiamSatCuaSo,  # noqa: E402
                                     vi_pham_cua_app)

ghi = GhiUTF8()
NL = chr(10)

#: Khoa GIA — ngau nhien moi lan chay, hinh dang `sk-…` de moi bo loc bat duoc.
KHOA_GIA = "sk-nghiemthu" + secrets.token_hex(20)

CAU_QD = ("hãy ghi nhớ đây là một quyết định của project: GPT-6 Astra chỉ được dùng "
          "cho các task đặc biệt khó hoặc cần reasoning cao, không dùng mặc định cho "
          "task thường.")
CAU_THAY = ("quyết định của project: thay cho {ma}, GPT-6 Astra được dùng cho mọi task "
            "review bảo mật, vẫn không dùng mặc định cho task thường.")
CAU_HOI_B = "Astra được dùng cho task nào? quyết định đó ghi khi nào, nguồn từ đâu?"


# ------------------------------------------------------------ may chu gia ----

class _TrangThaiGia:
    so_goi = 0
    khoa_khop = 0
    co_header = 0


class _MayChuGia(BaseHTTPRequestHandler):
    def log_message(self, *a):                                # im lang
        return

    def _xac_thuc(self):
        _TrangThaiGia.so_goi += 1
        h = self.headers.get("Authorization") or ""
        if h:
            _TrangThaiGia.co_header += 1
        if h == f"Bearer {KHOA_GIA}":
            _TrangThaiGia.khoa_khop += 1
            return True
        return False

    def _tra(self, ma: int, d: dict):
        than = json.dumps(d).encode()
        self.send_response(ma)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(than)))
        self.end_headers()
        self.wfile.write(than)

    def do_GET(self):
        if not self._xac_thuc():
            return self._tra(401, {"error": {"message": "Incorrect API key provided"}})
        if self.path.endswith("/models"):
            return self._tra(200, {"data": [{"id": "gia-1"}, {"id": "gia-2"}]})
        return self._tra(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        if not self._xac_thuc():
            return self._tra(401, {"error": {"message": "Incorrect API key provided"}})
        if self.path.endswith("/chat/completions"):
            return self._tra(200, {"choices": [{"message": {"content": "pong"}}],
                                   "usage": {"total_tokens": 3}})
        return self._tra(404, {"error": "not found"})


def _mo_may_chu_gia():
    sv = ThreadingHTTPServer(("127.0.0.1", 0), _MayChuGia)
    th = threading.Thread(target=sv.serve_forever, daemon=True)
    th.start()
    return sv, sv.server_address[1]


def _tim_khoa(goc: Path) -> list:
    """Tệp nào dưới gốc chứa KHOÁ GIẢ (UTF-8 hoặc UTF-16LE). Trả TÊN tệp thôi."""
    ra = []
    k8 = KHOA_GIA.encode("utf-8")
    k16 = KHOA_GIA.encode("utf-16-le")
    for f in goc.rglob("*"):
        if not f.is_file():
            continue
        try:
            b = f.read_bytes()
        except OSError:
            continue
        if k8 in b or k16 in b:
            ra.append(str(f.relative_to(goc)))
    return ra


def _api_dai(cdp, duong: str, method: str = "POST", than: dict | None = None,
             han: int = 420) -> dict:
    """Gọi API CHẬM (nhập lịch sử ~30–90 s): bắn `fetch` không chờ, rồi thăm dò
    kết quả — `CDP.js` chỉ chờ 40 s một lệnh."""
    khoa = f"__cc_dai_{int(time.time() * 1000)}"
    js = ("const t=sessionStorage.getItem('cc_token');"
          + NL + f"window.{khoa}=null;"
          + NL + f"fetch({json.dumps(duong)}, {{method:{json.dumps(method)},"
          + NL + "  headers:{'X-CC-Token':t,'Content-Type':'application/json'}"
          + (NL + f"  ,body:{json.dumps(json.dumps(than, ensure_ascii=False))}"
             if than is not None else "")
          + f"}}).then(r=>r.json()).then(d=>{{window.{khoa}=d;}})"
          + f".catch(e=>{{window.{khoa}={{error:String(e)}};}});"
          + NL + "return 1;")
    cdp.js(js)
    # `CDP.cho` chi tra CO/KHONG; gia tri lay bang mot lenh `js` rieng.
    if not cdp.cho(f"return !!window.{khoa};", han=han):
        return {"error": f"quá {han}s chưa có phản hồi"}
    ra = cdp.js(f"return JSON.stringify(window.{khoa});")
    return json.loads(ra or "{}") if isinstance(ra, str) else {}


def _cred_co(ref: str) -> bool:
    from scripts.control_center.providers.kho_bi_mat import KhoBiMatWindows
    try:
        return KhoBiMatWindows().co(ref)
    except Exception:                                       # noqa: BLE001
        return False


def main(argv=None) -> int:
    ap = BoDocUTF8(prog="control_center_v061_acceptance.py", ghi=ghi)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--cdp", type=int, default=9721)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--bo-leader-b", action="store_true",
                    help="bỏ câu hỏi Leader ở phiên B (nhanh)")
    a = ap.parse_args(argv)

    bd = Bang()
    goc = kho_git_tam()
    _gieo(goc)
    p_exe = Path(a.exe)
    if not p_exe.is_absolute():
        p_exe = (GOC / a.exe).resolve()

    ghi("=" * 78)
    ghi("NGHIỆM THU V0.6.1 — ĐỀ BẠT KÝ ỨC · NHẬP LỊCH SỬ · PROVIDER + KHO BÍ MẬT (EXE)")
    ghi(f"  exe : {p_exe}")
    ghi(f"  gốc : {goc}")
    ghi("=" * 78)

    sv, cong_gia = _mo_may_chu_gia()
    ref = ""
    acc = ""
    gs = GiamSatCuaSo(); gs.__enter__()
    ph = None
    try:
        # ================= PHIEN A =====================================
        gs.dat_pha("A: mở app")
        ph, cdp = _mo(p_exe, goc, a.cdp, gs)
        bd.ghi("1. mở EXE và chọn được dự án Router", _chon_du_an(cdp, "router"), f"pid {ph.pid}")
        tk0 = _api(cdp, "/api/memory/stats?project=router")
        tv = tk0.get("toan_ven") or {}
        bd.ghi("1b. ký ức SẴN, lược đồ ≥ v2 (trạng thái/thay thế/nguồn gốc)",
               bool(tk0.get("san_sang")) and int(tv.get("phien_ban_luoc_do") or 0) >= 2,
               f"chế độ tìm={tk0.get('che_do_tim')} · lược đồ v{tv.get('phien_ban_luoc_do')}")

        # -- A1: de bat qua CHAT — dung cau da lo khuyet tat V0.6 -------------
        gs.dat_pha("A: tuyên bố qua chat")
        n_lu0 = len([e for e in (_api(cdp, "/api/state?project=router").get("events") or [])
                     if e.get("kind") == "LEADER_UNAVAILABLE"])
        tl1 = _gui_chat(cdp, CAU_QD, han=420)
        d1 = (_api(cdp, "/api/memory/stats?project=router").get("dem") or {})
        # `list?loai=decision` tra [{ma: qd_…, hieu_luc, ky_uc: {…}}] — noi dung nam trong ky_uc.
        ds_qd = _api(cdp, "/api/memory/list?project=router&loai=decision").get("ket_qua") or []
        qd1_q = next((q for q in ds_qd
                      if "Astra" in ((q.get("ky_uc") or {}).get("noi_dung") or "")), {})
        qd1 = dict(qd1_q.get("ky_uc") or {})
        if qd1:
            qd1["ma"] = qd1_q.get("ma") or qd1.get("ma")
        n_lu1 = len([e for e in (_api(cdp, "/api/state?project=router").get("events") or [])
                     if e.get("kind") == "LEADER_UNAVAILABLE"])
        bd.ghi("2. A1 — tuyên bố QUA CHAT → Decisions = 1, authority user_explicit, nguồn chat_user",
               d1.get("quyet_dinh") == 1 and d1.get("ky_uc_user_explicit", 0) >= 1
               and qd1.get("tin_cay") == "user_explicit" and qd1.get("nguon_loai") == "chat_user",
               f"quyết định={d1.get('quyet_dinh')} · user_explicit={d1.get('ky_uc_user_explicit')} · "
               f"tin_cay={qd1.get('tin_cay')} · nguồn={qd1.get('nguon_loai')} · "
               f"Leader không sẵn: {n_lu1 - n_lu0} · " + (tl1 or "")[:160])
        bd.ghi("2b. Leader KHÔNG ghi lại (không có bản thứ hai)", d1.get("quyet_dinh") == 1,
               f"quyết định={d1.get('quyet_dinh')}")
        ma_qd1 = ""
        bg1 = {}
        if qd1.get("ma"):
            bg1 = _api(cdp, f"/api/memory/record?project=router&ma={qd1['ma']}")
            ma_qd1 = (bg1.get("quyet_dinh") or {}).get("ma") or ""
        bd.ghi("2c. A3 — nguồn gốc: bản ghi trỏ về đúng dòng L0 (tin nhắn người dùng), có mốc thời gian",
               bool(bg1.get("bang_chung")) and all(b.get("co") for b in bg1.get("bang_chung") or [])
               and bool((bg1.get("ky_uc") or {}).get("ts_su_kien")),
               f"mã qđ={ma_qd1} · {len(bg1.get('bang_chung') or [])} mắt xích · "
               f"L0: {((bg1.get('bang_chung') or [{}])[0].get('su_kien') or {}).get('loai', '?')}")

        # -- A2: thay the bang ma tuong minh ----------------------------------
        gs.dat_pha("A: thay thế")
        tl2 = _gui_chat(cdp, CAU_THAY.format(ma=ma_qd1 or "qd_0001"), han=420)
        d2 = (_api(cdp, "/api/memory/stats?project=router").get("dem") or {})
        bg1b = _api(cdp, f"/api/memory/record?project=router&ma={ma_qd1}") if ma_qd1 else {}
        q_cu = bg1b.get("quyet_dinh") or {}
        k_cu = bg1b.get("ky_uc") or {}
        ma_moi = k_cu.get("bi_thay_the") or ""
        bg2 = _api(cdp, f"/api/memory/record?project=router&ma={ma_moi}") if ma_moi else {}
        k_moi = bg2.get("ky_uc") or {}
        bd.ghi("3. A2 — thay thế: D1 SUPERSEDED (vẫn truy được), D2 hiệu lực, liên kết hai chiều",
               d2.get("quyet_dinh") == 2 and q_cu.get("hieu_luc") is False
               and k_cu.get("trang_thai") == "thay_the" and bool(ma_moi)
               and k_moi.get("hieu_luc") is True and k_cu.get("ma") in (k_moi.get("thay_the_cho") or []),
               f"quyết định={d2.get('quyet_dinh')} · D1 hiệu lực={q_cu.get('hieu_luc')} "
               f"trạng thái={k_cu.get('trang_thai')} · D2={ma_moi} hiệu lực={k_moi.get('hieu_luc')} · "
               + (tl2 or "")[:120])

        # -- tab Memory ----------------------------------------------------------
        gs.dat_pha("A: tab Memory")
        cdp.js("document.querySelector('.tab[data-khung=\"kyuc\"]').click(); return 1;")
        co_tk = cdp.cho("const t=(document.querySelector('#kyuc-thongke').textContent||'');"
                        + NL + "return t.includes('Quyết định') && t.includes('Ràng buộc');", han=30)
        chu = cdp.js("return (document.querySelector('#kyuc-thongke').textContent||'');") or ""
        co_chip = cdp.js("return !!document.querySelector('.kyuc-chip[data-loc=\"backfill\"]')"
                         + " && !!document.querySelector('.kyuc-chip[data-loc=\"constraint\"]');")
        bd.ghi("4. tab Memory: đếm Decisions/Constraints/Requirements/Procedures + chip Historical sources",
               bool(co_tk) and bool(co_chip), " ".join(str(chu).split())[:200])
        cdp.js("document.querySelector('.kyuc-chip[data-loc=\"decision\"]').click(); return 1;")
        co_ds = cdp.cho("const t=(document.querySelector('#kyuc-ds').textContent||'');"
                        + NL + "return t.includes('Astra');", han=30)
        kq_ui = cdp.js("return (document.querySelector('#kyuc-ds').textContent||'');") or ""
        bd.ghi("4b. danh sách quyết định trong UI hiện cả hai bản (qd_0001 + qd_0002)", bool(co_ds)
               and str(kq_ui).count("qd_") >= 2, " ".join(str(kq_ui).split())[:200])
        cdp.js("document.querySelector('.tab[data-khung=\"chat\"]').click(); return 1;")

        # -- B: nhap lich su cua CHINH kho nay ----------------------------------------
        gs.dat_pha("A: nhập lịch sử")
        them = _api(cdp, "/api/project", "POST", {"project_id": "kho", "name": "Kho này",
                                                   "repo_path": str(GOC)})
        ng = _api(cdp, "/api/memory/backfill/sources?project=kho")
        san = {n["nguon"]: n["san"] for n in ng.get("nguon") or []}
        bd.ghi("5. nguồn lịch sử của kho: 4 adapter, git/tài liệu/phiên Claude sẵn",
               bool(ng.get("san_sang")) and san.get("git") and san.get("tai_lieu")
               and san.get("phien_claude"),
               f"{san} · project: {them.get('project_id') or them.get('error')}")
        kho_ = _api_dai(cdp, "/api/memory/backfill", "POST", {"project": "kho", "thu_kho": True})
        t_k = kho_.get("tong") or {}
        bd.ghi("5b. thử khô: đếm mà không ghi", t_k.get("kham_pha", 0) > 100
               and (_api(cdp, "/api/memory/stats?project=kho").get("dem") or {}).get("su_kien_backfill", 0) == 0,
               f"khám phá={t_k.get('kham_pha')} · đề bạt={t_k.get('de_bat')} · {kho_.get('giay')}s")
        t0 = time.time()
        nhap = _api_dai(cdp, "/api/memory/backfill", "POST", {"project": "kho", "thu_kho": False})
        t_n = nhap.get("tong") or {}
        d_k = _api(cdp, "/api/memory/stats?project=kho").get("dem") or {}
        ghi_chu_pc = " ".join(x for s in nhap.get("nguon") or [] for x in (s.get("ghi_chu") or []))
        bd.ghi("5c. nhập thật: L0 mang loại backfill:<adapter>, có đề bạt, phiên đang mở bị bỏ qua",
               t_n.get("da_nhap", 0) > 100 and d_k.get("su_kien_backfill", 0) >= t_n.get("da_nhap", 0)
               and d_k.get("ky_uc_backfill", 0) >= 1,
               f"nhập={t_n.get('da_nhap')} · trùng={t_n.get('trung')} · đã lọc={t_n.get('da_loc')} · "
               f"đề bạt={t_n.get('de_bat')} · còn={t_n.get('con_lai')} · {time.time() - t0:.1f}s · "
               f"{ghi_chu_pc[:120]}")
        lai = _api_dai(cdp, "/api/memory/backfill", "POST", {"project": "kho", "thu_kho": False})
        t_l = lai.get("tong") or {}
        # `so_chinh` (su kien cua CHINH du an trong control.db) LON LEN trong luc
        # app song — vai su kien moi giua hai lan nhap la lich su moi, hop le.
        # Idempotent nghia la: git/tai lieu/phien Claude KHONG nhap lai gi, va
        # moi muc cua lan mot deu la "trung" o lan hai.
        theo_nguon = {s.get("nguon"): s for s in (lai.get("nguon") or [])}
        moi_ngoai_so = sum(int(s.get("da_nhap") or 0) for k, s in theo_nguon.items()
                           if k != "so_chinh")
        bd.ghi("5d. nhập lần hai: idempotent (git/tài liệu/phiên 0 mới; mọi mục lần một đều trùng)",
               moi_ngoai_so == 0 and t_l.get("trung", 0) >= t_n.get("da_nhap", 0) - 2,
               f"mới={t_l.get('da_nhap')} (so_chinh={int((theo_nguon.get('so_chinh') or {}).get('da_nhap') or 0)}, "
               f"khác={moi_ngoai_so}) · trùng={t_l.get('trung')}")
        tim = _api(cdp, "/api/memory/search?project=kho&q=fanficappwrite%20pem%20ssh")
        inc = _api(cdp, "/api/memory/list?project=kho&loai=incident")
        ds_inc = inc.get("ket_qua") or inc.get("ky_uc") or []
        if isinstance(ds_inc, dict):
            ds_inc = list(ds_inc.values())
        tu_bf = [k for k in ds_inc if str(k.get("nguon_loai") or "").startswith("backfill:")]
        bd.ghi("5e. B1 — 'vụ SSH key fanficappwrite' tìm lại được từ lịch sử (sự kiện thô + sự cố backfill)",
               bool(tim.get("su_kien")) and bool(tu_bf)
               and all(k.get("tin_cay") == "backfill" for k in tu_bf),
               f"{len(tim.get('ket_qua') or [])} ký ức · {len(tim.get('su_kien') or [])} sự kiện thô · "
               f"{len(tu_bf)} sự cố backfill · authority: "
               f"{sorted({k.get('tin_cay') for k in tu_bf})}")

        # -- D: provider + kho bi mat ---------------------------------------------------
        gs.dat_pha("A: provider")
        pv = _api(cdp, "/api/providers")
        kho = pv.get("kho_bi_mat") or {}
        bd.ghi("6. kho bí mật = Windows Credential Manager, SẴN; AUTO routing TẮT",
               kho.get("kieu") == "windows-credential-manager" and kho.get("san") is True
               and (pv.get("chinh_sach") or {}).get("auto_routing") is False,
               f"{kho.get('kieu')} · {kho.get('chi_tiet')} · presets={[p['ma'] for p in pv.get('presets') or []]}")
        p_them = _api(cdp, "/api/providers", "POST",
                      {"provider_id": "nghiemthu", "preset": "openai_compatible",
                       "base_url": f"http://127.0.0.1:{cong_gia}/v1", "ten": "Máy chủ giả"})
        tk_them = _api(cdp, "/api/providers/nghiemthu/accounts", "POST",
                       {"alias": "thu", "gia_tri": KHOA_GIA, "project": "router"})
        ref = tk_them.get("credential_ref") or ""
        acc = tk_them.get("account_id") or ""
        bd.ghi("6b. thêm tài khoản: phản hồi chỉ có credential_ref; giá trị NẰM TRONG Credential Manager",
               p_them.get("provider_id") == "nghiemthu" and bool(ref) and _cred_co(ref)
               and KHOA_GIA not in json.dumps(tk_them),
               f"ref={ref} · trong Credential Manager: {_cred_co(ref)}")
        thu = _api(cdp, f"/api/providers/accounts/{acc}/test", "POST", {"project": "router"})
        kq_t = thu.get("ket_qua") or {}
        bd.ghi("6c. thử kết nối chi phí tối thiểu: GET /models · máy chủ nhận đúng Bearer · model nạp 'probed'",
               kq_t.get("ok") is True and kq_t.get("cach") == "models"
               and _TrangThaiGia.khoa_khop >= 1 and "gia-1" in (kq_t.get("models") or []),
               f"{kq_t.get('chi_tiet')} · máy chủ giả: {_TrangThaiGia.so_goi} gọi, "
               f"{_TrangThaiGia.khoa_khop} khớp khoá")
        hoi = _api(cdp, f"/api/providers/accounts/{acc}/ask", "POST",
                   {"model": "gia-1", "cau": "ping", "project": "router"})
        bd.ghi("6d. hỏi thử (định tuyến THỦ CÔNG) trả lời qua máy chủ giả",
               hoi.get("ok") is True and hoi.get("noi_dung") == "pong",
               f"{hoi.get('noi_dung')} · usage={hoi.get('usage')}")
        pv2 = _api(cdp, "/api/providers")
        us = _api(cdp, "/api/usage?project=router")
        st = _api(cdp, "/api/state?project=router")
        lo = [x for x in ("/api/providers", "/api/usage", "/api/state")
              if KHOA_GIA in json.dumps({"/api/providers": pv2, "/api/usage": us, "/api/state": st}[x])]
        tep_lo = _tim_khoa(goc)
        bd.ghi("6e. khoá KHÔNG có ở: mọi phản hồi API · control.db · providers.db · sổ ký ức · log",
               not lo and not tep_lo, f"API lộ: {lo or 'không'} · tệp lộ: {tep_lo or 'không'}")
        ext = [r for r in (us.get("runtimes") or []) if str(r.get("runtime_id", "")).startswith("EXT_")]
        pool = (us.get("pool") or {}).get("antigravity") or {}
        bd.ghi("6f. provider ngoài vào fabric KHÔNG nhận dispatch; bể AG đếm từ sổ đăng ký",
               bool(ext) and all(r.get("dispatchable") is False for r in ext)
               and pool.get("dang_ky") == 8 and pool.get("ho_so_rieng") == 8,
               f"EXT={[r['runtime_id'] for r in ext]} · AG: đăng ký {pool.get('dang_ky')} · cấp phát "
               f"{pool.get('cap_phat')} · khoẻ {pool.get('khoe')} · chỗ {pool.get('dang_dung')}/{pool.get('tong_cho')} · "
               f"Leader chiếm {pool.get('leader_chiem')}")
        bd.ghi("6g. C — chỗ Leader chiếm hiện ra với bộ lập lịch (AG01 có nhãn LEADER:router)",
               "AG01" in (pool.get("leader_chiem") or []) or (n_lu1 - n_lu0) > 0,
               f"leader_chiem={pool.get('leader_chiem')} · Leader không sẵn: {n_lu1 - n_lu0}")

        # -- tat NHU NGUOI DUNG ----------------------------------------------------------
        kq = gs.ket_qua
        bd.ghi("7. phiên A: không cửa sổ console nào DO APP nhấp lên",
               not vi_pham_cua_app(kq.vi_pham),
               kq.tom_tat() + (NL + "      " + _ta_vi_pham(kq.vi_pham) if kq.vi_pham else ""))
        cdp.dong()
        gs.dat_pha("A: tắt")
        truoc = _dem_so(goc)
        cach = _dong_nhe(ph); ph = None
        so_tat = _so_ky_uc(goc)
        bd.ghi("8. tắt app như người dùng → điểm dừng trên đĩa", any(
            v.get("diem_dung_tat", 0) >= 1 for v in so_tat.values()), cach)

        # ================= PHIEN B =====================================
        gs2 = GiamSatCuaSo(); gs2.__enter__()
        gs2.dat_pha("B: mở lại")
        ph, cdp2 = _mo(p_exe, goc, a.cdp + 1, gs2)
        try:
            bd.ghi("9. mở lại được", _chon_du_an(cdp2, "router"), f"pid {ph.pid}")
            d_b = _api(cdp2, "/api/memory/stats?project=router").get("dem") or {}
            bg_b = _api(cdp2, f"/api/memory/record?project=router&ma={ma_qd1}") if ma_qd1 else {}
            d_kb = _api(cdp2, "/api/memory/stats?project=kho").get("dem") or {}
            pv_b = _api(cdp2, "/api/providers")
            tk_b = [t for t in pv_b.get("tai_khoan") or [] if t.get("account_id") == acc]
            bd.ghi("10. sống sót qua khởi động lại: 2 quyết định (D1 thay thế), lịch sử nhập, tài khoản provider",
                   d_b.get("quyet_dinh") == 2 and (bg_b.get("quyet_dinh") or {}).get("hieu_luc") is False
                   and d_kb.get("su_kien_backfill", 0) >= t_n.get("da_nhap", 0)
                   and bool(tk_b) and tk_b[0].get("trang_thai") == "ok" and _cred_co(ref),
                   f"qđ={d_b.get('quyet_dinh')} · D1 hiệu lực={(bg_b.get('quyet_dinh') or {}).get('hieu_luc')} · "
                   f"backfill={d_kb.get('su_kien_backfill')} · tài khoản={tk_b[0].get('trang_thai') if tk_b else '?'}")
            rs = [e for e in (_api(cdp2, "/api/state?project=router").get("events") or [])
                  if e.get("kind") == "MEMORY_RESUMED"]
            bd.ghi("10b. phiên MỚI tự ghi MEMORY_RESUMED", bool(rs), (rs[0].get("detail") if rs else "")[:120])

            if a.bo_leader_b:
                bd.ghi("11. Leader phiên MỚI trả lời từ ký ức", True, "(bỏ theo --bo-leader-b)")
            else:
                gs2.dat_pha("B: Leader mới")
                n_mc0 = len([e for e in (_api(cdp2, "/api/state?project=router").get("events") or [])
                             if e.get("kind") == "MEMORY_CONTEXT"])
                tl = _gui_chat(cdp2, CAU_HOI_B, han=420)
                n_mc1 = len([e for e in (_api(cdp2, "/api/state?project=router").get("events") or [])
                             if e.get("kind") == "MEMORY_CONTEXT"])
                tll = (tl or "").lower()
                khop = sum(1 for k in ("astra", "review", "qd_", "quyết định", "user") if k in tll)
                bd.ghi("11. Leader phiên MỚI trả lời từ ký ức (nêu Astra/review/mã)",
                       n_mc1 > n_mc0 and khop >= 2,
                       f"MEMORY_CONTEXT {n_mc0}->{n_mc1} · khớp {khop}/5 · " + (tl or "")[:220])
                d_b2 = _api(cdp2, "/api/memory/stats?project=router").get("dem") or {}
                bd.ghi("11b. hỏi không làm Leader ghi thêm quyết định", d_b2.get("quyet_dinh") == 2,
                       f"qđ={d_b2.get('quyet_dinh')}")

            # -- xoa tai khoan -> credential bien mat --------------------------------------
            gs2.dat_pha("B: xoá tài khoản")
            x1 = _api(cdp2, f"/api/providers/accounts/{acc}", "DELETE")
            x2 = _api(cdp2, f"/api/providers/accounts/{acc}?xac_nhan=true", "DELETE")
            bd.ghi("12. xoá tài khoản cần xác nhận; xoá xong credential BIẾN MẤT khỏi Credential Manager",
                   bool(x1.get("error")) and x2.get("credential_da_xoa") is True and not _cred_co(ref),
                   f"không xác nhận → {x1.get('error', '')[:60]} · đã xoá={x2.get('credential_da_xoa')} · "
                   f"còn trong CM: {_cred_co(ref)}")
            x3 = _api(cdp2, "/api/providers/nghiemthu?xac_nhan=true", "DELETE")
            pv_c = _api(cdp2, "/api/providers")
            bd.ghi("12b. xoá provider giả — sổ sạch", x3.get("provider_id") == "nghiemthu"
                   and not pv_c.get("providers"), f"{x3}")

            sau = _dem_so(goc)
            so_b = _so_ky_uc(goc)
            bd.ghi("13. sổ chính + sổ ký ức lành; khoá vẫn không có trong tệp nào",
                   sau["nguyen_ven"] == "ok" and all(v["quick_check"] == "ok" for v in so_b.values())
                   and not _tim_khoa(goc),
                   f"control.db={sau['nguyen_ven']} · ký ức=" + ",".join(
                       f"{k[:8]}:{v['quick_check']}/{v['su_kien']}sk" for k, v in so_b.items()))
            kq2 = gs2.ket_qua
            bd.ghi("14. phiên B: không cửa sổ console nào DO APP nhấp lên",
                   not vi_pham_cua_app(kq2.vi_pham),
                   kq2.tom_tat() + (NL + "      " + _ta_vi_pham(kq2.vi_pham) if kq2.vi_pham else ""))
            cdp2.dong()
        finally:
            if ph is not None:
                _dong_nhe(ph); ph = None
            gs2.dung()
    finally:
        gs.dung()
        sv.shutdown()
        if ph is not None and ph.poll() is None:
            _tat(ph)
        # Don: khong de lai credential gia trong Credential Manager du bai hong giua chung.
        if ref and _cred_co(ref):
            try:
                from scripts.control_center.providers.kho_bi_mat import KhoBiMatWindows
                KhoBiMatWindows().xoa(ref)
                ghi(f"  (đã dọn credential giả {ref} khỏi Credential Manager)")
            except Exception:                               # noqa: BLE001
                pass
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
