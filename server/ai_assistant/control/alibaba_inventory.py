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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from server.ai_assistant.control.model import (
    CAPABILITY_TIERS, MAX_INT, MAX_QUOTA, MODEL_RE, WORKLOADS, ConfigValidationError, normalize_timestamp, slot_from_dict,
    validate_slot,
)
from server.llm_gateway.alibaba import THINKING_MODES

INVENTORY_VERSION = 1
PROVIDER = "alibaba"
#: Trần số model trong một tệp kiểm kê (bảng Free Quota thật đã có 250 dòng; đặt rộng để một lần dán lớn hơn không bị từ chối vô cớ).
MAX_MODELS = 1000

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

_TOP_KEYS = {"version", "provider", "region", "captured_at", "notes", "models"}
_ENTRY_KEYS = {
    "model_id", "console_category", "status", "tiers", "quota_unit", "free_quota_total", "free_quota_remaining",
    "free_quota_snapshot_at", "free_quota_expires_at", "rpm", "tpm", "thinking_support", "thinking_default", "slot_thinking",
    "input_modalities", "free_quota_only", "free_quota_only_note", "observations", "source", "notes"}
_OBS_KEYS = {"measured_at", "source", "thinking", "samples", "ttft_ms_median", "ttft_ms_max", "total_ms_median", "total_ms_max",
             "output_tokens_min", "output_tokens_max", "note"}
_REQUIRED_FOR_SLOT = ("tiers", "quota_unit", "free_quota_remaining", "free_quota_snapshot_at", "free_quota_expires_at", "rpm", "tpm",
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
    #: Danh mục NGUYÊN VĂN trên console (ví dụ 语音模型 / 向量模型). Là BẰNG CHỨNG, không phải tầng: tầng do Owner phân loại.
    console_category: str = ""
    status: str = "inventoried"
    tiers: Tuple[str, ...] = ()
    #: Đơn vị của hạn mức miễn phí. `None` = CHƯA BIẾT (bảng console không ghi đơn vị): không được coi là token.
    quota_unit: Optional[str] = None
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
    #: Ghi chú CHUNG của cả tệp (giả định/hạn chế của nguồn dữ liệu). Không bí mật.
    notes: str = ""

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
    unit = _enum(errors, f"{path}.quota_unit", raw.get("quota_unit"), QUOTA_UNITS, nullable=True)
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
        model_id=mid, console_category=_text(errors, f"{path}.console_category", raw.get("console_category"), 60),
        status=status, tiers=tiers, quota_unit=unit, free_quota_total=total, free_quota_remaining=remaining,
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
    notes = _text(errors, "notes", raw.get("notes"), 4000)
    captured = _ts(errors, "captured_at", raw.get("captured_at"))
    models_raw = raw.get("models")
    models: List[ModelEntry] = []
    if not isinstance(models_raw, list) or len(models_raw) > MAX_MODELS:
        _err(errors, "models", f"danh sách, tối đa {MAX_MODELS} model")
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
    return Inventory(INVENTORY_VERSION, PROVIDER, region, captured, tuple(models), notes)


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
    if entry.quota_unit is not None and entry.quota_unit != "tokens":
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
    "model_id", "console_category", "status", "tiers", "quota_unit", "free_quota_total", "free_quota_remaining",
    "free_quota_snapshot_at", "free_quota_expires_at", "rpm", "tpm", "thinking_support", "thinking_default", "slot_thinking",
    "input_modalities", "free_quota_only", "free_quota_only_note", "source", "notes")
_LIST_COLUMNS = {"tiers", "input_modalities"}
_INT_COLUMNS = {"free_quota_total", "free_quota_remaining", "rpm", "tpm"}
#: Ô trống của các cột này nghĩa là "chưa biết" = null (các cột chuỗi khác trống = "").
_NULLABLE_COLUMNS = _INT_COLUMNS | {"quota_unit", "thinking_support", "thinking_default", "free_quota_only", "input_modalities"}
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
            if col in ("status", "slot_thinking") and not cell:
                continue  # để mặc định của định dạng
            if not cell:
                entry[col] = [] if col == "tiers" else (None if col in _NULLABLE_COLUMNS else "")
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
    return {"model_id": "", "console_category": "", "status": "inventoried", "tiers": [], "quota_unit": None, "free_quota_total": None,
            "free_quota_remaining": None, "free_quota_snapshot_at": "", "free_quota_expires_at": "", "rpm": None, "tpm": None,
            "thinking_support": None, "thinking_default": None, "slot_thinking": "provider_default", "input_modalities": None,
            "free_quota_only": None, "free_quota_only_note": "", "observations": [], "source": "", "notes": ""}


