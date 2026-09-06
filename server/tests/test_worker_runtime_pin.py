"""
Runtime cua WORKER phai duoc ghim, va phai ghim dung ban production dang chay.

Moi test o day bat nguon tu mot su viec quan sat duoc ngay 2026-09-06, khong
phai tu suy doan:

  Anh container `tts-worker:v1` chay tren Cloud Run NHAN duoc job roi that bai
  ngay lap tuc, ca 10/10, voi `provider_not_installed`:

      Phan 1/3: Chua cai goi piper-tts nen khong dung duoc giong Piper local

  Nguyen nhan: anh do duoc dung bang `server/requirements.txt` — tep cua tien
  trinh WEB, noi `piper-tts` bi comment CO Y. Worker thi bat buoc phai co no.
  Mot dong `-r requirements.txt` sai cho trong Dockerfile la du de giet toan bo
  kha nang tong hop, va no chi lo ra luc chay job that.

  Manh thu hai: ghim trong kho la `1.6.0` trong khi worker production
  (`13.212.224.218`) that su chay `1.7.0`. Ghim da lech khoi thuc te ma khong
  co gi keu len.

Hai test duoi day khoa lai ca hai manh do.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
REQ_WORKER = GOC / "requirements-worker.txt"
REQ_WEB = GOC / "requirements.txt"

#: Ban DA duoc kiem chung chay that tren Cloud Run (10/10 job, 3/3 doan moi
#: job) VA la ban worker production dang chay. Doi so nay ma khong chay lai
#: cong tuong duong la lam hong chinh dieu test nay bao ve.
PIPER_PRODUCTION = "1.7.0"

_DONG_HIEU_LUC = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)\s*([^\s;#]+)")


def _dong_hieu_luc(path: Path) -> dict:
    """Cac dong requirement THAT SU co hieu luc — bo qua comment va dong rong."""
    ra = {}
    for dong in path.read_text(encoding="utf-8").splitlines():
        if not dong.strip() or dong.lstrip().startswith("#"):
            continue
        m = _DONG_HIEU_LUC.match(dong)
        if m:
            ra[m.group(1).lower()] = (m.group(2), m.group(3))
    return ra


class GhimRuntimeWorker(unittest.TestCase):

    def test_worker_ghim_piper_dung_ban_production(self):
        """`requirements-worker.txt` phai ghim CHINH XAC ban production."""
        goi = _dong_hieu_luc(REQ_WORKER)
        self.assertIn(
            "piper-tts", goi,
            "requirements-worker.txt khong con dong piper-tts CO HIEU LUC. "
            "Worker khong co Piper thi nhan job roi chet voi "
            "provider_not_installed — da xay ra that tren Cloud Run 2026-09-06.",
        )
        toan_tu, ban = goi["piper-tts"]
        self.assertEqual(
            toan_tu, "==",
            "piper-tts phai ghim bang `==`, khong phai "
            f"`{toan_tu}`. Cac ban Piper khong tuong thich chu ky API voi nhau; "
            "mot ban moi bo `synthesize_wav` la giong chet ngay khi chay that.",
        )
        self.assertEqual(
            ban, PIPER_PRODUCTION,
            f"piper-tts ghim {ban} nhung ban production dang chay la "
            f"{PIPER_PRODUCTION}. Hai ben lech nhau nghia la cong 'tuong duong "
            "dau ra' khong con y nghia: Cloud Run va AWS chay hai runtime khac "
            "nhau. Neu that su muon doi, hay chay lai cong tuong duong roi cap "
            "nhat PIPER_PRODUCTION o day cung luc.",
        )

    def test_requirements_web_khong_keo_theo_piper(self):
        """
        Tep cua WEB phai KHONG cai piper — va do la co y, khong phai thieu sot.

        Test nay giu nguyen su tach doi. Neu ai do 'sua' bang cach bo comment o
        `requirements.txt`, tien trinh web se keo theo onnxruntime vai chuc MB
        tren mot goi Free 512 MB RAM. Cach dung la sua DOCKERFILE cua worker de
        no dung `requirements-worker.txt`, khong phai lam nang tien trinh web.
        """
        self.assertNotIn(
            "piper-tts", _dong_hieu_luc(REQ_WEB),
            "requirements.txt (tien trinh WEB) dang cai piper-tts. Web khong "
            "chay job TTS (FAS_INLINE_WORKER=false) nen khong can no. Anh "
            "worker phai dung requirements-worker.txt.",
        )

    def test_worker_ke_thua_requirements_web(self):
        """`-r requirements.txt` phai con — worker can ca phu thuoc cua web."""
        noi_dung = REQ_WORKER.read_text(encoding="utf-8")
        self.assertIsNotNone(
            re.search(r"^\s*-r\s+requirements\.txt\s*$", noi_dung, re.MULTILINE),
            "requirements-worker.txt phai con dong `-r requirements.txt`.",
        )


if __name__ == "__main__":
    unittest.main()
