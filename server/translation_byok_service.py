"""
Dich vu ket noi provider AI CA NHAN cua nguoi dung (V5.1, BYOK).

Tach RIENG khoi `TranslationService`: day la MOT moi quan tam khac (quan ly
credential CUA TUNG NGUOI DUNG — ma hoa/giai ma/kiem tra/xoa), khong phai
dieu phoi job dich. `TranslationService` GOI vao day khi can mot provider CA
NHAN de dich, khong tu lam viec do.

NGUYEN TAC BAT BUOC (Part D): `connection.user_id == nguoi_goi.user_id`
PHAI dung truoc khi giai ma hoac dung mot ket noi CA NHAN. Moi phuong thuc o
day di qua `self._store.get_connection(user_id, provider_id)` — ham store
nay tu no da CHI tra ve ket noi DUNG user_id truyen vao (xem
`MockTranslationStore.get_connection`/`AppwriteTranslationStore.get_connection`,
NotFoundError neu khac chu), nen KHONG CO DUONG NAO o tang nay de doc nham
ket noi cua nguoi khac — nhung van assert lai o day cho CHAC (rao chan kep,
xem `translation_byok_crypto.py` ve AAD — cung triet ly "hai lop doc lap").
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from server.adapters import NotFoundError
from server.domain import now_iso
from server.translation import TranslationError
from server.translation_byok_crypto import ByokCrypto, ByokDecryptError, lay_4_ky_tu_cuoi
from server.translation_domain import ProviderConnection
from server.translation_model_profiles import GROQ_MODEL_PROFILES, ModelProfile
from server.translation_provider_registry import (
    ConfiguredProvider,
    GroqProvider,
    ProviderStatus,
    kiem_tra_ket_noi_groq,
)

#: Provider BYOK duoc ho tro — them provider moi CHI can them mot muc o day
#: + mot nhanh trong `_kiem_tra`/`build_configured_provider`.
SUPPORTED_BYOK_PROVIDERS = ("groq",)

#: model_id -> ho so, tra cuu nguoc tu `GROQ_MODEL_PROFILES` (khoa o do la
#: "qwen"/"gpt_oss_120b"/... — o day can tra theo model_id THAT nguoi dung
#: da chon/luu, vi `ProviderConnection.selected_model` luu model_id).
_GROQ_PROFILE_BY_MODEL_ID = {p.model_id: p for p in GROQ_MODEL_PROFILES.values()}


def _model_mac_dinh(provider_id: str) -> str:
    if provider_id == "groq":
        return os.environ.get("GROQ_MODEL", "").strip() or "qwen/qwen3.6-27b"
    return ""


def _ho_so_groq_cho_model(model_id: str) -> ModelProfile:
    """Ho so tham so cho MOT model_id Groq — model CURATED (Qwen/GPT-OSS)
    tra dung ho so cua no; model KHAC (nguoi dung tu nhap, chua co trong
    danh sach curated) tra ho so RONG tham so — an toan, khong doan bua tham
    so cho mot model chua biet."""
    return _GROQ_PROFILE_BY_MODEL_ID.get(model_id) or ModelProfile(
        key="custom", model_id=model_id, display_name=model_id, quality_hint="")


class ByokNotConfiguredError(TranslationError):
    """May chu nay CHUA cau hinh `TRANSLATION_BYOK_MASTER_KEY` — tinh nang
    BYOK khong dung duoc. KHAC voi "nguoi dung chua ket noi" (do la trang
    thai binh thuong): day la mot LOI CAU HINH cua may chu."""


class ProviderConnectionService:
    def __init__(self, store: Any, crypto: Optional[ByokCrypto] = None):
        self._store = store
        #: None = may chu CHUA bat BYOK (thieu master key) — moi phuong thuc
        #: can ma hoa/giai ma se nem `ByokNotConfiguredError` ro rang, KHONG
        #: am tham lam gi khac (vd luu api key RO — tuyet doi khong).
        self._crypto = crypto

    def is_configured(self) -> bool:
        return self._crypto is not None

    def _crypto_bat_buoc(self) -> ByokCrypto:
        if self._crypto is None:
            raise ByokNotConfiguredError(
                "Máy chủ này chưa bật tính năng kết nối API key cá nhân.")
        return self._crypto

    # ==================================================================== CRUD

    def list_connections(self, user_id: str) -> List[ProviderConnection]:
        return self._store.list_connections(user_id)

    def connect(self, user_id: str, provider_id: str, api_key: str, *,
               selected_model: str = "") -> ProviderConnection:
        """
        Ket noi (hoac THAY THE — upsert) MOT provider ca nhan.

        Kiem tra key TRUOC KHI ma hoa/luu — khong bao gio luu mot key
        chua-biet-dung-hay-sai xuong kho (Part E: "Validation should happen
        server-side").
        """
        if provider_id not in SUPPORTED_BYOK_PROVIDERS:
            raise TranslationError(
                f"Chưa hỗ trợ kết nối cá nhân cho provider '{provider_id}'.")
        crypto = self._crypto_bat_buoc()
        sach = (api_key or "").strip()
        if not sach:
            raise TranslationError("Thiếu API key.")
        model = (selected_model or "").strip() or _model_mac_dinh(provider_id)

        self._kiem_tra_key(provider_id, sach, model)

        now = now_iso()
        conn = ProviderConnection(
            user_id=user_id, provider_id=provider_id,
            encrypted_secret=crypto.ma_hoa(sach, user_id=user_id,
                                           provider_id=provider_id),
            last4=lay_4_ky_tu_cuoi(sach),
            status=ProviderStatus.AVAILABLE.value,
            selected_model=model, created_at=now, updated_at=now,
            last_verified_at=now)
        return self._store.save_connection(conn)

    def test_connection(self, user_id: str, provider_id: str) -> ProviderConnection:
        """Kiem tra LAI mot ket noi DA co — giai ma, goi lai kiem tra nhe,
        cap nhat trang thai/moc kiem tra gan nhat."""
        crypto = self._crypto_bat_buoc()
        conn = self._store.get_connection(user_id, provider_id)
        if conn.user_id != user_id:  # rao chan kep — xem docstring dau file
            raise NotFoundError("Chưa kết nối provider này.")
        try:
            api_key = crypto.giai_ma(conn.encrypted_secret, user_id=conn.user_id,
                                     provider_id=conn.provider_id)
        except ByokDecryptError as exc:
            raise TranslationError(
                "Không đọc được kết nối đã lưu — hãy kết nối lại.") from exc

        self._kiem_tra_key(provider_id, api_key, conn.selected_model)

        conn.status = ProviderStatus.AVAILABLE.value
        conn.last_verified_at = now_iso()
        conn.updated_at = conn.last_verified_at
        return self._store.save_connection(conn)

    def delete(self, user_id: str, provider_id: str) -> None:
        self._store.delete_connection(user_id, provider_id)

    def _kiem_tra_key(self, provider_id: str, api_key: str, model: str) -> None:
        """Nem `ConnectionCheckError` (tu `translation_provider_registry.py`)
        voi `code` sach khi that bai — KHONG bat o day, de nguyen cho tang
        route anh xa thanh HTTP."""
        if provider_id == "groq":
            kiem_tra_ket_noi_groq(api_key, model)
        else:
            raise TranslationError(
                f"Chưa hỗ trợ kiểm tra kết nối cho provider '{provider_id}'.")

    # ==================================================================== dung de dich

    def build_configured_provider(self, user_id: str, provider_id: str
                                  ) -> Optional[ConfiguredProvider]:
        """
        Dung o `TranslationService` khi dich THAT bang provider ca nhan.

        Giai ma NGAY LUC GOI, KHONG cache qua lan goi khac (AES-GCM giai ma
        la vi-giay, khong dang de danh doi voi rui ro giu api key ro trong
        bo nho lau hon can thiet). Tra `None` (KHONG nem loi) neu chua ket
        noi/may chu chua bat BYOK/giai ma that bai — "khong co provider ca
        nhan" la mot trang thai BINH THUONG can xu ly, khong phai loi.
        """
        if self._crypto is None:
            return None
        try:
            conn = self._store.get_connection(user_id, provider_id)
        except NotFoundError:
            return None
        if conn.user_id != user_id:  # rao chan kep — xem docstring dau file
            return None
        try:
            api_key = self._crypto.giai_ma(
                conn.encrypted_secret, user_id=conn.user_id,
                provider_id=conn.provider_id)
        except ByokDecryptError:
            return None

        if provider_id == "groq":
            model = conn.selected_model or _model_mac_dinh("groq")
            provider = GroqProvider(api_key=api_key,
                                    profile=_ho_so_groq_cho_model(model))
        else:
            return None

        return ConfiguredProvider(
            provider_id=provider_id, model_id=model,
            display_name=f"{provider_id} (cá nhân)", quality_hint="cá nhân",
            provider=provider, free_tier=True, credential_source="personal")

    def build_all_model_providers(self, user_id: str, provider_id: str
                                  ) -> List[ConfiguredProvider]:
        """
        Phan 3G (overnight Phase 3): MOT ket noi Groq ca nhan -> BA
        `ConfiguredProvider` (Qwen/GPT-OSS 120B/GPT-OSS 20B), CUNG mot api
        key da giai ma — dung y "Do not ask user to enter a key per model".

        `credential.user_id == job.user_id` van duoc cuong che y HET
        `build_configured_provider`: giai ma qua CHINH `_crypto`, chi doc
        ket noi CUA user_id duoc truyen vao — KHONG co duong nao de gop
        credential ca nhan cua hai nguoi dung ("No pooling personal
        credentials").

        Provider KHAC "groq" hien chua ho tro nhieu model (chi Groq co
        catalog curated) — tra ve MOT phan tu duy nhat qua
        `build_configured_provider`, giu hanh vi cu.
        """
        if provider_id != "groq":
            cp = self.build_configured_provider(user_id, provider_id)
            return [cp] if cp is not None else []

        if self._crypto is None:
            return []
        try:
            conn = self._store.get_connection(user_id, provider_id)
        except NotFoundError:
            return []
        if conn.user_id != user_id:
            return []
        try:
            api_key = self._crypto.giai_ma(
                conn.encrypted_secret, user_id=conn.user_id,
                provider_id=conn.provider_id)
        except ByokDecryptError:
            return []

        ra = []
        for profile_key, profile in GROQ_MODEL_PROFILES.items():
            ra.append(ConfiguredProvider(
                provider_id=f"groq_{profile_key}", model_id=profile.model_id,
                display_name=f"{profile.display_name} (cá nhân)",
                quality_hint="cá nhân",
                provider=GroqProvider(api_key=api_key, profile=profile),
                free_tier=True, credential_source="personal"))
        return ra

    def build_all_configured_providers(self, user_id: str) -> List[ConfiguredProvider]:
        """Tat ca provider ca nhan DA KET NOI cua MOT nguoi dung, san sang
        dua vao `ProviderRegistry.translate_segment_with_personal`.

        Tu Phan 3G: mot ket noi Groq gop VAO DAY ca ba model curated (xem
        `build_all_model_providers`), khong chi MOT model da chon —
        `selected_model` cua ket noi van con y nghia rieng cho UI hien thi
        "model ưu tiên", nhung khong con GIOI HAN duong fallback nua."""
        if self._crypto is None:
            return []
        ra: List[ConfiguredProvider] = []
        for conn in self._store.list_connections(user_id):
            ra.extend(self.build_all_model_providers(user_id, conn.provider_id))
        return ra

    def sync_status(self, user_id: str, cp: ConfiguredProvider) -> None:
        """
        Ghi lai trang thai SONG (`ConfiguredProvider._status`, cap nhat
        trong bo nho ngay sau moi lan goi that/loi) xuong kho ben vung —
        de `GET .../provider-connections` phan anh dung "Groq của bạn đã
        đạt giới hạn" ma KHONG bat nguoi dung phai tu bam "Kiểm tra lại".

        Im lang bo qua neu khong tim thay ket noi (vd vua bi xoa giua
        chung) — day chi la dong bo hien thi, khong phai duong ghi chinh.
        """
        try:
            conn = self._store.get_connection(user_id, cp.provider_id)
        except NotFoundError:
            return
        entry = cp.catalog_entry()
        conn.status = entry.status.value
        conn.updated_at = now_iso()
        self._store.save_connection(conn)
