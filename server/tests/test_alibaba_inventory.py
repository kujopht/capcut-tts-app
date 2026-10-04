"""
Kiểm kê model Alibaba (`server/ai_assistant/control/alibaba_inventory.py`, `scripts/alibaba_inventory.py`).

Điều phải đúng TRƯỚC khi có bất kỳ model thứ hai nào được ghi vào:
  * không đoán: trường chưa biết là null, một model thiếu dữ liệu không bao giờ ra payload slot, id model giữ nguyên chính xác;
  * lược đồ chặt (khoá lạ, kiểu sai, trùng id, tầng lạ, thời điểm không múi giờ đều bị từ chối — và báo MỌI lỗi một lượt);
  * `slot_thinking=on` bị cấm (max_output_tokens không chặn token suy luận ẩn) nhưng số đo của lần chạy `on` vẫn ghi được;
  * payload slot luôn TẮT và đi qua `validate_slot` thật; `free_quota_only` ở app chỉ bật khi console đã xác nhận;
  * tệp kiểm kê đang giao ghi qwen3.7-plus là SMART / thinking OFF, và không chứa khoá/endpoint/WorkspaceId.

Xác định (không mạng, không đồng hồ thật).
"""
from __future__ import annotations

import copy
import csv
import io
import json
import re
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path

from server.ai_assistant.control import alibaba_inventory as inv
from server.ai_assistant.control.model import CAPABILITY_TIERS, ConfigValidationError
from server.tests.test_ai_alibaba_control_plane import BASE

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "docs" / "ai" / "alibaba_model_inventory.json"
NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def full_entry(**kw):
    """Một model ĐỦ dữ liệu (dùng cho các bài về payload/sẵn sàng)."""
    base = {
        "model_id": "model-from-owner-a", "status": "benchmarked", "tiers": ["FAST"], "quota_unit": "tokens",
        "free_quota_total": 1_000_000, "free_quota_remaining": 900_000, "free_quota_snapshot_at": "2026-10-03T06:00:00+00:00",
        "free_quota_expires_at": "2026-12-02T00:00:00+00:00", "rpm": 1000, "tpm": 500_000,
        "thinking_support": "none", "thinking_default": None, "slot_thinking": "provider_default",
        "input_modalities": ["text"], "free_quota_only": "confirmed_on", "observations": []}
    base.update(kw)
    return base


def doc(*models, **kw):
    d = {"version": 1, "provider": "alibaba", "region": "ap-southeast-1", "captured_at": "2026-10-03T06:00:00+00:00",
         "models": list(models)}
    d.update(kw)
    return d


def errors_of(raw):
    with unittest.TestCase().assertRaises(inv.InventoryError) as cm:
        inv.parse_inventory(raw)
    return {e["field"]: e["message"] for e in cm.exception.errors}


class TestParsing(unittest.TestCase):
    def test_a_complete_inventory_round_trips_with_exact_ids_and_normalised_times(self) -> None:
        parsed = inv.parse_inventory(doc(full_entry(free_quota_expires_at="2026-12-02T07:00:00+07:00")))
        m = parsed.models[0]
        self.assertEqual(m.model_id, "model-from-owner-a")
        self.assertEqual(m.free_quota_expires_at, "2026-12-02T00:00:00+00:00", "múi giờ được chuẩn hoá về UTC")
        self.assertEqual((m.rpm, m.tpm, m.tiers, m.multimodal), (1000, 500_000, ("FAST",), False))
        self.assertIs(parsed.get("model-from-owner-a"), m)
        self.assertIsNone(parsed.get("MODEL-FROM-OWNER-A"), "id khớp CHÍNH XÁC, không phân biệt hoa/thường để đoán hộ")

    def test_the_model_id_is_kept_exactly_as_given_including_case_and_separators(self) -> None:
        for mid in ("Model-From-Owner-X", "vendor/Model_Name.v2:latest@3", "ABC123"):
            with self.subTest(mid):
                self.assertEqual(inv.parse_inventory(doc(full_entry(model_id=mid))).models[0].model_id, mid)

    def test_unknown_stays_unknown_and_nothing_is_filled_in(self) -> None:
        m = inv.parse_inventory(doc({"model_id": "model-from-owner-b"})).models[0]
        self.assertEqual((m.tiers, m.rpm, m.tpm, m.free_quota_remaining, m.free_quota_expires_at, m.thinking_support,
                          m.thinking_default, m.input_modalities, m.free_quota_only, m.multimodal, m.quota_unit, m.console_category),
                         ((), None, None, None, "", None, None, None, None, None, None, ""))
        self.assertEqual(m.slot_thinking, "provider_default", "mặc định an toàn, KHÔNG phải `off` đoán hộ")
        self.assertEqual(inv.readiness(m, NOW)[0], inv.INCOMPLETE)

    def test_every_error_is_reported_in_one_pass_not_one_at_a_time(self) -> None:
        errs = errors_of(doc(full_entry(tiers=["FASTER"], rpm=True, free_quota_expires_at="2026-12-02T00:00:00",
                                        quota_unit="gigabytes", typo_field=1), full_entry(model_id="bad id with spaces")))
        for key in ("models[0].tiers", "models[0].rpm", "models[0].free_quota_expires_at", "models[0].quota_unit",
                    "models[0].typo_field", "models[1].model_id"):
            self.assertIn(key, errs, key)

    def test_strict_schema_rejects_what_would_otherwise_be_silent_data_loss(self) -> None:
        cases = {
            "unknown top-level key": (doc(full_entry(), extra=1), "extra"),
            "wrong version": (doc(full_entry(), version=2), "version"),
            "wrong provider": (doc(full_entry(), provider="openai"), "provider"),
            "models not a list": (doc(full_entry(), models={}), "models"),
            "duplicate id": (doc(full_entry(), full_entry()), "models[1].model_id"),
            "empty id": (doc(full_entry(model_id="")), "models[0].model_id"),
            "id with ..": (doc(full_entry(model_id="a..b")), "models[0].model_id"),
            "id with surrounding space": (doc(full_entry(model_id=" qwen")), "models[0].model_id"),
            "lowercased tier": (doc(full_entry(tiers=["fast"])), "models[0].tiers"),
            "duplicate tier": (doc(full_entry(tiers=["FAST", "FAST"])), "models[0].tiers"),
            "bool as int": (doc(full_entry(tpm=True)), "models[0].tpm"),
            "float as int": (doc(full_entry(tpm=1.5)), "models[0].tpm"),
            "negative quota": (doc(full_entry(free_quota_remaining=-1)), "models[0].free_quota_remaining"),
            "remaining over total": (doc(full_entry(free_quota_remaining=2_000_000)), "models[0].free_quota_remaining"),
            "naive timestamp": (doc(full_entry(free_quota_snapshot_at="2026-10-03T06:00:00")), "models[0].free_quota_snapshot_at"),
            "empty modalities": (doc(full_entry(input_modalities=[])), "models[0].input_modalities"),
            "unknown modality": (doc(full_entry(input_modalities=["smell"])), "models[0].input_modalities"),
            "unknown free-quota-only state": (doc(full_entry(free_quota_only="yes")), "models[0].free_quota_only"),
            "none + default on": (doc(full_entry(thinking_support="none", thinking_default="on")), "models[0].thinking_default"),
            "thinking-only + default off": (doc(full_entry(thinking_support="thinking_only", thinking_default="off")),
                                            "models[0].thinking_default"),
        }
        for name, (raw, field) in cases.items():
            with self.subTest(name):
                self.assertIn(field, errors_of(raw))
        with self.assertRaises(inv.InventoryError):
            inv.parse_inventory([])
        self.assertTrue(issubclass(inv.InventoryError, ConfigValidationError))

    def test_all_six_capability_tiers_are_accepted_and_nothing_else(self) -> None:
        self.assertEqual(tuple(inv.CAPABILITY_TIERS), ("FAST", "SMART", "ADVANCED", "TRANSLATION", "VISION", "EMBEDDING"))
        for tier in CAPABILITY_TIERS:
            self.assertEqual(inv.parse_inventory(doc(full_entry(tiers=[tier]))).models[0].tiers, (tier,))


