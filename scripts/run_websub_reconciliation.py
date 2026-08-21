#!/usr/bin/env python3
"""
Doi chieu dinh ky cho Trusted Video Sources (Phase 6, du phong khi WebSub bo
lo do gian doan webhook/dang ky het han/callback tam thoi khong truy cap
duoc) — xem `TrustedSourceService.run_reconciliation`.

DUNG TAN SUAT THAP (moi vai gio den mot ngay, KHONG phai polling lien tuc) —
goi tu mot bo lap lich BEN NGOAI (Task Scheduler tren Windows dev, systemd
timer tren VM production, cung kien truc voi worker TTS/dich thuat da co,
xem `docs/handoffs/admin-trusted-video-v2-handoff.md`) — script nay KHONG tu
lap lich, chi chay MOT LAN roi thoat.

An toan khi chay lai: pipeline dung LAI `scan_source` (idempotent qua
`create_import_once`), khong tao tap trung ke ca chay lien tiep nhieu lan.

Chay:
    .venv\\Scripts\\python.exe -m scripts.run_websub_reconciliation
    .venv\\Scripts\\python.exe -m scripts.run_websub_reconciliation --source tsrc_xxx
    FAS_ENV_FILE=server/.env.selfhost .venv\\Scripts\\python.exe -m scripts.run_websub_reconciliation
"""

from __future__ import annotations

import sys
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _lay_tham_so(argv: List[str], ten: str) -> Optional[str]:
    for i, tham_so in enumerate(argv):
        if tham_so == ten and i + 1 < len(argv):
            return argv[i + 1]
        if tham_so.startswith(f"{ten}="):
            return tham_so.split("=", 1)[1]
    return None


def main(argv: List[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    from server.adapters import build_metadata_store
    from server.appwrite_animation_store import build_animation_store
    from server.appwrite_trusted_source_store import build_trusted_source_store
    from server.config import load_settings
    from server.trusted_source_service import TrustedSourceService

    source_id = _lay_tham_so(argv, "--source") or ""

    settings = load_settings()
    animation_store = build_animation_store(settings)
    trusted_store = build_trusted_source_store(settings)
    metadata_store = build_metadata_store(settings)
    svc = TrustedSourceService(
        trusted_store, animation_store, metadata_store,
        youtube_api_key=settings.youtube_api_key,
        websub_callback_base_url=settings.youtube_websub_callback_base_url)

    print(f"Backend dữ liệu : {settings.data_backend}")
    print(f"Nguồn           : {source_id or '(tất cả nguồn bật + auto_discover)'}")
    print()

    ket_qua = svc.run_reconciliation(source_id=source_id, actor_id="", actor_role="")

    print(f"Nguồn đã kiểm : {ket_qua['sources_checked']}")
    print(f"Nguồn lỗi     : {ket_qua['sources_failed']}")
    print(f"Video phát hiện: {ket_qua['videos_detected']}")
    return 1 if ket_qua["sources_failed"] and ket_qua["sources_failed"] == ket_qua["sources_checked"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
