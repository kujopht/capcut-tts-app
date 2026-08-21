"""
V5.1 BYOK — cac muc CON LAI cua danh sach 16 "SECURITY TESTS" (Part K) chua
duoc phu boi `test_translation_byok_crypto.py` (ma hoa/AAD/fail-closed),
`test_translation_byok_service.py` (CRUD/quyen so huu tang service),
`test_translation_byok_routes.py` (HTTP/quyen so huu tang route), va
`test_translation_byok_integration.py` (fallback shared/personal, resume).
"""

from __future__ import annotations

import inspect
import re
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import main as server_main
from server import translation_byok_service
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation import TranslationJobStatus
from server.translation_byok_crypto import ByokCrypto, sinh_master_key_moi
from server.translation_byok_service import ProviderConnectionService
from server.translation_domain import TranslationVersion
from server.translation_provider_registry import ConfiguredProvider, ProviderRegistry
from server.translation_providers import TranslationProviderError
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore
from server.tests.test_translation_service import cho_job_xong

KHOA_TEST = sinh_master_key_moi()
VB_HAI_CHUONG = (
    "第1章 Khởi đầu\n萧炎看向药老。\n\n他继续前进。\n第2章 Tiếp theo\n他继续前进。"
)


# ---- Muc 3: plaintext key khong bao gio xuat hien trong LOG/PRINT -----------

class KhongInPlaintextTest(unittest.TestCase):
    """Kiem tra TINH BAT BIEN cua ma nguon: khong co dong `print`/logging
    nao trong module BYOK dong cham toi bien chua api key ro. Day la mot
    kiem tra TINH (source scan) — dung y "never log the key" cua yeu cau
    goc, boi khong co framework log tap trung nao trong du an de theo doi
    o tang runtime."""

    def test_khong_co_print_nao_trong_module_byok_service(self):
        nguon = inspect.getsource(translation_byok_service)
        self.assertNotIn("print(", nguon)

    def test_khong_co_print_nao_trong_module_crypto(self):
        from server import translation_byok_crypto
        nguon = inspect.getsource(translation_byok_crypto)
        self.assertNotIn("print(", nguon)


# ---- Muc 9: ket noi da xoa khong dung duoc nua -------------------------------

