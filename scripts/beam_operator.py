#!/usr/bin/env python3
"""
Provider-neutral Beam Cloud operator — mission "REMOVE THE HUMAN FROM BEAM
OPERATIONS" (2026-09-01), muc B/C/D.

Muc tieu: operator (nguoi/Claude) khong con phai tu tay mo Cloud Shell, chay
`beam deploy`, copy URL, hay doc dashboard — moi buoc do qua MOT script nay,
output la JSON co cau truc, khong bao gio can doc log bang mat.

    .venv\\Scripts\\python.exe scripts\\beam_operator.py check-version
    .venv\\Scripts\\python.exe scripts\\beam_operator.py deploy --kind endpoint --handler beam_apps/cover_illustrious_app.py:generate
    .venv\\Scripts\\python.exe scripts\\beam_operator.py deploy --kind vllm --handler beam_apps/translation_hymt2_app.py:hymt2_1_8b
    .venv\\Scripts\\python.exe scripts\\beam_operator.py list
    .venv\\Scripts\\python.exe scripts\\beam_operator.py wait-ready --url <invoke_url> --kind vllm

BAT BUOC THAT (khong doan) duoc ma hoa truc tiep vao script nay, tung dieu
deu doc tu ma nguon `beta9` 0.1.265 (beam-client 0.2.207) dang cai trong
`.venv`, khong phai tai lieu hay gia dinh:

1. `CI=1` trong moi subprocess `beam` — bo qua banner first-auth tuong tac
   cua `beta9/cli/main.py::check_config` (crash THAT tren Windows: no
   dung `UnicodeEncodeError` khi in emoji duoi code page cp1252 mac dinh
   cua console, tai hien duoc truc tiep, khong phai doan). Day la CHI MOT
   noi dung `os.getenv("CI")` trong toan bo ma nguon beta9 (grep xac
   nhan), nen khong co tac dung phu nao khac.

2. LOI VLLM-DEPLOY THAT, con dang ton tai trong beta9 0.1.265 (KHONG PHAI
   mot phien ban cu da lac hau — day la ban MOI NHAT tinh den 2026-09-01):
   `beta9/abstractions/integrations/vllm.py::VLLM.deploy()` nhan
   `**invocation_details_options` (khong co tham so `rollout` rieng, khac
   voi `beta9/abstractions/mixins.py`'s generic `deploy()` — noi CO tham
   so `rollout: str = "auto"` RIENG nen KHONG bi cuon vao
   `**invocation_details_options`). CLI's `deployment.py::create_deployment`
   LUON goi `user_obj.deploy(..., rollout=rollout, url_type=url_type)` —
   voi VLLM, `rollout` roi vao `**invocation_details_options`, duoc
   forward nguyen vao `self.print_invocation_snippet(**invocation_details_options)`
   — nhung `print_invocation_snippet(self, url_type: str = "")` KHONG co
   tham so `rollout`, KHONG co `**kwargs` — nem THANG
   `TypeError: print_invocation_snippet() got an unexpected keyword
   argument 'rollout'`. Crash nay xay ra SAU KHI `deploy_stub` RPC da
   thanh cong that (`deploy_response.ok` da True, `self.deployment_id`
   da duoc gan) — dung nhu mission yeu cau: "Deployment success must NOT
   be interpreted as deployment failure merely because invocation-snippet
   rendering crashes." VA vi crash nam BEN TRONG `.deploy()` (truoc khi no
   kip return), `beam deploy ... --format json` qua CLI/subprocess KHONG
   BAO GIO kip in JSON cho duong VLLM — bat buoc phai goi `.deploy()`
   qua SDK Python TRUC TIEP (khong qua subprocess CLI) voi tham so
   `invocation_details_func` (mot hook CO SAN, CHINH THUC cua chinh
   `.deploy()`, khong phai vien mot ham noi bo) tro toi mot ham RONG —
   nho vay `print_invocation_snippet` KHONG BAO GIO duoc tu dong goi voi
   `rollout` nua.
   KHONG PATCH site-packages — day la cach dung API cong khai da co san
   cua chinh SDK de tranh mot loi that trong MOT phuong thuc cu the, dung
   nguyen tac CLAUDE.md "Do NOT patch random site-packages as the
   permanent solution."

   SU CO THAT (2026-09-01, DA SUA): ban dau script nay tu goi
   `obj.print_invocation_snippet(url_type="")` de lay `invoke_url` - tuong
   la "an toan" vi khong con `rollout`. NHUNG chinh ham nay IN THANG mot
   curl snippet ra stdout, TRONG DO CO `Authorization: Bearer
   {self.config_context.token}` — CHINH BEAM_TOKEN that cua tai khoan (xem
   `beta9/abstractions/base/runner.py::print_invocation_snippet`). Lan
   chay THAT dau tien cua script nay da lam LO token that vao log
   background-task va vao transcript hoi thoai — operator da duoc bao va
   da xoay token ngay sau do. Sua tan goc: KHONG BAO GIO goi
   `print_invocation_snippet` (hay bat ky ham nao co tien to "print_"/
   "terminal." trong beta9) tu mot script tu dong — thay vao do goi THANG
   RPC `gateway_stub.get_url(GetUrlRequest(...))` (chinh la RPC ma
   `print_invocation_snippet` dung NOI BO) de lay `GetUrlResponse.url` ma
   KHONG co tac dung phu in-ra-man-hinh nao ca. Day la ly do MOI ham SDK
   "tien loi" (in san curl/anh huong dep) can duoc doc ky truoc khi goi tu
   dong — chung duoc thiet ke cho NGUOI dung CLI xem bang mat, khong phai
   cho script khac tieu thu ket qua.
3. Duong `@endpoint` thuong (vd cover_illustrious_app.py) KHONG bi loi
   nay — `mixins.py`'s generic `deploy()` xu ly `rollout` dung cach — nen
   van dung `beam deploy <handler> --format json` qua subprocess binh
   thuong, khong can di vong.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.beam_credential import TOKEN_ENV_VAR, resolve_beam_token  # noqa: E402

#: Phien ban `beam-client` da THU that va ghi lai trong mission nay
#: (2026-09-01) — cai moi (`pip install beam-client==...`) qua dry-run
#: khong xung dot voi cac goi da co trong .venv nay. KHONG tu dong nang
#: cap: neu phien ban cai dat khac di, `check-version` CANH BAO thay vi
#: am tham chay tiep — dung yeu cau mission "add a setup check that
#: detects this mismatch before real work".
BEAM_CLIENT_TESTED_VERSION = "0.2.207"

#: Cac loi HTTP/exception coi la TAM THOI khi cho endpoint san sang — mot
#: serverless GPU dang khoi dong lanh se tra ve nhung dang nay TRUOC KHI
#: san sang, khong phai dau hieu that bai.
_READY_CHECK_TRANSIENT_STATUS = (404, 500, 502, 503, 504)


#: Khop `Authorization: Bearer <token>` (co the nam trong mot dong curl,
#: JSON string, hay bat ky dang nao) - PHONG THU CHIEU SAU sau su co that
#: (2026-09-01, xem module docstring muc 2): `beam deploy ... --format
#: json` co the nhet CHINH curl snippet CHUA BEAM_TOKEN vao truong "logs"
#: cua JSON tra ve (StoredStdoutInterceptor bat lai moi thu da in ra,
#: bao gom ca invocation-snippet curl neu duong deploy nao do van con goi
#: no). Ap dung REDACT nay cho MOI chuoi raw (stdout/stderr) truoc khi dat
#: vao dict tra ve - khong bao giờ tin day la "chac chan sach" chi vi
#: duong code hien tai khong co ve nhu se in bearer token.
_BEARER_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-+/=]{16,}", re.IGNORECASE)


def _redact_secrets(text: str) -> str:
    return _BEARER_PATTERN.sub(r"\1<redacted>", text or "")


def _err(msg: str) -> Dict[str, Any]:
    return {"status": "ERROR", "error": msg}


#: Mission "REMOVE THE HUMAN FROM BEAM OPERATIONS", packaging follow-up
#: (2026-09-01): nguong "goi tin bat thuong" TRUOC KHI tinh model weights
#: (weights nam trong Beam Volume/HF cache, khong bao gio nam trong repo
#: local). Vuot nguong nay nghia la mot thu moi/lon vo tinh lot qua
#: `.beamignore` - coi la mot REGRESSION dong goi, khong phai chuyen binh
#: thuong.
PAYLOAD_SIZE_REGRESSION_THRESHOLD_BYTES = 500 * 1024 * 1024


def cmd_check_payload_size(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Tinh THAT dung luong `beam deploy` se dong goi, CUC BO, KHONG GPU,
    KHONG deploy - mo phong CHINH XAC logic that cua
    `beta9.sync.FileSyncer._collect_files`/`_should_ignore` (doc `.beamignore`
    qua cung thu vien `pathspec` da vendor san trong beta9, cat tia thu muc
    NGAY trong os.walk giong beta9, khong phai doan lai tu tai lieu)."""
    root = repo_root or Path(__file__).resolve().parent.parent
    ignore_path = root / ".beamignore"
    if not ignore_path.is_file():
        return _err(f".beamignore not found at {ignore_path}")

    try:
        from beta9.vendor.pathspec import PathSpec
    except ImportError:
        return _err("beta9 not installed - cannot replicate its ignore "
                    "logic (run: pip install beam-client)")

    with ignore_path.open(encoding="utf-8") as f:
        patterns = [line.strip() for line in f.readlines() if line.strip()
                   and not line.strip().startswith("#")]
    spec = PathSpec.from_lines("gitwildmatch", patterns)

    total_bytes = 0
    file_count = 0
    largest: list = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = [
            d for d in dirnames
            if not spec.match_file(os.path.join(rel_dir, d) if rel_dir != "." else d)
        ]
        for name in filenames:
            rel_file = os.path.join(rel_dir, name) if rel_dir != "." else name
            if spec.match_file(rel_file):
                continue
            full_path = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue
            total_bytes += size
            file_count += 1
            largest.append((size, rel_file))

    largest.sort(reverse=True)
    is_regression = total_bytes > PAYLOAD_SIZE_REGRESSION_THRESHOLD_BYTES
    return {
        "status": "REGRESSION" if is_regression else "OK",
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 1),
        "file_count": file_count,
        "threshold_mb": round(
            PAYLOAD_SIZE_REGRESSION_THRESHOLD_BYTES / (1024 * 1024), 1),
        "largest_files": [
            {"path": p, "mb": round(s / (1024 * 1024), 2)}
            for s, p in largest[:10]
        ],
    }


