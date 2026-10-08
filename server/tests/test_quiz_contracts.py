"""
Hop dong quiz: artefact sinh tu `server/quiz/contracts.py` phai khop ban commit
(freeze cho P1-C/P1-D), fixture valid/invalid phai dung voi model strict, va
fixture API khong lo khoa dap an truoc reveal.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from server.quiz import codegen
from server.quiz import contracts as C

FIXTURES = codegen.OUT_DIR / codegen.FIXTURE_DIR
MODELS = {m.__name__: m for m in C.PUBLIC_MODELS}
KEY_FIELDS = ("correct_option_ids", "answer_key", "key_hash")


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _keys(obj) -> set:
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(k)
            found |= _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _keys(v)
    return found


class GeneratedArtefactsTest(unittest.TestCase):
    def test_committed_artefacts_match_generator(self):
        files = codegen.build_all()
        current = codegen._existing(codegen.OUT_DIR)
        self.assertEqual(sorted(current), sorted(files), "run: python -m server.quiz.codegen")
        for name, text in files.items():
            self.assertEqual(current[name], text, f"out of date: {name}")

    def test_generator_is_deterministic(self):
        self.assertEqual(codegen.build_all(), codegen.build_all())

    def test_ts_lists_every_public_model_and_error_code(self):
        ts = (codegen.OUT_DIR / codegen.TS_FILE).read_text(encoding="utf-8")
        for name in MODELS:
            self.assertRegex(ts, rf"export (interface|type) {name}\b")
        for code in C.ErrorCode.__args__:
            self.assertIn(json.dumps(code), ts)
        self.assertNotIn("live", [m.lower() for m in MODELS])


class ContractFixturesTest(unittest.TestCase):
    def test_valid_and_invalid_cases(self):
        cases = sorted(FIXTURES.glob("valid/*.json")) + sorted(FIXTURES.glob("invalid/*.json"))
        self.assertGreaterEqual(len(cases), 20)
        for p in cases:
            case = _load(p)
            model = MODELS[case["model"]]
            with self.subTest(fixture=p.name, why=case["why"]):
                if case["valid"]:
                    model.model_validate(case["data"])
                else:
                    with self.assertRaises(ValidationError):
                        model.model_validate(case["data"])

    def test_api_responses_conform_to_declared_models(self):
        api = sorted(FIXTURES.glob("api/*.json"))
        self.assertGreaterEqual(len(api), 30)
        for p in api:
            fx = _load(p)
            with self.subTest(fixture=p.name):
                name, body = fx["response_model"], fx["response"]["body"]
                if name is None:
                    self.assertEqual(fx["response"]["status"], 204)
                    self.assertIsNone(body)
                    continue
                MODELS[name].model_validate(body)

    def test_public_and_participant_fixtures_carry_no_answer_key(self):
        """Key chi duoc nam trong `reveal` cua view da dong cau (phase != answering)."""
        checked = 0
        for p in sorted(FIXTURES.glob("api/*.json")):
            fx = _load(p)
            name, body = fx["response_model"], fx["response"]["body"]
            if name not in ("PublicQuizSnapshot", "ParticipantView", "SubmitResponse", "PublishResult"):
                continue
            body = dict(body)
            view = body.pop("view", None) if name == "SubmitResponse" else None
            if name == "ParticipantView":
                view, body = body, {}
            with self.subTest(fixture=p.name):
                self.assertFalse(_keys(body) & set(KEY_FIELDS))
                if view is not None:
                    view = dict(view)
                    reveal = view.pop("reveal", None)
                    self.assertFalse(_keys(view) & set(KEY_FIELDS))
                    if view["phase"] == "answering":
                        self.assertIsNone(reveal)
                checked += 1
        self.assertGreaterEqual(checked, 10)

    def test_index_lists_every_fixture(self):
        index = _load(FIXTURES / "index.json")
        on_disk = sorted(p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*.json")
                         if p.name != "index.json")
        self.assertEqual(sorted(index), sorted(on_disk + ["index.json"]) if "index.json" in index
                         else on_disk)


if __name__ == "__main__":
    unittest.main()