class TestThinkingRules(unittest.TestCase):
    def test_slot_thinking_on_is_refused_until_a_bounded_reasoning_budget_exists(self) -> None:
        errs = errors_of(doc(full_entry(thinking_support="hybrid", thinking_default="on", slot_thinking="on")))
        self.assertIn("max_output_tokens", errs["models[0].slot_thinking"])
        self.assertEqual(inv.SLOT_THINKING_ALLOWED, ("provider_default", "off"))

    def test_off_is_only_allowed_for_a_model_known_to_be_hybrid(self) -> None:
        for support in (None, "none", "thinking_only"):
            with self.subTest(support):
                self.assertIn("models[0].slot_thinking",
                              errors_of(doc(full_entry(thinking_support=support, thinking_default=None if support != "thinking_only" else "on",
                                                       slot_thinking="off"))))
        ok = inv.parse_inventory(doc(full_entry(thinking_support="hybrid", thinking_default="on", slot_thinking="off")))
        self.assertEqual(ok.models[0].slot_thinking, "off")

    def test_a_thinking_on_measurement_is_still_recordable_as_data(self) -> None:
        obs = {"measured_at": "2026-10-03T08:30:00+00:00", "source": "canary", "thinking": "on", "samples": 2,
               "ttft_ms_median": 20293, "ttft_ms_max": 21977, "output_tokens_min": 1233, "output_tokens_max": 1482}
        m = inv.parse_inventory(doc(full_entry(thinking_support="hybrid", thinking_default="on", slot_thinking="off",
                                               observations=[obs]))).models[0]
        self.assertEqual((m.observations[0].thinking, m.observations[0].output_tokens_max), ("on", 1482))

    def test_observations_need_a_source_a_time_and_a_sample_count_and_sane_ordering(self) -> None:
        good = {"measured_at": "2026-10-03T08:30:00+00:00", "source": "canary", "thinking": "off", "samples": 3}
        for name, bad in {"no source": {**good, "source": ""}, "no time": {**good, "measured_at": ""},
                          "zero samples": {**good, "samples": 0}, "missing samples": {k: v for k, v in good.items() if k != "samples"},
                          "bad mode": {**good, "thinking": "maybe"}, "median above max": {**good, "ttft_ms_median": 9, "ttft_ms_max": 3},
                          "unknown key": {**good, "p99": 1}}.items():
            with self.subTest(name):
                self.assertTrue(any(k.startswith("models[0].observations[0]") for k in errors_of(doc(full_entry(observations=[bad])))))
        self.assertEqual(inv.parse_inventory(doc(full_entry(observations=[good]))).models[0].observations[0].samples, 3)