def _beam_executable() -> Optional[str]:
    """Resolve the `beam` CLI binary. REAL bug found running this script:
    `beam-client` installs `beam.exe` into `.venv\\Scripts\\` alongside
    `python.exe`, but invoking Python via its full path does NOT put its
    own directory on PATH for child subprocess.run(["beam", ...]) calls -
    a bare "beam" resolved via shutil.which() came back None even though
    the file exists right next to the interpreter running this script.
    Falls back to the interpreter's own directory before giving up."""
    found = shutil.which("beam")
    if found:
        return found
    candidate = Path(sys.executable).parent / (
        "beam.exe" if os.name == "nt" else "beam")
    if candidate.is_file():
        return str(candidate)
    return None


def _beam_subprocess_env(token: str) -> dict:
    """Env cho MOT subprocess `beam` - CI=1 (bo qua banner crash) + token,
    khong bao gio sua `os.environ` cua chinh tien trinh nay."""
    env = dict(os.environ)
    env["CI"] = "1"
    env[TOKEN_ENV_VAR] = token
    return env


def _ensure_config_context(token: str) -> None:
    """REAL bug found (2026-09-01): `beam logs` (khac voi `deploy`/
    `deployment list`/`container list`) doc context TU FILE
    `~/.beam/config.ini` (`beta9/cli/logs.py::logs` goi
    `load_config(...)[DEFAULT_CONTEXT_NAME]` truc tiep), KHONG qua
    `SDKSettings`'s duong doc BEAM_TOKEN tu env var nhu cac lenh khac -
    thieu file nay nem `KeyError: 'default'` du BEAM_TOKEN da co san trong
    env. Ghi file MOT LAN, idempotent, dung CHINH XAC schema that cua
    `beta9.config.ConfigContext`/`save_config` (doc truc tiep tu ma nguon,
    khong doan) - KHONG BAO GIO in/log gia tri `token`.

    BUG THU HAI, LIEN QUAN (tim thay khi kiem tra fix dau tien): `beta9.
    config.SDKSettings.__post_init__` CHI chuyen sang duong dan
    `~/.beam/config.ini` (thay vi `~/.beta9/config.ini` mac dinh) NEU
    `"beam" in sys.modules` DA True TAI THOI DIEM `SDKSettings()` duoc
    khoi tao (xem dieu kien trong config.py). Tien trinh CUA CHINH SCRIPT
    NAY (khac voi tien trinh con `beam` subprocess, tu dong import `beam`
    lam entry point) chua tung import `beam` neu chua goi qua
    `cmd_deploy_vllm` truoc do trong CUNG tien trinh - `import beam` tuong
    minh o day de dam bao ghi DUNG file ma subprocess `beam logs` se doc,
    thay vi vo tinh ghi vao `~/.beta9/config.ini` (sai vi tri, van khong
    sua duoc loi)."""
    os.environ.setdefault("CI", "1")
    import beam  # noqa: F401 - side effect: lam "beam" in sys.modules True
    from beta9.config import (
        ConfigContext, DEFAULT_CONTEXT_NAME, get_settings, load_config, save_config,
    )

    settings = get_settings()
    existing = load_config(settings.config_path) if settings.config_path.exists() else {}
    ctx = existing.get(DEFAULT_CONTEXT_NAME)
    if ctx and ctx.is_valid():
        return
    # Merge, khong ghi de: save_config ghi LAI TOAN BO file tu dict truyen
    # vao - bo qua cac context khac da co se lam MAT chung.
    existing[DEFAULT_CONTEXT_NAME] = ConfigContext(
        token=token, gateway_host="gateway.beam.cloud", gateway_port=443)
    save_config(existing, settings.config_path)


