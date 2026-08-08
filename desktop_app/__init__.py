"""
Fanfic Audio Studio - ung dung desktop Windows tao audio tu van ban.

Package nay chua toan bo phan desktop (PySide6). Package `capcut_tts_api` goc
khong bi sua doi: chi duoc dung de dung (build) request da ky.

Cac module:
    models.py           - dataclass/enum dung chung (Job, JobPart, VoiceEntry, ...)
    voice_catalog.py     - doc Voice.json, tim kiem/loc/sap xep/yeu thich
    text_importer.py     - nhap van ban tu .txt/.md/.docx + thu muc
    text_chunker.py      - chia van ban dai theo doan/cau
    tts_service.py       - goi API CapCut (timeout/poll/download/phan loai loi)
    output_manager.py    - thu muc ket qua, manifest.json, report.json, ghep MP3, ZIP
    settings_manager.py  - QSettings + thu muc du lieu nguoi dung
    queue_manager.py     - hang doi job, start/pause/resume/stop/retry
    workers.py           - QThread worker chay job (khong chan giao dien)
    result_library.py    - doc lai ket qua cac lan chay truoc
    main_window.py       - cua so chinh + 4 trang + theme toi
"""

APP_NAME = "Fanfic Audio Studio"
APP_ORG = "FanficAudioStudio"
APP_VERSION = "2.0.0"

__all__ = ["APP_NAME", "APP_ORG", "APP_VERSION"]