class TestReadiness(unittest.TestCase):
    def parse(self, **kw):
        return inv.parse_inventory(doc(full_entry(**kw))).models[0]

    def test_a_complete_model_is_ready_and_a_missing_field_is_named(self) -> None:
        self.assertEqual(inv.readiness(self.parse(), NOW), (inv.READY, []))
        for field, value in (("rpm", None), ("tpm", None), ("quota_unit", None), ("free_quota_remaining", None), ("free_quota_expires_at", ""),
                             ("free_quota_snapshot_at", ""), ("input_modalities", None), ("free_quota_only", None),
                             ("thinking_support", None), ("tiers", [])):
            with self.subTest(field):
                m = self.parse(**{field: value})
                state, why = inv.readiness(m, NOW)
                self.assertEqual(state, inv.INCOMPLETE)
                self.assertIn(field, inv.missing(m))
                self.assertIn(field, why[0])

    def test_a_hybrid_model_also_needs_its_default_mode(self) -> None:
        m = self.parse(thinking_support="hybrid", thinking_default=None)
        self.assertIn("thinking_default", inv.missing(m))

    def test_blocked_beats_incomplete(self) -> None:
        for name, kw in {"expired": {"free_quota_expires_at": "2026-10-01T00:00:00+00:00"}, "exhausted": {"free_quota_remaining": 0},
                         "non-token unit": {"quota_unit": "images"}, "rejected": {"status": "rejected"}}.items():
            with self.subTest(name):
                m = self.parse(rpm=None, **kw)  # cũng thiếu rpm: BLOCKED vẫn thắng
                self.assertEqual(inv.readiness(m, NOW)[0], inv.BLOCKED)

    def test_warnings_flag_the_real_cost_guard_and_the_hidden_reasoning_default(self) -> None:
        w = inv.warnings(self.parse(free_quota_only="not_enabled", thinking_support="hybrid", thinking_default="on",
                                    slot_thinking="provider_default"))
        self.assertEqual(len(w), 2)
        self.assertEqual(inv.warnings(self.parse()), [])

    def test_tier_coverage_lists_only_ready_models_soonest_expiry_first(self) -> None:
        d = inv.parse_inventory(doc(
            full_entry(model_id="late", tiers=["FAST", "SMART"], free_quota_expires_at="2026-12-30T00:00:00+00:00"),
            full_entry(model_id="soon", tiers=["FAST"], free_quota_expires_at="2026-11-01T00:00:00+00:00"),
            full_entry(model_id="gap", tiers=["SMART"], rpm=None),
            full_entry(model_id="img", tiers=["VISION"], quota_unit="images")))
        cov = inv.tier_coverage(d, NOW)
        self.assertEqual(cov["FAST"], ["soon", "late"])
        self.assertEqual(cov["SMART"], ["late"], "model thiếu dữ liệu không được vào bảng phủ")
        self.assertEqual((cov["VISION"], cov["ADVANCED"], cov["EMBEDDING"], cov["TRANSLATION"]), ([], [], [], []))


class TestSlotPayload(unittest.TestCase):
    def entry(self, **kw):
        return inv.parse_inventory(doc(full_entry(**kw))).models[0]

    def body(self, **kw):
        return inv.to_slot_dict(self.entry(**kw), slot_id="alibaba-sg-02", secret_ref="ALIBABA_SG_02", endpoint=BASE, now=NOW)

    def test_payload_is_disabled_and_passes_the_real_slot_validator(self) -> None:
        b = self.body()
        self.assertIs(b["enabled"], False)
        self.assertEqual((b["provider_type"], b["model"], b["tiers"], b["thinking"], b["rpm_soft_cap"], b["tpm_soft_cap"]),
                         ("alibaba", "model-from-owner-a", ["FAST"], "provider_default", 1000, 500_000))
        self.assertEqual((b["free_quota_remaining"], b["free_quota_expires_at"]), (900_000, "2026-12-02T00:00:00+00:00"))
        self.assertNotIn("api_key", json.dumps(b).lower())

    def test_the_app_side_lock_follows_the_console_never_the_other_way_round(self) -> None:
        self.assertIs(self.body(free_quota_only="confirmed_on")["free_quota_only"], True)
        self.assertIs(self.body(free_quota_only="not_enabled")["free_quota_only"], False)

    def test_an_incomplete_blocked_or_unknown_model_never_produces_a_payload(self) -> None:
        for kw in ({"rpm": None}, {"free_quota_expires_at": "2026-10-01T00:00:00+00:00"}, {"quota_unit": "seconds"}, {"input_modalities": None}):
            with self.subTest(kw), self.assertRaises(inv.InventoryError):
                self.body(**kw)

    def test_the_validator_still_has_the_last_word(self) -> None:
        with self.assertRaises(ConfigValidationError):
            inv.to_slot_dict(self.entry(), slot_id="alibaba-sg-02", secret_ref="GEMINI_NOT_ALLOWED", endpoint=BASE, now=NOW)
        with self.assertRaises(ConfigValidationError):
            inv.to_slot_dict(self.entry(), slot_id="alibaba-sg-02", secret_ref="ALIBABA_SG_02", endpoint="https://evil.example.com/v1", now=NOW)
        with self.assertRaises(ConfigValidationError):
            inv.to_slot_dict(self.entry(), slot_id="alibaba-sg-02", secret_ref="ALIBABA_SG_02", endpoint=BASE, workloads=("nonsense",), now=NOW)

    def test_a_hybrid_model_keeps_thinking_off_in_its_payload(self) -> None:
        b = self.body(thinking_support="hybrid", thinking_default="on", slot_thinking="off")
        self.assertEqual(b["thinking"], "off")


