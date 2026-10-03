"""
Báo cáo ỨNG VIÊN năng lực từ kiểm kê model Alibaba (`alibaba_inventory`) — CHỈ PHÂN TÍCH, ngoại tuyến, không mạng, không production.

Đây KHÔNG phải tầng định tuyến: `CAPABILITY_TIERS` của slot (FAST/SMART/ADVANCED/TRANSLATION/VISION/EMBEDDING, đang được bộ kiểm tra slot ở
production dùng) KHÔNG đổi và `ModelEntry.tiers` KHÔNG bị ghi. Mười hai nhóm của báo cáo
    FAST SMART ADVANCED DEEP CODING CHARACTER TRANSLATION VISION IMAGE VIDEO AUDIO EMBEDDING_RERANK
là NHÃN GỢI Ý để Owner duyệt. Mỗi gợi ý mang theo BẰNG CHỨNG và luật đã bắn:
  * `category` — danh mục console tự nói (向量模型 → vector, 语音模型 → giọng nói, 多模态模型 → đa phương thức): bằng chứng mạnh;
  * `name`     — dấu hiệu trong tên model (coder, thinking, flash, plus, max…): chỉ là GIẢ THUYẾT. Danh mục console còn xếp sai chỗ
                 (ví dụ wan2.2-kf2v-flash nằm ở 大语言模型 với hạn mức 50) nên không có gì ở đây là sự thật về khả năng.
Model không có bằng chứng nào → `unclassified` (không bị ép vào nhóm). Mọi phép phân loại là hàm thuần của (danh mục, id), nên báo cáo xác định:
cùng kiểm kê cho cùng báo cáo, và tệp Markdown đang giao được bài kiểm so lại từng ký tự.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from server.ai_assistant.control.alibaba_inventory import (
    BLOCKED, INCOMPLETE, READY, Inventory, ModelEntry, parse_console_free_quota, raw_line_counts, readiness, verify_console_counts,
)

CANDIDATE_CLASSES: Tuple[str, ...] = ("FAST", "SMART", "ADVANCED", "DEEP", "CODING", "CHARACTER", "TRANSLATION", "VISION", "IMAGE", "VIDEO", "AUDIO",
                                      "EMBEDDING_RERANK")
CATEGORY_LLM, CATEGORY_VISUAL_GEN, CATEGORY_MULTIMODAL, CATEGORY_SPEECH, CATEGORY_VECTOR = "大语言模型", "视觉模型", "多模态模型", "语音模型", "向量模型"
STRONG, WEAK = "category", "name"
BASELINE_MODEL = "qwen3.7-plus"
EXPIRING_DAYS = 7

IMAGE_TOKENS = frozenset({"image", "t2i", "i2i"})
VIDEO_TOKENS = frozenset({"t2v", "i2v", "r2v", "kf2v", "vace", "videoedit", "video", "animate", "happyhorse"})
CODING_TOKENS = frozenset({"coder", "code"})
DEEP_TOKENS = frozenset({"thinking", "qwq", "qvq"})
VISION_UNDERSTAND_TOKENS = frozenset({"vl", "ocr", "qvq"})
FAST_TOKENS = frozenset({"flash", "turbo", "lite"})

#: Luật -> mô tả (hiển thị trong báo cáo để Owner thấy gợi ý dựa vào đâu).
RULES: Dict[str, str] = {
    "C-VECTOR": "danh mục console 向量模型 (vector/embedding)",
    "C-SPEECH": "danh mục console 语音模型 (giọng nói: TTS, nhận dạng, dịch trực tiếp)",
    "C-MULTIMODAL": "danh mục console 多模态模型 (đa phương thức) — đầu vào hỗ trợ CHƯA xác nhận",
    "N-IMAGE": "tên chứa image / t2i / i2i",
    "N-VIDEO": "tên chứa t2v / i2v / r2v / kf2v / vace / videoedit / video / animate / happyhorse",
    "N-TRANSLATION": "tên chứa mt (qwen-mt-*) hoặc translate",
    "N-CODING": "tên chứa coder / code",
    "N-CHARACTER": "tên chứa character",
    "N-VISION": "tên chứa vl / ocr / qvq (hiểu ảnh)",
    "N-DEEP": "tên chứa thinking / qwq / qvq (suy luận)",
    "N-FAST": "tên chứa flash / turbo / lite (chỉ cho model văn bản tổng quát, không chuyên biệt, không suy luận)",
    "N-SMART": "tên chứa plus (bậc giữa của dòng Qwen; chỉ cho model văn bản tổng quát, không chuyên biệt, không suy luận)",
    "N-ADVANCED": "tên chứa max (bậc cao nhất của dòng Qwen; chỉ cho model văn bản tổng quát, không chuyên biệt, không suy luận)",
}


@dataclass(frozen=True)
class Candidate:
    cls: str
    rule: str
    strength: str
    note: str = ""


def _tokens(model_id: str) -> frozenset:
    return frozenset(t for t in re.split(r"[-_.:/@]+", model_id.lower()) if t)


def classify(entry: ModelEntry) -> Tuple[Candidate, ...]:
    """Các nhóm ỨNG VIÊN của một model: hàm thuần của (danh mục console, id model). Rỗng = chưa đủ bằng chứng."""
    toks = _tokens(entry.model_id)
    cat = entry.console_category
    out: List[Candidate] = []

    def add(cls: str, rule: str, strength: str, note: str = "") -> None:
        out.append(Candidate(cls, rule, strength, note))

    if cat == CATEGORY_VECTOR:
        add("EMBEDDING_RERANK", "C-VECTOR", STRONG)
    if cat == CATEGORY_SPEECH:
        add("AUDIO", "C-SPEECH", STRONG)
    if cat == CATEGORY_MULTIMODAL:
        add("VISION", "C-MULTIMODAL", STRONG, "đầu vào hỗ trợ chưa xác nhận")
        add("AUDIO", "C-MULTIMODAL", STRONG, "đầu vào hỗ trợ chưa xác nhận")
    generation = False
    if toks & IMAGE_TOKENS:
        add("IMAGE", "N-IMAGE", WEAK)
        generation = True
    if toks & VIDEO_TOKENS:
        add("VIDEO", "N-VIDEO", WEAK)
        generation = True
    translation = "mt" in toks or "translate" in entry.model_id.lower() or "livetranslate" in entry.model_id.lower()
    if translation:
        add("TRANSLATION", "N-TRANSLATION", WEAK)
    if cat == CATEGORY_LLM:
        specialized = translation or generation
        if toks & CODING_TOKENS:
            add("CODING", "N-CODING", WEAK)
            specialized = True
        if "character" in toks:
            add("CHARACTER", "N-CHARACTER", WEAK)
            specialized = True
        if toks & VISION_UNDERSTAND_TOKENS:
            add("VISION", "N-VISION", WEAK)
            specialized = True
        deep = bool(toks & DEEP_TOKENS)
        if deep:
            add("DEEP", "N-DEEP", WEAK)
        if not specialized and not deep:
            if toks & FAST_TOKENS:
                add("FAST", "N-FAST", WEAK)
            if "plus" in toks:
                add("SMART", "N-SMART", WEAK)
            if "max" in toks:
                add("ADVANCED", "N-ADVANCED", WEAK)
    return tuple(out)


def _best_strength(cands: Tuple[Candidate, ...], cls: str) -> str:
    return STRONG if any(c.cls == cls and c.strength == STRONG for c in cands) else WEAK


def _row(m: ModelEntry, cands: Tuple[Candidate, ...], as_of: datetime) -> Dict[str, Any]:
    return {"model_id": m.model_id, "console_category": m.console_category, "remaining": m.free_quota_remaining, "total": m.free_quota_total,
            "expires_at": m.free_quota_expires_at, "free_quota_only": m.free_quota_only, "quota_unit": m.quota_unit,
            "readiness": readiness(m, as_of)[0], "rules": sorted({c.rule for c in cands}),
            "classes": [c.cls for c in cands]}


def parse_section(paste_text: str) -> Dict[str, Any]:
    """Đọc lại bản dán NGUỒN và đối chiếu số đếm thô — để báo cáo nói đúng về lỗi parse thay vì khẳng định cứng."""
    parsed = parse_console_free_quota(paste_text)
    raw = raw_line_counts(paste_text)
    return {"rows_by_category": dict(sorted(raw["heads_by_category"].items())), "rows": sum(raw["heads_by_category"].values()),
            "entries": len(parsed.entries), "quota_lines": raw["quota_lines"], "expiry_lines": raw["expiry_lines"],
            "state_lines": raw["state_on"] + raw["state_off"], "header_blocks": raw["header_blocks"],
            "snapshot_at": parsed.snapshot_at,
            "errors": [{"line": i["line"], "code": i["code"], "message": i["message"]} for i in parsed.errors],
            "warnings": [{"line": i["line"], "code": i["code"], "model_id": i["model_id"]} for i in parsed.warnings],
            "count_problems": verify_console_counts(paste_text, parsed)}


def build_report(inv: Inventory, paste_text: Optional[str] = None) -> Dict[str, Any]:
    """Báo cáo ứng viên (dict kiểu JSON, xác định). Mốc thời gian là ngày chụp lớn nhất của kiểm kê — không dùng đồng hồ thật.
    `paste_text` (tuỳ chọn) = bản dán nguồn: nếu có, báo cáo đọc lại và đối chiếu số đếm thô."""
    snaps = [m.free_quota_snapshot_at for m in inv.models if m.free_quota_snapshot_at]
    as_of = datetime.fromisoformat(max(snaps or [inv.captured_at or "1970-01-01T00:00:00+00:00"]))
    classes: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CANDIDATE_CLASSES}
    unclassified: List[Dict[str, Any]] = []
    by_category: Dict[str, int] = {}
    anomalies: List[Dict[str, str]] = []
    expiring: List[Dict[str, Any]] = []
    partial: List[Dict[str, Any]] = []
    missing_state: List[str] = []
    states = {"confirmed_on": 0, "not_enabled": 0, "unknown": 0}
    readiness_counts = {READY: 0, INCOMPLETE: 0, BLOCKED: 0}
    unit_unknown = 0
    for m in sorted(inv.models, key=lambda x: x.model_id):
        cands = classify(m)
        row = _row(m, cands, as_of)
        by_category[m.console_category or "(không ghi)"] = by_category.get(m.console_category or "(không ghi)", 0) + 1
        readiness_counts[row["readiness"]] += 1
        states[m.free_quota_only or "unknown"] += 1
        if m.free_quota_only is None:
            missing_state.append(m.model_id)
        if m.quota_unit is None:
            unit_unknown += 1
        if not cands:
            unclassified.append(row)
        for cls in dict.fromkeys(c.cls for c in cands):
            classes[cls].append({**row, "strength": _best_strength(cands, cls)})
        if m.console_category == CATEGORY_LLM and any(c.cls in ("IMAGE", "VIDEO") for c in cands):
            anomalies.append({"model_id": m.model_id, "console_category": m.console_category,
                              "why": f"danh mục {CATEGORY_LLM} nhưng tên là model {'/'.join(sorted({c.cls for c in cands if c.cls in ('IMAGE', 'VIDEO')}))}; "
                                     f"hạn mức {m.free_quota_total} (không cỡ token)"})
        if m.free_quota_expires_at and m.free_quota_snapshot_at:
            left = datetime.fromisoformat(m.free_quota_expires_at) - datetime.fromisoformat(m.free_quota_snapshot_at)
            if left <= timedelta(days=EXPIRING_DAYS):
                expiring.append({"model_id": m.model_id, "expires_at": m.free_quota_expires_at, "remaining": m.free_quota_remaining})
        if m.free_quota_total is not None and m.free_quota_remaining is not None and m.free_quota_remaining < m.free_quota_total:
            partial.append({"model_id": m.model_id, "used": m.free_quota_total - m.free_quota_remaining, "total": m.free_quota_total})
    base = inv.get(BASELINE_MODEL)
    return {
        "parse": None if paste_text is None else parse_section(paste_text),
        "provider": inv.provider, "region": inv.region, "as_of": as_of.isoformat(timespec="seconds"), "models": len(inv.models),
        "by_category": dict(sorted(by_category.items())), "readiness": readiness_counts, "free_quota_only": states,
        "quota_unit_unknown": unit_unknown, "classes": classes, "unclassified": unclassified, "anomalies": anomalies,
        "expiring_soon": expiring, "partially_used": partial, "missing_free_quota_only": missing_state,
        "baseline": None if base is None else {"model_id": base.model_id, "status": base.status, "tiers": list(base.tiers),
                                               "slot_thinking": base.slot_thinking, "quota_unit": base.quota_unit,
                                               "free_quota_only": base.free_quota_only},
    }


def _ids(rows: List[Dict[str, Any]]) -> str:
    return ", ".join(f"`{r['model_id']}`" for r in rows)


def render_markdown(rep: Dict[str, Any]) -> str:
    """Markdown xác định của báo cáo (đã sắp theo id model). Tệp `docs/ai/ALIBABA_CAPABILITY_CANDIDATES.md` được sinh từ đây."""
    L: List[str] = []
    w = L.append
    w("# Báo cáo ứng viên năng lực — model Alibaba Model Studio")
    w("")
    w("> **Sinh tự động** từ `docs/ai/alibaba_model_inventory.json` và bản dán nguồn bằng `python scripts/alibaba_inventory.py candidates "
      "docs/ai/alibaba_model_inventory.json --paste docs/ai/alibaba_free_quota_console_paste.txt --md docs/ai/ALIBABA_CAPABILITY_CANDIDATES.md`."
      " Một bài kiểm so lại từng ký tự, nên đừng sửa tay.")
    w("")
    w("**Đây là GỢI Ý để Owner duyệt, không phải tầng định tuyến.** `CAPABILITY_TIERS` của slot không đổi, `tiers` của kiểm kê không bị ghi. Bằng chứng có hai bậc:")
    w("")
    w("* **category** — danh mục console tự nói (bằng chứng mạnh);")
    w("* **name** — dấu hiệu trong tên model (chỉ là giả thuyết; console còn xếp sai chỗ, xem mục 3).")
    w("")
    w(f"Mốc dữ liệu: **{rep['as_of'][:10]}** (ngày chụp bảng Free Quota) · vùng `{rep['region']}` · **{rep['models']} model**. "
      f"Mọi model đều là một mục hạn mức riêng (id + ảnh chụp riêng).")
    w("")
    w("## 1. Số model theo danh mục console")
    w("")
    w("| Danh mục console | Số model |")
    w("|---|---|")
    for cat, n in rep["by_category"].items():
        w(f"| {cat} | {n} |")
    w(f"| **Tổng** | **{rep['models']}** |")
    w("")
    r = rep["readiness"]
    fq = rep["free_quota_only"]
    w(f"Mức sẵn sàng tạo slot: READY {r[READY]} · INCOMPLETE {r[INCOMPLETE]} · BLOCKED {r[BLOCKED]}. "
      f"Free Quota Only (cột `用完即停`): bật {fq['confirmed_on']} · chưa bật {fq['not_enabled']} · chưa biết {fq['unknown']}. "
      f"**Thiếu đơn vị hạn mức: {rep['quota_unit_unknown']}/{rep['models']}** (bảng không có cột đơn vị).")
    w("")
    w("## 2. Ứng viên theo nhóm")
    w("")
    w("Một model có thể thuộc nhiều nhóm. Nhóm tổng quát FAST/SMART/ADVANCED chỉ xét model văn bản không chuyên biệt và không phải model suy luận.")
    w("")
    w("| Nhóm | Số ứng viên | Bằng chứng category | Bằng chứng name |")
    w("|---|---|---|---|")
    for cls in CANDIDATE_CLASSES:
        rows = rep["classes"][cls]
        w(f"| {cls} | {len(rows)} | {sum(1 for x in rows if x['strength'] == STRONG)} | {sum(1 for x in rows if x['strength'] == WEAK)} |")
    w("")
    base = rep["baseline"]
    if base:
        w(f"**Baseline đã kiểm chứng:** `{base['model_id']}` — {', '.join(base['tiers'])} · `thinking={base['slot_thinking']}` · trạng thái `{base['status']}` · "
          f"đơn vị `{base['quota_unit']}` · Free Quota Only `{base['free_quota_only']}`.")
        w("")
    for cls in CANDIDATE_CLASSES:
        rows = rep["classes"][cls]
        w(f"### {cls} ({len(rows)})")
        w("")
        if not rows:
            w("_Chưa có ứng viên._")
            w("")
            continue
        for strength, label in ((STRONG, "category"), (WEAK, "name")):
            sub = [x for x in rows if x["strength"] == strength]
            if sub:
                rules = sorted({rule for x in sub for rule in x["rules"] if (rule.startswith("C-") == (strength == STRONG))
                                and rule in RULES and (cls in _RULE_CLASSES.get(rule, ()))})
                w(f"* **{label}** ({len(sub)}; luật: {', '.join(f'`{x}`' for x in rules)}): {_ids(sub)}")
        on = sum(1 for x in rows if x["free_quota_only"] == "confirmed_on")
        off = sum(1 for x in rows if x["free_quota_only"] == "not_enabled")
        unk = len(rows) - on - off
        earliest = min((x["expires_at"] for x in rows if x["expires_at"]), default="")
        w(f"* Free Quota Only: bật {on} · chưa bật {off} · chưa biết {unk}; hạn dùng sớm nhất {earliest[:10] or '(không có)'}.")
        w("")
    w("### Chưa đủ bằng chứng (unclassified)")
    w("")
    if rep["unclassified"]:
        w(f"{len(rep['unclassified'])} model không khớp luật nào, không bị ép vào nhóm nào — cần model card hoặc quyết định của Owner: {_ids(rep['unclassified'])}")
    else:
        w("_Không có._")
    w("")
    w("## 3. Dòng cần chú ý")
    w("")
    p = rep["parse"]
    if p is None:
        w("**Parse:** không có bản dán nguồn để đối chiếu khi sinh báo cáo này.")
    else:
        ok = not p["errors"] and not p["count_problems"] and p["entries"] == p["rows"]
        w(f"**Parse bản dán nguồn:** {'SẠCH' if ok else 'CÓ VẤN ĐỀ'} — {p['rows']} khối model thô → {p['entries']} đọc được; dòng hạn mức {p['quota_lines']}, "
          f"dòng hạn dùng {p['expiry_lines']}, dòng trạng thái {p['state_lines']}, khối tiêu đề {p['header_blocks']}; ngày chụp suy ra {p['snapshot_at'][:10]}; "
          f"lỗi bị loại {len(p['errors'])}; cảnh báo {len(p['warnings'])}.")
        for e in p["errors"]:
            w("")
            w(f"* LỖI dòng {e['line']} `{e['code']}`: {e['message']}")
        for c in p["count_problems"]:
            w("")
            w(f"* LỆCH số đếm: {c}")
    w("")
    ms = rep["missing_free_quota_only"]
    w(f"**Thiếu dòng trạng thái `用完即停` ({len(ms)}):** " + (", ".join(f"`{x}`" for x in ms) + " — free_quota_only để chưa biết (hàng bị ngắt trang/cuối bảng)." if ms else "không có."))
    w("")
    w(f"**Thiếu đơn vị hạn mức ({rep['quota_unit_unknown']}):** bảng không có cột đơn vị. Cỡ số gợi ý nhưng KHÔNG xác nhận: `1M` ở nhóm văn bản/đa phương thức/vector giống token; "
      f"`10–200` ở nhóm ảnh/video giống số lần/ảnh/video; `10K/36K/1K/10` ở giọng nói có thể là ký tự/giây/lần. Riêng `{BASELINE_MODEL}` đã đối chiếu: số dư giảm đúng bằng token ta đã tiêu.")
    w("")
    if rep["anomalies"]:
        w("**Danh mục console không khớp tên model:**")
        w("")
        for a in rep["anomalies"]:
            w(f"* `{a['model_id']}`: {a['why']}.")
        w("")
    exp = rep["expiring_soon"]
    if exp:
        w(f"**Sắp hết hạn (≤ {EXPIRING_DAYS} ngày kể từ ngày chụp):** " + ", ".join(f"`{x['model_id']}` (hết {x['expires_at'][:10]}, còn {x['remaining']})" for x in exp)
          + " — hạn dùng chỉ có NGÀY và ta lưu 00:00 UTC của ngày đó (sớm hơn hạn thật tới ~1 ngày), nên các model này bị coi là đã hết hạn.")
        w("")
    pu = rep["partially_used"]
    if pu:
        w(f"**Đã bị tiêu một phần ({len(pu)} model):** " + ", ".join(f"`{x['model_id']}` (−{x['used']})" for x in pu)
          + f". Ta chỉ từng gọi `{BASELINE_MODEL}` (canary 2026-10-03: ~7,9K token, chỉ là một phần của mức đã tiêu): phần còn lại và mọi model khác cho thấy hạn mức này "
            f"**còn được tiêu từ nơi khác** (console, ứng dụng khác) — đúng giới hạn đã nêu ở mục 7 của `ALIBABA_PROVIDER.md`.")
        w("")
    w("## 4. Luật phân loại")
    w("")
    w("| Luật | Điều kiện |")
    w("|---|---|")
    for rid, desc in RULES.items():
        w(f"| `{rid}` | {desc} |")
    w("")
    return "\n".join(L) + "\n"


#: Luật -> các nhóm mà nó có thể sinh ra (để dòng "luật" của mỗi nhóm chỉ liệt kê luật liên quan tới nhóm đó).
_RULE_CLASSES: Dict[str, Tuple[str, ...]] = {
    "C-VECTOR": ("EMBEDDING_RERANK",), "C-SPEECH": ("AUDIO",), "C-MULTIMODAL": ("VISION", "AUDIO"), "N-IMAGE": ("IMAGE",), "N-VIDEO": ("VIDEO",),
    "N-TRANSLATION": ("TRANSLATION",), "N-CODING": ("CODING",), "N-CHARACTER": ("CHARACTER",), "N-VISION": ("VISION",), "N-DEEP": ("DEEP",),
    "N-FAST": ("FAST",), "N-SMART": ("SMART",), "N-ADVANCED": ("ADVANCED",)}
