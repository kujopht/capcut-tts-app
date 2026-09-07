"""Fanfic Production Farmer — vong lap san xuat noi dung tu dong.

Chay 24/7 tren may AWS t3a.medium (2 vCPU / 4 GiB). May do la NGUOI GAT:
no tim nguon, khu trung lap, dieu phoi, va giu han muc. No **khong** la noi
chay suy dien nang.

Ranh gioi do phan cung quyet dinh, khong phai so thich:

    ASR do duoc 0,96x thoi gian thuc tren chinh lop may nay. Mot tap 30 phut
    an tron mot trong hai vCPU nua tieng va lam dung ca hai lan san xuat.
    Nen: danh gia chat luong -> Gemini API, TTS -> Cloud Run da co, anh bia
    -> provider HTTP. Tren VM chi con I/O va dieu phoi.

Hai lan:

  A. AUDIO CO SAN   nguon -> sieu du lieu/ban boc loi -> Gemini duyet ->
                    chuan hoa audio -> anh bia -> ung vien xuat ban
  B. TRUYEN CHU     nguon -> trich xuat/lam sach -> Gemini duyet ->
                    TTS Cloud Run -> anh bia -> ung vien xuat ban

KHONG xay lai cong doan nao da co: `content_queue` +
`chinese_media_orchestrator` cho lan A, `tts_dispatch` cho lan B,
`CoverPipelineService` cho anh bia, R2 + Appwrite cho luu tru.

KHONG sinh hoat hinh AI — do la backlog, co y chua lam.
"""

from server.farmer.dedup import WorkKey, work_key
from server.farmer.quotas import FarmerQuotas, QuotaState, QuotaExceeded

__all__ = ["WorkKey", "work_key", "FarmerQuotas", "QuotaState", "QuotaExceeded"]
