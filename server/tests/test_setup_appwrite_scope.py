"""`--only` phai FAIL CLOSED, khong duoc am tham noi rong ra toan bo schema.

Neu ra qua review doi khang doc lap (Antigravity Claude Opus, 2026-08-29) khi
chuan bi mot migration co pham vi hep tren san xuat.

Loi cu: `--only` khong co gia tri lam `only = ""`. Vi "" la falsy nen
`run()` doc no Y HET "khong loc" va chay TOAN BO SCHEMA. Nguoi van hanh
duoc phep tao DUNG MOT bang; mot lan go thieu chu lai ban POST vao moi
collection dang song. Khong bao loi, khong canh bao — mot cu tut pham vi
am tham, dung loai su co ma migration co pham vi sinh ra de tranh.
"""
from __future__ import annotations

import unittest
from unittest import mock

from scripts.setup_appwrite import SCHEMA, main


class OnlyFailsClosedTest(unittest.TestCase):
    """Moi dang `--only` KHONG chi ro collection deu phai dung han."""

    def _run(self, argv):
        """Chay `main` voi `Setup` da bi thay — khong the cham mang."""
        with mock.patch("scripts.setup_appwrite.Setup") as gia:
            rc = main(argv)
        return rc, gia

    def test_only_as_last_argument_refuses(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run(["--dry-run", "--only"])
        self.assertIn("--only", str(ctx.exception))

    def test_only_with_empty_value_refuses(self):
        with self.assertRaises(SystemExit):
            self._run(["--only="])

    def test_only_with_whitespace_value_refuses(self):
        with self.assertRaises(SystemExit):
            self._run(["--only", "   "])
        with self.assertRaises(SystemExit):
            self._run(["--only=  "])

    def test_refusal_never_reaches_setup_at_all(self):
        """Phai dung TRUOC khi dung toi Appwrite, khong phai giua chung."""
        with mock.patch("scripts.setup_appwrite.Setup") as gia:
            with self.assertRaises(SystemExit):
                main(["--only"])
        gia.assert_not_called()

    def test_error_message_lists_the_valid_choices(self):
        """Thong bao phai chi ra viec can lam, khong chi noi 'sai'."""
        with self.assertRaises(SystemExit) as ctx:
            main(["--only"])
        self.assertIn("scrape_run_items", str(ctx.exception))


class OnlyStillWorksTest(unittest.TestCase):
    """Ban sua khong duoc lam hong cach dung dung."""

    def test_space_form_scopes_to_one_collection(self):
        with mock.patch("scripts.setup_appwrite.Setup") as gia:
            self.assertEqual(main(["--dry-run", "--only", "scrape_run_items"]), 0)
        gia.return_value.run.assert_called_once_with(only="scrape_run_items")

    def test_equals_form_scopes_to_one_collection(self):
        with mock.patch("scripts.setup_appwrite.Setup") as gia:
            self.assertEqual(main(["--only=scrape_run_items"]), 0)
        gia.return_value.run.assert_called_once_with(only="scrape_run_items")

    def test_no_only_flag_still_means_every_collection(self):
        """Khong truyen `--only` van la 'tat ca' — day la y dinh, khong phai
        tut pham vi am tham. Chi truong hop `--only` RONG moi la loi."""
        with mock.patch("scripts.setup_appwrite.Setup") as gia:
            self.assertEqual(main(["--dry-run"]), 0)
        gia.return_value.run.assert_called_once_with(only="")

    def test_unknown_collection_name_is_still_rejected_by_run(self):
        """`run()` van la choi cuoi cung: ten khong co trong SCHEMA -> dung."""
        from scripts.setup_appwrite import Setup

        setup = Setup.__new__(Setup)
        with self.assertRaises(SystemExit):
            Setup.run(setup, only="khong_he_ton_tai")

    def test_a_flag_mistaken_for_a_value_is_caught_downstream(self):
        """`--only --dry-run` lay "--dry-run" lam ten; no khong o trong SCHEMA
        nen `run()` dung. Ghi lai de ban sua sau khong lam mat lop chan nay."""
        self.assertNotIn("--dry-run", SCHEMA)


if __name__ == "__main__":
    unittest.main()
