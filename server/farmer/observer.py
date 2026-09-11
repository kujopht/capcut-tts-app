"""ẢNH CHỤP QUAN SÁT ĐÃ LỌC cho Router Control Center — bản ĐỀ XUẤT.

TỆP NÀY CHƯA ĐƯỢC TRIỂN KHAI. Nó thuộc kho Fanfic (`server/farmer/
observer.py`), không thuộc kho Router — để ở đây kèm kế hoạch triển khai ở
`README.md` cùng thư mục, và CHỜ người vận hành duyệt. Xem mục "Triển khai".

VÌ SAO KHÔNG NỚI QUYỀN `status.json`:

`status.json` phần lớn là số đếm và mốc thời gian, nhưng có HAI đường dẫn
văn bản tự do của bên thứ ba chảy thẳng vào nó:

  1. `archive.detail`  <- `proc.stderr` thô của `rclone`
     (`server/farmer/drive_archive.py`, nhánh `else` của `probe()`)
  2. `lanes[*].errors[]` <- `msg[:300]` của một ngoại lệ bất kỳ
     (`LaneMetrics.note_error`)

Cả hai đều CÓ THỂ mang URL ký sẵn, tên tài khoản, hay mảnh token tuỳ vào lỗi
mà nhà cung cấp trả về. Không chứng minh được là sạch, nên không nới quyền.
Ảnh chụp này giải bài toán bằng cách khác: một DANH SÁCH CHO PHÉP chỉ gồm
siêu dữ liệu vận hành, và văn bản lỗi bị quy về một MÃ LỚP LỖI đóng.

VÌ SAO KHÔNG PHƠI `rclone.conf`: nó chứa token OAuth. Ảnh chụp chỉ nêu
BÍ DANH remote (`gdrive`) và đường dẫn chuẩn — đủ để trả lời "mirror đi đâu"
mà không để lộ thứ mở được cửa.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

#: Đường dẫn ảnh chụp. `644` CÓ CHỦ Ý: nội dung đã được lọc theo danh sách
#: cho phép nên đọc được bằng tài khoản quan sát là an toàn.
DEFAULT_OBSERVER_PATH = "/var/lib/fanfic-farmer/observability.json"
ENV_OBSERVER_PATH = "FARMER_OBSERVER_PATH"
OBSERVER_MODE = 0o644

#: Phải khớp `probe_van_hanh.TELEMETRY_SCHEMA` bên Router.
OBSERVER_SCHEMA_VERSION = 1

#: Bộ đếm của một lane được phép xuất. Tất cả đều là SỐ NGUYÊN.
LANE_COUNTERS = (
    "discovered", "deduped", "reviewed", "approved", "rejected", "produced",
    "published_candidates", "blocked_no_cover", "review_pending", "resumed",
    "audio_attached", "archived", "archive_pending", "failed",
    "skipped_quota",
)

#: Lớp lỗi ĐÓNG. Văn bản lỗi thô KHÔNG BAO GIỜ được xuất ra.
ERROR_CLASSES = (
    "", "auth_invalid_grant", "quota_exceeded", "network", "not_found",
    "permission_denied", "timeout", "rclone_missing", "disabled", "unknown",
)

_MAU_LOP_LOI = (
    ("auth_invalid_grant", r"invalid_grant|token (expired|revoked)|unauthorized|401"),
    ("quota_exceeded", r"quota|rate ?limit|429|userRateLimitExceeded"),
    ("permission_denied", r"permission denied|forbidden|403"),
    ("not_found", r"not found|404|directory not found|no such"),
    ("timeout", r"timeout|timed out|deadline exceeded"),
    ("network", r"network|connection|dns|temporary failure|unreachable|tls"),
)


def classify_error(text: str) -> str:
    """Văn bản lỗi thô -> MỘT mã trong `ERROR_CLASSES`. Không giữ chữ nào.

    Mặc định là `unknown` chứ không phải `""`: "có lỗi mà chưa phân loại
    được" và "không có lỗi" là hai chuyện khác nhau, và gộp chúng sẽ giấu
    mất một sự cố thật.
    """
    t = (text or "").strip().lower()
    if not t:
        return ""
    for ma, mau in _MAU_LOP_LOI:
        if re.search(mau, t):
            return ma
    return "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ints(d: Any, keys) -> Dict[str, int]:
    ra: Dict[str, int] = {}
    if isinstance(d, dict):
        for k in keys:
            v = d.get(k)
            if isinstance(v, bool):
                continue
            if isinstance(v, int):
                ra[k] = v
    return ra


def build_snapshot(status: Dict[str, Any], *,
                   archive_totals: Optional[Dict[str, int]] = None,
                   last_attempt_at: str = "",
                   last_success_at: str = "") -> Dict[str, Any]:
    """`status.as_dict()` -> ảnh chụp ĐÃ LỌC.

    Hàm THUẦN, không đụng đĩa — nên kiểm được bằng bài kiểm đơn vị ở cả hai
    kho. Mọi trường đi ra đều do hàm này DỰNG TƯỜNG MINH; không có nhánh nào
    chép nguyên một dict của bên gọi vào kết quả.
    """
    st = status or {}
    vong = st.get("round") or {}
    ar = st.get("archive") or {}
    lanes_in = st.get("lanes") or {}

    lanes_out: Dict[str, Any] = {}
    for ten, lm in (lanes_in.items() if isinstance(lanes_in, dict) else []):
        if not isinstance(lm, dict):
            continue
        muc = _ints(lm, LANE_COUNTERS)
        loi = lm.get("errors") or []
        muc["error_count"] = len(loi) if isinstance(loi, list) else 0
        muc["last_error_class"] = classify_error(
            str(loi[-1]) if isinstance(loi, list) and loi else "")
        lanes_out[str(ten)[:40]] = muc

    tong = archive_totals or {}
    return {
        "schema_version": OBSERVER_SCHEMA_VERSION,
        "generated_at": _now(),
        "farmer": {
            "started_at": str(st.get("started_at") or "")[:40],
            "updated_at": str(st.get("updated_at") or "")[:40],
            "healthy": bool(st.get("healthy", True)),
            # Day la chuoi tu do DUY NHAT di ra, va no do CHINH farmer viet
            # (khong phai stderr cua ben thu ba). Van cat ngan.
            "unhealthy_reason": str(st.get("unhealthy_reason") or "")[:200],
        },
        "round": {
            "number": int(vong.get("number") or 0),
            "started_at": str(vong.get("started_at") or "")[:40],
            "seconds": float(vong.get("seconds") or 0.0),
        },
        "lanes": lanes_out,
        "totals": _ints(st.get("totals"), LANE_COUNTERS),
        "quotas": _ints(st.get("quotas"), tuple(
            k for k in (st.get("quotas") or {}) if isinstance(k, str))),
        "archive": {
            # BI DANH remote, khong phai cau hinh remote.
            "remote_alias": str(ar.get("remote") or "")[:60],
            "root": str(ar.get("root") or "")[:120],
            "enabled": bool(ar.get("enabled", False)),
            "rclone_installed": bool(ar.get("rclone_installed", False)),
            "reachable": bool(ar.get("reachable", False)),
            "status": str(ar.get("status") or "")[:40],
            # `detail` THO KHONG di ra — chi mot ma lop loi.
            "last_error_class": classify_error(str(ar.get("detail") or "")),
            "last_attempt_at": str(last_attempt_at)[:40],
            "last_success_at": str(last_success_at)[:40],
            "done": int(tong.get("done") or 0),
            "pending": int(tong.get("pending") or 0),
            "failed": int(tong.get("failed") or 0),
        },
        "integrity": {"ok": bool((st.get("integrity") or {}).get("ok", True))},
    }


def observer_path() -> Path:
    return Path(os.environ.get(ENV_OBSERVER_PATH) or DEFAULT_OBSERVER_PATH)


def write_snapshot(snapshot: Dict[str, Any],
                   path: Optional[Path] = None) -> Path:
    """Ghi NGUYÊN TỬ + đặt mode `644` TRƯỚC khi `os.replace`.

    `tempfile.mkstemp` tạo tệp `600`, và `os.replace` GIỮ NGUYÊN mode của tệp
    tạm — đó chính là lý do `status.json` đang là `600`: một tác dụng phụ của
    `mkstemp`, không phải một quyết định bảo mật. Ảnh chụp này thì CẦN đọc
    được, nên phải `chmod` tường minh.
    """
    p = Path(path) if path else observer_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tam = tempfile.mkstemp(dir=str(p.parent), prefix=".observability-",
                               suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tam, OBSERVER_MODE)
        os.replace(tam, p)
    except Exception:
        try:
            os.unlink(tam)
        except OSError:
            pass
        raise
    return p


def publish(status: Dict[str, Any], **kw) -> Optional[Path]:
    """Dựng + ghi. KHÔNG BAO GIỜ ném ra ngoài.

    Quan sát không được phép làm chết vòng sản xuất: một lỗi ghi ảnh chụp
    phải im lặng chứ không được kéo theo cả farmer.
    """
    try:
        return write_snapshot(build_snapshot(status, **kw))
    except Exception:                                       # noqa: BLE001
        return None
