"""
Báo cáo ứng viên năng lực (`server/ai_assistant/control/alibaba_candidates.py`, `scripts/alibaba_inventory.py candidates`).

Điều phải đúng:
  * chỉ là GỢI Ý: `CAPABILITY_TIERS` của slot không đổi, `tiers` của kiểm kê không bị ghi;
  * mỗi gợi ý mang bằng chứng (category mạnh / name giả thuyết) và luật đã bắn; model thiếu bằng chứng -> unclassified, không bị ép vào nhóm;
  * nhóm chuyên biệt thắng nhóm tổng quát (coder không phải FAST/SMART; thinking/qwq không phải SMART; mt không phải FAST);
  * số liệu trên bộ dữ liệu thật được đối chiếu ĐỘC LẬP với số đếm danh mục (AUDIO = giọng nói + omni, IMAGE + VIDEO = mô hình sinh ảnh/video…);
  * báo cáo xác định và tệp Markdown đang giao khớp từng ký tự với bản sinh lại.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from server.ai_assistant.control import alibaba_candidates as cand
from server.ai_assistant.control import alibaba_inventory as inv
from server.ai_assistant.control.model import CAPABILITY_TIERS

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "docs" / "ai" / "alibaba_model_inventory.json"
PASTE = ROOT / "docs" / "ai" / "alibaba_free_quota_console_paste.txt"
DOC = ROOT / "docs" / "ai" / "ALIBABA_CAPABILITY_CANDIDATES.md"

LLM, VGEN, MM, SPEECH, VEC = cand.CATEGORY_LLM, cand.CATEGORY_VISUAL_GEN, cand.CATEGORY_MULTIMODAL, cand.CATEGORY_SPEECH, cand.CATEGORY_VECTOR


def classes_of(model_id: str, category: str) -> set:
    return {c.cls for c in cand.classify(inv.ModelEntry(model_id=model_id, console_category=category))}


class TestClassification(unittest.TestCase):
    CASES = [
        # tầng tổng quát theo tên (chỉ model văn bản không chuyên biệt)
        ("qwen3.7-plus", LLM, {"SMART"}), ("qwen-plus-2025-07-28", LLM, {"SMART"}), ("qwen3.5-plus", LLM, {"SMART"}),
        ("qwen-turbo", LLM, {"FAST"}), ("qwen-flash", LLM, {"FAST"}), ("qwen3.7-flash-2026-07-15", LLM, {"FAST"}), ("deepseek-v4.1-flash", LLM, {"FAST"}),
        ("qwen-max", LLM, {"ADVANCED"}), ("qwen3.8-max-0902", LLM, {"ADVANCED"}), ("qwen3.6-max-preview", LLM, {"ADVANCED"}),
        # chuyên biệt thắng tổng quát
        ("qwen3-coder-flash", LLM, {"CODING"}), ("qwen3-coder-plus", LLM, {"CODING"}), ("kimi-k2.7-code", LLM, {"CODING"}),
        ("qwen-plus-character", LLM, {"CHARACTER"}), ("qwen-flash-character", LLM, {"CHARACTER"}),
        ("qwen-mt-flash", LLM, {"TRANSLATION"}), ("qwen-mt-turbo", LLM, {"TRANSLATION"}), ("qwen-mt-lite", LLM, {"TRANSLATION"}),
        ("qwen3-vl-plus", LLM, {"VISION"}), ("qwen3-vl-flash", LLM, {"VISION"}), ("qwen-vl-max", LLM, {"VISION"}), ("qwen-vl-ocr", LLM, {"VISION"}),
        # suy luận: DEEP, không phải SMART/FAST/ADVANCED
        ("qwq-plus", LLM, {"DEEP"}), ("qwen3-next-80b-a3b-thinking", LLM, {"DEEP"}), ("qwen3-235b-a22b-thinking-2507", LLM, {"DEEP"}),
        ("qwen3-vl-235b-a22b-thinking", LLM, {"VISION", "DEEP"}), ("qvq-max", LLM, {"VISION", "DEEP"}),
        # không đủ bằng chứng
        ("qwen3-32b", LLM, set()), ("glm-5.1", LLM, set()), ("kimi-k3", LLM, set()), ("deepseek-v4-pro", LLM, set()), ("qwen3.8-2.4t-a95b", LLM, set()),
        # sinh ảnh / video (danh mục 视觉模型)
        ("qwen-image-edit-plus", VGEN, {"IMAGE"}), ("z-image-turbo", VGEN, {"IMAGE"}), ("wan2.5-i2i-preview", VGEN, {"IMAGE"}),
        ("wan2.5-t2i-preview", VGEN, {"IMAGE"}), ("wan2.6-image", VGEN, {"IMAGE"}), ("qwen-mt-image-2.0", VGEN, {"IMAGE", "TRANSLATION"}),
        ("wan2.6-t2v", VGEN, {"VIDEO"}), ("wan2.7-r2v", VGEN, {"VIDEO"}), ("wan2.1-kf2v-plus", VGEN, {"VIDEO"}), ("wan2.1-vace-plus", VGEN, {"VIDEO"}),
        ("wan2.7-videoedit", VGEN, {"VIDEO"}), ("wan2.2-animate-move", VGEN, {"VIDEO"}), ("happyhorse-1.0-video-edit", VGEN, {"VIDEO"}),
        ("wan3.0-video", VGEN, {"VIDEO"}),
        # danh mục console làm bằng chứng
        ("qwen3.5-omni-plus", MM, {"VISION", "AUDIO"}), ("qwen3-omni-flash-realtime", MM, {"VISION", "AUDIO"}),
        ("qwen3-tts-flash", SPEECH, {"AUDIO"}), ("fun-asr", SPEECH, {"AUDIO"}), ("cosyvoice-v3-plus", SPEECH, {"AUDIO"}),
        ("qwen3-livetranslate-flash-realtime", SPEECH, {"AUDIO", "TRANSLATION"}),
        ("text-embedding-v4", VEC, {"EMBEDDING_RERANK"}), ("qwen3-rerank", VEC, {"EMBEDDING_RERANK"}),
        # model video bị console xếp vào danh mục chat: tên thắng, không thành FAST
        ("wan2.2-kf2v-flash", LLM, {"VIDEO"}),
        # danh mục lạ / không ghi: tầng tổng quát CHỈ áp cho danh mục 大语言模型
        ("qwen-flash", "图像模型", set()), ("qwen-plus", "", set()),
    ]

    def test_each_rule_fires_on_exactly_the_models_it_should(self) -> None:
        for mid, cat, want in self.CASES:
            with self.subTest(mid=mid, cat=cat):
                self.assertEqual(classes_of(mid, cat), want)

    def test_evidence_strength_is_category_for_console_categories_and_name_for_tokens(self) -> None:
        for e in (inv.ModelEntry("qwen3-tts-flash", console_category=SPEECH), inv.ModelEntry("text-embedding-v4", console_category=VEC),
                  inv.ModelEntry("qwen3.5-omni-plus", console_category=MM)):
            self.assertTrue(all(c.strength == cand.STRONG and c.rule.startswith("C-") for c in cand.classify(e)), e.model_id)
        for e in (inv.ModelEntry("qwen-max", console_category=LLM), inv.ModelEntry("wan2.6-t2v", console_category=VGEN),
                  inv.ModelEntry("qwen3-coder-plus", console_category=LLM)):
            self.assertTrue(all(c.strength == cand.WEAK and c.rule.startswith("N-") for c in cand.classify(e)), e.model_id)
        both = cand.classify(inv.ModelEntry("qwen3-livetranslate-flash", console_category=SPEECH))
        self.assertEqual({(c.cls, c.strength) for c in both}, {("AUDIO", cand.STRONG), ("TRANSLATION", cand.WEAK)})

    def test_the_multimodal_category_is_flagged_as_unconfirmed_modalities(self) -> None:
        for c in cand.classify(inv.ModelEntry("qwen3.5-omni-plus", console_category=MM)):
            self.assertIn("chưa xác nhận", c.note)

    def test_the_twelve_classes_exist_in_order_and_the_slot_tiers_are_untouched(self) -> None:
        self.assertEqual(cand.CANDIDATE_CLASSES, ("FAST", "SMART", "ADVANCED", "DEEP", "CODING", "CHARACTER", "TRANSLATION", "VISION", "IMAGE", "VIDEO",
                                                  "AUDIO", "EMBEDDING_RERANK"))
        self.assertEqual(CAPABILITY_TIERS, ("FAST", "SMART", "ADVANCED", "TRANSLATION", "VISION", "EMBEDDING"),
                         "tầng định tuyến của slot (đang dùng ở production) KHÔNG đổi")

    def test_every_rule_that_can_fire_is_documented(self) -> None:
        fired = {c.rule for mid, cat, _ in self.CASES for c in cand.classify(inv.ModelEntry(mid, console_category=cat))}
        self.assertEqual(fired, set(cand.RULES), "mỗi luật trong RULES có ít nhất một ca kiểm, và không có luật nào không được ghi tài liệu")
        self.assertEqual(set(cand._RULE_CLASSES), set(cand.RULES))  # noqa: SLF001
        for rule, classes in cand._RULE_CLASSES.items():  # noqa: SLF001
            self.assertTrue(set(classes) <= set(cand.CANDIDATE_CLASSES), rule)


class TestShippedReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = inv.load_inventory(str(SHIPPED))
        cls.paste = PASTE.read_text(encoding="utf-8")
        cls.rep = cand.build_report(cls.inventory, cls.paste)

    def test_counts_per_class_match_the_independently_derived_totals(self) -> None:
        r = self.rep
        n = {c: len(rows) for c, rows in r["classes"].items()}
        self.assertEqual(n, {"FAST": 13, "SMART": 14, "ADVANCED": 13, "DEEP": 9, "CODING": 9, "CHARACTER": 2, "TRANSLATION": 12, "VISION": 40,
                             "IMAGE": 32, "VIDEO": 36, "AUDIO": 74, "EMBEDDING_RERANK": 6})
        cat = r["by_category"]
        self.assertEqual(cat, {LLM: 102, VGEN: 67, MM: 21, SPEECH: 53, VEC: 6})
        # Đối chiếu độc lập với số đếm danh mục (không dùng luật tên):
        self.assertEqual(n["AUDIO"], cat[SPEECH] + cat[MM], "AUDIO = giọng nói + omni")
        self.assertEqual(n["EMBEDDING_RERANK"], cat[VEC])
        self.assertEqual(n["IMAGE"] + n["VIDEO"], cat[VGEN] + 1, "mọi mô hình sinh ảnh/video + wan2.2-kf2v-flash (console xếp vào danh mục chat)")
        self.assertEqual(sum(1 for x in r["classes"]["VISION"] if x["strength"] == cand.STRONG), cat[MM])

    def test_every_model_is_classified_or_listed_as_unclassified_never_lost(self) -> None:
        r = self.rep
        classified = {x["model_id"] for rows in r["classes"].values() for x in rows}
        unclassified = {x["model_id"] for x in r["unclassified"]}
        self.assertEqual(classified & unclassified, set())
        self.assertEqual(classified | unclassified, {m.model_id for m in self.inventory.models})
        self.assertEqual(len(unclassified), 23)
        self.assertEqual(unclassified, {"deepseek-v3.2", "deepseek-v4-pro", "deepseek-v4-pro-0813", "glm-5.1", "glm-5.2", "glm-5.3", "kimi-k3",
                                        "qwen3-14b", "qwen3-235b-a22b", "qwen3-235b-a22b-instruct-2507", "qwen3-30b-a3b", "qwen3-30b-a3b-instruct-2507",
                                        "qwen3-32b", "qwen3-8b", "qwen3-next-80b-a3b-instruct", "qwen3.5-122b-a10b", "qwen3.5-27b", "qwen3.5-35b-a3b",
                                        "qwen3.5-397b-a17b", "qwen3.6-27b", "qwen3.6-35b-a3b", "qwen3.8-2.4t-a95b", "qwen3.8-27b"})

    def test_the_validated_baseline_stays_a_validated_smart_candidate_with_thinking_off(self) -> None:
        b = self.rep["baseline"]
        self.assertEqual((b["model_id"], b["status"], b["tiers"], b["slot_thinking"], b["quota_unit"], b["free_quota_only"]),
                         ("qwen3.7-plus", "validated_candidate", ["SMART"], "off", "tokens", "confirmed_on"))
        self.assertIn("qwen3.7-plus", [x["model_id"] for x in self.rep["classes"]["SMART"]])
        self.assertEqual([m.model_id for m in self.inventory.models if m.tiers], ["qwen3.7-plus"], "báo cáo không ghi tiers cho model nào khác")

    def test_parse_problems_missing_units_and_oddities_are_reported(self) -> None:
        r = self.rep
        p = r["parse"]
        self.assertEqual((p["rows"], p["entries"], p["errors"], p["count_problems"], p["header_blocks"]), (249, 249, [], [], 2))
        self.assertEqual(p["snapshot_at"], "2026-10-03T00:00:00+00:00")
        self.assertEqual(sorted(w["model_id"] for w in p["warnings"]), ["fun-asr-2025-11-07", "qwen3.6-plus-2026-04-02"])
        self.assertEqual(sorted(r["missing_free_quota_only"]), ["fun-asr-2025-11-07", "qwen3.6-plus-2026-04-02"])
        self.assertEqual(r["quota_unit_unknown"], 248, "mọi model trừ qwen3.7-plus (đã đối chiếu = tokens) thiếu đơn vị")
        self.assertEqual([a["model_id"] for a in r["anomalies"]], ["wan2.2-kf2v-flash"])
        self.assertEqual(sorted(x["model_id"] for x in r["expiring_soon"]), ["qwen-plus", "qwen-turbo"])
        self.assertEqual(len(r["partially_used"]), 12)
        self.assertEqual(r["readiness"], {"READY": 0, "INCOMPLETE": 247, "BLOCKED": 2})
        self.assertEqual(r["free_quota_only"], {"confirmed_on": 159, "not_enabled": 88, "unknown": 2})

    def test_a_broken_source_makes_the_report_say_so_instead_of_claiming_clean(self) -> None:
        broken = self.paste.replace("剩 984.2K / 共 1M", "984.2K of 1M", 1)
        rep = cand.build_report(self.inventory, broken)
        self.assertTrue(rep["parse"]["errors"])
        self.assertIn("CÓ VẤN ĐỀ", cand.render_markdown(rep))
        self.assertIn("SẠCH", cand.render_markdown(self.rep))
        self.assertIn("không có bản dán nguồn", cand.render_markdown(cand.build_report(self.inventory)))

    def test_the_report_is_deterministic_and_does_not_touch_the_inventory(self) -> None:
        before = SHIPPED.read_text(encoding="utf-8")
        again = cand.build_report(self.inventory, self.paste)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.rep, sort_keys=True))
        self.assertEqual(cand.render_markdown(again), cand.render_markdown(self.rep))
        self.assertEqual(SHIPPED.read_text(encoding="utf-8"), before)

    def test_the_committed_markdown_is_exactly_the_regenerated_report(self) -> None:
        committed = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(committed, cand.render_markdown(self.rep), "chạy lại: python scripts/alibaba_inventory.py candidates … --md docs/ai/ALIBABA_CAPABILITY_CANDIDATES.md")

    def test_the_markdown_names_all_twelve_classes_and_the_evidence_levels(self) -> None:
        md = cand.render_markdown(self.rep)
        for cls in cand.CANDIDATE_CLASSES:
            self.assertIn(f"### {cls} (", md)
        for needle in ("không phải tầng định tuyến", "category", "name", "Chưa đủ bằng chứng", "wan2.2-kf2v-flash", "Thiếu đơn vị hạn mức (248)",
                       "SẠCH", "`qwen3.7-plus` — SMART"):
            self.assertIn(needle, md)


class TestCandidatesCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("alibaba_inventory_cli2", ROOT / "scripts" / "alibaba_inventory.py")
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_candidates_command_prints_every_class_and_writes_the_committed_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md, js = Path(tmp) / "bao_cao.md", Path(tmp) / "bao_cao.json"
            code, out, err = self.run_cli("candidates", str(SHIPPED), "--paste", str(PASTE), "--md", str(md), "--json", str(js))
            self.assertEqual((code, err), (0, ""))
            for cls in cand.CANDIDATE_CLASSES:
                self.assertIn(cls, out)
            self.assertIn("chưa đủ bằng chứng: 23", out)
            self.assertIn("Parse nguồn: SẠCH — 249 → 249, lỗi 0, cảnh báo 2", out)
            self.assertEqual(md.read_text(encoding="utf-8"), DOC.read_text(encoding="utf-8").replace("\r\n", "\n"))
            self.assertEqual(json.loads(js.read_text(encoding="utf-8"))["models"], 249)

    def test_candidates_command_fails_loudly_on_a_broken_paste_and_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "hong.txt"
            bad.write_text(PASTE.read_text(encoding="utf-8").replace("剩 984.2K / 共 1M", "984.2K of 1M", 1), encoding="utf-8")
            code, out, _ = self.run_cli("candidates", str(SHIPPED), "--paste", str(bad))
            self.assertEqual(code, 1)
            self.assertIn("CÓ VẤN ĐỀ", out)
            code, _, err = self.run_cli("candidates", str(SHIPPED), "--paste", str(Path(tmp) / "khong_co.txt"))
            self.assertEqual(code, 1)
            self.assertIn("KHÔNG TÌM THẤY", err)


if __name__ == "__main__":
    unittest.main()
