"""
`/api/admin/ai/*` — the AI control plane API (docs/ai/AI_ADMIN_CONTROL_PLANE.md).

Access: every route needs an admin role; READ routes accept ADMIN or OWNER,
every WRITE route is OWNER-only (same split as the Image Studio kill switch,
`owner_profile` in server/main.py). MODERATOR and normal users get 403,
anonymous 401 — decided by the dependencies `server/main.py` injects.

`FAS_AI_ADMIN_V1` off -> every route answers 503 `ai_admin_not_enabled`.

No response ever contains a secret value: slots carry `secret_ref`, the env
variable NAME, presence and a masked fingerprint (`secrets.py`).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from server.ai_assistant.control.model import ConfigValidationError
from server.ai_assistant.control.service import ControlConflict, ControlPlane
from server.ai_assistant.control.store import ControlStoreUnavailable


#: Plain number: Starlette renamed the constant (…_ENTITY -> …_CONTENT) and
#: warns on the old name; the status code itself never changed.
_HTTP_422 = 422


def build_ai_admin_router(plane: Optional[ControlPlane], *, reader: Callable[..., Any],
                          owner: Callable[..., Any]) -> APIRouter:
    r = APIRouter()

    def _plane() -> ControlPlane:
        if plane is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "ai_admin_not_enabled",
                                 "message": "Bảng điều khiển AI chưa được bật (FAS_AI_ADMIN_V1)."})
        return plane

    def _run(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except ConfigValidationError as exc:
            raise HTTPException(_HTTP_422,
                                {"code": "ai_admin_invalid", "message": "Dữ liệu không hợp lệ.", "errors": exc.errors})
        except ControlConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, {"code": "ai_admin_conflict", "message": str(exc)})
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "ai_admin_not_found", "message": "Không tìm thấy."})
        except ControlStoreUnavailable:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "ai_admin_store_unavailable", "message": "Kho cấu hình AI đang bận — thử lại sau."})

    def _body(b: Any) -> Dict[str, Any]:
        if not isinstance(b, dict):
            raise HTTPException(_HTTP_422,
                                {"code": "ai_admin_invalid", "message": "Thân yêu cầu phải là một object."})
        return b

    # ------------------------------------------------------------- read (ADMIN, OWNER)
    @r.get("/api/admin/ai/overview")
    def overview(response: Response, _p: Any = Depends(reader)) -> Dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return _run(lambda: _plane().overview())

    @r.get("/api/admin/ai/config")
    def config(response: Response, _p: Any = Depends(reader)) -> Dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return _run(lambda: _plane().config_view())

    @r.get("/api/admin/ai/audit")
    def audit(response: Response, limit: int = 50, _p: Any = Depends(reader)) -> Dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return {"items": _run(lambda: _plane().audit(max(1, min(int(limit), 100))))}

    # ------------------------------------------------------------- write (OWNER)
    @r.put("/api/admin/ai/global")
    def put_global(body: Any = Body(...), p: Any = Depends(owner)) -> Dict[str, Any]:
        b = dict(_body(body))
        expected = b.pop("expected_version", None)
        if expected is not None and (isinstance(expected, bool) or not isinstance(expected, int)):
            raise HTTPException(_HTTP_422,
                                {"code": "ai_admin_invalid", "message": "expected_version phải là số nguyên."})
        return {"controls": _run(lambda: _plane().update_controls(p.user_id, b, expected))}

    @r.put("/api/admin/ai/provider-types/{provider_type}")
    def put_type(provider_type: str, body: Any = Body(...), p: Any = Depends(owner)) -> Dict[str, Any]:
        b = _body(body)
        _run(lambda: _plane().set_provider_type(p.user_id, provider_type, b.get("enabled")))
        return {"ok": True}

    @r.post("/api/admin/ai/slots")
    def post_slot(body: Any = Body(...), p: Any = Depends(owner)) -> Dict[str, Any]:
        return {"slot": _run(lambda: _plane().create_slot(p.user_id, _body(body)))}

    @r.put("/api/admin/ai/slots/{slot_id}")
    def put_slot(slot_id: str, body: Any = Body(...), p: Any = Depends(owner)) -> Dict[str, Any]:
        return {"slot": _run(lambda: _plane().update_slot(p.user_id, slot_id, _body(body)))}

    @r.delete("/api/admin/ai/slots/{slot_id}")
    def delete_slot(slot_id: str, p: Any = Depends(owner)) -> Dict[str, Any]:
        _run(lambda: _plane().delete_slot(p.user_id, slot_id))
        return {"deleted": True}

    @r.post("/api/admin/ai/slots/{slot_id}/reset-cooldown")
    def reset_cooldown(slot_id: str, p: Any = Depends(owner)) -> Dict[str, Any]:
        _run(lambda: _plane().reset_cooldown(p.user_id, slot_id))
        return {"ok": True}

    @r.put("/api/admin/ai/profiles/{name}")
    def put_profile(name: str, body: Any = Body(...), p: Any = Depends(owner)) -> Dict[str, Any]:
        b = _body(body)
        return {"profile": _run(lambda: _plane().update_profile(p.user_id, name, b.get("steps"), b.get("enabled", True)))}

    return r
