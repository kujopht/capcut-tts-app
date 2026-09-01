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
   `rollout` nua. Sau do script nay tu goi LAI
   `obj.print_invocation_snippet(url_type="")` MOT MINH (CHI mot tham so
   dung), day la loi goi AN TOAN vi khong con `rollout` di kem — day CHINH
   XAC la co che that su cung cap `invoke_url`.
   KHONG PATCH site-packages — day la cach dung API cong khai da co san
   cua chinh SDK de tranh mot loi that trong MOT phuong thuc cu the, dung
   nguyen tac CLAUDE.md "Do NOT patch random site-packages as the
   permanent solution."
3. Duong `@endpoint` thuong (vd cover_illustrious_app.py) KHONG bi loi
   nay — `mixins.py`'s generic `deploy()` xu ly `rollout` dung cach — nen
   van dung `beam deploy <handler> --format json` qua subprocess binh
   thuong, khong can di vong.
"""
from __future__ import annotations

import argparse
import json
import os
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


def _err(msg: str) -> Dict[str, Any]:
    return {"status": "ERROR", "error": msg}


def _beam_subprocess_env(token: str) -> dict:
    """Env cho MOT subprocess `beam` - CI=1 (bo qua banner crash) + token,
    khong bao gio sua `os.environ` cua chinh tien trinh nay."""
    env = dict(os.environ)
    env["CI"] = "1"
    env[TOKEN_ENV_VAR] = token
    return env


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
    try:
        result = subprocess.run(
            ["beam", "deploy", handler, "--format", "json"],
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
            "stderr": result.stderr[-2000:],
        }
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return _err(
            "beam deploy exited 0 but stdout was not valid JSON: "
            f"{result.stdout[-500:]}")
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
        return _err(f"failed to import {module_path}: {exc}")

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
        return _err(f"vllm deploy() raised: {exc}")

    if not ok:
        return {"status": "DEPLOY_FAILED", "response": response}

    invoke_url = ""
    try:
        # Goi AN TOAN, MOT MINH: CHI url_type, khong co rollout - day la
        # chinh xac cach VLLM.deploy() LE RA phai goi no (xem muc 2).
        url_response = vllm_obj.print_invocation_snippet(url_type="")
        if getattr(url_response, "ok", False):
            invoke_url = url_response.url
    except Exception as exc:
        # Khong coi la that bai deploy - deploy_stub DA thanh cong
        # (`ok` True o tren) - chi la khong lay duoc URL o buoc phu nay.
        return {
            "status": "DEPLOYED_URL_UNKNOWN",
            "deployment_id": response.get("deployment_id", ""),
            "url_lookup_error": str(exc),
        }
    return {
        "status": "DEPLOYED",
        "deployment_id": response.get("deployment_id", ""),
        "invoke_url": invoke_url,
    }


def cmd_list(token: str) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["beam", "deployment", "list", "--format", "json"],
            capture_output=True, text=True, timeout=60,
            env=_beam_subprocess_env(token))
    except FileNotFoundError:
        return _err("'beam' binary not found on PATH")
    if result.returncode != 0:
        return {"status": "ERROR", "returncode": result.returncode,
                "stderr": result.stderr[-2000:]}
    try:
        return {"status": "OK", "deployments": json.loads(result.stdout)}
    except ValueError:
        return _err(f"deployment list did not return valid JSON: "
                    f"{result.stdout[-500:]}")


def cmd_wait_ready(url: str, token: str, *, kind: str,
                   max_wait_seconds: int = 600,
                   initial_delay_seconds: float = 5.0,
                   max_delay_seconds: float = 60.0) -> Dict[str, Any]:
    """Cho endpoint SAN SANG THAT — cho VLLM, kiem tra `/v1/models`
    (nhe, KHONG sinh token nao, dung y mission "Do not consume
    model-generation tokens merely to check readiness"). Backoff mu
    (exponential) co gioi han, KHONG poll vo han."""
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
    with httpx.Client(timeout=10.0) as client:
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
                last_error = str(exc)
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

    p_deploy = sub.add_parser("deploy", help="deploy an app/function")
    p_deploy.add_argument("--handler", required=True,
                          help="path/to/file.py:object_name")
    p_deploy.add_argument("--kind", required=True, choices=["endpoint", "vllm"])
    p_deploy.add_argument("--timeout-seconds", type=int, default=300)

    sub.add_parser("list", help="list deployments")

    p_ready = sub.add_parser("wait-ready", help="poll until endpoint is ready")
    p_ready.add_argument("--url", required=True)
    p_ready.add_argument("--kind", required=True, choices=["vllm"])
    p_ready.add_argument("--max-wait-seconds", type=int, default=600)

    args = parser.parse_args()

    if args.command == "check-version":
        result = cmd_check_version()
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") in ("OK", "VERSION_MISMATCH") else 1

    token = resolve_beam_token()
    if not token and args.command != "check-version":
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
    elif args.command == "wait-ready":
        result = cmd_wait_ready(args.url, token, kind=args.kind,
                                max_wait_seconds=args.max_wait_seconds)
    else:
        result = _err(f"unknown command {args.command!r}")

    print(json.dumps(result, indent=2))
    return 0 if result.get("status", "").startswith(("OK", "DEPLOYED", "READY")) else 1


if __name__ == "__main__":
    sys.exit(main())