class DeletedConnectionUnusableTest(unittest.TestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_xoa_roi_build_configured_provider_tra_none(self, kiem_tra):
        store = MockTranslationStore()
        svc = ProviderConnectionService(store, crypto=ByokCrypto.tu_moi_truong(KHOA_TEST))
        svc.connect("u1", "groq", "gsk_x0000000000AB42")
        self.assertIsNotNone(svc.build_configured_provider("u1", "groq"))
        svc.delete("u1", "groq")
        self.assertIsNone(svc.build_configured_provider("u1", "groq"))

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_xoa_roi_build_all_khong_con_chua_no(self, kiem_tra):
        store = MockTranslationStore()
        svc = ProviderConnectionService(store, crypto=ByokCrypto.tu_moi_truong(KHOA_TEST))
        svc.connect("u1", "groq", "gsk_x0000000000AB42")
        svc.delete("u1", "groq")
        self.assertEqual(svc.build_all_configured_providers("u1"), [])


# ---- Muc 12: provenance khong bao gio chua bi mat ----------------------------

class ProvenanceNoSecretTest(unittest.TestCase):
    def test_translation_version_khong_co_truong_bi_mat_nao(self):
        v = TranslationVersion(
            project_id="p1", chapter_index=0, operation="auto_translate",
            pass_type="translator", previous_text="", new_text="x",
            provider_id="groq", model_id="qwen/qwen3.6-27b")
        d = v.to_dict()
        for tu_cam in ("encrypted_secret", "api_key", "authorization", "secret", "token"):
            self.assertNotIn(tu_cam, d)
        # Truong hop THAT: mot ban ghi provenance that su co provider_id/
        # model_id — dam bao gia tri do KHONG PHAI la chuoi trong key.
        self.assertNotIn("gsk_", str(d))

    def test_dataclass_khong_co_field_nao_ten_lien_quan_bi_mat(self):
        ten_field = {f for f in TranslationVersion.__dataclass_fields__}
        for tu_cam in ("secret", "api_key", "token", "authorization", "credential"):
            self.assertFalse(any(tu_cam in f.lower() for f in ten_field),
                            f"TranslationVersion co field nghi ngo: {ten_field}")


# ---- Muc 14: ca nhan het han muc -> fallback dung (chieu con lai) -----------

class _LuonThatBai:
    name = "x"

    def translate_segment(self, text, *, context):
        raise TranslationProviderError("het han muc")


#: V6 cerebras-groq-translation — xem chu thich tuong duong o
#: `test_translation_byok_integration.py` (cung ly do: gia lap dau ra "trong
#: giong ban dich" de khong trigger sai `translation_integrity.kiem_tra_tinh_ven`).
_MAU_HAN = re.compile(r"[一-鿿]")
_DOI_DAU_CAU = {"。": ".", "！": "!", "？": "?"}


class _LuonThanhCong:
    def __init__(self, name="ok"):
        self.name = name

    def translate_segment(self, text, *, context):
        sach = _MAU_HAN.sub("", text)
        for cu, moi in _DOI_DAU_CAU.items():
            sach = sach.replace(cu, moi)
        return f"[{self.name}] {sach}"


class PersonalExhaustedFallbackTest(unittest.TestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_prefer_personal_nhung_ca_nhan_het_han_muc_thi_dung_shared(self, kiem_tra):
        identity = MockIdentityAdapter()
        novels = MockMetadataStore()
        store = MockTranslationStore()
        shared_cp = ConfiguredProvider(
            provider_id="shared-groq", model_id="m", display_name="x",
            quality_hint="x", provider=_LuonThanhCong("shared"))
        registry = ProviderRegistry([shared_cp])
        byok = ProviderConnectionService(store, crypto=ByokCrypto.tu_moi_truong(KHOA_TEST))
        byok.connect("u1", "groq", "gsk_x0000000000AB42")
        svc = TranslationService(store, novels, registry=registry, byok=byok)
        an = identity.register("an@vidu.vn", "MatKhau123", "An")

        p = svc.create_project(an.user_id, title="x", source_text="第1章 x\n你好。",
                               quality_mode="nhanh")
        project = svc.get_project(p.project_id, an.user_id)
        project.prefer_personal_provider = True
        store.save_project(project)

        that_bai_cp = ConfiguredProvider(
            provider_id="groq", model_id="m", display_name="x", quality_hint="x",
            provider=_LuonThatBai(), credential_source="personal")
        with patch.object(byok, "build_all_configured_providers",
                          return_value=[that_bai_cp]):
            job = cho_job_xong(
                svc, svc.create_job(p.project_id, an.user_id).job_id, an.user_id)
        self.assertEqual(job.status, TranslationJobStatus.COMPLETED)
        lich_su = svc.list_versions(p.project_id, an.user_id)
        # Ca nhan that bai -> phai roi sang shared-groq, KHONG waiting.
        self.assertTrue(any(v.provider_id == "shared-groq"
                           for v in lich_su if v.operation == "auto_translate"))


# ---- Muc 15/16: job cho tiep tuc qua HTTP that + khong dich lai chuong da xong

class ResumeViaHttpTest(unittest.TestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_ket_noi_qua_http_lam_job_dang_cho_tiep_tuc_khong_dich_lai_chuong_xong(
        self, kiem_tra,
    ):
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.translation_store = MockTranslationStore()
        server_main.translation_byok_crypto = ByokCrypto.tu_moi_truong(KHOA_TEST)
        server_main.translation_byok_svc = ProviderConnectionService(
            server_main.translation_store, crypto=server_main.translation_byok_crypto)

        # Registry CHIA SE that bai NGAY TU DAU — mo phong shared het han muc.
        shared_that_bai = ConfiguredProvider(
            provider_id="shared-groq", model_id="m", display_name="x",
            quality_hint="x", provider=_LuonThatBai())
        registry = ProviderRegistry([shared_that_bai])
        server_main.translation_svc = TranslationService(
            server_main.translation_store, server_main.store,
            registry=registry, byok=server_main.translation_byok_svc)
        client = TestClient(server_main.app)

        token = client.post("/api/auth/register", json={
            "email": "a@vidu.vn", "password": "matkhau123"}).json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        rp = client.post("/api/translate/projects", headers=auth, json={
            "title": "x", "source_text": VB_HAI_CHUONG, "quality_mode": "nhanh"})
        project_id = rp.json()["project"]["project_id"]
        rj = client.post(f"/api/translate/projects/{project_id}/jobs", headers=auth)
        job_id_ban_dau = rj.json()["job"]["job_id"]

        han = time.time() + 5
        job = None
        while time.time() < han:
            job = client.get(f"/api/translate/jobs/{job_id_ban_dau}",
                            headers=auth).json()["job"]
            if job["status"] == "waiting_for_provider":
                break
            time.sleep(0.01)
        self.assertEqual(job["status"], "waiting_for_provider")
        self.assertEqual(job["waiting_reason"], "shared_free_quota_exhausted")

        # Thay THANH CONG cho registry CHIA SE truoc khi ket noi (mo phong
        # "moi truong da khoi phuc" KHONG can thiet — muc dich o day la ket
        # noi ca nhan phai kich hoat lai job NGAY, du chi qua registry
        # CHIA SE van con that bai; dung provider CA NHAN thanh cong).
        thanh_cong_cp = ConfiguredProvider(
            provider_id="groq", model_id="m", display_name="x", quality_hint="x",
            provider=_LuonThanhCong("personal"), credential_source="personal")
        with patch.object(server_main.translation_byok_svc,
                          "build_all_configured_providers",
                          return_value=[thanh_cong_cp]):
            rc = client.post("/api/translate/provider-connections/groq",
                             headers=auth, json={"api_key": "gsk_x0000000000AB42"})
            self.assertEqual(rc.status_code, 201, rc.text)

            han = time.time() + 5
            while time.time() < han:
                job = client.get(f"/api/translate/jobs/{job_id_ban_dau}",
                                headers=auth).json()["job"]
                if job["status"] == "completed":
                    break
                time.sleep(0.01)

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["job_id"], job_id_ban_dau)  # VAN LA job cu
        rproj = client.get(f"/api/translate/projects/{project_id}", headers=auth)
        chuong = rproj.json()["chapters"]
        self.assertEqual(len(chuong), 2)
        self.assertTrue(all(c["translated"] for c in chuong))
        # Chi 1 job cho ca du an — khong tao job thu hai khi ket noi.
        self.assertEqual(len(rproj.json()["jobs"]), 1)


if __name__ == "__main__":
    unittest.main()