# ------------------------------------------------------------------------------------------------ console paste import
#: Bảng Free Quota của console (tiếng Trung) dán nguyên văn. Tiêu đề cột (lặp lại ở mỗi trang, đúng 6 dòng):
#:   模型 Code / 模型类型 / 剩余额度 / 到期时间 / 状态 / 用完即停
#: Mỗi model là một khối 3–4 dòng:
#:   <id model>    <模型类型>  |  剩 <còn lại> / 共 <tổng>  |  <YYYY/MM/DD>剩余 <N> 天  |  [已开启 | 未开启]
#: Dòng cuối là giá trị của cột `用完即停` ("dừng khi dùng hết" = Free Quota Only); cột `状态` không có chữ trong bản dán. Khối có thể THIẾU
#: dòng cuối (đo thật: hàng bị ngắt trang, và một hàng ở cuối bảng) -> cảnh báo `missing_state`, trạng thái để chưa biết — không đoán.
_CONSOLE_HEADER: Tuple[str, ...] = ("模型 Code", "模型类型", "剩余额度", "到期时间", "状态", "用完即停")
#: id model trên console luôn bắt đầu bằng CHỮ CÁI (qwen…, wan…, glm…, text-embedding…): nhờ vậy một dòng số/ngày bị hỏng (ví dụ "10K of 10K") không bị đọc
#: nhầm thành tiêu đề của một model, mà bị báo `bad_line`.
_CONSOLE_HEAD = re.compile(r"^(?P<id>[A-Za-z][A-Za-z0-9._:/@-]*)\s+(?P<category>\S.*)$")
_CONSOLE_QUOTA = re.compile(r"^剩\s*(?P<remaining>\S+)\s*/\s*共\s*(?P<total>\S+)$")
_CONSOLE_EXPIRY = re.compile(r"^(?P<y>\d{4})/(?P<m>\d{1,2})/(?P<d>\d{1,2})\s*剩余\s*(?P<days>\d+)\s*天$")
_CONSOLE_FQO = {"未开启": "not_enabled", "已开启": "confirmed_on"}
#: Trường do CONSOLE quyết định: lần dán sau làm mới chúng; mọi trường khác (tầng, RPM, TPM, thinking, số đo…) là của Owner/benchmark và KHÔNG bị ghi đè.
CONSOLE_FIELDS: Tuple[str, ...] = ("console_category", "free_quota_total", "free_quota_remaining", "free_quota_snapshot_at",
                                   "free_quota_expires_at", "free_quota_only")
CONSOLE_NOTE_MARK = "[console] "
#: Ghi chú chung của phiên bản đầu (chưa có dấu): vẫn được nhận ra và THAY, để một tệp cũ không giữ lại câu đã sai.
_LEGACY_CONSOLE_NOTE_PREFIX = "Nhập từ bảng Free Quota của console do Owner dán nguyên văn"
CONSOLE_NOTE = (CONSOLE_NOTE_MARK + "Nhập từ bảng Free Quota của console do Owner dán nguyên văn (docs/ai/alibaba_free_quota_console_paste.txt). "
                "Giới hạn của nguồn: (1) bảng KHÔNG có cột đơn vị nên quota_unit=null (đừng suy ra token; riêng qwen3.7-plus đã đối chiếu được: số dư giảm đúng "
                "bằng token ta đã tiêu); (2) '10K', '1M', '984.2K' là số làm tròn của console; (3) hạn dùng chỉ có NGÀY: lưu là 00:00 UTC của ngày đó, "
                "sớm hơn hạn thật tới ~1 ngày (thận trọng); (4) tiêu đề cột có trong bản dán; dòng cuối mỗi khối được đọc là cột `用完即停` (Free Quota Only: "
                "已开启=bật, 未开启=chưa bật), vì cột `状态` không có chữ — vị trí này là suy ra, chờ Owner xác nhận; khối thiếu dòng này thì để chưa biết; "
                "(5) ngày chụp = ngày hết hạn − (N − 1) với '剩余 N 天' (console đếm cả ngày hết hạn; kiểm chứng bằng số dư qwen3.7-plus phản ánh cả canary "
                "ngày 2026-10-03) hoặc do người gọi cấp; giờ trong ngày chưa biết (lưu 00:00 UTC); (6) console xếp một số model vào danh mục không khớp tên "
                "(ví dụ wan2.2-kf2v-flash nằm ở 大语言模型 với hạn mức 50): danh mục là bằng chứng, không phải khả năng.")