class TestCsvImport(unittest.TestCase):
    HEAD = ",".join(inv.CSV_COLUMNS)

    def test_human_numbers_follow_the_console_format_and_nothing_else(self) -> None:
        for text, want in (("1,000,000", 1_000_000), ("992.19K", 992_190), ("1M", 1_000_000), ("5_000_000", 5_000_000), ("15000", 15_000),
                           (" 2.5m ", 2_500_000), ("1B", 10 ** 9)):
            self.assertEqual(inv.parse_human_int(text), want, text)
        for bad in ("", "abc", "12 K", "1e6", "-5", "1.2.3", "∞"):
            with self.subTest(bad), self.assertRaises(ValueError):
                inv.parse_human_int(bad)

    def test_csv_blank_cells_are_unknown_lists_use_pipes_and_it_round_trips(self) -> None:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(inv.CSV_COLUMNS)
        w.writerow(["model-from-owner-a", "语音模型", "", "FAST|SMART", "", "1M", "992.19K", "2026-10-03T06:00:00+00:00", "2026-12-02T00:00:00+00:00",
                    "15,000", "5M", "hybrid", "on", "off", "text|image", "not_enabled", "owner skipped", "screenshot", ""])
        w.writerow(["model-from-owner-b"] + [""] * (len(inv.CSV_COLUMNS) - 1))
        raw = inv.from_csv(buf.getvalue(), captured_at="2026-10-03T06:00:00+00:00", region="ap-southeast-1")
        d = inv.parse_inventory(raw)
        a, b = d.models
        self.assertEqual((a.tiers, a.free_quota_total, a.free_quota_remaining, a.rpm, a.tpm, a.input_modalities, a.multimodal),
                         (("FAST", "SMART"), 1_000_000, 992_190, 15_000, 5_000_000, ("text", "image"), True))
        self.assertEqual((a.status, a.quota_unit, a.slot_thinking), ("inventoried", None, "off"),
                         "ô trống = mặc định của định dạng; đơn vị trống = CHƯA BIẾT, không phải token")
        self.assertEqual((b.tiers, b.rpm, b.free_quota_remaining, b.input_modalities, b.thinking_support), ((), None, None, None, None))

    def test_csv_rejects_unknown_columns_and_garbage_numbers_instead_of_dropping_them(self) -> None:
        with self.assertRaises(ValueError):
            inv.from_csv("model_id,surprise\nx,1\n")
        with self.assertRaises(ValueError):
            inv.from_csv("rpm\n10\n")
        with self.assertRaises(ValueError):
            inv.from_csv("model_id,rpm\nmodel-x,lots\n")

    def test_a_header_only_template_file_is_valid_csv_with_the_exact_columns(self) -> None:
        template = (ROOT / "docs" / "ai" / "alibaba_model_inventory.template.csv").read_text(encoding="utf-8").strip()
        self.assertEqual(template.split(","), list(inv.CSV_COLUMNS))
        self.assertEqual(inv.from_csv(template + "\n")["models"], [])


HEADER = "模型 Code\n模型类型\n剩余额度\n到期时间\n状态\n用完即停\n"


def block(model, category, remaining, total, expiry, state="已开启"):
    """Một khối model đúng như bảng console: id+danh mục, số dư, hạn dùng, và (nếu có) giá trị cột 用完即停."""
    out = f"{model}    {category}    \n剩 {remaining} / 共 {total}\n{expiry}    \n"
    return out + (f"{state}    \n" if state else "")


PASTE_ROWS = (HEADER
              + block("qwen3.7-plus", "大语言模型", "984.2K", "1M", "2026/12/02剩余 61 天")
              + block("qwen-plus", "大语言模型", "970.67K", "1M", "2026/10/03剩余 1 天")
              + block("qwen3-tts-flash", "语音模型", "10K", "10K", "2026/12/02剩余 61 天", "未开启")
              + HEADER  # ngắt trang: tiêu đề lặp lại giữa bảng
              + block("text-embedding-v4", "向量模型", "900K", "1M", "2026/12/02剩余 61 天")
              + block("qwen-voice-design", "语音模型", "10", "10", "2026/12/02剩余 61 天", "未开启"))
GOOD = block("qwen-good", "大语言模型", "1M", "1M", "2026/12/02剩余 61 天")
GOOD2 = GOOD.replace("qwen-good", "qwen-good2")


