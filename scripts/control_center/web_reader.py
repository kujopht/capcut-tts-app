# -*- coding: utf-8 -*-
"""WebReader — Router tự đọc web CÔNG KHAI, CHỈ ĐỌC, an toàn SSRF.

VÌ SAO TỒN TẠI (khuyết tật nghiệm thu tay 2026-09-10): người dùng hỏi
"https://github.com/koala73/worldmonitor/releases/tag/v2.10.0 github này là
gì?". Router tạo một việc analysis, dispatch AG02; worker `agy` headless cần
công cụ `read_url` — chế độ `--print` KHÔNG hỏi được người nên tự chối
(`tool_permission_denied`), việc FAILED sau ~17s. Đây đúng chế độ hỏng đã gặp
với `read_file`/`command`: headless không có ai để duyệt một prompt quyền.

CÁCH SỬA — GIỐNG `nguon_git`: Router có sẵn đường đọc an toàn thì ĐỌC THAY,
đưa NỘI DUNG/BẰNG CHỨNG cho model, không đưa mạng/credential. Quyền của worker
KHÔNG đổi, không `--dangerously-skip-permissions`, không cấp `read_url` bừa.

RANH GIỚI (đây là NỀN ĐỌC cho Browser Runtime sau này, KHÔNG phải browser):
đọc công khai HTTP/HTTPS, GET/HEAD, không JS, không DOM, không click, không
đăng nhập, không cookie, không header xác thực. Trả về bằng chứng có nguồn gốc.

AN TOÀN SSRF (chặn mặc định):
  * scheme ngoài http/https (file, ftp, gopher, data…),
  * URL có user:pass@,
  * host là localhost / loopback / RFC1918 / link-local / unique-local /
    metadata đám mây (169.254.169.254) / .local,
  * MỌI địa chỉ phân giải được của host bị kiểm (chặn hostname→IP riêng),
  * kết nối GHIM vào đúng IP đã kiểm (chống DNS rebinding giữa kiểm và nối),
  * mỗi bước chuyển hướng được kiểm LẠI từ đầu.
Từ chối luôn kèm LÝ DO cụ thể, không phải "hỏng" chung chung.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, quote

#: Kích thước tối đa tải về (byte). Đủ cho trang/README/JSON, chặn tải file lớn.
KICH_TOI_DA = 3 * 1024 * 1024
#: Thời gian chờ mỗi kết nối (giây).
HAN_MAC_DINH = 12.0
#: Số bước chuyển hướng tối đa.
CHUYEN_TOI_DA = 5
#: User-Agent trung thực — không giả trình duyệt.
UA = "RouterControlCenter-WebReader/0.6.1 (+read-only; public web only)"

#: Scheme duy nhất được phép.
SCHEME_CHO_PHEP = ("http", "https")

#: Tham số truy vấn giống credential — cảnh báo/loại khi thực tế.
_QP_NHAY_CAM = re.compile(
    r"^(?:access_?token|api_?key|apikey|auth|authorization|client_?secret|"
    r"password|passwd|pwd|secret|token|sig|signature|session|sessionid|sid|"
    r"x-api-key|key)$", re.I)

#: Host cấm theo TÊN (trước cả phân giải DNS).
_HOST_CAM = re.compile(
    r"^(localhost|.*\.local|.*\.internal|.*\.localdomain|ip6-localhost|"
    r"metadata|metadata\.google\.internal)$", re.I)


class SSRFLoi(ValueError):
    """URL bị từ chối vì lý do an toàn — mang lý do cụ thể (đọc được)."""


@dataclass
class KetQuaDoc:
    """Bằng chứng đọc web — có nguồn gốc, không có mạng/credential."""
    url_goc: str
    url_cuoi: str = ""
    trang_thai: int = 0
    content_type: str = ""
    van_ban: str = ""
    tieu_de: str = ""
    bam_noi_dung: str = ""          # sha256 của thân đã tải (hex)
    so_byte: int = 0
    ts: float = 0.0
    chuyen_huong: Tuple[str, ...] = ()
    nguon: str = "web"              # web | github
    ok: bool = True
    loi: str = ""

    def to_dict(self) -> Dict:
        return {"url_goc": self.url_goc, "url_cuoi": self.url_cuoi,
                "trang_thai": self.trang_thai, "content_type": self.content_type,
                "tieu_de": self.tieu_de, "bam_noi_dung": self.bam_noi_dung,
                "so_byte": self.so_byte, "ts": self.ts, "nguon": self.nguon,
                "chuyen_huong": list(self.chuyen_huong), "ok": self.ok,
                "loi": self.loi, "van_ban": self.van_ban}

    def khoi_bang_chung(self, *, gioi_han: int = 6000) -> str:
        """Khối chữ đính vào nhắc nhở Leader / hợp đồng worker."""
        if not self.ok:
            return (f"[WEB ĐỌC THẤT BẠI] {self.url_goc}\n  lý do: {self.loi}\n"
                    "  (Router đã thử đọc thay; KHÔNG dùng công cụ read_url của "
                    "agent — headless sẽ bị từ chối quyền.)")
        vb = self.van_ban[:gioi_han]
        if len(self.van_ban) > gioi_han:
            vb += "\n… (đã cắt cho vừa giới hạn)"
        cx = "" if self.url_cuoi == self.url_goc else f"\n  URL cuối: {self.url_cuoi}"
        return (f"NỘI DUNG WEB DO ROUTER ĐỌC (chỉ đọc, công khai — {self.nguon}):\n"
                f"  URL: {self.url_goc}{cx}\n"
                f"  trạng thái: {self.trang_thai} · kiểu: {self.content_type} · "
                f"{self.so_byte} byte · băm {self.bam_noi_dung[:16]}…\n"
                f"  tiêu đề: {self.tieu_de}\n--- NỘI DUNG ---\n{vb}\n--- HẾT ---\n"
                "Phân tích NGAY trên nội dung trên. KHÔNG chạy read_url/lệnh: "
                "phiên headless từ chối quyền và lượt của bạn sẽ kết thúc rỗng.")


# ------------------------------------------------------------- SSRF guard ---

def _la_ip_cong_khai(ip_str: str) -> Tuple[bool, str]:
    """`(công khai?, lý do nếu không)`. Chặn mọi dải nội bộ/đặc biệt."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"IP không hợp lệ: {ip_str}"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # Thu tu de LY DO chinh xac: metadata + link-local TRUOC is_private (o
    # Python 3.12 link-local nam trong is_private, se nuot mat nhan dung).
    if str(ip) in ("169.254.169.254", "fd00:ec2::254", "100.100.100.200"):
        return False, f"điểm metadata đám mây ({ip})"
    if ip.is_loopback:
        return False, f"địa chỉ loopback ({ip})"
    if ip.is_link_local:
        return False, f"địa chỉ link-local ({ip})"
    if ip.is_multicast:
        return False, f"địa chỉ multicast ({ip})"
    if ip.is_unspecified:
        return False, f"địa chỉ không xác định ({ip})"
    if ip.is_private:
        return False, f"địa chỉ mạng riêng RFC1918/ULA ({ip})"
    if ip.is_reserved:
        return False, f"địa chỉ dành riêng ({ip})"
    return True, ""


