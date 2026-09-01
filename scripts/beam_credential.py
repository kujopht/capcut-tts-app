"""
Mot diem doc DUY NHAT cho BEAM_TOKEN — mission "REMOVE THE HUMAN FROM BEAM
OPERATIONS" (2026-09-01), muc A.

Truoc mission nay, moi script `beam_*.py` tu doc
`os.environ.get("BEAM_TOKEN")` rieng le — nghia la operator phai
`$env:BEAM_TOKEN = "..."` LAI moi phien shell moi, khong co gi ben duoi de
tu dong hoa tiep. `resolve_beam_token()` giu NGUYEN duong doc env var (van
uu tien, cho phep ghi de tam thoi trong MOT phien) nhung THEM mot lop du
phong: `scripts/fanfic_credential_broker.py` (Windows Credential Manager
qua `advapi32` CredRead/CredWrite, KHONG file plaintext, KHONG bien moi
truong shell profile) — cai co san DUY NHAT trong kho nay dung dung nguyen
tac "operator go MOT lan qua stdin, khong bao gio qua argv/log" ma mission
yeu cau, nen MO RONG no (them "BEAM_TOKEN" vao KNOWN_NAMES) thay vi dung
mot he thong bi mat thu hai.

Thiet lap MOT LAN (nguoi dung tu chay, gia tri khong bao gio di qua context
cua Claude — day la ranh gioi an toan quan trong nhat: script nay CHI DOC
lai, khong bao gio la noi NHAP gia tri):

    python scripts/fanfic_credential_broker.py store --name BEAM_TOKEN

Sau do MOI script beam_*.py trong kho nay goi `resolve_beam_token()` thay
vi `os.environ.get("BEAM_TOKEN")` truc tiep — tu dong lay tu Credential
Manager neu bien moi truong vang mat, khong can operator lam gi them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

TOKEN_ENV_VAR = "BEAM_TOKEN"
_CREDENTIAL_NAME = "BEAM_TOKEN"


def resolve_beam_token() -> Optional[str]:
    """BEAM_TOKEN cua phien nay: uu tien bien moi truong hien co (cho phep
    ghi de tam thoi, hanh vi CU khong doi), roi moi thu Windows Credential
    Manager qua broker. Tra `None` neu ca hai deu vang mat — KHONG BAO GIO
    in/log gia tri, dung nguyen tac cua broker."""
    tu_env = os.environ.get(TOKEN_ENV_VAR)
    if tu_env:
        return tu_env
    if sys.platform != "win32":
        return None
    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import fanfic_credential_broker as _broker
    except ImportError:
        return None
    try:
        return _broker.fetch(_CREDENTIAL_NAME)
    except _broker.BrokerEnvironmentError:
        return None


if __name__ == "__main__":
    # Read-only self-check — bao cao SU HIEN DIEN, khong bao gio gia tri.
    token = resolve_beam_token()
    print(f"{TOKEN_ENV_VAR}: {'resolved (value withheld)' if token else 'ABSENT'}")
    sys.exit(0 if token else 1)
