"""ADAPTER OpenAI-compatible — thử kết nối chi phí tối thiểu, hỏi một câu thủ công.

Ranh giới bí mật của tệp này:
  * header xác thực chỉ được dựng BÊN TRONG `bi_mat.dung(...)` và chỉ sống
    trong dict `headers` của đúng một request;
  * mọi văn bản đi ra (`chi_tiet`, `noi_dung`) qua `_lam_sach()`: thay đúng
    giá trị credential (nếu nhà cung cấp dội lại nó) rồi qua bộ lọc chung;
  * lỗi HTTP không bao giờ kèm header của request.

HTTP dùng `urllib` chuẩn — không thêm phụ thuộc. `HttpClient` là một giao
thức nhỏ để CI thay bằng bản giả (`HttpGia`), nên toàn bộ đường thử kết nối
và hỏi thử chạy được không mạng, không khoá thật.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from scripts.control_center.memory.bi_mat import loc as _loc
from scripts.control_center.providers.kho_bi_mat import BiMat
from scripts.control_center.providers.preset import Preset
from scripts.control_center.providers.so import Provider

#: Ma HTTP cho thay endpoint /models khong ton tai -> thu bang chat toi thieu.
_KHONG_CO_MODELS = (404, 405, 501)
TRAN_TRICH = 300


class HttpClient:
    """`goi(method, url, headers, body, timeout) -> (status, bytes)`."""

    def goi(self, method: str, url: str, headers: Dict[str, str],
            body: Optional[bytes], timeout: float) -> Tuple[int, bytes]:  # pragma: no cover
        raise NotImplementedError


class UrllibClient(HttpClient):
    def goi(self, method, url, headers, body, timeout):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:    # noqa: S310
                return int(r.status), r.read()
        except urllib.error.HTTPError as e:
            try:
                than = e.read()
            except Exception:                                   # noqa: BLE001
                than = b""
            return int(e.code), than


class HttpGia(HttpClient):
    """Bản giả cho kiểm thử: `tra_loi(method, url, headers, body) -> (status, bytes)`."""

    def __init__(self, tra_loi: Callable[[str, str, Dict[str, str], Optional[bytes]],
                                         Tuple[int, bytes]]):
        self._f = tra_loi
        self.goi_lai: List[Dict] = []

    def goi(self, method, url, headers, body, timeout):
        # Ghi lai request KHONG kem header — chinh la dieu ma log that phai lam.
        self.goi_lai.append({"method": method, "url": url,
                             "co_xac_thuc": any(k.lower() == "authorization" or
                                                "api-key" in k.lower() for k in headers),
                             "body": body})
        return self._f(method, url, headers, body)


@dataclass
class KetQuaThu:
    ok: bool
    ma_http: int = 0
    chi_tiet: str = ""
    giay: float = 0.0
    models: List[str] = field(default_factory=list)
    cach: str = ""                      # "models" | "chat_toi_thieu" | ""
    ts: float = 0.0

    def to_dict(self) -> Dict:
        return {"ok": self.ok, "ma_http": self.ma_http, "chi_tiet": self.chi_tiet,
                "giay": round(self.giay, 3), "models": list(self.models), "cach": self.cach,
                "ts": self.ts}


@dataclass
class KetQuaHoi:
    ok: bool
    noi_dung: str = ""
    ma_http: int = 0
    chi_tiet: str = ""
    giay: float = 0.0
    model: str = ""
    usage: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"ok": self.ok, "noi_dung": self.noi_dung, "ma_http": self.ma_http,
                "chi_tiet": self.chi_tiet, "giay": round(self.giay, 3), "model": self.model,
                "usage": dict(self.usage)}


def _lam_sach(van: str, gia_tri: str = "") -> str:
    s = str(van or "")
    if gia_tri and len(gia_tri) >= 6:
        s = s.replace(gia_tri, "[DA-LOC]")
    return _loc(s)[0]


class AdapterOpenAICompat:
    def __init__(self, provider: Provider, preset: Preset, *, http: Optional[HttpClient] = None):
        self.provider = provider
        self.preset = preset
        self.http = http or UrllibClient()

    # -- url/header -----------------------------------------------------------

    @property
    def base_url(self) -> str:
        return (self.provider.base_url or self.preset.base_url_mac_dinh).rstrip("/")

    def _url(self, duong: str) -> str:
        return self.base_url + duong

    def _headers(self, gia_tri: str) -> Dict[str, str]:
        return {self.preset.header_xac_thuc: f"{self.preset.tien_to}{gia_tri}",
                "Content-Type": "application/json", "Accept": "application/json",
                "User-Agent": "router-control-center/0.6.1"}

    # -- thu ket noi ------------------------------------------------------------

    def thu_ket_noi(self, bi_mat: BiMat, *, model_goi_y: str = "",
                    timeout: float = 15.0) -> KetQuaThu:
        """Chi phí tối thiểu: GET /models (miễn phí ở mọi API OpenAI-compatible).
        Endpoint không có /models → POST chat với `max_tokens=1`."""
        t0 = time.perf_counter()
        kq = KetQuaThu(ok=False, ts=time.time())
        if not self.base_url:
            kq.chi_tiet = "thiếu base_url"
            return kq

        def _chay(gia_tri: str) -> None:
            h = self._headers(gia_tri)
            try:
                st, than = self.http.goi("GET", self._url(self.preset.duong_models), h, None,
                                         timeout)
            except Exception as exc:                            # noqa: BLE001
                kq.chi_tiet = _lam_sach(f"không kết nối được: {type(exc).__name__}: {exc}",
                                        gia_tri)[:TRAN_TRICH]
                return
            kq.ma_http = st
            if st == 200:
                kq.cach = "models"
                kq.models = _doc_models(than)
                kq.ok = True
                kq.chi_tiet = f"GET {self.preset.duong_models} 200 · {len(kq.models)} model"
                return
            if st in _KHONG_CO_MODELS:
                model = model_goi_y or (self.preset.models_goi_y[0]
                                        if self.preset.models_goi_y else "")
                if not model:
                    kq.chi_tiet = (f"GET {self.preset.duong_models} {st} và không có model "
                                   f"để thử chat tối thiểu — nhập model rồi thử lại")
                    return
                body = json.dumps({"model": model, "max_tokens": 1,
                                   "messages": [{"role": "user", "content": "ping"}]},
                                  ensure_ascii=False).encode("utf-8")
                try:
                    st2, than2 = self.http.goi("POST", self._url(self.preset.duong_chat), h,
                                               body, timeout)
                except Exception as exc:                        # noqa: BLE001
                    kq.chi_tiet = _lam_sach(f"chat tối thiểu không kết nối được: "
                                            f"{type(exc).__name__}: {exc}", gia_tri)[:TRAN_TRICH]
                    return
                kq.ma_http = st2
                kq.cach = "chat_toi_thieu"
                if st2 == 200:
                    kq.ok = True
                    kq.models = [model]
                    kq.chi_tiet = f"POST {self.preset.duong_chat} 200 (max_tokens=1, model {model})"
                else:
                    kq.chi_tiet = _lam_sach(f"chat tối thiểu HTTP {st2}: "
                                            f"{_trich(than2)}", gia_tri)[:TRAN_TRICH]
                return
            kq.chi_tiet = _lam_sach(f"HTTP {st}: {_trich(than)}", gia_tri)[:TRAN_TRICH]

        bi_mat.dung(_chay)
        kq.giay = time.perf_counter() - t0
        return kq

    # -- hoi mot cau (dinh tuyen THU CONG) ---------------------------------------

    def hoi(self, bi_mat: BiMat, *, model: str, cau: str, max_tokens: int = 128,
            timeout: float = 60.0) -> KetQuaHoi:
        """Một lượt chat completion do NGƯỚI bấm. Không phải đường AUTO."""
        t0 = time.perf_counter()
        kq = KetQuaHoi(ok=False, model=model)
        if not model:
            kq.chi_tiet = "thiếu model"
            return kq
        body = json.dumps({"model": model, "max_tokens": int(max(1, min(max_tokens, 2048))),
                           "messages": [{"role": "user", "content": str(cau)[:8000]}]},
                          ensure_ascii=False).encode("utf-8")

        def _chay(gia_tri: str) -> None:
            h = self._headers(gia_tri)
            try:
                st, than = self.http.goi("POST", self._url(self.preset.duong_chat), h, body,
                                         timeout)
            except Exception as exc:                            # noqa: BLE001
                kq.chi_tiet = _lam_sach(f"không kết nối được: {type(exc).__name__}: {exc}",
                                        gia_tri)[:TRAN_TRICH]
                return
            kq.ma_http = st
            if st != 200:
                kq.chi_tiet = _lam_sach(f"HTTP {st}: {_trich(than)}", gia_tri)[:TRAN_TRICH]
                return
            try:
                d = json.loads(than.decode("utf-8", "replace"))
                kq.noi_dung = _lam_sach(str(((d.get("choices") or [{}])[0].get("message") or {})
                                            .get("content") or ""), gia_tri)
                kq.usage = {k: v for k, v in (d.get("usage") or {}).items()
                            if isinstance(v, (int, float))}
                kq.ok = True
            except (ValueError, AttributeError, IndexError) as exc:
                kq.chi_tiet = f"phản hồi không đọc được: {type(exc).__name__}"

        bi_mat.dung(_chay)
        kq.giay = time.perf_counter() - t0
        return kq


def _trich(than: bytes) -> str:
    try:
        s = than.decode("utf-8", "replace")
    except Exception:                                           # noqa: BLE001
        return ""
    return " ".join(s.split())[:TRAN_TRICH]


def _doc_models(than: bytes) -> List[str]:
    try:
        d = json.loads(than.decode("utf-8", "replace"))
    except ValueError:
        return []
    ds = d.get("data") if isinstance(d, dict) else d
    ra: List[str] = []
    for m in ds or []:
        if isinstance(m, dict) and m.get("id"):
            ra.append(str(m["id"])[:120])
        elif isinstance(m, str):
            ra.append(m[:120])
    return sorted(set(ra))[:500]