def kiem_url(url: str) -> Tuple[str, str, int, bool, List[str]]:
    """Kiểm một URL. Trả `(host, scheme, port, https, ip_da_kiem)` hoặc ném
    `SSRFLoi` kèm LÝ DO cụ thể. Phân giải DNS và kiểm MỌI địa chỉ."""
    u = urlsplit((url or "").strip())
    if u.scheme.lower() not in SCHEME_CHO_PHEP:
        raise SSRFLoi(f"scheme {u.scheme or '(trống)'!r} không được phép — "
                      f"chỉ http/https (không file/ftp/data/…)")
    if u.username or u.password:
        raise SSRFLoi("URL chứa thông tin đăng nhập nhúng (user:pass@) — từ chối")
    host = (u.hostname or "").strip()
    if not host:
        raise SSRFLoi("URL không có host")
    if _HOST_CAM.match(host):
        raise SSRFLoi(f"host {host!r} là tên nội bộ/loopback — từ chối")
    https = u.scheme.lower() == "https"
    port = u.port or (443 if https else 80)
    # Host la IP truc tiep?
    #
    # BAY DA VAP (bai kiem bat duoc): `SSRFLoi` la con cua `ValueError`, nen
    # dat `raise SSRFLoi` BEN TRONG mot `try/except ValueError: pass` khien
    # chinh phep tu choi bi NUOT, roi ham roi xuong nhanh phan giai DNS. Tach
    # phep THU PHAN TICH khoi phep KIEM — khong bao giu `raise` trong `try`.
    la_ip = True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        la_ip = False
    if la_ip:
        ok, ly = _la_ip_cong_khai(host)
        if not ok:
            raise SSRFLoi(f"host là IP nội bộ — {ly}")
        return host, u.scheme.lower(), port, https, [host]
    # Phan giai DNS -> kiem MOI dia chi (chan hostname tro ve IP rieng).
    try:
        thong_tin = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFLoi(f"không phân giải được host {host!r}: {exc}")
    ips = []
    for fam, _t, _p, _c, sa in thong_tin:
        ip = sa[0]
        ok, ly = _la_ip_cong_khai(ip)
        if not ok:
            raise SSRFLoi(f"host {host!r} phân giải về địa chỉ không công khai — {ly}")
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise SSRFLoi(f"host {host!r} không có địa chỉ nào")
    return host, u.scheme.lower(), port, https, ips


