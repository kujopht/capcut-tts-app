"""
`production-deploy.yml`: hai co giao dien AI (`NEXT_PUBLIC_AI_ASSISTANT_ENABLED`,
`NEXT_PUBLIC_AI_COMPANION_ENABLED`) la DAU VAO TUONG MINH cua ban build frontend, va
buoc cho health doi DUNG commit vua deploy.

Truoc ban nay workflow khong truyen hai co, nen moi deploy tu dong lang le build UI AI
TAT; va buoc cho health dung o phan hoi 200 dau tien (thuong la instance Render CU) nen
"commit_sha matches" hong du deploy that thanh cong (run 36859518425, 36867838397).

Kiem ca CAU TRUC (nguon gia tri, mot nguon duy nhat, khong secret) lan HANH VI (chay
that doan shell cua buoc bang bash voi cac gia tri bien khac nhau).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "production-deploy.yml"
BASH = shutil.which("bash")
FLAGS = ("NEXT_PUBLIC_AI_ASSISTANT_ENABLED", "NEXT_PUBLIC_AI_COMPANION_ENABLED")


def _wf() -> dict:
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _step(job: str, name_prefix: str) -> dict:
    steps = _wf()["jobs"][job]["steps"]
    hits = [s for s in steps if str(s.get("name", "")).startswith(name_prefix)]
    assert len(hits) == 1, f"{job}: {name_prefix!r} -> {len(hits)} buoc"
    return hits[0]


def _run(script: str, env: Dict[str, str], cwd: Optional[str] = None) -> Tuple[int, str]:
    base = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp")}
    if "SYSTEMROOT" in os.environ:  # bash tren Windows can bien nay de khoi dong
        base["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    p = subprocess.run([BASH, "-c", script], env={**base, **env}, cwd=cwd,
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


class TestFlagWiring(unittest.TestCase):
    def test_flags_come_from_repository_variables_never_secrets(self) -> None:
        env = _step("validate", "Resolve AI UI build flags")["env"]
        self.assertEqual(env["AI_ASSISTANT_FLAG"], "${{ vars.PRODUCTION_AI_ASSISTANT_ENABLED }}")
        self.assertEqual(env["AI_COMPANION_FLAG"], "${{ vars.PRODUCTION_AI_COMPANION_ENABLED }}")
        self.assertNotIn("PRODUCTION_AI_", "\n".join(
            line for line in WF.read_text(encoding="utf-8").splitlines() if "secrets." in line))

    def test_validate_runs_before_any_deploy_and_exports_the_flags(self) -> None:
        wf = _wf()
        out = wf["jobs"]["validate"]["outputs"]
        self.assertEqual(out["ai_assistant_flag"], "${{ steps.ui_flags.outputs.assistant }}")
        self.assertEqual(out["ai_companion_flag"], "${{ steps.ui_flags.outputs.companion }}")
        self.assertEqual(wf["jobs"]["deploy"]["needs"], "validate")
        # Buoc kiem co nam TRUOC moi buoc deploy: job `deploy` (Render hook roi Cloudflare) can `validate`.
        names = [s.get("name", "") for s in wf["jobs"]["deploy"]["steps"]]
        self.assertLess(names.index("Trigger Render deploy (backend)"), names.index("Cloudflare deploy (frontend)"))

    def test_frontend_build_reads_only_the_validated_outputs(self) -> None:
        env = _step("deploy", "Cloudflare deploy (frontend)")["env"]
        self.assertEqual(env["NEXT_PUBLIC_AI_ASSISTANT_ENABLED"], "${{ needs.validate.outputs.ai_assistant_flag }}")
        self.assertEqual(env["NEXT_PUBLIC_AI_COMPANION_ENABLED"], "${{ needs.validate.outputs.ai_companion_flag }}")

    def test_no_other_step_sets_the_flags(self) -> None:
        """Mot nguon duy nhat: khong buoc/job nao khac dat hai co (ke ca env cap job/workflow)."""
        wf = _wf()
        self.assertFalse(set(FLAGS) & set(wf.get("env") or {}))
        seen = []
        for jname, job in wf["jobs"].items():
            self.assertFalse(set(FLAGS) & set(job.get("env") or {}), jname)
            for s in job.get("steps") or []:
                for k in FLAGS:
                    if k in (s.get("env") or {}):
                        seen.append((jname, s.get("name"), k))
        self.assertEqual(sorted(seen), sorted(("deploy", "Cloudflare deploy (frontend)", k) for k in FLAGS))

    def test_scripts_never_interpolate_expressions(self) -> None:
        """Quy uoc cua tep: gia tri ngoai di qua `env:`, khong `${{ }}` trong than `run:`."""
        for job, name in (("validate", "Resolve AI UI build flags"), ("deploy", "Cloudflare deploy (frontend)"),
                          ("post_deploy_checks", "Wait for health on the deployed commit")):
            with self.subTest(step=name):
                self.assertNotIn("${{", _step(job, name)["run"])


@unittest.skipUnless(BASH, "can bash de chay doan shell cua workflow")
class TestFlagValidationBehaviour(unittest.TestCase):
    def _resolve(self, assistant: Optional[str], companion: Optional[str]) -> Tuple[int, str, Dict[str, str]]:
        script = _step("validate", "Resolve AI UI build flags")["run"]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            out.write_text("", encoding="utf-8")
            env = {"GITHUB_OUTPUT": out.as_posix()}
            if assistant is not None:
                env["AI_ASSISTANT_FLAG"] = assistant
            if companion is not None:
                env["AI_COMPANION_FLAG"] = companion
            code, log = _run(script, env)
            pairs = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if "=" in line)
        return code, log, pairs

    def test_explicit_values_pass_through(self) -> None:
        for a, c in (("0", "0"), ("1", "0"), ("1", "1")):
            with self.subTest(assistant=a, companion=c):
                code, log, pairs = self._resolve(a, c)
                self.assertEqual(code, 0, log)
                self.assertEqual(pairs, {"assistant": a, "companion": c})

    def test_missing_or_fuzzy_values_stop_the_deploy(self) -> None:
        for a, c in ((None, "0"), ("0", None), (None, None), ("", "0"), ("true", "0"), ("yes", "0"),
                     (" 1", "0"), ("1\n", "0"), ("0", "on"), ("01", "0")):
            with self.subTest(assistant=a, companion=c):
                code, log, pairs = self._resolve(a, c)
                self.assertEqual(code, 1, log)
                self.assertEqual(pairs, {}, "khong ghi output khi gia tri sai")
                self.assertIn("must be exactly 0 or 1", log)

    def test_companion_requires_assistant(self) -> None:
        code, log, pairs = self._resolve("0", "1")
        self.assertEqual(code, 1)
        self.assertIn("requires PRODUCTION_AI_ASSISTANT_ENABLED=1", log)
        self.assertEqual(pairs, {})

    def test_invalid_value_is_never_echoed(self) -> None:
        code, log, _ = self._resolve("value-that-should-not-be-printed", "0")
        self.assertEqual(code, 1)
        self.assertNotIn("value-that-should-not-be-printed", log)


@unittest.skipUnless(BASH, "can bash de chay doan shell cua workflow")
class TestFrontendStepGuards(unittest.TestCase):
    """Chi chay PHAN KIEM dau buoc Cloudflare — cat TRUOC `npm ci`, khong bao gio build/deploy."""

    def _guard(self, **env: str) -> Tuple[int, str]:
        run = _step("deploy", "Cloudflare deploy (frontend)")["run"]
        prefix = run.split("\nnpm ci", 1)[0]
        self.assertNotEqual(prefix, run, "khong tim thay `npm ci` de cat")
        self.assertNotRegex(prefix, r"\bnpm\b|wrangler|cf:deploy")
        base = {"CLOUDFLARE_API_TOKEN": "x" * 8, "NEXT_PUBLIC_API_BASE": "https://api.example.test"}
        return _run(prefix, {**base, **env})

    def test_matching_levels_pass(self) -> None:
        for a, c in (("0", "0"), ("1", "0"), ("1", "1")):
            with self.subTest(a=a, c=c):
                code, log = self._guard(NEXT_PUBLIC_AI_ASSISTANT_ENABLED=a, NEXT_PUBLIC_AI_COMPANION_ENABLED=c,
                                        AI_ASSISTANT_FLAG_ENV_VIEW=a, AI_COMPANION_FLAG_ENV_VIEW=c)
                self.assertEqual(code, 0, log)
                self.assertIn(f"NEXT_PUBLIC_AI_ASSISTANT_ENABLED={a} NEXT_PUBLIC_AI_COMPANION_ENABLED={c}", log)

    def test_environment_level_override_is_refused(self) -> None:
        code, log = self._guard(NEXT_PUBLIC_AI_ASSISTANT_ENABLED="0", NEXT_PUBLIC_AI_COMPANION_ENABLED="0",
                                AI_ASSISTANT_FLAG_ENV_VIEW="1", AI_COMPANION_FLAG_ENV_VIEW="0")
        self.assertEqual(code, 1)
        self.assertIn("differs between the 'production' environment variables", log)

    def test_missing_validated_output_is_refused(self) -> None:
        code, log = self._guard(NEXT_PUBLIC_AI_ASSISTANT_ENABLED="", NEXT_PUBLIC_AI_COMPANION_ENABLED="0",
                                AI_ASSISTANT_FLAG_ENV_VIEW="", AI_COMPANION_FLAG_ENV_VIEW="0")
        self.assertEqual(code, 1)
        self.assertIn("missing from the validate job outputs", log)


@unittest.skipUnless(BASH, "can bash de chay doan shell cua workflow")
class TestHealthWaitsForDeployedCommit(unittest.TestCase):
    NEW = "5cd87272088224897bed331a875307fb9336de1b"
    OLD = "6f9fedf6f9fedf6f9fedf6f9fedf6f9fedf6f9fe"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        bin_dir = self.d / "bin"
        bin_dir.mkdir()
        # `curl` gia: doc danh sach phan hoi theo thu tu (dong cuoi lap lai mai); "FAIL" = loi mang.
        (bin_dir / "curl").write_text(
            "#!/usr/bin/env bash\n"
            f"q='{(self.d / 'queue').as_posix()}'; n='{(self.d / 'n').as_posix()}'\n"
            "i=$(cat \"$n\" 2>/dev/null || echo 0); i=$((i+1)); echo $i > \"$n\"\n"
            "line=$(sed -n \"${i}p\" \"$q\"); [ -n \"$line\" ] || line=$(tail -n 1 \"$q\")\n"
            "[ \"$line\" = FAIL ] && exit 22\n"
            "echo \"$line\"\n", encoding="utf-8", newline="\n")
        (bin_dir / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n")
        # `python3` cua buoc: tro toi chinh trinh thong dich dang chay test (Windows khong co `python3`).
        (bin_dir / "python3").write_text(
            f"#!/usr/bin/env bash\nexec '{Path(sys.executable).as_posix()}' \"$@\"\n", encoding="utf-8", newline="\n")
        for f in bin_dir.iterdir():
            f.chmod(0o755)
        self.bin = bin_dir

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _wait(self, responses) -> Tuple[int, str, Optional[str]]:
        (self.d / "queue").write_text("\n".join(responses) + "\n", encoding="utf-8", newline="\n")
        script = _step("post_deploy_checks", "Wait for health on the deployed commit")["run"]
        script = script.replace("/tmp/", f"{self.d.as_posix()}/")
        # Dat `bin` gia len dau PATH BEN TRONG bash (Git Bash tren Windows can dang /c/..., `cygpath`).
        b = self.bin.as_posix()
        script = f'export PATH="$(cygpath -u \'{b}\' 2>/dev/null || echo \'{b}\'):$PATH"\n' + script
        code, log = _run(script, {"API_BASE": "https://api.example.test", "EXPECTED_SHA": self.NEW})
        health = self.d / "health.json"
        return code, log, health.read_text(encoding="utf-8") if health.exists() else None

    @staticmethod
    def _h(sha: str) -> str:
        return '{"status":"ok","commit_sha":"%s"}' % sha

    def test_waits_past_the_old_instance(self) -> None:
        code, log, health = self._wait([self._h(self.OLD), "FAIL", self._h(self.OLD), self._h(self.NEW)])
        self.assertEqual(code, 0, log)
        self.assertIn("after attempt 4", log)
        self.assertIn(self.NEW, health or "")

    def test_never_live_hands_the_last_response_to_the_verify_step(self) -> None:
        code, log, health = self._wait([self._h(self.OLD)])
        self.assertEqual(code, 0, log)
        self.assertIn("::warning::", log)
        self.assertIn(self.OLD, health or "", "buoc Verify ben duoi se bao commit_sha khong khop")

    def test_health_never_answers_fails(self) -> None:
        code, log, _ = self._wait(["FAIL"])
        self.assertEqual(code, 1)
        self.assertIn("never responded", log)

    def test_short_server_sha_prefix_counts_as_live(self) -> None:
        code, log, _ = self._wait([self._h(self.NEW[:12])])
        self.assertEqual(code, 0, log)
        self.assertIn("after attempt 1", log)


if __name__ == "__main__":
    unittest.main()
