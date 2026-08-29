"""Render provider adapter — the safety properties, not the happy path.

This adapter writes a credential into a production service, so what matters is
what it REFUSES to do: guess between two services, act on a half-read env
snapshot, echo an API error body that may contain the request it rejected, or
mutate anything at all during a dry run.

Every test stubs the HTTP layer. Nothing here reaches the network, Render, or
the Windows Credential Manager.
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATH = os.path.join(_ROOT, "scripts", "fanfic_credential_broker.py")


def _load():
    spec = importlib.util.spec_from_file_location("_broker_qa", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _svc(name, sid):
    return {"service": {"name": name, "id": sid, "type": "web_service"}}


def _env(key):
    return {"envVar": {"key": key, "value": "irrelevant"}, "cursor": "c-" + key}


class ServiceResolutionTest(unittest.TestCase):
    """Resolving the wrong service would write a production credential into
    someone else's config, so ambiguity must refuse rather than pick."""

    def test_exact_name_resolves(self):
        b = _load()
        with patch.object(b, "_render", return_value=(200, [_svc("fas-prod-api", "srv-1")])):
            self.assertEqual(b.render_resolve_service("k")["id"], "srv-1")

    def test_substring_match_is_not_accepted_either_direction(self):
        """Render's ?name= is a FILTER, not an exact match.

        Both directions matter. A returned name that CONTAINS the target
        catches `expected in returned`; a returned name that is a PREFIX of
        the target catches the reverse, `returned in expected`. Testing only
        one direction would let the opposite bug through.
        """
        b = _load()
        for returned in ("fas-prod-api-staging", "fas-prod"):
            with patch.object(b, "_render", return_value=(200, [_svc(returned, "srv-9")])):
                with self.assertRaises(b.RenderNotFound, msg=f"accepted {returned!r}"):
                    b.render_resolve_service("fas-prod-api")

    def test_two_exact_matches_refuse_to_guess(self):
        b = _load()
        both = [_svc("fas-prod-api", "srv-1"), _svc("fas-prod-api", "srv-2")]
        with patch.object(b, "_render", return_value=(200, both)):
            with self.assertRaises(b.RenderError) as ctx:
                b.render_resolve_service("k")
            self.assertNotIsInstance(ctx.exception, b.RenderNotFound)

    def test_service_without_id_is_refused(self):
        b = _load()
        broken = [{"service": {"name": "fas-prod-api"}}]
        with patch.object(b, "_render", return_value=(200, broken)):
            with self.assertRaises(b.RenderError):
                b.render_resolve_service("k")

    def test_missing_service_is_not_found_not_downstream_error(self):
        b = _load()
        with patch.object(b, "_render", return_value=(200, [])):
            with self.assertRaises(b.RenderNotFound):
                b.render_resolve_service("k")


class EnvSnapshotCompletenessTest(unittest.TestCase):
    """The "nothing else was lost" check compares a before/after snapshot. A
    PARTIAL snapshot would make that comparison quietly meaningless."""

    def test_single_page(self):
        b = _load()
        with patch.object(b, "_render", return_value=(200, [_env("A"), _env("B")])):
            self.assertEqual(b.render_env_names("k", "srv-1"), ["A", "B"])

    def test_empty_service_is_legitimate_not_an_error(self):
        b = _load()
        with patch.object(b, "_render", return_value=(200, [])):
            self.assertEqual(b.render_env_names("k", "srv-1"), [])

    def test_paginates_past_the_first_page_and_actually_sends_the_cursor(self):
        """Returning 101 names is not proof of cursor pagination.

        A sequential side_effect yields page 2 no matter what the caller asks
        for, so this also asserts that the cursor from page 1 appears in the
        page-2 REQUEST. Without that, an implementation that simply called
        twice with no cursor would pass.
        """
        b = _load()
        page1 = [_env(f"K{i:03d}") for i in range(100)]
        page2 = [_env("ZZZ")]
        paths = []

        def fake(api_key, method, path, payload=None, timeout=60):
            paths.append(path)
            return (200, page1) if len(paths) == 1 else (200, page2)

        with patch.object(b, "_render", side_effect=fake):
            names = b.render_env_names("k", "srv-1")

        self.assertEqual(len(names), 101)
        self.assertIn("ZZZ", names, "a variable on page 2 must not be invisible")
        self.assertEqual(len(paths), 2)
        expected_cursor = page1[-1]["cursor"]
        self.assertIn(f"cursor={expected_cursor}", paths[1],
                      f"page 2 must carry page 1's cursor; got {paths[1]}")

    def test_full_page_without_cursor_refuses(self):
        b = _load()
        page = [{"envVar": {"key": f"K{i}"}} for i in range(100)]   # no cursor
        with patch.object(b, "_render", return_value=(200, page)):
            with self.assertRaises(b.RenderError):
                b.render_env_names("k", "srv-1")

    def test_pagination_ceiling_raises_instead_of_returning_partial(self):
        """Every page is DISTINCT, with a fresh cursor each time.

        A fixed return_value would hand back identical cursors forever, so the
        loop might terminate for that reason instead of the iteration cap —
        passing the test while leaving the ceiling untested. Unique pages mean
        only the cap can stop it.
        """
        b = _load()
        counter = {"n": 0}

        def fake(api_key, method, path, payload=None, timeout=60):
            n = counter["n"]
            counter["n"] += 1
            return (200, [_env(f"P{n:03d}K{i:03d}") for i in range(100)])

        with patch.object(b, "_render", side_effect=fake):
            with self.assertRaises(b.RenderError):
                b.render_env_names("k", "srv-1")
        self.assertGreaterEqual(counter["n"], 50,
                                "the ceiling, not an early exit, must end the loop")