def _canh_bao_qp(url: str) -> List[str]:
    """Tên tham số truy vấn giống credential (để cảnh báo/không log giá trị)."""
    q = urlsplit(url).query
    return [k for k, _ in parse_qsl(q, keep_blank_values=True) if _QP_NHAY_CAM.match(k)]


# ------------------------------------------------------------- HTML text ---

class _BocText(HTMLParser):
    """Rút văn bản đọc được + <title>. Bỏ script/style/noscript/head-noise."""
    _BO = {"script", "style", "noscript", "template", "svg", "canvas"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.phan: List[str] = []
        self.tieu_de = ""
        self._trong_title = False
        self._bo_sau = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._BO:
            self._bo_sau += 1
        elif tag == "title":
            self._trong_title = True
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4",
                     "section", "article", "header", "footer"):
            self.phan.append("\n")

    def handle_endtag(self, tag):
        if tag in self._BO and self._bo_sau:
            self._bo_sau -= 1
        elif tag == "title":
            self._trong_title = False

    def handle_data(self, data):
        if self._bo_sau:
            return
        if self._trong_title:
            self.tieu_de += data
            return
        t = data.strip()
        if t:
            self.phan.append(t)

    def van_ban(self) -> str:
        ra = " ".join(x for x in " ".join(self.phan).split(" ") if x)
        # Gom nhieu xuong dong lien tiep, cat khoang trang thua.
        ra = re.sub(r"[ \t]*\n[ \t]*", "\n", " ".join(self.phan))
        ra = re.sub(r"\n{3,}", "\n\n", ra)
        ra = re.sub(r"[ \t]{2,}", " ", ra)
        return ra.strip()


def _charset_tu(content_type: str, than: bytes) -> str:
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        return m.group(1)
    m = re.search(rb'charset=["\']?([\w\-]+)', than[:2048], re.I)
    if m:
        try:
            return m.group(1).decode("ascii", "ignore")
        except Exception:                                   # noqa: BLE001
            pass
    return "utf-8"