class TestConsolePaste(unittest.TestCase):
    def test_header_blocks_and_rows_are_read_exactly_and_nothing_is_guessed(self) -> None:
        p = inv.parse_console_free_quota(PASTE_ROWS)
        self.assertEqual(p.issues, ())
        self.assertEqual(p.snapshot_at, "2026-10-03T00:00:00+00:00", "ngày chụp = ngày hết hạn − (N − 1): 12/02 còn 61 ngày và 10/03 còn 1 ngày cùng cho 10/03")
        self.assertEqual([e["model_id"] for e in p.entries],
                         ["qwen3.7-plus", "qwen-plus", "qwen3-tts-flash", "text-embedding-v4", "qwen-voice-design"])
        a, b, c, d, e = p.entries
        self.assertEqual((a["console_category"], a["free_quota_total"], a["free_quota_remaining"], a["free_quota_expires_at"], a["free_quota_only"]),
                         ("大语言模型", 1_000_000, 984_200, "2026-12-02T00:00:00+00:00", "confirmed_on"))
        self.assertEqual((b["free_quota_remaining"], b["free_quota_expires_at"]), (970_670, "2026-10-03T00:00:00+00:00"))
        self.assertEqual((c["free_quota_total"], c["free_quota_only"], d["console_category"], e["free_quota_total"]), (10_000, "not_enabled", "向量模型", 10))
        for ent in p.entries:
            for unknown in ("tiers", "quota_unit", "rpm", "tpm", "thinking_support", "input_modalities", "slot_thinking"):
                self.assertNotIn(unknown, ent, "bản dán không có thông tin này: không được điền hộ")
            self.assertEqual(ent["free_quota_snapshot_at"], p.snapshot_at)

    def test_a_block_without_the_last_line_is_a_warning_and_the_state_stays_unknown(self) -> None:
        text = HEADER + block("qwen3.6-plus-2026-04-02", "大语言模型", "1M", "1M", "2026/12/02剩余 61 天", None) \
            + HEADER + block("qwen3.8-max", "大语言模型", "1M", "1M", "2026/12/02剩余 61 天")
        p = inv.parse_console_free_quota(text)
        self.assertEqual(p.errors, [])
        self.assertEqual([(i["code"], i["line"], i["model_id"]) for i in p.warnings], [("missing_state", 7, "qwen3.6-plus-2026-04-02")])
        first, second = p.entries
        self.assertNotIn("free_quota_only", first, "không có dòng 用完即停 => chưa biết, KHÔNG đoán")
        self.assertEqual(second["free_quota_only"], "confirmed_on")

    def test_capture_day_counts_the_expiry_day_inclusively_and_explicit_time_wins(self) -> None:
        self.assertEqual(inv.parse_console_free_quota(HEADER + block("qwen-x", "大语言模型", "1M", "1M", "2026/10/03剩余 1 天")).snapshot_at,
                         "2026-10-03T00:00:00+00:00")
        conflict = inv.parse_console_free_quota(PASTE_ROWS.replace("2026/10/03剩余 1 天", "2026/10/08剩余 1 天"))
        self.assertEqual(conflict.snapshot_at, "")
        self.assertEqual([i["code"] for i in conflict.errors], ["capture_day_conflict"])
        self.assertIn("2026-10-08", conflict.errors[0]["message"])
        explicit = inv.parse_console_free_quota(PASTE_ROWS.replace("2026/10/03剩余 1 天", "2026/10/08剩余 1 天"), captured_at="2026-10-04T03:00:00+07:00")
        self.assertEqual((explicit.snapshot_at, explicit.errors), ("2026-10-03T20:00:00+00:00", []))
        bad = inv.parse_console_free_quota(PASTE_ROWS, captured_at="2026-10-04T03:00:00")  # không múi giờ
        self.assertEqual([i["code"] for i in bad.errors], ["bad_captured_at"])

    def test_every_malformed_block_is_reported_with_its_line_and_dropped_never_silent(self) -> None:
        x = block("qwen-x", "大语言模型", "1M", "1M", "2026/12/02剩余 61 天")
        cases = {
            "unreadable quota line": (x.replace("剩 1M / 共 1M", "1M of 1M"), "bad_line", True),
            "unreadable expiry line": (x.replace("2026/12/02剩余 61 天", "2026-12-02 61 days"), "bad_line", True),
            "impossible date": (x.replace("2026/12/02", "2026/13/45"), "bad_date", True),
            "garbage number": (x.replace("剩 1M / 共 1M", "剩 lots / 共 1M"), "bad_number", True),
            "remaining above total": (x.replace("剩 1M / 共 1M", "剩 2M / 共 1M"), "quota_over_total", True),
            "truncated after the quota line": ("\n".join(x.split("\n")[:2]) + "\n", "incomplete_row", True),
            "duplicate model": (x + x, "duplicate_model", False),
            "stray state line": (x + "已开启\n", "orphan_line", False),
            "stray quota line": (x + "剩 1M / 共 1M\n", "orphan_line", False),
            "digit-leading id read as a header": (x.replace("qwen-x", "10K"), "bad_line", True),
            "incomplete header": ("模型 Code\n模型类型\n" + x, "header_incomplete", False),
            "unknown state text": (x.replace("已开启", "也许"), "bad_line", False),
        }
        for name, (text, code, dropped) in cases.items():
            with self.subTest(name):
                p = inv.parse_console_free_quota(HEADER + GOOD + text + GOOD2)
                self.assertIn(code, [i["code"] for i in p.errors], [i["code"] for i in p.issues])
                for i in p.errors:
                    self.assertTrue(i["message"])
                    self.assertGreater(i["line"], 0)
                ids = [e["model_id"] for e in p.entries]
                self.assertIn("qwen-good", ids)
                self.assertIn("qwen-good2", ids, "một khối hỏng không được làm mất các khối lành")
                if dropped:
                    self.assertNotIn("qwen-x", ids)
        p = inv.parse_console_free_quota(HEADER + GOOD + cases["unreadable quota line"][0] + GOOD2)
        self.assertIn(("bad_line", 12), [(i["code"], i["line"]) for i in p.errors], "header 6 dòng + khối lành 4 dòng => dòng hạn mức hỏng là dòng 12")
        with self.assertRaises(ValueError):
            inv.parse_console_free_quota("  \n\n")

    def test_counts_are_verified_independently_of_the_reader(self) -> None:
        p = inv.parse_console_free_quota(PASTE_ROWS)
        self.assertEqual(inv.verify_console_counts(PASTE_ROWS, p), [])
        raw = inv.raw_line_counts(PASTE_ROWS)
        self.assertEqual(raw["heads_by_category"], {"大语言模型": 2, "语音模型": 2, "向量模型": 1})
        self.assertEqual((raw["quota_lines"], raw["expiry_lines"], raw["state_on"], raw["state_off"], raw["header_blocks"]), (5, 5, 3, 2, 2))
        lost = inv.ConsoleParse(p.entries[1:], p.snapshot_at, p.issues)  # một model "biến mất" mà không được báo
        problems = inv.verify_console_counts(PASTE_ROWS, lost)
        self.assertTrue(any("danh mục" in x for x in problems), problems)
        text = PASTE_ROWS + block("qwen-y", "大语言模型", "1M", "1M", "2026/12/02剩余 61 天", None)
        q = inv.parse_console_free_quota(text)
        self.assertEqual(inv.verify_console_counts(text, q), [], "thiếu dòng trạng thái đã được tính vào đối chiếu (cảnh báo missing_state)")

    def test_merge_adds_new_models_and_refreshes_only_what_the_console_decides(self) -> None:
        base = doc(full_entry(model_id="qwen3-tts-flash", tiers=["FAST"], rpm=777, observations=[], notes="tay",
                              free_quota_remaining=5, free_quota_total=10_000, free_quota_only="confirmed_on"),
                   full_entry(model_id="qwen-voice-design", free_quota_only="confirmed_on"), notes="Ghi chú của Owner.\n" + inv._LEGACY_CONSOLE_NOTE_PREFIX + " cũ")
        snapshot = json.dumps(base, sort_keys=True)
        p = inv.parse_console_free_quota(PASTE_ROWS + block("qwen-voice-design", "语音模型", "10", "10", "2026/12/02剩余 61 天", None).replace("qwen-voice-design", "qwen-voice-x"))
        merged, rep = inv.merge_console(base, list(p.entries), p.snapshot_at)
        self.assertEqual(json.dumps(base, sort_keys=True), snapshot, "đầu vào không bị sửa")
        self.assertEqual(rep["added"], ["qwen3.7-plus", "qwen-plus", "text-embedding-v4", "qwen-voice-x"])
        self.assertEqual(rep["refreshed"], ["qwen3-tts-flash", "qwen-voice-design"])
        mine = next(m for m in merged["models"] if m["model_id"] == "qwen3-tts-flash")
        self.assertEqual((mine["free_quota_remaining"], mine["free_quota_only"], mine["console_category"]), (10_000, "not_enabled", "语音模型"),
                         "console làm mới số dư/Free Quota Only/danh mục")
        self.assertEqual((mine["tiers"], mine["rpm"], mine["notes"], mine["quota_unit"]), (["FAST"], 777, "tay", "tokens"),
                         "tầng/RPM/ghi chú/đơn vị do Owner ghi KHÔNG bị ghi đè")
        self.assertIn("confirmed_on -> not_enabled", mine["free_quota_only_note"], "đổi trạng thái Free Quota Only được ghi lại, không âm thầm")
        new = next(m for m in merged["models"] if m["model_id"] == "text-embedding-v4")
        self.assertEqual((new["tiers"], new["quota_unit"], new["rpm"], new["status"]), ([], None, None, "inventoried"))
        nostate = next(m for m in merged["models"] if m["model_id"] == "qwen-voice-x")
        self.assertIsNone(nostate["free_quota_only"], "khối thiếu dòng 用完即停: chưa biết")
        self.assertEqual(merged["notes"].split("\n")[0], "Ghi chú của Owner.", "ghi chú của Owner được giữ")
        self.assertEqual(len([n for n in merged["notes"].split("\n") if n.startswith(inv.CONSOLE_NOTE_MARK)]), 1)
        self.assertNotIn("cũ", merged["notes"], "ghi chú console phiên bản đầu bị thay")
        again, rep2 = inv.merge_console(merged, list(p.entries), p.snapshot_at)
        self.assertEqual((rep2["added"], rep2["refreshed"], len(rep2["unchanged"])), ([], [], 6), "chạy lại là idempotent")
        self.assertEqual(again, merged)
        inv.parse_inventory(again)

    def test_a_block_that_now_lacks_the_state_never_erases_a_known_one(self) -> None:
        base = doc(full_entry(model_id="qwen-y", free_quota_only="confirmed_on"))
        p = inv.parse_console_free_quota(HEADER + block("qwen-y", "大语言模型", "1M", "1M", "2026/12/02剩余 61 天", None))
        merged, rep = inv.merge_console(base, list(p.entries), p.snapshot_at)
        self.assertEqual(merged["models"][0]["free_quota_only"], "confirmed_on")
        self.assertEqual(rep["refreshed"], ["qwen-y"])

    def test_every_pasted_model_stays_incomplete_until_the_owner_supplies_the_rest(self) -> None:
        p = inv.parse_console_free_quota(PASTE_ROWS)
        merged, _ = inv.merge_console(doc(), list(p.entries), p.snapshot_at)
        parsed = inv.parse_inventory(merged)
        for m in parsed.models:
            state, why = inv.readiness(m, NOW)
            self.assertIn(state, (inv.INCOMPLETE, inv.BLOCKED), m.model_id)
            for field in ("tiers", "quota_unit", "rpm", "tpm", "thinking_support", "input_modalities"):
                self.assertIn(field, inv.missing(m), (m.model_id, field))
            with self.assertRaises(inv.InventoryError):
                inv.to_slot_dict(m, slot_id="alibaba-sg-02", secret_ref="ALIBABA_SG_02", endpoint=BASE, now=NOW)
        self.assertEqual(inv.readiness(parsed.get("qwen-plus"), datetime(2026, 10, 4, tzinfo=timezone.utc))[0], inv.BLOCKED,
                         "hạn dùng 2026-10-03 (00:00 UTC, thận trọng) đã qua")