class ErrorRedactionTest(unittest.TestCase):
    """A 4xx body can echo the request that produced it — here that would be
    the Authorization header or {"value": <secret>}."""

    def test_http_error_body_never_enters_the_message(self):
        import urllib.error
        import io
        b = _load()
        leaked = "SECRETVALUE-should-never-appear-abcdefghijklmnop"
        err = urllib.error.HTTPError(
            "https://api.render.com/v1/x", 400, "Bad Request", {},
            io.BytesIO(f'{{"echo":"{leaked}"}}'.encode()))
        with patch.object(b.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(b.RenderError) as ctx:
                b._render("k", "PUT", "/x", {"value": leaked})
        self.assertNotIn(leaked, str(ctx.exception))
        self.assertIn("400", str(ctx.exception))


class DryRunTest(unittest.TestCase):
    def test_dry_run_performs_zero_mutations(self):
        b = _load()
        calls = []

        def fake(api_key, method, path, payload=None, timeout=60):
            calls.append((method, path))
            if path.startswith("/owners"):
                return 200, [{"owner": {"id": "own-1"}}]
            if path.startswith("/services?"):
                return 200, [_svc("fas-prod-api", "srv-1")]
            if "/env-vars" in path:
                return 200, [_env("FAS_OTHER")]
            return 200, []

        args = type("A", (), {"dry_run": True})()
        with patch.object(b, "_render", side_effect=fake), \
             patch.object(b, "fetch", side_effect=lambda n: "stub-value"):
            rc = b.cmd_sync_render_canary(args)

        self.assertEqual(rc, 0)
        # Without this, a short-circuit like `if dry_run: return 0` would make
        # `calls` empty and every assertion below pass VACUOUSLY. A dry run is
        # supposed to still READ, so demand evidence it did.
        self.assertTrue(calls, "dry run must still perform reads, but made no calls")
        self.assertTrue(any(m == "GET" for m, _ in calls), f"expected reads, saw {calls}")
        mutating = [c for c in calls if c[0] in ("PUT", "POST", "PATCH", "DELETE")]
        self.assertEqual(mutating, [], f"dry run must not mutate, saw: {mutating}")


class PreservationTest(unittest.TestCase):
    def test_write_uses_single_key_endpoint_not_bulk_replace(self):
        """Bulk PUT replaces the WHOLE set; single-key PUT cannot drop others."""
        b = _load()
        seen = []

        def fake(api_key, method, path, payload=None, timeout=60):
            seen.append((method, path, payload))
            return (200, None)

        with patch.object(b, "_render", side_effect=fake):
            b.render_upsert_env("k", "srv-1", "FAS_CANARY_SERVICE_TOKEN", "the-value")
        self.assertEqual(len(seen), 1)
        method, path, payload = seen[0]
        self.assertEqual(method, "PUT")
        self.assertTrue(path.endswith("/env-vars/FAS_CANARY_SERVICE_TOKEN"), path)
        # Assert the BODY too: omitting the value, or sending it under the
        # wrong field name, would otherwise pass this test while writing an
        # empty variable to production.
        self.assertEqual(payload, {"value": "the-value"})


class CliExitCodeTest(unittest.TestCase):
    """The documented codes (0 ok / 1 not found / 2 usage / 3 downstream) are
    what a caller branches on, so wire them through main() at least once."""

    def test_missing_credential_exits_1(self):
        b = _load()
        with patch.object(b, "fetch", return_value=None):
            self.assertEqual(b.main(["render-status"]), 1)
            self.assertEqual(b.main(["sync-render-canary", "--dry-run"]), 1)

    def test_downstream_render_failure_exits_3(self):
        b = _load()
        with patch.object(b, "fetch", side_effect=lambda n: "stub"), \
             patch.object(b, "_render", side_effect=b.RenderError("boom")):
            self.assertEqual(b.main(["render-status"]), 3)

    def test_service_not_found_exits_1_not_3(self):
        b = _load()
        with patch.object(b, "fetch", side_effect=lambda n: "stub"), \
             patch.object(b, "render_identity", return_value="own-1"), \
             patch.object(b, "render_resolve_service",
                          side_effect=b.RenderNotFound("nope")):
            self.assertEqual(b.main(["render-status"]), 1)

    def test_lost_variable_is_detected_and_fails(self):
        b = _load()
        state = {"phase": "before"}

        def fake(api_key, method, path, payload=None, timeout=60):
            if path.startswith("/owners"):
                return 200, [{"owner": {"id": "own-1"}}]
            if path.startswith("/services?"):
                return 200, [_svc("fas-prod-api", "srv-1")]
            if "/env-vars/" in path:
                state["phase"] = "after"
                return 200, None
            # Simulate Render losing an unrelated variable across the write.
            if state["phase"] == "before":
                return 200, [_env("FAS_OTHER"), _env("FAS_KEEP")]
            return 200, [_env("FAS_CANARY_SERVICE_TOKEN"), _env("FAS_KEEP")]

        args = type("A", (), {"dry_run": False})()
        with patch.object(b, "_render", side_effect=fake), \
             patch.object(b, "fetch", side_effect=lambda n: "stub-value"):
            rc = b.cmd_sync_render_canary(args)
        self.assertEqual(rc, 3, "losing an unrelated variable must fail closed")


if __name__ == "__main__":
    unittest.main()
