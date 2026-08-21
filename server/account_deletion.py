"""
Xoa tai khoan theo yeu cau cua CHINH nguoi dung.

VI SAO MOT MODULE RIENG: du lieu cua mot nguoi dung nam o BON kho doc lap
(metadata/xa hoi, gamification, ban dich, danh tinh) cong voi kho tep. Khong
kho nao trong so do biet ve nhung kho con lai — do la co y (xem docstring dau
`server/translation_store.py`) — nen phai co DUNG MOT cho biet thu tu don. Rai
thu tu do vao route la cach chac chan nhat de mot nhanh nao do quen mot buoc.

THU TU LA MOT PHAN CUA HOP DONG, khong phai chi tiet cai dat:

    1. du lieu ung dung (truyen, audio, xa hoi, gamification, ban dich)
    2. doi tuong trong kho tep (audio, phu de, bia, anh bai dang, anh dai dien)
    3. DANH TINH — sau cung

Neu buoc 3 chay truoc va mot buoc sau hong, ta con lai du lieu KHONG CO CHU:
khong route nao doi lai duoc (moi route deu loc theo `owner_id` lay tu token),
va chinh nguoi dung cung khong con duong nao goi lai de don not. Lam theo thu
tu nay thi truong hop xau nhat la mot lan xoa DO NUA DUONG voi tai khoan van
con — nguoi dung bam lai la chay tiep, va moi buoc deu IDEMPOTENT.

Chinh sach luu tru (ai xoa, ai o lai, ai bi an danh) KHONG o day: no o
`MetadataStore.delete_account` (server/adapters.py), canh chinh cho hien thuc
no. Doc docstring do truoc khi doi bat ky dong nao trong tep nay.
"""

from __future__ import annotations

from typing import Any, Dict, List

from server.adapters import AuthError, NotFoundError


class AccountDeletionService:
    """
    Xoa tai khoan cua CHINH nguoi goi.

    KHONG co phep kiem quyen so huu nao trong tep nay, va do la dung: `user_id`
    duy nhat di vao day den tu `current_profile` (token da xac minh). Khong co
    ban "quan tri xoa nguoi khac" — them no la them mot duong co the bi lam
    dung, va khu quan tri da co `set_account_enabled` de chan dang nhap.
    """

    def __init__(self, identity, store, storage, gamification_store,
                 translation_store, translation_service) -> None:
        self._identity = identity
        self._store = store
        self._storage = storage
        self._gamification = gamification_store
        self._translation_store = translation_store
        self._translation = translation_service

    def delete_account(self, user_id: str) -> Dict[str, Any]:
        """
        Don sach roi xoa tai khoan. Tra ve so ban ghi da don theo tung nhom.

        IDEMPOTENT o MOI buoc: goi lan hai (request bi thu lai, hoac nguoi dung
        bam hai lan) chi tra ve cac so 0 va `identity_deleted=False`, khong nem.
        """
        if not user_id:
            return {"identity_deleted": False}

        # Doc `avatar_key` TRUOC KHI xoa bat cu thu gi: sau khi hang `profiles`
        # mat di thi khong con duong nao biet anh dai dien nam o khoa nao, va
        # object do se o lai trong R2 mai mai.
        khoa_avatar = self._khoa_avatar(user_id)

        bc = dict(self._store.delete_account(user_id))
        khoa_doi_tuong: List[str] = list(bc.pop("object_keys", []))
        if khoa_avatar:
            khoa_doi_tuong.append(khoa_avatar)

        bc["gamification"] = self._gamification.delete_account_data(user_id)
        bc["translation_projects"] = self._xoa_ban_dich(user_id)
        bc["provider_connections"] = self._xoa_ket_noi_provider(user_id)
        bc["objects"] = self._xoa_doi_tuong(khoa_doi_tuong)

        # SAU CUNG — xem ghi chu dau module ve thu tu.
        bc["identity_deleted"] = bool(self._identity.delete_account(user_id))
        return bc

    # -- tung buoc ------------------------------------------------------------

    def _khoa_avatar(self, user_id: str) -> str:
        """Khoa anh dai dien, hoac chuoi rong. KHONG BAO GIO nem: khong doc
        duoc ho so (chua co, hoac Appwrite dang gian doan) khong duoc lam hong
        ca lan xoa — mat mot object trong kho chi ton dung luong."""
        try:
            return str(getattr(self._identity.get_profile(user_id),
                               "avatar_key", "") or "")
        except (NotFoundError, AuthError):
            return ""

    def _xoa_ban_dich(self, user_id: str) -> int:
        """Xoa TUNG du an dich qua `TranslationService.delete_project` — KHONG
        lai logic cascade cua no (job/thuat ngu/lich su phien ban) o day.

        `delete_project` tu kiem quyen so huu; truyen `user_id` vao chinh la
        phep bao dam khong bao gio xoa du an cua nguoi khac, ke ca khi
        `list_projects` co loi loc."""
        dem = 0
        for project in self._translation.list_projects(user_id):
            self._translation.delete_project(project.project_id, user_id)
            dem += 1
        return dem

    def _xoa_ket_noi_provider(self, user_id: str) -> int:
        """Ket noi BYOK (`translation_provider_connections`) khong gan voi du
        an nao — no gan voi NGUOI DUNG, nen `delete_project` khong don duoc.

        Day la ban ghi chua bi mat da ma hoa (`encrypted_secret`), nen no phai
        di cung tai khoan chu khong duoc de lai."""
        dem = 0
        for conn in self._translation_store.list_connections(user_id):
            self._translation_store.delete_connection(user_id, conn.provider_id)
            dem += 1
        return dem

    def _xoa_doi_tuong(self, khoa: List[str]) -> int:
        """Xoa object trong kho tep. Loi o day KHONG lam hong lan xoa: metadata
        da mat nen khong route nao cham toi duoc object con lai — no chi ton
        dung luong. CUNG cach xu ly voi `main.py::_purge_chapter`."""
        dem = 0
        for k in dict.fromkeys([k for k in khoa if k]):
            try:
                if self._storage.delete(k):
                    dem += 1
            except Exception:
                continue
        return dem