class TestShippedInventory(unittest.TestCase):
    """Tệp đang giao: qwen3.7-plus phải còn là SMART / thinking OFF, và không chứa dữ liệu tài khoản/bí mật."""

    def setUp(self) -> None:
        self.raw = SHIPPED.read_text(encoding="utf-8")
        self.inv = inv.parse_inventory(json.loads(self.raw))

    def test_qwen37_plus_is_recorded_as_smart_with_thinking_off(self) -> None:
        m = self.inv.get("qwen3.7-plus")
        self.assertIsNotNone(m)
        self.assertEqual((m.tiers, m.slot_thinking, m.status), (("SMART",), "off", "validated_candidate"))
        self.assertEqual((m.thinking_support, m.thinking_default, m.rpm, m.tpm), ("hybrid", "on", 15_000, 5_000_000))
        self.assertEqual((m.free_quota_total, m.free_quota_remaining, m.free_quota_expires_at), (1_000_000, 984_200, "2026-12-02T00:00:00+00:00"))
        self.assertEqual((m.free_quota_snapshot_at, m.quota_unit), ("2026-10-03T00:00:00+00:00", "tokens"))
        self.assertEqual(m.free_quota_only, "confirmed_on", "bảng đầy đủ: cột 用完即停 của qwen3.7-plus = 已开启 (trước đó Owner chưa bật)")
        self.assertIn("confirmed_on", m.free_quota_only_note)
        self.assertIn("VẪN là false", m.free_quota_only_note, "cờ phía ứng dụng của slot chưa đổi")

    def test_the_canary_measurements_and_the_reasoning_finding_are_on_record(self) -> None:
        by_mode = {o.thinking: o for o in self.inv.get("qwen3.7-plus").observations}
        self.assertEqual(set(by_mode), {"off", "on"})
        self.assertGreater(by_mode["on"].output_tokens_min, by_mode["off"].output_tokens_max * 2, "suy luận ẩn tốn token gấp nhiều lần")
        self.assertGreater(by_mode["on"].ttft_ms_median, by_mode["off"].ttft_ms_max * 5)
        self.assertIn("max_output_tokens", by_mode["on"].note)
        self.assertIn("KHÔNG chặn", by_mode["on"].note)

    def test_it_does_not_pretend_to_know_what_was_not_captured(self) -> None:
        m = self.inv.get("qwen3.7-plus")
        self.assertIsNone(m.input_modalities, "đa phương thức chưa được ghi nhận: không đoán")
        state, why = inv.readiness(m, NOW)
        self.assertEqual(state, inv.INCOMPLETE)
        self.assertIn("input_modalities", why[0])

    def test_the_pasted_console_table_is_in_the_inventory_exactly_and_cannot_drift_from_its_source(self) -> None:
        paste = (ROOT / "docs" / "ai" / "alibaba_free_quota_console_paste.txt").read_text(encoding="utf-8")
        p = inv.parse_console_free_quota(paste)
        self.assertEqual((len(p.entries), p.errors, len(p.warnings), p.snapshot_at), (249, [], 2, "2026-10-03T00:00:00+00:00"))
        self.assertEqual(inv.verify_console_counts(paste, p), [], "số đếm thô khớp số model đọc được theo từng danh mục")
        self.assertEqual({m.model_id for m in self.inv.models}, {e["model_id"] for e in p.entries}, "mỗi model ID là một mục riêng, không thiếu không thừa")
        self.assertEqual(len(self.inv.models), 249)
        for e in p.entries:
            m = self.inv.get(e["model_id"])
            self.assertEqual((m.console_category, m.free_quota_total, m.free_quota_remaining, m.free_quota_snapshot_at,
                              m.free_quota_expires_at, m.free_quota_only),
                             (e["console_category"], e["free_quota_total"], e["free_quota_remaining"], e["free_quota_snapshot_at"],
                              e["free_quota_expires_at"], e.get("free_quota_only")), e["model_id"])
        # Số đếm tay (grep độc lập trên bản dán khi nhập): 102 + 67 + 21 + 53 + 6 = 249.
        cats = {}
        for m in self.inv.models:
            cats[m.console_category] = cats.get(m.console_category, 0) + 1
        self.assertEqual(cats, {"大语言模型": 102, "视觉模型": 67, "多模态模型": 21, "语音模型": 53, "向量模型": 6})
        self.assertEqual(sorted(w["model_id"] for w in p.warnings), ["fun-asr-2025-11-07", "qwen3.6-plus-2026-04-02"])
        for mid in ("fun-asr-2025-11-07", "qwen3.6-plus-2026-04-02"):
            self.assertIsNone(self.inv.get(mid).free_quota_only, "thiếu dòng 用完即停: chưa biết, không đoán")

    def test_nothing_beyond_the_paste_was_guessed_for_the_pasted_models(self) -> None:
        pasted = [m for m in self.inv.models if m.model_id != "qwen3.7-plus"]
        self.assertEqual(len(pasted), 248)
        blocked = []
        for m in pasted:
            self.assertEqual((m.tiers, m.quota_unit, m.rpm, m.tpm, m.thinking_support, m.thinking_default, m.input_modalities, m.slot_thinking,
                              m.status, m.observations),
                             ((), None, None, None, None, None, None, "provider_default", "inventoried", ()), m.model_id)
            state = inv.readiness(m, NOW)[0]
            self.assertIn(state, (inv.INCOMPLETE, inv.BLOCKED), m.model_id)
            if state == inv.BLOCKED:
                blocked.append(m.model_id)
        self.assertEqual(sorted(blocked), ["qwen-plus", "qwen-turbo"], "hai model hết hạn 2026-10-03 (00:00 UTC, thận trọng)")
        self.assertIn("quota_unit=null", self.inv.notes)
        self.assertIn("Free Quota Only", self.inv.notes)
        self.assertEqual(len([n for n in self.inv.notes.split("\n") if n.startswith(inv.CONSOLE_NOTE_MARK)]), 1)
        self.assertNotIn("không kèm tiêu đề cột", self.inv.notes, "câu của phiên bản đầu (bản dán không có tiêu đề) đã sai và đã bị thay")

    def test_the_catalogue_has_the_models_the_owner_cares_about_and_the_baseline_is_untouched(self) -> None:
        for mid in ("qwen3.7-plus", "qwen-plus", "qwen-max", "qwen3-coder-plus", "qwen-vl-max", "qwen-mt-plus", "wan2.7-t2v", "qwen-image-2.0-pro",
                    "qwen3.5-omni-plus", "qwen3-tts-flash", "text-embedding-v4", "qwen3-rerank", "qwq-plus", "qwen-plus-character", "glm-5.3", "kimi-k3"):
            self.assertIsNotNone(self.inv.get(mid), mid)
        tiered = [m.model_id for m in self.inv.models if m.tiers]
        self.assertEqual(tiered, ["qwen3.7-plus"], "chỉ baseline đã kiểm chứng có tầng; báo cáo ứng viên KHÔNG ghi vào tiers")

    def test_no_secret_or_account_specific_value_is_in_the_inventory_file(self) -> None:
        low = self.raw.lower()
        for needle in ("maas.aliyuncs", "dashscope", "ws-", "api_key", "apikey", "secret", "bearer"):
            self.assertNotIn(needle, low, needle)
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{16,}", self.raw))


class TestCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("alibaba_inventory_cli", ROOT / "scripts" / "alibaba_inventory.py")
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_validate_and_report_on_the_shipped_file(self) -> None:
        code, out, _ = self.run_cli("validate", str(SHIPPED))
        self.assertEqual(code, 0)
        self.assertIn("HỢP LỆ: 249 model", out)
        code, out, _ = self.run_cli("report", str(SHIPPED), "--now", "2026-10-04T00:00:00+00:00")
        self.assertEqual(code, 0)
        self.assertIn("qwen3.7-plus", out)
        self.assertIn("INCOMPLETE", out)
        self.assertIn("input_modalities", out)
        for tier in CAPABILITY_TIERS:
            self.assertIn(tier, out)
        self.assertIn("Free Quota Only", out)

    def test_brief_report_counts_every_state_and_category(self) -> None:
        code, out, _ = self.run_cli("report", str(SHIPPED), "--brief", "--now", "2026-10-04T00:00:00+00:00")
        self.assertEqual(code, 0)
        self.assertIn("Tổng 249 model: READY 0 · INCOMPLETE 247 · BLOCKED 2", out)
        for cat in ("向量模型 6", "语音模型 53", "大语言模型 102", "视觉模型 67", "多模态模型 21"):
            self.assertIn(cat, out)
        self.assertIn("quota_unit [248 model]", out)
        self.assertNotIn("=> INCOMPLETE", out, "--brief không liệt kê từng model")

    def test_parse_console_is_idempotent_on_the_shipped_inventory_and_rejects_garbage(self) -> None:
        import tempfile
        paste = ROOT / "docs" / "ai" / "alibaba_free_quota_console_paste.txt"
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "moi.json"
            code, _, err = self.run_cli("parse-console", str(paste), "--into", str(SHIPPED), "--out", str(out_file))
            self.assertEqual(code, 0)
            self.assertIn("Đọc 249 model", err)
            self.assertIn("thêm 0, làm mới 0, không đổi 249", err)
            self.assertIn("Đối chiếu số đếm: KHỚP", err)
            self.assertIn("大语言模型: 102 → 102", err)
            self.assertIn("Thiếu đơn vị hạn mức (quota_unit): 249/249", err)
            self.assertEqual(err.count("CẢNH BÁO dòng"), 2)
            self.assertEqual(json.loads(out_file.read_text(encoding="utf-8")), json.loads(SHIPPED.read_text(encoding="utf-8")))
            bad = Path(tmp) / "hong.txt"
            bad.write_text("qwen3-tts-flash    语音模型\n剩 10K / 共 10K\n", encoding="utf-8")
            code, out, err = self.run_cli("parse-console", str(bad))
            self.assertEqual((code, out), (1, ""))
            self.assertIn("LỖI dòng 1 [incomplete_row]", err)
            self.assertIn("Không ghi kết quả vì còn lỗi", err)
            code, _, err = self.run_cli("parse-console", str(Path(tmp) / "khong_co.txt"))
            self.assertEqual(code, 1)
            self.assertIn("KHÔNG TÌM THẤY", err)

    def test_parse_console_from_scratch_builds_a_valid_inventory_on_stdout(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            paste = Path(tmp) / "dan.txt"
            paste.write_text(PASTE_ROWS, encoding="utf-8")
            code, out, err = self.run_cli("parse-console", str(paste), "--captured-at", "2026-10-04T00:00:00+00:00")
            self.assertEqual(code, 0)
            self.assertIn("thêm 5", err)
            self.assertIn("大语言模型: 2 → 2", err)
            self.assertEqual(len(inv.parse_inventory(json.loads(out)).models), 5)

    def test_a_missing_or_broken_file_is_an_error_not_a_crash(self) -> None:
        code, out, _ = self.run_cli("validate", str(ROOT / "docs" / "ai" / "khong_co.json"))
        self.assertEqual(code, 1)
        self.assertIn("KHÔNG TÌM THẤY", out)

    def test_slot_refuses_an_incomplete_model_with_exit_2_and_prints_no_body(self) -> None:
        code, out, err = self.run_cli("slot", str(SHIPPED), "qwen3.7-plus", "--slot-id", "alibaba-sg-02", "--secret-ref", "ALIBABA_SG_02",
                                      "--endpoint", BASE)
        self.assertEqual((code, out.strip()), (2, ""))
        self.assertIn("INCOMPLETE", err)

    def test_slot_does_not_guess_an_unknown_model_id(self) -> None:
        code, out, _ = self.run_cli("slot", str(SHIPPED), "qwen-something-else", "--slot-id", "alibaba-sg-02", "--secret-ref",
                                    "ALIBABA_SG_02", "--endpoint", BASE)
        self.assertEqual(code, 1)
        self.assertIn("không đoán", out)

    def test_template_has_an_empty_model_id_on_purpose(self) -> None:
        code, out, _ = self.run_cli("template")
        self.assertEqual(code, 0)
        t = json.loads(out)
        self.assertEqual((t["model_id"], t["tiers"], t["rpm"], t["input_modalities"]), ("", [], None, None))
        with self.assertRaises(inv.InventoryError):
            inv.parse_inventory(doc(copy.deepcopy(t)))


if __name__ == "__main__":
    unittest.main()