@dataclass(frozen=True)
class ConsoleParse:
    """Kết quả đọc bản dán: entry hợp lệ + MỌI vấn đề theo từng dòng (không dừng ở lỗi đầu tiên). `error` = dòng/khối không dùng được (bị loại,
    không bao giờ im lặng); `warning` = dùng được nhưng thiếu một mẩu (ví dụ không có dòng 用完即停)."""
    entries: Tuple[Dict[str, Any], ...]
    snapshot_at: str
    issues: Tuple[Dict[str, Any], ...]

    @property
    def errors(self) -> List[Dict[str, Any]]:
        return [i for i in self.issues if i["kind"] == "error"]

    @property
    def warnings(self) -> List[Dict[str, Any]]:
        return [i for i in self.issues if i["kind"] == "warning"]


def _issue(kind: str, code: str, line: int, message: str, model_id: str = "") -> Dict[str, Any]:
    return {"kind": kind, "code": code, "line": line, "model_id": model_id, "message": message}


def parse_console_free_quota(text: str, *, captured_at: str = "") -> ConsoleParse:
    """Đọc văn bản dán từ bảng Free Quota -> `ConsoleParse` (entry kiểu JSON + thời điểm chụp ISO + MỌI vấn đề theo dòng). Khối 3–4 dòng, tiêu đề cột bị
    bỏ qua, dòng lạ/số sai/ngày không tồn tại/id lặp -> `error` kèm số dòng và khối đó BỊ LOẠI (không bao giờ im lặng); thiếu dòng cuối ->
    `warning`. Không đoán: quota_unit=null, tầng=[], RPM/TPM/thinking/đa phương thức chưa biết. Văn bản rỗng -> ValueError."""
    lines = [(n, raw.strip()) for n, raw in enumerate(text.splitlines(), 1) if raw.strip()]
    if not lines:
        raise ValueError("không có dòng nào để đọc")
    issues: List[Dict[str, Any]] = []
    blocks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    def close() -> None:
        nonlocal cur
        if cur is None:
            return
        if cur["quota"] is None or cur["expiry"] is None:
            issues.append(_issue("error", "incomplete_row", cur["line"],
                                 f"model '{cur['id']}': thiếu dòng " + ("hạn mức" if cur["quota"] is None else "hạn dùng") + " (bản dán bị cắt?)", cur["id"]))
        else:
            blocks.append(cur)
        cur = None

    i = 0
    while i < len(lines):
        n, s = lines[i]
        if s == _CONSOLE_HEADER[0]:
            close()
            rest = _CONSOLE_HEADER[1:]
            if tuple(x for _, x in lines[i + 1:i + 1 + len(rest)]) == rest:
                i += len(_CONSOLE_HEADER)
                continue
            issues.append(_issue("error", "header_incomplete", n, "tiêu đề cột không đủ/sai thứ tự (cần: " + " / ".join(_CONSOLE_HEADER) + ")"))
        elif s in _CONSOLE_FQO:
            if cur is not None and cur["expiry"] is not None and cur["state"] is None:
                cur["state"], cur["state_line"] = s, n
            else:
                issues.append(_issue("error", "orphan_line", n, f"dòng trạng thái {s!r} không thuộc khối model nào"))
        elif _CONSOLE_QUOTA.match(s):
            if cur is not None and cur["quota"] is None and cur["expiry"] is None:
                cur["quota"], cur["quota_line"] = _CONSOLE_QUOTA.match(s), n
            else:
                issues.append(_issue("error", "orphan_line", n, f"dòng hạn mức không thuộc khối model nào hoặc bị lặp: {s!r}"))
        elif _CONSOLE_EXPIRY.match(s):
            if cur is not None and cur["quota"] is not None and cur["expiry"] is None:
                cur["expiry"], cur["expiry_line"] = _CONSOLE_EXPIRY.match(s), n
            else:
                issues.append(_issue("error", "orphan_line", n, f"dòng hạn dùng không thuộc khối model nào hoặc bị lặp: {s!r}"))
        elif _CONSOLE_HEAD.match(s):
            close()
            mh = _CONSOLE_HEAD.match(s)
            cur = {"id": mh["id"], "category": mh["category"].strip(), "line": n, "quota": None, "expiry": None, "state": None}
        else:
            issues.append(_issue("error", "bad_line", n, f"không nhận ra dòng: {s!r}"))
        i += 1
    close()

    entries: List[Dict[str, Any]] = []
    capture_days: Dict[str, List[str]] = {}
    seen: Dict[str, int] = {}
    for b in blocks:
        mid = b["id"]
        if mid in seen:
            issues.append(_issue("error", "duplicate_model", b["line"], f"model '{mid}' xuất hiện hai lần (lần đầu ở dòng {seen[mid]}); bản thứ hai bị loại", mid))
            continue
        try:
            remaining, total = parse_human_int(b["quota"]["remaining"]), parse_human_int(b["quota"]["total"])
        except ValueError as exc:
            issues.append(_issue("error", "bad_number", b["quota_line"], f"model '{mid}': {exc}", mid))
            continue
        if remaining > total:
            issues.append(_issue("error", "quota_over_total", b["quota_line"], f"model '{mid}': còn lại ({remaining}) lớn hơn tổng ({total})", mid))
            continue
        try:
            expires = datetime(int(b["expiry"]["y"]), int(b["expiry"]["m"]), int(b["expiry"]["d"]), tzinfo=timezone.utc)
        except ValueError:
            issues.append(_issue("error", "bad_date", b["expiry_line"], f"model '{mid}': ngày không tồn tại", mid))
            continue
        seen[mid] = b["line"]
        # Console đếm CẢ ngày hết hạn ('剩余 1 天' vào chính ngày hết hạn): ngày chụp = ngày hết hạn − (N − 1).
        capture_days.setdefault((expires - timedelta(days=int(b["expiry"]["days"]) - 1)).date().isoformat(), []).append(mid)
        entry: Dict[str, Any] = {"model_id": mid, "console_category": b["category"], "free_quota_total": total, "free_quota_remaining": remaining,
                                 "free_quota_expires_at": expires.isoformat(timespec="seconds")}
        if b["state"] is None:
            issues.append(_issue("warning", "missing_state", b["line"],
                                 f"model '{mid}': không có dòng 已开启/未开启 (cột 用完即停) — free_quota_only để chưa biết", mid))
        else:
            entry["free_quota_only"] = _CONSOLE_FQO[b["state"]]
        entries.append(entry)

    snap = ""
    if captured_at:
        snap = normalize_timestamp(captured_at) or ""
        if not snap:
            issues.append(_issue("error", "bad_captured_at", 0, "captured_at phải là ISO-8601 CÓ múi giờ"))
    elif len(capture_days) == 1:
        snap = next(iter(capture_days)) + "T00:00:00+00:00"
    elif capture_days:
        issues.append(_issue("error", "capture_day_conflict", 0, "'剩余 N 天' cho nhiều ngày chụp khác nhau (" +
                             ", ".join(f"{d}: {len(m)} model" for d, m in sorted(capture_days.items())) + ") — hãy cấp --captured-at"))
    if snap:
        for e in entries:
            e["free_quota_snapshot_at"] = snap
    return ConsoleParse(tuple(entries), snap, tuple(issues))


