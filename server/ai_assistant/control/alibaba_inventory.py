"""
Kiểm kê model Alibaba Model Studio — định dạng NGOẠI TUYẾN (không gọi mạng, không đọc/ghi production, không chạm định tuyến).

Mục đích: ghi LẠI, theo từng model và có bằng chứng, những gì Owner đọc được trên console (id model chính xác, tầng năng lực, số dư
hạn mức miễn phí, hạn dùng, RPM/TPM, hỗ trợ thinking, đa phương thức, trạng thái "Free Quota Only") cùng số đo thật nếu đã benchmark,
để bước sau (tạo slot TẮT từng model rồi định tuyến theo tầng) làm bằng DỮ LIỆU chứ không bằng suy đoán.

Nguyên tắc (mỗi điều có bài kiểm):
  * KHÔNG ĐOÁN. Trường chưa biết là `None` (hoặc rỗng) — không có giá trị mặc định "hợp lý". Một model thiếu dữ liệu bắt buộc thì
    `readiness` = INCOMPLETE và `missing()` nói ĐÚNG thiếu gì; nó không bao giờ xuất ra payload slot.
  * `model_id` là chuỗi CHÍNH XÁC (không chuẩn hoá chữ hoa/thường, không điền hộ).
  * Lược đồ chặt: khoá lạ bị từ chối (một lỗi gõ tên trường không được im lặng thành "không có dữ liệu"), kiểu cứng (bool không phải số).
  * `slot_thinking` chỉ nhận `provider_default`/`off`. `on` bị TỪ CHỐI cho tới khi có ngân sách suy luận RIÊNG có giới hạn:
    đo thật (2026-10-03) cho thấy `max_output_tokens` KHÔNG chặn token suy luận ẩn (ra 1.233–1.482 token so với 247–320 khi tắt).
    Số đo của lần chạy `on` vẫn được ghi trong `observations` (đó là dữ liệu, không phải cấu hình).
  * Đơn vị hạn mức khác "tokens" (ảnh, ký tự, giây…) được GHI NHẬN nhưng model đó bị chặn khỏi định tuyến theo token (BLOCKED).
  * Không bí mật, không dữ liệu riêng của tài khoản: không có khoá, không có WorkspaceId/endpoint (endpoint chỉ được truyền lúc xuất
    payload slot).

Không import dịch vụ chạy (`service`, `store`, `providers`): chỉ hằng số + `validate_slot` của `model` — xuất payload nào cũng phải
qua chính validator của slot thật.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from server.ai_assistant.control.model import (
    CAPABILITY_TIERS, MAX_INT, MAX_QUOTA, MODEL_RE, WORKLOADS, ConfigValidationError, normalize_timestamp, slot_from_dict,
    validate_slot,
)
from server.llm_gateway.alibaba import THINKING_MODES

INVENTORY_VERSION = 1
PROVIDER = "alibaba"

STATUSES: Tuple[str, ...] = ("inventoried", "benchmarked", "validated_candidate", "rejected")
QUOTA_UNITS: Tuple[str, ...] = ("tokens", "calls", "characters", "images", "seconds")
THINKING_SUPPORT: Tuple[str, ...] = ("none", "hybrid", "thinking_only")
THINKING_DEFAULTS: Tuple[str, ...] = ("on", "off")
INPUT_MODALITIES: Tuple[str, ...] = ("text", "image", "audio", "video")
#: Trạng thái công tắc "Free Quota Only" trên CONSOLE Alibaba (rào chặn phí thật). `None` = chưa biết.
FREE_QUOTA_ONLY_STATES: Tuple[str, ...] = ("confirmed_on", "not_enabled")
#: Giá trị `slot_thinking` được phép trong kiểm kê (xem docstring đầu tệp về `on`).
SLOT_THINKING_ALLOWED: Tuple[str, ...] = tuple(m for m in THINKING_MODES if m != "on")
THINKING_ON_BLOCKED_REASON = ("slot_thinking=on chưa được phép: max_output_tokens không chặn token suy luận ẩn — cần ngân sách suy luận "
                              "RIÊNG có giới hạn trước")

READY, INCOMPLETE, BLOCKED = "READY", "INCOMPLETE", "BLOCKED"

_TOP_KEYS = {"version", "provider", "region", "captured_at", "models"}
_ENTRY_KEYS = {
    "model_id", "status", "tiers", "quota_unit", "free_quota_total", "free_quota_remaining", "free_quota_snapshot_at",
    "free_quota_expires_at", "rpm", "tpm", "thinking_support", "thinking_default", "slot_thinking", "input_modalities",
    "free_quota_only", "free_quota_only_note", "observations", "source", "notes"}
_OBS_KEYS = {"measured_at", "source", "thinking", "samples", "ttft_ms_median", "ttft_ms_max", "total_ms_median", "total_ms_max",
             "output_tokens_min", "output_tokens_max", "note"}
_REQUIRED_FOR_SLOT = ("tiers", "free_quota_remaining", "free_quota_snapshot_at", "free_quota_expires_at", "rpm", "tpm",
                      "thinking_support", "input_modalities", "free_quota_only")


class InventoryError(ConfigValidationError):
    """Một hay nhiều lỗi của tệp kiểm kê. `errors` = [{"field": "models[0].rpm", "message": ...}]."""


@dataclass(frozen=True)
class Observation:
    """Số đo THẬT của một lần benchmark (không phải số ước lượng). `thinking` = chế độ slot lúc đo."""
    measured_at: str
    source: str
    thinking: str
    samples: int
    ttft_ms_median: Optional[int] = None
    ttft_ms_max: Optional[int] = None
    total_ms_median: Optional[int] = None
    total_ms_max: Optional[int] = None
    output_tokens_min: Optional[int] = None
    output_tokens_max: Optional[int] = None
    note: str = ""


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    status: str = "inventoried"
    tiers: Tuple[str, ...] = ()
    quota_unit: str = "tokens"
    free_quota_total: Optional[int] = None
    free_quota_remaining: Optional[int] = None
    #: Thời điểm Owner ĐỌC số dư trên console (ảnh chụp, không tự cập nhật). "" = chưa biết.
    free_quota_snapshot_at: str = ""
    free_quota_expires_at: str = ""
    rpm: Optional[int] = None
    tpm: Optional[int] = None
    thinking_support: Optional[str] = None
    thinking_default: Optional[str] = None
    slot_thinking: str = "provider_default"
    input_modalities: Optional[Tuple[str, ...]] = None
    free_quota_only: Optional[str] = None
    free_quota_only_note: str = ""
    observations: Tuple[Observation, ...] = ()
    source: str = ""
    notes: str = ""

    @property
    def multimodal(self) -> Optional[bool]:
        """None = chưa biết; True nếu nhận đầu vào ngoài văn bản."""
        if self.input_modalities is None:
            return None
        return any(m != "text" for m in self.input_modalities)


@dataclass(frozen=True)
class Inventory:
    version: int
    provider: str
    region: str
    captured_at: str
    models: Tuple[ModelEntry, ...]

    def get(self, model_id: str) -> Optional[ModelEntry]:
        return next((m for m in self.models if m.model_id == model_id), None)


# ------------------------------------------------------------------------------------------------ parsing
def _err(errors: List[Dict[str, str]], field: str, message: str) -> None:
    errors.append({"field": field, "message": message})


def _opt_int(errors: List[Dict[str, str]], field: str, v: Any, lo: int = 0, hi: int = MAX_INT) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        _err(errors, field, f"để null hoặc số nguyên {lo}–{hi}")
        return None
    return v


def _text(errors: List[Dict[str, str]], field: str, v: Any, limit: int = 500) -> str:
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > limit:
        _err(errors, field, f"chuỗi tối đa {limit} ký tự")
        return ""
    return v.strip()


def _ts(errors: List[Dict[str, str]], field: str, v: Any) -> str:
    if v is None or v == "":
        return ""
    out = normalize_timestamp(v) if isinstance(v, str) else None
    if out is None:
        _err(errors, field, "thời điểm ISO-8601 CÓ múi giờ, ví dụ 2026-12-02T00:00:00+00:00")
        return ""
    return out


def _enum(errors: List[Dict[str, str]], field: str, v: Any, allowed: Tuple[str, ...], *, nullable: bool) -> Optional[str]:
    if v is None and nullable:
        return None
    if not isinstance(v, str) or v not in allowed:
        _err(errors, field, ("null hoặc " if nullable else "") + "một trong: " + ", ".join(allowed))
        return None
    return v


def _unknown_keys(errors: List[Dict[str, str]], path: str, raw: Mapping[str, Any], allowed: Iterable[str]) -> None:
    for k in sorted(set(raw) - set(allowed)):
        _err(errors, f"{path}.{k}" if path else str(k), "khoá không có trong định dạng (gõ sai tên trường?)")


def _parse_observation(errors: List[Dict[str, str]], path: str, raw: Any) -> Optional[Observation]:
    if not isinstance(raw, dict):
        _err(errors, path, "phải là object")
        return None
    _unknown_keys(errors, path, raw, _OBS_KEYS)
    thinking = _enum(errors, f"{path}.thinking", raw.get("thinking"), tuple(THINKING_MODES), nullable=False)
    samples = _opt_int(errors, f"{path}.samples", raw.get("samples"), 1)
    if samples is None and raw.get("samples") is None:
        _err(errors, f"{path}.samples", "bắt buộc (số mẫu đo)")
    source = _text(errors, f"{path}.source", raw.get("source"), 120)
    if not source:
        _err(errors, f"{path}.source", "bắt buộc (số đo lấy từ đâu)")
    measured = _ts(errors, f"{path}.measured_at", raw.get("measured_at"))
    if not measured:
        _err(errors, f"{path}.measured_at", "bắt buộc")
    nums = {k: _opt_int(errors, f"{path}.{k}", raw.get(k), 0, 10 ** 9) for k in
            ("ttft_ms_median", "ttft_ms_max", "total_ms_median", "total_ms_max", "output_tokens_min", "output_tokens_max")}
    for a, b in (("ttft_ms_median", "ttft_ms_max"), ("total_ms_median", "total_ms_max"), ("output_tokens_min", "output_tokens_max")):
        if nums[a] is not None and nums[b] is not None and nums[a] > nums[b]:
            _err(errors, f"{path}.{a}", f"không được lớn hơn {b}")
    if thinking is None or samples is None or not source or not measured:
        return None
    return Observation(measured, source, thinking, samples, note=_text(errors, f"{path}.note", raw.get("note")), **nums)


def _parse_entry(errors: List[Dict[str, str]], path: str, raw: Any) -> Optional[ModelEntry]:
    if not isinstance(raw, dict):
        _err(errors, path, "phải là object")
        return None
    _unknown_keys(errors, path, raw, _ENTRY_KEYS)
    mid = raw.get("model_id")
    if not isinstance(mid, str) or not MODEL_RE.match(mid) or ".." in mid or mid != mid.strip():
        _err(errors, f"{path}.model_id", "id model CHÍNH XÁC (1–120 ký tự A-Z a-z 0-9 . _ : / @ -), không điền hộ")
        mid = ""
    status = _enum(errors, f"{path}.status", raw.get("status", "inventoried"), STATUSES, nullable=False) or "inventoried"
    tiers_raw = raw.get("tiers", [])
    tiers: Tuple[str, ...] = ()
    if not isinstance(tiers_raw, list) or any(not isinstance(t, str) or t not in CAPABILITY_TIERS for t in tiers_raw) \
            or len(set(tiers_raw)) != len(tiers_raw):
        _err(errors, f"{path}.tiers", "danh sách, mỗi phần tử một trong " + ", ".join(CAPABILITY_TIERS) + ", không lặp")
    else:
        tiers = tuple(tiers_raw)
    unit = _enum(errors, f"{path}.quota_unit", raw.get("quota_unit", "tokens"), QUOTA_UNITS, nullable=False) or "tokens"
    support = _enum(errors, f"{path}.thinking_support", raw.get("thinking_support"), THINKING_SUPPORT, nullable=True)
    default = _enum(errors, f"{path}.thinking_default", raw.get("thinking_default"), THINKING_DEFAULTS, nullable=True)
    if support == "none" and default is not None:
        _err(errors, f"{path}.thinking_default", "model không có thinking thì để null")
    if support == "thinking_only" and default == "off":
        _err(errors, f"{path}.thinking_default", "model chỉ-thinking luôn bật")
    slot_thinking = raw.get("slot_thinking", "provider_default")
    if slot_thinking == "on":
        _err(errors, f"{path}.slot_thinking", THINKING_ON_BLOCKED_REASON)
    elif not isinstance(slot_thinking, str) or slot_thinking not in SLOT_THINKING_ALLOWED:
        _err(errors, f"{path}.slot_thinking", "một trong: " + ", ".join(SLOT_THINKING_ALLOWED))
    elif slot_thinking == "off" and support != "hybrid":
        # `off` gửi enable_thinking=false: chỉ model LAI (hybrid) mới nhận; không biết/không có thì không được ép (không đoán).
        _err(errors, f"{path}.slot_thinking", "chỉ đặt off cho model đã biết là hybrid (thinking_support=hybrid)")
    mods_raw = raw.get("input_modalities")
    mods: Optional[Tuple[str, ...]] = None
    if mods_raw is not None:
        if not isinstance(mods_raw, list) or not mods_raw or any(not isinstance(m, str) or m not in INPUT_MODALITIES for m in mods_raw) \
                or len(set(mods_raw)) != len(mods_raw):
            _err(errors, f"{path}.input_modalities", "null hoặc danh sách không rỗng, không lặp, trong " + ", ".join(INPUT_MODALITIES))
        else:
            mods = tuple(mods_raw)
    fqo = _enum(errors, f"{path}.free_quota_only", raw.get("free_quota_only"), FREE_QUOTA_ONLY_STATES, nullable=True)
    total = _opt_int(errors, f"{path}.free_quota_total", raw.get("free_quota_total"), 0, MAX_QUOTA)
    remaining = _opt_int(errors, f"{path}.free_quota_remaining", raw.get("free_quota_remaining"), 0, MAX_QUOTA)
    if total is not None and remaining is not None and remaining > total:
        _err(errors, f"{path}.free_quota_remaining", "không được lớn hơn free_quota_total")
    obs_raw = raw.get("observations", [])
    obs: List[Observation] = []
    if not isinstance(obs_raw, list) or len(obs_raw) > 20:
        _err(errors, f"{path}.observations", "danh sách, tối đa 20 mục")
    else:
        for i, o in enumerate(obs_raw):
            parsed = _parse_observation(errors, f"{path}.observations[{i}]", o)
            if parsed is not None:
                obs.append(parsed)
    return ModelEntry(
        model_id=mid, status=status, tiers=tiers, quota_unit=unit, free_quota_total=total, free_quota_remaining=remaining,
        free_quota_snapshot_at=_ts(errors, f"{path}.free_quota_snapshot_at", raw.get("free_quota_snapshot_at")),
        free_quota_expires_at=_ts(errors, f"{path}.free_quota_expires_at", raw.get("free_quota_expires_at")),
        rpm=_opt_int(errors, f"{path}.rpm", raw.get("rpm"), 1), tpm=_opt_int(errors, f"{path}.tpm", raw.get("tpm"), 1),
        thinking_support=support, thinking_default=default,
        slot_thinking=slot_thinking if isinstance(slot_thinking, str) and slot_thinking in SLOT_THINKING_ALLOWED else "provider_default",
        input_modalities=mods, free_quota_only=fqo, free_quota_only_note=_text(errors, f"{path}.free_quota_only_note", raw.get("free_quota_only_note")),
        observations=tuple(obs), source=_text(errors, f"{path}.source", raw.get("source"), 200), notes=_text(errors, f"{path}.notes", raw.get("notes"), 2000))


def parse_inventory(raw: Any) -> Inventory:
    """Kiểm tra TOÀN BỘ rồi mới báo: trả `Inventory` hoặc raise `InventoryError` với MỌI lỗi (Owner sửa một lượt)."""
    errors: List[Dict[str, str]] = []
    if not isinstance(raw, dict):
        raise InventoryError([{"field": "", "message": "tệp kiểm kê phải là một object JSON"}])
    _unknown_keys(errors, "", raw, _TOP_KEYS)
    if raw.get("version") != INVENTORY_VERSION:
        _err(errors, "version", f"phải bằng {INVENTORY_VERSION}")
    if raw.get("provider") != PROVIDER:
        _err(errors, "provider", f"phải là '{PROVIDER}'")
    region = _text(errors, "region", raw.get("region"), 60)
    captured = _ts(errors, "captured_at", raw.get("captured_at"))
    models_raw = raw.get("models")
    models: List[ModelEntry] = []
    if not isinstance(models_raw, list) or len(models_raw) > 200:
        _err(errors, "models", "danh sách, tối đa 200 model")
    else:
        seen = set()
        for i, m in enumerate(models_raw):
            entry = _parse_entry(errors, f"models[{i}]", m)
            if entry is None:
                continue
            if entry.model_id and entry.model_id in seen:
                _err(errors, f"models[{i}].model_id", "trùng id model")
            seen.add(entry.model_id)
            models.append(entry)
    if errors:
        raise InventoryError(errors)
    return Inventory(INVENTORY_VERSION, PROVIDER, region, captured, tuple(models))


def load_inventory(path: str) -> Inventory:
    with open(path, encoding="utf-8") as fh:
        return parse_inventory(json.load(fh))


# ------------------------------------------------------------------------------------------------ readiness
def missing(entry: ModelEntry) -> List[str]:
    """Tên các trường CÒN THIẾU để model này thành một slot (rỗng = đủ). Không đoán thay Owner."""
    out: List[str] = []
    for name in _REQUIRED_FOR_SLOT:
        v = getattr(entry, name)
        if v is None or v == "" or v == ():
            out.append(name)
    if entry.thinking_support in ("hybrid", "thinking_only") and entry.thinking_default is None:
        out.append("thinking_default")
    return out


def readiness(entry: ModelEntry, now: Optional[datetime] = None) -> Tuple[str, List[str]]:
    """(READY | INCOMPLETE | BLOCKED, lý do). BLOCKED thắng INCOMPLETE: dữ liệu có đủ cũng không dùng được."""
    now = now or datetime.now(timezone.utc)
    blocked: List[str] = []
    if entry.status == "rejected":
        blocked.append("status=rejected")
    if entry.quota_unit != "tokens":
        blocked.append(f"quota_unit={entry.quota_unit}: sổ hạn mức của ta đếm token, không định tuyến được theo đơn vị này")
    if entry.free_quota_expires_at:
        exp = datetime.fromisoformat(entry.free_quota_expires_at)
        if exp <= now:
            blocked.append("free_quota_expires_at đã qua")
    if entry.free_quota_remaining == 0:
        blocked.append("free_quota_remaining=0")
    if blocked:
        return BLOCKED, blocked
    gaps = missing(entry)
    if gaps:
        return INCOMPLETE, ["thiếu: " + ", ".join(gaps)]
    return READY, []


def warnings(entry: ModelEntry) -> List[str]:
    out: List[str] = []
    if entry.free_quota_only == "not_enabled":
        out.append("Free Quota Only chưa bật ở console: rào chặn phí thật nằm ngoài tầm với của ta (xem free_quota_only_note)")
    if entry.thinking_support == "hybrid" and entry.thinking_default == "on" and entry.slot_thinking != "off":
        out.append("model lai thinking MẶC ĐỊNH BẬT mà slot_thinking không phải off: sẽ tốn token suy luận ẩn")
    return out


def tier_coverage(inv: Inventory, now: Optional[datetime] = None) -> Dict[str, List[str]]:
    """Mỗi tầng -> các model READY, hạn dùng SỚM nhất đứng trước (khớp thứ tự ưu tiên hạn mức sắp hết hạn, vẫn NGỦ ĐÔNG).
    Tầng rỗng = chưa có model nào dùng được cho tầng đó (Owner cần thêm dữ liệu)."""
    out: Dict[str, List[Tuple[str, str]]] = {t: [] for t in CAPABILITY_TIERS}
    for m in inv.models:
        if readiness(m, now)[0] == READY:
            for t in m.tiers:
                out[t].append((m.free_quota_expires_at, m.model_id))
    return {t: [mid for _, mid in sorted(v)] for t, v in out.items()}


# ------------------------------------------------------------------------------------------------ slot payload
def to_slot_dict(entry: ModelEntry, *, slot_id: str, secret_ref: str, endpoint: str, label: Optional[str] = None,
                 workloads: Tuple[str, ...] = ("general",), daily_request_cap: int = 30, daily_token_cap: int = 30_000,
                 priority: int = 90, weight: int = 1, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Body cho `POST /api/admin/ai/slots`. LUÔN `enabled=False`. Chỉ model READY; ĐÃ qua `validate_slot` thật.
    `endpoint` + `secret_ref` do người gọi cấp (kiểm kê không giữ dữ liệu tài khoản/bí mật). Không bao giờ kèm thinking=on."""
    state, why = readiness(entry, now)
    if state != READY:
        raise InventoryError([{"field": entry.model_id or "model", "message": f"{state}: " + "; ".join(why)}])
    if any(w not in WORKLOADS for w in workloads):
        raise InventoryError([{"field": "workloads", "message": "workload không hợp lệ"}])
    body: Dict[str, Any] = {
        "slot_id": slot_id, "provider_type": PROVIDER, "label": label or f"Alibaba {entry.model_id}", "secret_ref": secret_ref,
        "model": entry.model_id, "enabled": False, "endpoint": endpoint, "workloads": list(workloads), "tiers": list(entry.tiers),
        "priority": priority, "weight": weight, "daily_request_cap": daily_request_cap, "daily_token_cap": daily_token_cap,
        "rpm_soft_cap": entry.rpm, "tpm_soft_cap": entry.tpm, "free_quota_remaining": entry.free_quota_remaining,
        "free_quota_expires_at": entry.free_quota_expires_at,
        # Khoá phía ta chỉ bật khi CONSOLE đã xác nhận: không bao giờ bật hộ khi chưa có rào thật.
        "free_quota_only": entry.free_quota_only == "confirmed_on",
        "thinking": entry.slot_thinking}
    validate_slot(slot_from_dict(body))
    return body


