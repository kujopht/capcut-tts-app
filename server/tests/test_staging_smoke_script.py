"""
Script smoke test staging khong duoc lo gi ra log.

Script nay chay tren may nguoi van hanh va dau ra cua no thuong duoc dan vao
ticket hoac bao cao. Mot presigned URL in nguyen ra la du de bat ky ai tai file
ve, va host cua no chua R2 account id.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]


def nap_script():
    duong = GOC / "scripts" / "staging_smoke.py"
    spec = importlib.util.spec_from_file_location("staging_smoke", duong)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["staging_smoke"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPresignedUrlIsRedacted(unittest.TestCase):
    #: Dang that cua mot URL R2 da ky. MOI GIA TRI DEU LA GIA — chuoi lap
    #: `000…`/`111…` co y de khong ai nham voi dinh danh that. Ban dau cho nay
    #: chua R2 account id THAT, chep tu dau ra luc chay thu; commit len la lo.
    URL = (
        "https://00000000000000000000000000000000.r2.cloudflarestorage.com"
        "/fanfic-staging/audio/11111111111111111111/chp_2222222222222222"
        "/3333333333333333333333333333333333333333333333333333333333333333.mp3"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
        "&X-Amz-Credential=00000000000000000000000000000000%2F20260808%2Fauto%2Fs3%2Faws4_request"
        "&X-Amz-Signature=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    )

    def setUp(self) -> None:
        self.mod = nap_script()

    def rut_gon(self) -> str:
        return self.mod.rut_gon_url(self.URL)

    def test_the_signature_is_gone(self):
        ra = self.rut_gon()
        for cam in ("X-Amz-Signature", "deadbeef", "X-Amz-Credential",
                    "AWS4-HMAC-SHA256"):
            self.assertNotIn(cam, ra, f"chu ky/credential bi lo: {cam}")

    def test_the_r2_account_id_is_gone(self):
        ra = self.rut_gon()
        self.assertNotIn("00000000000000000000000000000000", ra,
                         "host chua R2 account id — khong duoc in")
        self.assertNotIn("r2.cloudflarestorage.com", ra)

    def test_the_bucket_and_owner_are_gone(self):
        ra = self.rut_gon()
        for cam in ("fanfic-staging", "11111111111111111111",
                    "chp_2222222222222222"):
            self.assertNotIn(cam, ra, f"dinh danh bi lo: {cam}")

    def test_the_object_hash_is_gone(self):
        ra = self.rut_gon()
        bam = "3" * 64
        self.assertIn(bam, self.URL, "moc phai con nam trong URL nguon")
        self.assertNotIn(bam[:16], ra, "hash noi dung bi lo")

    def test_it_still_says_something_useful(self):
        """Che het ma khong con thong tin gi thi cung vo dung."""
        ra = self.rut_gon()
        self.assertIn("mp3", ra, "phai con biet duoc duoi tep")
        self.assertIn("co_query=co", ra, "phai con biet URL co duoc ky hay khong")

    def test_a_url_without_a_query_is_reported_as_unsigned(self):
        ra = self.mod.rut_gon_url("https://vi-du.test/a/b.mp3")
        self.assertIn("co_query=KHONG", ra)


class TestTheScriptCleansUpAfterItself(unittest.TestCase):
    def setUp(self) -> None:
        self.nguon = (GOC / "scripts" / "staging_smoke.py").read_text(encoding="utf-8")

    def test_cleanup_runs_even_when_a_step_fails(self):
        """
        `don_dep` phai nam trong `finally`.

        Mot buoc hong ma khong don thi fixture `[SMOKE]` nam lai tren staging,
        va lan chay sau se doc phai rac cua lan truoc.
        """
        i = self.nguon.find("finally:")
        self.assertGreater(i, 0, "phai co khoi finally")
        self.assertIn("don_dep(", self.nguon[i:i + 400],
                      "don dep phai nam trong finally")

    def test_fixtures_are_clearly_marked(self):
        self.assertIn("[SMOKE]", self.nguon,
                      "fixture phai co tien to de nhan ra va don duoc")

    def test_it_never_prints_a_token(self):
        """Khong duoc in `token`, `tok_a`, `tok_b` ra man hinh."""
        for dong in self.nguon.splitlines():
            hep = dong.strip()
            if not hep.startswith("print("):
                continue
            for cam in ("tok_a", "tok_b", '["token"]', "['token']"):
                self.assertNotIn(cam, hep, f"dong print lo token: {hep[:80]}")


if __name__ == "__main__":
    unittest.main()