def raw_line_counts(text: str) -> Dict[str, Any]:
    """Đếm THÔ theo regex trên toàn văn bản (không dùng bộ đọc ở trên) — để đối chiếu độc lập số model theo danh mục."""
    heads: Dict[str, int] = {}
    for m in re.finditer(r"^[A-Za-z][A-Za-z0-9._:/@-]*[ \t]+(\S[^\r\n]*?)[ \t]*$", text, re.M):
        heads[m.group(1)] = heads.get(m.group(1), 0) + 1
    return {"heads_by_category": heads,
            "quota_lines": len(re.findall(r"^[ \t]*剩 ", text, re.M)),
            "expiry_lines": len(re.findall(r"^[ \t]*\d{4}/\d{1,2}/\d{1,2}剩余 \d+ 天", text, re.M)),
            "state_on": len(re.findall(r"^[ \t]*已开启[ \t]*$", text, re.M)),
            "state_off": len(re.findall(r"^[ \t]*未开启[ \t]*$", text, re.M)),
            "header_blocks": len(re.findall(r"^[ \t]*模型 Code[ \t]*$", text, re.M))}


def verify_console_counts(text: str, parsed: ConsoleParse) -> List[str]:
    """Đối chiếu số đếm thô với kết quả đọc. Trả danh sách điểm LỆCH (rỗng = khớp hoàn toàn): theo danh mục, tổng, dòng hạn mức/hạn dùng,
    và số dòng trạng thái = số model − số cảnh báo missing_state."""
    raw = raw_line_counts(text)
    problems: List[str] = []
    rows = sum(raw["heads_by_category"].values())
    parsed_by_cat: Dict[str, int] = {}
    for e in parsed.entries:
        parsed_by_cat[e["console_category"]] = parsed_by_cat.get(e["console_category"], 0) + 1
    if parsed_by_cat != raw["heads_by_category"]:
        problems.append(f"số model theo danh mục lệch: thô {raw['heads_by_category']} ≠ đọc {parsed_by_cat}")
    for name in ("quota_lines", "expiry_lines"):
        if raw[name] != rows:
            problems.append(f"{name}={raw[name]} ≠ số dòng tiêu đề model ({rows})")
    missing_state = len([i for i in parsed.issues if i["code"] == "missing_state"])
    if raw["state_on"] + raw["state_off"] != rows - missing_state:
        problems.append(f"dòng trạng thái ({raw['state_on'] + raw['state_off']}) ≠ model ({rows}) − thiếu trạng thái ({missing_state})")
    if len(parsed.entries) + len(parsed.errors) < rows:
        problems.append("có model bị mất mà không được báo lỗi")
    return problems


