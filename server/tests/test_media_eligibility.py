"""Cong dieu kien do dai nguon.

Bat bien quan trong nhat: **fail closed**. Khong do duoc do dai thi KHONG cho
vao hang doi thuc thi. Doan la "chac ngan" roi de mot nguon 22 gio lot vao se
lam ket ban tieu thu DUY NHAT ca ngay — dat hon nhieu so voi mot lan bo sot
phai kiem lai bang tay.
"""
from __future__ import annotations

import unittest
from unittest import mock

from server.scraper import media_eligibility as me


class ThresholdTest(unittest.TestCase):
    def test_default_is_two_hours(self):
        self.assertEqual(me.DEFAULT_MAX_SOURCE_SECONDS, 7200)

    def test_env_var_overrides(self):
        with mock.patch.dict("os.environ", {me.MAX_SOURCE_SECONDS_ENV: "1800"}):
            self.assertEqual(me.max_source_seconds(), 1800)

    def test_a_typo_does_not_open_the_gate(self):
        """Mot bien moi truong danh sai phai quay ve mac dinh, KHONG duoc
        hieu thanh 'khong gioi han'."""
        for bad in ("khong-phai-so", "", "0", "-5", "  "):
            with self.subTest(value=bad):
                with mock.patch.dict("os.environ",
                                     {me.MAX_SOURCE_SECONDS_ENV: bad}):
                    self.assertEqual(me.max_source_seconds(),
                                     me.DEFAULT_MAX_SOURCE_SECONDS)


class EvaluateTest(unittest.TestCase):
    def test_unknown_duration_is_ineligible_not_allowed(self):
        verdict = me.evaluate(None, 7200)
        self.assertFalse(verdict.eligible)
        self.assertIn("fail closed", verdict.reason)

    def test_zero_or_negative_duration_is_ineligible(self):
        for bad in (0, -1):
            with self.subTest(duration=bad):
                self.assertFalse(me.evaluate(bad, 7200).eligible)

    def test_boundary_is_inclusive(self):
        self.assertTrue(me.evaluate(7200, 7200).eligible)
        self.assertFalse(me.evaluate(7201, 7200).eligible)

    def test_the_proven_canary_length_is_eligible(self):
        """Lan san xuat thanh cong da chung minh dung mot video 102 giay."""
        self.assertTrue(me.evaluate(102, 7200).eligible)

    def test_every_currently_queued_source_length_is_ineligible(self):
        """Do that tu hang doi production 2026-09-07: ngan nhat 38.019s."""
        for seconds in (38019, 77447, 82060, 111617):
            with self.subTest(seconds=seconds):
                verdict = me.evaluate(seconds, 7200)
                self.assertFalse(verdict.eligible)
                self.assertIn("backlog", verdict.reason)

    def test_reason_names_both_numbers(self):
        verdict = me.evaluate(38019, 7200)
        self.assertIn("10h33m39s", verdict.reason)
        self.assertIn("2h00m00s", verdict.reason)

    def test_marker_roundtrips(self):
        verdict = me.evaluate(38019, 7200)
        self.assertTrue(me.is_ineligible_marker(verdict.as_last_error()))

    def test_marker_does_not_fire_on_ordinary_errors(self):
        for other in ("", "translation: JSONDecodeError",
                      "transcript: CHO: can --audio"):
            with self.subTest(last_error=other):
                self.assertFalse(me.is_ineligible_marker(other))


if __name__ == "__main__":
    unittest.main()
