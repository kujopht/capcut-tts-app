#!/usr/bin/env python3
"""
Tao database / collections / attributes / indexes cho Fanfic Audio Studio.

AN TOAN KHI CHAY LAI: moi buoc deu bo qua neu doi tuong da ton tai (409).

Script nay KHONG chua secret. No doc cau hinh tu bien moi truong:
    APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, APPWRITE_DATABASE_ID

Chay:
    .venv\\Scripts\\python.exe -m scripts.setup_appwrite
    .venv\\Scripts\\python.exe -m scripts.setup_appwrite --dry-run
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

import httpx

from server.config import load_settings

TIMEOUT = 30.0

#: (key, kieu, bat_buoc, kich_thuoc/tuy_chon)
SCHEMA: Dict[str, Dict[str, Any]] = {
    "profiles": {
        "name": "Profiles",
        "attributes": [
            ("user_id", "string", True, 64),
            ("email", "email", True, None),
            ("display_name", "string", False, 120),
            ("tier", "enum", True, ["free", "listener_pro", "creator_pro", "ultra"]),
            ("listened_minutes", "integer", False, None),
            ("tts_characters_used", "integer", False, None),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [("email_unique", "unique", ["email"])],
    },
    "novels": {
        "name": "Novels",
        "attributes": [
            ("novel_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("title", "string", True, 200),
            ("description", "string", False, 2000),
            ("cover_key", "string", False, 512),
            ("state", "enum", True, ["draft", "published", "archived"]),
            ("tags", "string", False, 64),          # mang
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("owner_idx", "key", ["owner_id"]),
            ("state_idx", "key", ["state"]),
            ("state_created_idx", "key", ["state", "created_at"]),
        ],
    },
    "chapters": {
        "name": "Chapters",
        "attributes": [
            ("chapter_id", "string", True, 64),
            ("novel_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("title", "string", True, 200),
            ("content", "string", False, 1000000),
            ("order_index", "integer", True, None),
            ("state", "enum", True, ["draft", "published", "archived"]),
            ("created_at", "datetime", True, None),
            ("updated_at", "datetime", True, None),
        ],
        "indexes": [
            ("novel_idx", "key", ["novel_id"]),
            ("novel_order_idx", "key", ["novel_id", "order_index"]),
            ("owner_idx", "key", ["owner_id"]),
        ],
    },
    "tts_jobs": {
        "name": "TTS Jobs",
        "attributes": [
            ("job_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("chapter_id", "string", True, 64),
            ("voice_id", "string", True, 128),
            ("content_hash", "string", True, 64),
            ("status", "enum", True, ["pending", "running", "completed", "failed"]),
            ("output_key", "string", False, 512),
            ("error_kind", "string", False, 64),
            ("error_message", "string", False, 1000),
            ("total_parts", "integer", False, None),
            ("done_parts", "integer", False, None),
            ("rate", "string", False, 16),
            ("chunk_chars", "integer", False, None),
            ("created_at", "datetime", True, None),
            ("started_at", "datetime", False, None),
            ("finished_at", "datetime", False, None),
        ],
        "indexes": [
            # Index QUAN TRONG NHAT: phuc vu idempotency
            ("idempotency_idx", "key", ["owner_id", "chapter_id", "content_hash"]),
            ("status_idx", "key", ["status"]),
        ],
    },
    "audio_tracks": {
        "name": "Audio Tracks",
        "attributes": [
            ("track_id", "string", True, 64),
            ("chapter_id", "string", True, 64),
            ("owner_id", "string", True, 64),
            ("voice_id", "string", True, 128),
            ("object_key", "string", True, 512),
            ("content_hash", "string", True, 64),
            ("duration_seconds", "double", False, None),
            ("size_bytes", "integer", False, None),
            ("created_at", "datetime", True, None),
        ],
        "indexes": [
            ("chapter_idx", "key", ["chapter_id"]),
            ("chapter_created_idx", "key", ["chapter_id", "created_at"]),
        ],
    },
}

#: Quyen o muc COLLECTION: khong cap gi cho client.
#:
#: Truoc day day la `['create("users")']`, tuc la BAT KY nguoi dung da dang
#: nhap nao cung tu tao document truc tiep qua Appwrite API duoc, o CA NAM
#: collection - bo qua hoan toan backend. Quyen o muc collection ap dung
#: THEM vao quyen tung document, nen no vo hieu hoa chinh mo hinh phan quyen
#: theo document ma ta thiet ke.
#:
#: Moi thao tac GHI deu di qua backend bang API key, ma API key bo qua
#: permission - nen de rong o day khong lam hong chuc nang nao.
#: Quyen DOC van do tung document quyet dinh (documentSecurity=True).
COLLECTION_PERMISSIONS: List[str] = []


class Setup:
    def __init__(self, dry_run: bool = False):
        settings = load_settings()
        # Che do thu chi in ke hoach nen khong can credential
        if not settings.appwrite.configured and not dry_run:
            raise SystemExit(
                "Thiếu cấu hình Appwrite. Cần đủ APPWRITE_ENDPOINT, "
                "APPWRITE_PROJECT_ID, APPWRITE_API_KEY, APPWRITE_DATABASE_ID."
            )
        self.cfg = settings.appwrite
        self.endpoint = (self.cfg.endpoint or "https://<endpoint>").rstrip("/")
        self.dry_run = dry_run
        self.created = 0
        self.skipped = 0

    def _call(self, method: str, path: str, payload: Optional[Dict] = None) -> Any:
        if self.dry_run:
            print(f"    [dry-run] {method} {path}")
            return None
        headers = {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self.cfg.project_id,
            "X-Appwrite-Key": self.cfg.api_key,     # CHI o phia server
        }
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request(
                method, f"{self.endpoint}{path}", json=payload, headers=headers
            )
        if response.status_code == 409:
            self.skipped += 1
            return "exists"
        if response.status_code >= 400:
            message = response.text[:300]
            try:
                body = response.json()
                message = body.get("message", message)
            except Exception:
                pass
            raise SystemExit(f"Appwrite lỗi {response.status_code}: {message}")
        self.created += 1
        return response.json() if response.content else {}

    # -- cac buoc -------------------------------------------------------------

    def ensure_database(self) -> None:
        print(f"Database {self.cfg.database_id or '<APPWRITE_DATABASE_ID>'}")
        result = self._call("POST", "/v1/databases", {
            "databaseId": self.cfg.database_id,
            "name": "Fanfic Audio Studio",
        })
        print("  đã có sẵn" if result == "exists" else "  đã tạo")

    def ensure_collection(self, cid: str, spec: Dict[str, Any]) -> None:
        print(f"Collection {cid}")
        result = self._call("POST", f"/v1/databases/{self.cfg.database_id}/collections", {
            "collectionId": cid,
            "name": spec["name"],
            "permissions": COLLECTION_PERMISSIONS,
            "documentSecurity": True,      # quyen theo TUNG document
        })
        print("  đã có sẵn" if result == "exists" else "  đã tạo")

        base = f"/v1/databases/{self.cfg.database_id}/collections/{cid}"
        for key, kind, required, extra in spec["attributes"]:
            self._ensure_attribute(base, key, kind, required, extra)
        for name, kind, keys in spec["indexes"]:
            self._ensure_index(base, name, kind, keys)

    def _ensure_attribute(self, base: str, key: str, kind: str,
                          required: bool, extra: Any) -> None:
        payload: Dict[str, Any] = {"key": key, "required": required}
        if kind == "string":
            path, payload["size"] = f"{base}/attributes/string", extra
            if key == "tags":
                payload["array"] = True
        elif kind == "email":
            path = f"{base}/attributes/email"
        elif kind == "enum":
            path, payload["elements"] = f"{base}/attributes/enum", extra
        elif kind == "integer":
            path = f"{base}/attributes/integer"
        elif kind == "double":
            path = f"{base}/attributes/float"
        elif kind == "datetime":
            path = f"{base}/attributes/datetime"
        else:
            raise SystemExit(f"Kiểu thuộc tính chưa hỗ trợ: {kind}")

        result = self._call("POST", path, payload)
        print(f"    - {key} ({kind}): {'đã có' if result == 'exists' else 'đã tạo'}")

    def _ensure_index(self, base: str, name: str, kind: str, keys: List[str]) -> None:
        result = self._call("POST", f"{base}/indexes", {
            "key": name,
            "type": kind,
            "attributes": keys,
            "orders": ["ASC"] * len(keys),
        })
        print(f"    * index {name} {keys}: {'đã có' if result == 'exists' else 'đã tạo'}")

    def run(self) -> None:
        self.ensure_database()
        for cid, spec in SCHEMA.items():
            self.ensure_collection(cid, spec)
        print(f"\nHoàn tất — tạo mới {self.created}, bỏ qua (đã có) {self.skipped}.")
        print("Chạy lại script này bất cứ lúc nào đều an toàn.")


def main(argv: List[str]) -> int:
    dry_run = "--dry-run" in argv
    if dry_run:
        print("Chế độ thử: không gọi Appwrite, chỉ in các bước sẽ chạy.\n")
    Setup(dry_run=dry_run).run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
