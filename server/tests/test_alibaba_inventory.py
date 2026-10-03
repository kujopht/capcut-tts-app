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
                          m.thinking_default, m.input_modalities, m.free_quota_only, m.multimodal),
                         ((), None, None, None, "", None, None, None, None, None))
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
        for field, value in (("rpm", None), ("tpm", None), ("free_quota_remaining", None), ("free_quota_expires_at", ""),
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
        w.writerow(["model-from-owner-a", "", "FAST|SMART", "", "1M", "992.19K", "2026-10-03T06:00:00+00:00", "2026-12-02T00:00:00+00:00",
                    "15,000", "5M", "hybrid", "on", "off", "text|image", "not_enabled", "owner skipped", "screenshot", ""])
        w.writerow(["model-from-owner-b"] + [""] * (len(inv.CSV_COLUMNS) - 1))
        raw = inv.from_csv(buf.getvalue(), captured_at="2026-10-03T06:00:00+00:00", region="ap-southeast-1")
        d = inv.parse_inventory(raw)
        a, b = d.models
        self.assertEqual((a.tiers, a.free_quota_total, a.free_quota_remaining, a.rpm, a.tpm, a.input_modalities, a.multimodal),
                         (("FAST", "SMART"), 1_000_000, 992_190, 15_000, 5_000_000, ("text", "image"), True))
        self.assertEqual((a.status, a.quota_unit, a.slot_thinking), ("inventoried", "tokens", "off"), "ô trống = mặc định của định dạng")
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
        self.assertEqual((m.free_quota_total, m.free_quota_remaining, m.free_quota_expires_at), (1_000_000, 992_190, "2026-12-02T00:00:00+00:00"))
        self.assertEqual(m.free_quota_only, "not_enabled")

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
        self.assertIn("HỢP LỆ: 1 model", out)
        code, out, _ = self.run_cli("report", str(SHIPPED), "--now", "2026-10-04T00:00:00+00:00")
        self.assertEqual(code, 0)
        self.assertIn("qwen3.7-plus", out)
        self.assertIn("INCOMPLETE", out)
        self.assertIn("input_modalities", out)
        for tier in CAPABILITY_TIERS:
            self.assertIn(tier, out)
        self.assertIn("Free Quota Only", out)

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
