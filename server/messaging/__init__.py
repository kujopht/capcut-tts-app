"""
Nhan tin 1:1 cua Fanfic (Chat V1, phan chu) — Appwrite SO HUU du lieu va Realtime.

    ids.py                 dinh danh tat dinh (nguoi, hoi thoai, tin, chan)
    domain.py              mo hinh + loi, KHONG biet kho luu tru
    repository.py          hop dong kho + ban bo nho (mock/test) co Realtime mo phong
    service.py             nghiep vu (chan, idempotent, chua doc, xem truoc) — chi noi voi hop dong
    appwrite_tablesdb.py   kho Appwrite TablesDB (kiem that tren fanfic-staging, Cloud 2.3)
    realtime.py            Appwrite Realtime -> su kien, xac thuc bang session CUA NGUOI XEM
    runtime.py             chon kho theo moi truong (FAS_CHAT_V1 — tat mac dinh tren Appwrite)
    routes.py              /api/chat/* (REST + SSE)

Khong nham voi `server/chat/` (AI Chat/RAG). Tencent/TRTC de danh cho goi thoai/video.
"""