def _trich_text(content_type: str, than: bytes) -> Tuple[str, str]:
    """`(văn bản, tiêu đề)` theo content-type."""
    cs = _charset_tu(content_type, than)
    try:
        raw = than.decode(cs, "replace")
    except (LookupError, TypeError):
        raw = than.decode("utf-8", "replace")
    ct = (content_type or "").lower()
    if "html" in ct:
        b = _BocText()
        try:
            b.feed(raw)
        except Exception:                                   # noqa: BLE001
            return raw[:KICH_TOI_DA], ""
        return b.van_ban(), b.tieu_de.strip()[:200]
    if "json" in ct:
        try:
            return json.dumps(json.loads(raw), ensure_ascii=False, indent=1), ""
        except Exception:                                   # noqa: BLE001
            return raw, ""
    return raw, ""


# ------------------------------------------------------------- tai ve -------

def _tai_mot(host: str, ip: str, port: int, https: bool, url: str,
             han: float, phuong_thuc: str = "GET") -> Tuple[int, Dict[str, str], bytes, str]:
    """Tải MỘT bước — GHIM vào `ip` đã kiểm, SNI/chứng chỉ theo `host`.

    Ghim IP chống DNS rebinding: ta đã kiểm `ip` là công khai, và nối đúng vào
    nó thay vì phân giải lại (có thể đã đổi sang IP riêng giữa kiểm và nối).
    """
    u = urlsplit(url)
    duong = urlunsplit(("", "", u.path or "/", u.query, ""))
    raw = socket.create_connection((ip, port), timeout=han)
    try:
        if https:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            sock = raw
        conn = http.client.HTTPConnection(host, port, timeout=han)
        conn.sock = sock
        conn.request(phuong_thuc, duong, headers={
            "Host": host, "User-Agent": UA, "Accept": "*/*",
            "Accept-Encoding": "identity", "Connection": "close"})
        resp = conn.getresponse()
        hdr = {k.lower(): v for k, v in resp.getheaders()}
        than = b""
        if phuong_thuc != "HEAD":
            while len(than) < KICH_TOI_DA + 1:
                khuc = resp.read(65536)
                if not khuc:
                    break
                than += khuc
            than = than[:KICH_TOI_DA]
        vi_tri = hdr.get("location", "")
        conn.close()
        return resp.status, hdr, than, vi_tri
    finally:
        try:
            raw.close()
        except Exception:                                   # noqa: BLE001
            pass


class WebReader:
    """Đọc web công khai, an toàn SSRF. Không giữ trạng thái, không ném ra
    ngoài — mọi lỗi thành `KetQuaDoc(ok=False, loi=…)`."""

    def __init__(self, *, han: float = HAN_MAC_DINH, chuyen_toi_da: int = CHUYEN_TOI_DA):
        self.han = han
        self.chuyen_toi_da = chuyen_toi_da

    def read(self, url: str) -> KetQuaDoc:
        kq = KetQuaDoc(url_goc=(url or "").strip(), ts=time.time())
        try:
            return self._doc(kq, phuong_thuc="GET")
        except SSRFLoi as exc:
            kq.ok, kq.loi = False, f"từ chối an toàn: {exc}"
            return kq
        except (socket.timeout, TimeoutError):
            kq.ok, kq.loi = False, f"hết thời gian chờ ({self.han}s)"
            return kq
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            kq.ok, kq.loi = False, f"lỗi mạng: {type(exc).__name__}: {exc}"[:200]
            return kq
        except Exception as exc:                            # noqa: BLE001
            kq.ok, kq.loi = False, f"{type(exc).__name__}: {exc}"[:200]
            return kq

    def metadata(self, url: str) -> KetQuaDoc:
        kq = KetQuaDoc(url_goc=(url or "").strip(), ts=time.time())
        try:
            return self._doc(kq, phuong_thuc="HEAD")
        except SSRFLoi as exc:
            kq.ok, kq.loi = False, f"từ chối an toàn: {exc}"
            return kq
        except Exception as exc:                            # noqa: BLE001
            kq.ok, kq.loi = False, f"{type(exc).__name__}: {exc}"[:200]
            return kq

    def extract_text(self, url: str) -> str:
        return self.read(url).van_ban

    def _doc(self, kq: KetQuaDoc, *, phuong_thuc: str) -> KetQuaDoc:
        url = kq.url_goc
        hops: List[str] = []
        for _ in range(self.chuyen_toi_da + 1):
            host, scheme, port, https, ips = kiem_url(url)
            status, hdr, than, vi_tri = _tai_mot(
                host, ips[0], port, https, url, self.han, phuong_thuc)
            if status in (301, 302, 303, 307, 308) and vi_tri:
                nxt = _giai_chuyen_huong(url, vi_tri)
                hops.append(nxt)
                if len(hops) > self.chuyen_toi_da:
                    kq.ok, kq.loi = False, f"quá {self.chuyen_toi_da} lần chuyển hướng"
                    return kq
                url = nxt
                continue
            ct = hdr.get("content-type", "")
            kq.url_cuoi = url
            kq.trang_thai = status
            kq.content_type = ct
            kq.chuyen_huong = tuple(hops)
            kq.so_byte = len(than)
            kq.bam_noi_dung = hashlib.sha256(than).hexdigest()
            if phuong_thuc != "HEAD":
                vb, td = _trich_text(ct, than)
                kq.van_ban, kq.tieu_de = vb, td
            kq.ok = 200 <= status < 400
            if not kq.ok:
                kq.loi = f"máy chủ trả {status}"
            return kq
        kq.ok, kq.loi = False, "vòng chuyển hướng"
        return kq