def cmd_check_version() -> Dict[str, Any]:
    """Kiem tra phien ban `beam-client` cai dat khop voi phien ban DA THU
    trong mission nay — KHONG deploy/goi mang gi ca."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "beam-client"],
            capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return _err(f"could not run pip show: {exc}")
    installed_version = ""
    for line in result.stdout.splitlines():
        if line.lower().startswith("version:"):
            installed_version = line.split(":", 1)[1].strip()
            break
    if not installed_version:
        return {
            "status": "NOT_INSTALLED",
            "tested_version": BEAM_CLIENT_TESTED_VERSION,
            "install_command": (
                f"{sys.executable} -m pip install beam-client=="
                f"{BEAM_CLIENT_TESTED_VERSION}"),
        }
    matches = installed_version == BEAM_CLIENT_TESTED_VERSION
    return {
        "status": "OK" if matches else "VERSION_MISMATCH",
        "installed_version": installed_version,
        "tested_version": BEAM_CLIENT_TESTED_VERSION,
        "note": (
            "" if matches else
            "Cai dat KHAC voi phien ban da thu that trong mission nay - "
            "khong tu dong chan, nhung mot CLI crash khac voi bang chung "
            "da ghi lai (vd 'rollout' TypeError o module docstring) co "
            "the la dau hieu mismatch phien ban, khong phai bug moi."),
    }


def cmd_deploy_endpoint(handler: str, token: str,
                        timeout_seconds: int = 300) -> Dict[str, Any]:
    """`@endpoint`-style app (vd cover_illustrious_app.py) - KHONG bi loi
    VLLM/rollout (xem module docstring muc 3) - subprocess CLI binh
    thuong voi `--format json` la du."""
    beam_bin = _beam_executable()
    if not beam_bin:
        return _err("'beam' binary not found on PATH or next to the interpreter")
    try:
        result = subprocess.run(
            [beam_bin, "deploy", handler, "--format", "json"],
            capture_output=True, text=True, timeout=timeout_seconds,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    except subprocess.TimeoutExpired:
        return _err(f"beam deploy timed out after {timeout_seconds}s")
    if result.returncode != 0:
        return {
            "status": "DEPLOY_FAILED",
            "returncode": result.returncode,
            "stderr": _redact_secrets(result.stderr[-2000:]),
        }
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return _err(
            "beam deploy exited 0 but stdout was not valid JSON: "
            f"{_redact_secrets(result.stdout[-500:])}")
    # CHI whitelist cac truong an toan - `payload` co the co mot truong
    # "logs" chua invocation-snippet curl (voi Authorization: Bearer
    # {BEAM_TOKEN}) neu duong deploy nao do van goi print_invocation_snippet
    # noi bo (xem module docstring muc 2's "SU CO THAT") - KHONG BAO GIO
    # forward `payload` nguyen ven hay truong "logs" cua no.
    return {
        "status": "DEPLOYED",
        "deployment_id": payload.get("deployment_id", ""),
        "deployment_name": payload.get("deployment_name", ""),
        "invoke_url": payload.get("invoke_url", ""),
        "version": payload.get("version"),
        "warning": payload.get("warning", ""),
    }


def cmd_deploy_vllm(handler: str, token: str) -> Dict[str, Any]:
    """`beam.integrations.VLLM` app (vd translation_hymt2_app.py) - PHAI
    di qua SDK Python truc tiep, KHONG qua subprocess CLI - xem module
    docstring muc 2 cho ly do that (crash nam TRONG `.deploy()` truoc khi
    no kip tra JSON qua CLI)."""
    if ":" not in handler:
        return _err("handler must be 'path/to/file.py:object_name'")
    file_path, object_name = handler.rsplit(":", 1)
    module_path = Path(file_path).resolve()
    if not module_path.is_file():
        return _err(f"file not found: {module_path}")

    os.environ["BEAM_TOKEN"] = token
    os.environ["CI"] = "1"

    import importlib.util
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        return _err(f"failed to import {module_path}: {_redact_secrets(str(exc))}")

    vllm_obj = getattr(module, object_name, None)
    if vllm_obj is None:
        return _err(f"{object_name!r} not found in {module_path}")

    captured: Dict[str, Any] = {}

    def _no_op_invocation_details(**_kwargs) -> None:
        # Hook CHINH THUC cua VLLM.deploy() (xem module docstring muc 2) -
        # ngan KHONG cho no tu goi print_invocation_snippet(**rollout=...)
        # gay crash. Khong lam gi ca o day - URL that se duoc lay RIENG,
        # AN TOAN, ngay ben duoi.
        captured["invocation_details_called"] = True

    try:
        response, ok = vllm_obj.deploy(
            name=getattr(vllm_obj, "name", None),
            invocation_details_func=_no_op_invocation_details)
    except Exception as exc:
        return _err(f"vllm deploy() raised: {_redact_secrets(str(exc))}")

    if not ok:
        return {"status": "DEPLOY_FAILED", "response": response}

    invoke_url = ""
    try:
        # KHONG goi vllm_obj.print_invocation_snippet() - no IN THANG mot
        # curl snippet ra stdout CHUA `Authorization: Bearer
        # {self.config_context.token}` (chinh BEAM_TOKEN cua tai khoan,
        # xem beta9/abstractions/base/runner.py) - da tu tay xac nhan dieu
        # nay lam LO THAT mot token that vao log/transcript trong qua trinh
        # xay dung script nay (token da duoc operator xoay lai ngay sau
        # do). Goi THANG RPC `get_url` ben duoi ma `print_invocation_snippet`
        # dung noi bo - CUNG mot du lieu, KHONG co tac dung phu in-ra-stdout
        # nao ca.
        from beta9.clients.gateway import GetUrlRequest
        url_response = vllm_obj.gateway_stub.get_url(GetUrlRequest(
            stub_id=vllm_obj.stub_id,
            deployment_id=getattr(vllm_obj, "deployment_id", ""),
            url_type=""))
        if getattr(url_response, "ok", False):
            invoke_url = url_response.url
    except Exception as exc:
        # Khong coi la that bai deploy - deploy_stub DA thanh cong
        # (`ok` True o tren) - chi la khong lay duoc URL o buoc phu nay.
        return {
            "status": "DEPLOYED_URL_UNKNOWN",
            "deployment_id": response.get("deployment_id", ""),
            "url_lookup_error": _redact_secrets(str(exc)),
        }
    return {
        "status": "DEPLOYED",
        "deployment_id": response.get("deployment_id", ""),
        "invoke_url": invoke_url,
    }


def cmd_list(token: str) -> Dict[str, Any]:
    beam_bin = _beam_executable()
    if not beam_bin:
        return _err("'beam' binary not found on PATH or next to the interpreter")
    try:
        result = subprocess.run(
            [beam_bin, "deployment", "list", "--format", "json"],
            capture_output=True, text=True, timeout=60,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    if result.returncode != 0:
        return {"status": "ERROR", "returncode": result.returncode,
                "stderr": _redact_secrets(result.stderr[-2000:])}
    try:
        raw_deployments = json.loads(result.stdout)
    except ValueError:
        return _err(f"deployment list did not return valid JSON: "
                    f"{_redact_secrets(result.stdout[-500:])}")
    # Whitelist - Beam's `Deployment` message also carries
    # `connection_string_secret`/`connection_env_name` for database-kind
    # deployments (confirmed by reading beta9/clients/gateway's generated
    # message class) - forwarding the raw list unfiltered would leak those
    # for ANY database deployment on the account, not just the VLLM/
    # endpoint apps this repo cares about.
    safe_fields = ("id", "name", "active", "stub_type", "stub_name",
                  "version", "workspace_name", "created_at", "updated_at")
    deployments = [{k: d.get(k) for k in safe_fields}
                  for d in raw_deployments if isinstance(d, dict)]
    return {"status": "OK", "deployments": deployments}


def cmd_volumes(token: str) -> Dict[str, Any]:
    """`beam volume list` — mission 'COST SAFETY OVERRIDE' quy tac 6 (sua
    loi xac dinh TRUOC KHI thu GPU them): kiem tra Volume `vllm_cache`
    (mac dinh cua `VLLM`, xem translation_hymt2_app.py's own docstring)
    CO du lieu hay khong TRUOC KHI gia dinh mot lan cold-start moi se lai
    tai tu dau/co the ke thua cache HONG tu lan truoc."""
    beam_bin = _beam_executable()
    if not beam_bin:
        return _err("'beam' binary not found on PATH or next to the interpreter")
    try:
        result = subprocess.run(
            [beam_bin, "volume", "list"],
            capture_output=True, text=True, timeout=60,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    if result.returncode != 0:
        return {"status": "ERROR", "returncode": result.returncode,
                "stderr": _redact_secrets(result.stderr[-2000:])}
    # `beam volume list` has no --format json (confirmed - only table
    # output) - redact defensively and return as text rather than
    # pretending a structure this CLI doesn't provide.
    return {"status": "OK", "volumes_table": _redact_secrets(result.stdout)}


def cmd_ls_volume(token: str, remote_path: str) -> Dict[str, Any]:
    """`beam ls <volume>/<path>` — duyet noi dung Volume, KHONG tinh phi
    GPU (thao tac luu tru, khac han container/compute) - dung de kiem tra
    model weights CO THAT SU nam trong `vllm_cache` hay khong TRUOC KHI
    quyet dinh chi them mot lan cold-start GPU (mission 'COST SAFETY
    OVERRIDE' quy tac 6/7)."""
    beam_bin = _beam_executable()
    if not beam_bin:
        return _err("'beam' binary not found on PATH or next to the interpreter")
    try:
        result = subprocess.run(
            [beam_bin, "ls", remote_path],
            capture_output=True, text=True, timeout=60,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    if result.returncode != 0:
        return {"status": "ERROR", "returncode": result.returncode,
                "stderr": _redact_secrets(result.stderr[-2000:])}
    return {"status": "OK", "listing": _redact_secrets(result.stdout)}


def cmd_containers(token: str, deployment_id: str = "") -> Dict[str, Any]:
    """`beam container list` — mission 'COST SAFETY OVERRIDE' (2026-09-01):
    `status`/`uptime` la du lieu THAT de biet mot container co dang CHAY
    (dang tinh phi GPU) hay khong, TRUOC KHI quyet dinh cho tiep/dung lai -
    khong con phai doan "co le van dang cold-start" tu MOT ky hieu HTTP
    don le nhu 500/timeout."""
    beam_bin = _beam_executable()
    if not beam_bin:
        return _err("'beam' binary not found on PATH or next to the interpreter")
    try:
        result = subprocess.run(
            [beam_bin, "container", "list", "--format", "json"],
            capture_output=True, text=True, timeout=60,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    if result.returncode != 0:
        return {"status": "ERROR", "returncode": result.returncode,
                "stderr": _redact_secrets(result.stderr[-2000:])}
    try:
        raw = json.loads(result.stdout)
    except ValueError:
        return _err(f"container list did not return valid JSON: "
                    f"{_redact_secrets(result.stdout[-500:])}")
    safe_fields = ("container_id", "status", "stub_id", "deployment_id",
                  "scheduled_at", "uptime")
    containers = [{k: c.get(k) for k in safe_fields}
                 for c in raw if isinstance(c, dict)
                 and (not deployment_id or c.get("deployment_id") == deployment_id)]
    return {"status": "OK", "containers": containers}


def cmd_stop_container(token: str, container_id: str) -> Dict[str, Any]:
    """`beam container stop` — dung MOT container dang chay TRUC TIEP, HANH
    DONG NHANH NHAT de cat chi phi GPU khi mot lan cold-start/loi that KHONG
    con dang duoc "chung minh" bang du lieu that (mission 'COST SAFETY
    OVERRIDE' quy tac 4: "Stop any cold-start attempt that exceeds its
    justified time/cost budget")."""
    beam_bin = _beam_executable()
    if not beam_bin:
        return _err("'beam' binary not found on PATH or next to the interpreter")
    try:
        result = subprocess.run(
            [beam_bin, "container", "stop", container_id],
            capture_output=True, text=True, timeout=60,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    if result.returncode != 0:
        return {"status": "ERROR", "returncode": result.returncode,
                "stderr": _redact_secrets(result.stderr[-2000:])}
    return {"status": "OK", "container_id": container_id}


def cmd_logs(token: str, *, deployment_id: str = "", container_id: str = "",
            lines: int = 250) -> Dict[str, Any]:
    """`beam logs` — nguon THAT DUY NHAT de biet TAI SAO mot container tra
    loi 500/timeout thay vi doan mo mam qua ma HTTP don le, roi thu lai mu
    quang (dung mission 'COST SAFETY OVERRIDE' quy tac 5: "Never blindly
    retry a failed GPU operation")."""
    beam_bin = _beam_executable()
    if not beam_bin:
        return _err("'beam' binary not found on PATH or next to the interpreter")
    try:
        _ensure_config_context(token)
    except Exception as exc:
        return _err(f"could not prepare ~/.beam/config.ini for 'beam logs': "
                    f"{_redact_secrets(str(exc))}")
    argv = [beam_bin, "logs", "-n", str(lines)]
    if deployment_id:
        argv += ["--deployment-id", deployment_id]
    if container_id:
        argv += ["--container-id", container_id]
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=60,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    if result.returncode != 0:
        return {"status": "ERROR", "returncode": result.returncode,
                "stderr": _redact_secrets(result.stderr[-2000:])}
    return {"status": "OK", "logs": _redact_secrets(result.stdout)}


def cmd_wait_ready(url: str, token: str, *, kind: str,
                   max_wait_seconds: int = 600,
                   initial_delay_seconds: float = 5.0,
                   max_delay_seconds: float = 60.0,
                   request_timeout_seconds: float = 120.0) -> Dict[str, Any]:
    """Cho endpoint SAN SANG THAT — cho VLLM, kiem tra `/v1/models`
    (nhe, KHONG sinh token nao, dung y mission "Do not consume
    model-generation tokens merely to check readiness"). Backoff mu
    (exponential) co gioi han, KHONG poll vo han.

    REAL FINDING (2026-09-01, lan chay dau tien): voi
    `request_timeout_seconds` mac dinh cu (10s), 16/16 lan thu deu bao
    "The read operation timed out" trong suot 900s - Beam serverless
    container LAN DAU tien co the giu KET NOI TCP mo trong khi container
    that su khoi dong (tai model weights + init vLLM engine), nghia la MOT
    request rieng le co the that su can HON 10s de nhan phan hoi, khong
    phai la loi mang thoang qua giua cac lan thu. Nang timeout MOI request
    len 120s (van BI GIOI HAN boi `max_wait_seconds` tong the) de mot lan
    goi co co hoi that su cho het cold-start, thay vi bi cat giua chung
    lien tuc va khong bao gio biet duoc endpoint co thuc su san sang hay
    khong."""
    import httpx

    if kind != "vllm":
        return _err(f"wait-ready only implements the 'vllm' /v1/models "
                    f"check today (got kind={kind!r})")

    check_url = url.rstrip("/") + "/v1/models"
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.monotonic() + max_wait_seconds
    delay = initial_delay_seconds
    attempt = 0
    last_error = ""
    started = time.monotonic()
    with httpx.Client(timeout=request_timeout_seconds) as client:
        while time.monotonic() < deadline:
            attempt += 1
            try:
                resp = client.get(check_url, headers=headers)
                if resp.status_code == 200:
                    return {
                        "status": "READY",
                        "attempts": attempt,
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                    }
                if resp.status_code not in _READY_CHECK_TRANSIENT_STATUS:
                    # Ma trang thai KHONG nam trong danh sach tam thoi da
                    # biet (vd 401/403) - that bai that, dung cho tiep.
                    return {
                        "status": "FAILED",
                        "attempts": attempt,
                        "http_status": resp.status_code,
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                    }
                last_error = f"HTTP {resp.status_code}"
            except httpx.HTTPError as exc:
                last_error = _redact_secrets(str(exc))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, max_delay_seconds)
    return {
        "status": "TIMEOUT",
        "attempts": attempt,
        "last_error": last_error,
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-version", help="verify installed beam-client version")
    sub.add_parser("check-payload-size",
                   help="compute the real .beamignore-filtered deploy "
                        "payload size locally, no deploy/GPU needed")

    p_deploy = sub.add_parser("deploy", help="deploy an app/function")
    p_deploy.add_argument("--handler", required=True,
                          help="path/to/file.py:object_name")
    p_deploy.add_argument("--kind", required=True, choices=["endpoint", "vllm"])
    p_deploy.add_argument("--timeout-seconds", type=int, default=300)

    sub.add_parser("list", help="list deployments")

    sub.add_parser("volumes", help="list volumes (e.g. vllm_cache)")

    p_ls = sub.add_parser("ls-volume", help="list a volume's contents (no GPU cost)")
    p_ls.add_argument("--path", required=True, help="e.g. vllm_cache")

    p_containers = sub.add_parser("containers", help="list current containers")
    p_containers.add_argument("--deployment-id", default="")

    p_stop = sub.add_parser("stop-container", help="stop a running container")
    p_stop.add_argument("--container-id", required=True)

    p_logs = sub.add_parser("logs", help="fetch logs for a deployment/container")
    p_logs.add_argument("--deployment-id", default="")
    p_logs.add_argument("--container-id", default="")
    p_logs.add_argument("--lines", type=int, default=250)

    p_ready = sub.add_parser("wait-ready", help="poll until endpoint is ready")
    p_ready.add_argument("--url", required=True)
    p_ready.add_argument("--kind", required=True, choices=["vllm"])
    p_ready.add_argument("--max-wait-seconds", type=int, default=600)
    p_ready.add_argument("--request-timeout-seconds", type=float, default=120.0)

    args = parser.parse_args()

    if args.command == "check-version":
        result = cmd_check_version()
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") in ("OK", "VERSION_MISMATCH") else 1

    if args.command == "check-payload-size":
        result = cmd_check_payload_size()
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "OK" else 1

    token = resolve_beam_token()
    if not token and args.command not in ("check-version", "check-payload-size"):
        print(json.dumps(_err(
            f"{TOKEN_ENV_VAR} not found in process env or the credential "
            "broker. One-time setup: python scripts/fanfic_credential_broker.py "
            "store --name BEAM_TOKEN")), file=sys.stderr)
        return 2

    if args.command == "deploy":
        if args.kind == "endpoint":
            result = cmd_deploy_endpoint(args.handler, token, args.timeout_seconds)
        else:
            result = cmd_deploy_vllm(args.handler, token)
    elif args.command == "list":
        result = cmd_list(token)
    elif args.command == "volumes":
        result = cmd_volumes(token)
    elif args.command == "ls-volume":
        result = cmd_ls_volume(token, args.path)
    elif args.command == "containers":
        result = cmd_containers(token, args.deployment_id)
    elif args.command == "stop-container":
        result = cmd_stop_container(token, args.container_id)
    elif args.command == "logs":
        result = cmd_logs(token, deployment_id=args.deployment_id,
                          container_id=args.container_id, lines=args.lines)
    elif args.command == "wait-ready":
        result = cmd_wait_ready(args.url, token, kind=args.kind,
                                max_wait_seconds=args.max_wait_seconds,
                                request_timeout_seconds=args.request_timeout_seconds)
    else:
        result = _err(f"unknown command {args.command!r}")

    print(json.dumps(result, indent=2))
    return 0 if result.get("status", "").startswith(("OK", "DEPLOYED", "READY")) else 1


if __name__ == "__main__":
    sys.exit(main())
