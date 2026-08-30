"""Nơi cất token cầu nối cục bộ — Router V3.2, Phase 5.

Token cầu nối KHÔNG phải credential nhà cung cấp (xem `bridge.py`), nhưng vẫn
là một bí mật ứng dụng: ai cầm nó gửi được việc tới cầu nối. Vẫn cất riêng
từng người dùng, không commit, không đi qua đối số dòng lệnh (lộ trong danh
sách tiến trình), không bao giờ in ra màn hình sau khi đã ghép.

    %LOCALAPPDATA%\\FanficAudioStudio\\router\\bridge\\<worker_id>.json

Nằm NGOÀI kho — không dựa vào .gitignore để tránh lộ.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

TEN_THU_MUC = ("FanficAudioStudio", "router", "bridge")


def _goc() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    p = Path(base)
    for phan in TEN_THU_MUC:
        p = p / phan
    return p


def duong_luu(worker_id: str) -> Path:
    return _goc() / f"{worker_id}.json"


def _siet_quyen_tep(p: Path) -> None:
    """Chỉ chủ sở hữu đọc được — phòng hờ dù %LOCALAPPDATA% vốn đã riêng tư."""
    if os.name != "nt":
        return
    try:
        moi = dict(os.environ)
        moi["MSYS_NO_PATHCONV"] = "1"
        subprocess.run(["icacls", str(p), "/inheritance:r", "/grant:r",
                        f"{os.environ.get('USERNAME', '')}:(F)",
                        "/grant:r", "SYSTEM:(F)"],
                       capture_output=True, text=True, env=moi)
    except Exception:
        pass  # khong lam hong viec ghep chi vi buoc siet quyen phu them


def luu(worker_id: str, *, host: str, port: int, token: str) -> Path:
    p = duong_luu(worker_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"host": host, "port": port, "token": token}),
                encoding="utf-8")
    _siet_quyen_tep(p)
    return p


def doc(worker_id: str) -> Optional[dict]:
    p = duong_luu(worker_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