def _giai_chuyen_huong(goc: str, vi_tri: str) -> str:
    """Giải Location tương đối thành URL tuyệt đối (kiểm SSRF ở vòng sau)."""
    from urllib.parse import urljoin
    return urljoin(goc, vi_tri)


# =============================================== GitHub public adapter =====

_GH = re.compile(r"^(?:www\.)?github\.com$", re.I)
_GH_RAW = re.compile(r"^raw\.githubusercontent\.com$", re.I)
_API = "https://api.github.com"


def _gh_api(reader: WebReader, duong: str) -> Optional[dict]:
    kq = reader.read(_API + duong)
    if not kq.ok or "json" not in kq.content_type.lower():
        return None
    try:
        return json.loads(kq.van_ban)
    except Exception:                                       # noqa: BLE001
        return None


def doc_github(reader: WebReader, url: str) -> Optional[KetQuaDoc]:
    """Đọc URL GitHub công KHAI qua REST API công khai (không cần token) —
    sạch hơn HTML nặng JS. Trả `None` nếu không phải URL GitHub xử lý được
    (người gọi rơi về `read()` thường)."""
    u = urlsplit(url)
    host = (u.hostname or "")
    if not (_GH.match(host) or _GH_RAW.match(host)):
        return None
    if _GH_RAW.match(host):
        return None                          # raw da la text/HTTPS: read() thuong
    phan = [x for x in (u.path or "").split("/") if x]
    if len(phan) < 2:
        return None
    o, r = phan[0], phan[1]
    goc = KetQuaDoc(url_goc=url, ts=time.time(), nguon="github")

    def _dong(tieu_de: str, than: str, api_url: str) -> KetQuaDoc:
        goc.tieu_de = tieu_de[:200]
        goc.van_ban = than.strip()
        goc.url_cuoi = api_url
        goc.trang_thai = 200
        goc.content_type = "application/json (github api)"
        goc.so_byte = len(than.encode("utf-8"))
        goc.bam_noi_dung = hashlib.sha256(than.encode("utf-8")).hexdigest()
        goc.ok = True
        return goc

    # /releases/tag/<tag>  hoac /releases/tag/<tag>
    if len(phan) >= 5 and phan[2] == "releases" and phan[3] in ("tag", "tags"):
        tag = phan[4]
        d = _gh_api(reader, f"/repos/{quote(o)}/{quote(r)}/releases/tags/{quote(tag)}")
        if d:
            than = (f"Release: {d.get('name') or tag}\n"
                    f"tag: {d.get('tag_name')} · tác giả: {(d.get('author') or {}).get('login')}\n"
                    f"đăng: {d.get('published_at')} · prerelease: {d.get('prerelease')}\n\n"
                    + (d.get("body") or "(không có mô tả)"))
            return _dong(f"{o}/{r} release {d.get('tag_name') or tag}", than,
                         f"{_API}/repos/{o}/{r}/releases/tags/{tag}")
    # /releases (danh sach) -> release moi nhat
    if len(phan) >= 3 and phan[2] == "releases" and (len(phan) == 3 or phan[3] == "latest"):
        d = _gh_api(reader, f"/repos/{quote(o)}/{quote(r)}/releases/latest")
        if d:
            than = (f"Release mới nhất: {d.get('name')}\ntag: {d.get('tag_name')}\n\n"
                    + (d.get("body") or ""))
            return _dong(f"{o}/{r} release mới nhất", than,
                         f"{_API}/repos/{o}/{r}/releases/latest")
    # issue / pull
    if len(phan) >= 4 and phan[2] in ("issues", "pull"):
        num = phan[3]
        d = _gh_api(reader, f"/repos/{quote(o)}/{quote(r)}/issues/{quote(num)}")
        if d:
            than = (f"#{d.get('number')} [{d.get('state')}] {d.get('title')}\n"
                    f"tác giả: {(d.get('user') or {}).get('login')} · {d.get('created_at')}\n\n"
                    + (d.get("body") or ""))
            return _dong(f"{o}/{r} #{num}: {d.get('title','')}", than,
                         f"{_API}/repos/{o}/{r}/issues/{num}")
    # repo goc hoac /tree/... -> repo + README
    d = _gh_api(reader, f"/repos/{quote(o)}/{quote(r)}")
    if d:
        readme = ""
        rd = _gh_api(reader, f"/repos/{quote(o)}/{quote(r)}/readme")
        if rd and rd.get("content"):
            import base64
            try:
                readme = base64.b64decode(rd["content"]).decode("utf-8", "replace")[:4000]
            except Exception:                               # noqa: BLE001
                readme = ""
        than = (f"{d.get('full_name')}\n{d.get('description') or ''}\n"
                f"ngôn ngữ: {d.get('language')} · ★{d.get('stargazers_count')} · "
                f"fork {d.get('forks_count')} · cập nhật {d.get('updated_at')}\n"
                f"chủ đề: {', '.join(d.get('topics') or [])}\n\n"
                + (f"--- README ---\n{readme}" if readme else ""))
        return _dong(f"{d.get('full_name')} (repo)", than, f"{_API}/repos/{o}/{r}")
    return None