def merge_console(raw: Mapping[str, Any], entries: List[Dict[str, Any]], snapshot_at: str) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
    """Gộp các entry đọc từ console vào kiểm kê (dict kiểu JSON), KHÔNG sửa đầu vào. Model MỚI -> thêm (các trường còn lại ở mặc định 'chưa biết');
    model ĐÃ CÓ -> chỉ làm mới `CONSOLE_FIELDS`, giữ nguyên mọi thứ Owner/benchmark đã ghi. Trả (kiểm kê mới, {added, refreshed, unchanged})."""
    out = json.loads(json.dumps(raw))
    models: List[Dict[str, Any]] = out.setdefault("models", [])
    index = {m.get("model_id"): m for m in models}
    report: Dict[str, List[str]] = {"added": [], "refreshed": [], "unchanged": []}
    for e in entries:
        existing = index.get(e["model_id"])
        if existing is None:
            fresh = entry_template()
            fresh.update(e)
            fresh["source"] = "bảng Free Quota của console (Owner dán)"
            models.append(fresh)
            index[e["model_id"]] = fresh
            report["added"].append(e["model_id"])
            continue
        # Chỉ trường CÓ trong dòng đọc mới làm mới: một khối thiếu dòng 用完即停 (chưa biết bây giờ) không được xoá giá trị đã biết.
        changed = [f for f in CONSOLE_FIELDS if f in e and existing.get(f) != e.get(f)]
        old_fqo = existing.get("free_quota_only")
        for f in changed:
            existing[f] = e[f]
        if "free_quota_only" in changed and old_fqo is not None:
            stamp = (snapshot_at or "")[:10]
            existing["free_quota_only_note"] = ((existing.get("free_quota_only_note") or "") + f" | Console {stamp}: free_quota_only {old_fqo} -> "
                                                f"{existing['free_quota_only']}.").strip(" |")
        report["refreshed" if changed else "unchanged"].append(e["model_id"])
    if snapshot_at and (not out.get("captured_at") or normalize_timestamp(out["captured_at"]) is None or snapshot_at > out["captured_at"]):
        out["captured_at"] = snapshot_at
    # Ghi chú chung của lần nhập console được THAY (không nhân đôi) mỗi lần: phần ghi chú khác của Owner giữ nguyên.
    kept = [p for p in (out.get("notes") or "").split("\n")
            if p and not p.startswith(CONSOLE_NOTE_MARK) and not p.startswith(_LEGACY_CONSOLE_NOTE_PREFIX)]
    out["notes"] = "\n".join(kept + [CONSOLE_NOTE])
    return out, report