# ------------------------------------------------------------------------------------------------ CSV import
CSV_COLUMNS: Tuple[str, ...] = (
    "model_id", "status", "tiers", "quota_unit", "free_quota_total", "free_quota_remaining", "free_quota_snapshot_at",
    "free_quota_expires_at", "rpm", "tpm", "thinking_support", "thinking_default", "slot_thinking", "input_modalities",
    "free_quota_only", "free_quota_only_note", "source", "notes")
_LIST_COLUMNS = {"tiers", "input_modalities"}
_INT_COLUMNS = {"free_quota_total", "free_quota_remaining", "rpm", "tpm"}
_SUFFIX = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def parse_human_int(text: str) -> int:
    """Số như console hiển thị: "1,000,000", "992.19K", "1M", "5_000_000". Làm tròn theo console (KHÔNG chính xác tới từng token):
    người nhập phải biết điều đó. Ngoài định dạng này -> ValueError (không đoán)."""
    s = text.strip().replace(",", "").replace("_", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([KMBkmb])?", s)
    if not m:
        raise ValueError(f"không đọc được số: {text!r}")
    value = float(m.group(1)) * (_SUFFIX[m.group(2).upper()] if m.group(2) else 1)
    return int(round(value))


def from_csv(text: str, *, captured_at: str = "", region: str = "") -> Dict[str, Any]:
    """CSV (một dòng mỗi model, cột trong `CSV_COLUMNS`; ô trống = chưa biết; danh sách ngăn bằng `|`) -> dict kiểu JSON KIỂM KÊ.
    Chưa kiểm hợp lệ: gọi `parse_inventory` lên kết quả. Cột lạ -> ValueError (không im lặng bỏ qua)."""
    reader = csv.DictReader(io.StringIO(text))
    cols = [c.strip() for c in (reader.fieldnames or [])]
    unknown = [c for c in cols if c not in CSV_COLUMNS]
    if unknown:
        raise ValueError("cột không có trong định dạng: " + ", ".join(unknown))
    if "model_id" not in cols:
        raise ValueError("thiếu cột model_id")
    models: List[Dict[str, Any]] = []
    for row in reader:
        entry: Dict[str, Any] = {}
        for col in cols:
            cell = (row.get(col) or "").strip()
            if col in ("status", "quota_unit", "slot_thinking") and not cell:
                continue  # để mặc định của định dạng
            if not cell:
                entry[col] = None if col in _INT_COLUMNS or col in {"thinking_support", "thinking_default", "free_quota_only",
                                                                    "input_modalities"} else ""
                if col == "tiers":
                    entry[col] = []
                continue
            if col in _LIST_COLUMNS:
                entry[col] = [p.strip() for p in cell.split("|") if p.strip()]
            elif col in _INT_COLUMNS:
                entry[col] = parse_human_int(cell)
            else:
                entry[col] = cell
        if entry.get("model_id"):
            models.append(entry)
    return {"version": INVENTORY_VERSION, "provider": PROVIDER, "region": region, "captured_at": captured_at, "models": models}


def entry_template() -> Dict[str, Any]:
    """Khung MỘT model để Owner/Claude điền từ ảnh chụp console. `model_id` để trống có chủ ý: kiểm kê KHÔNG đoán id."""
    return {"model_id": "", "status": "inventoried", "tiers": [], "quota_unit": "tokens", "free_quota_total": None,
            "free_quota_remaining": None, "free_quota_snapshot_at": "", "free_quota_expires_at": "", "rpm": None, "tpm": None,
            "thinking_support": None, "thinking_default": None, "slot_thinking": "provider_default", "input_modalities": None,
            "free_quota_only": None, "free_quota_only_note": "", "observations": [], "source": "", "notes": ""}