def doc_web(url: str, *, reader: Optional[WebReader] = None) -> KetQuaDoc:
    """Điểm vào chính: đọc một URL công khai, ưu tiên adapter GitHub sạch.

    Không bao giờ ném — luôn trả `KetQuaDoc` (ok=False kèm lý do khi hỏng)."""
    rd = reader or WebReader()
    u = (url or "").strip()
    # Kiem SSRF SOM cho ca duong GitHub (goi API cung qua reader da kiem, nhung
    # URL nguoi dung dua phai hop le truoc).
    try:
        kiem_url(u)
    except SSRFLoi as exc:
        return KetQuaDoc(url_goc=u, ts=time.time(), ok=False,
                         loi=f"từ chối an toàn: {exc}")
    try:
        gh = doc_github(rd, u)
        if gh is not None:
            return gh
    except Exception:                                       # noqa: BLE001
        pass
    return rd.read(u)


#: Regex rút URL http/https từ một câu người dùng.
_URL_TRONG_CAU = re.compile(r"https?://[^\s<>\"'`)\]}]+", re.I)


def rut_url(text: str, *, toi_da: int = 3) -> List[str]:
    """Các URL http/https trong một câu (đã cắt dấu câu cuối). Rỗng nếu không."""
    ra: List[str] = []
    for m in _URL_TRONG_CAU.finditer(text or ""):
        u = m.group(0).rstrip(".,;:!?")
        if u not in ra:
            ra.append(u)
        if len(ra) >= toi_da:
            break
    return ra
