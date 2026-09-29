"""
Du lieu THU CUC BO cho Social & Play V1 — CHI chay voi backend mock tren may lap trinh.

Tao 3 nguoi dung thu (co nhan "thu nghiem"), vai bai dang, luot theo doi, binh luan,
va 2 truyen da xuat ban co fandom de kiem bo loc fandom. Moi noi dung deu mang nhan
"[Dữ liệu thử cục bộ]" de khong ai nham voi du lieu that.

AN TOAN:
  * Tu choi chay neu `/api/health` KHONG bao `data_backend=mock` va `identity=mock`
    — script nay khong bao gio duoc cham toi Appwrite/production.
  * Mat khau sinh NGAU NHIEN moi lan chay, chi ghi vao `server/var/.../local_test_users.json`
    (thu muc da git-ignore). Khong in mat khau/token ra man hinh.
  * Backend mock giu du lieu trong bo nho: moi lan uvicorn --reload khoi dong lai la mat
    het — chay lai script nay (idempotent theo email: email da co thi dang nhap lai).

Dung:
  python scripts/dev_social_play_seed.py --api http://127.0.0.1:8010 \
      --out server/var/social-play/local_test_users.json
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

NHAN = "[Dữ liệu thử cục bộ]"

NGUOI_THU = [
    {"key": "lan", "email": "qa.lan@example.test", "display_name": "QA Lan (thử nghiệm)", "username": "qa_lan"},
    {"key": "minh", "email": "qa.minh@example.test", "display_name": "QA Minh (thử nghiệm)", "username": "qa_minh"},
    {"key": "hoa", "email": "qa.hoa@example.test", "display_name": "QA Hoa (thử nghiệm)", "username": "qa_hoa"},
]


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
             token: str = "") -> Dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode("utf-8") or "{}"
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:300]
            raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    ap.add_argument("--out", default="server/var/social-play/local_test_users.json")
    args = ap.parse_args()
    api = Api(args.api)

    health = api.call("GET", "/api/health")
    if health.get("data_backend") != "mock" or health.get("identity") != "mock":
        print("TU CHOI: backend khong phai mock — script nay chi cho du lieu thu cuc bo.")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cu: Dict[str, Any] = {}
    if out.exists():
        cu = json.loads(out.read_text(encoding="utf-8"))

    users: Dict[str, Dict[str, Any]] = {}
    for n in NGUOI_THU:
        mat_khau = (cu.get(n["key"]) or {}).get("password") or secrets.token_urlsafe(18)
        try:
            ra = api.call("POST", "/api/auth/register", {
                "email": n["email"], "password": mat_khau, "display_name": n["display_name"]})
        except RuntimeError as exc:
            if "đã được đăng ký" not in str(exc):
                raise
            ra = api.call("POST", "/api/auth/login", {"email": n["email"], "password": mat_khau})
        tok = ra["token"]
        uid = ra["profile"]["user_id"]
        try:
            api.call("PUT", "/api/creator/username", {"username": n["username"]}, tok)
        except RuntimeError:
            pass  # da dat roi
        users[n["key"]] = {"user_id": uid, "email": n["email"], "password": mat_khau,
                           "token": tok, "username": n["username"],
                           "display_name": n["display_name"]}

    lan, minh, hoa = users["lan"], users["minh"], users["hoa"]

    # Da seed trong tien trinh backend nay chua? (bai cua Lan co nhan).
    da_co = api.call("GET", f"/api/users/{lan['user_id']}/posts?limit=1")
    if not da_co.get("items"):
        # Truyen da xuat ban co fandom — cho bo loc fandom.
        # Ten phai co trong `server/fandom_registry.py::_SEED_FANDOMS`.
        for chu, t in ((lan, "Naruto"), (minh, "One Piece")):
            try:
                nv = api.call("POST", "/api/novels", {
                    "title": f"{NHAN} Truyện thử {t}", "description": f"{NHAN} Chỉ để kiểm bộ lọc fandom.",
                    "fandom_names": [t]}, chu["token"])["novel"]
                api.call("POST", "/api/chapters", {
                    "novel_id": nv["novel_id"], "title": "Chương 1 thử",
                    "content": f"{NHAN} Nội dung chương thử để xuất bản truyện thử.", "order_index": 1},
                    chu["token"])
                api.call("POST", f"/api/novels/{nv['novel_id']}/publish", {}, chu["token"])
                chu.setdefault("novels", []).append({"novel_id": nv["novel_id"], "fandom": t})
            except RuntimeError as exc:
                print("bo qua truyen thu:", str(exc)[:160])

        bai = [
            (lan, f"{NHAN} Chào mọi người, đây là bài thử đầu tiên của Lan."),
            (minh, f"{NHAN} Minh đang đọc lại arc Chunin — có ai muốn bàn không?"),
            (hoa, f"{NHAN} Hoa thử đăng một bài dài hơn một chút để xem cách cắt dòng trên điện thoại "
                  "và độ rộng cột đọc trên desktop có dễ chịu không."),
            (lan, f"{NHAN} Bài thứ hai của Lan — dùng để kiểm phân trang không trùng."),
            (minh, f"{NHAN} Minh: tối nay ai chơi Caro không?"),
        ]
        ids = []
        for chu, text in bai:
            ra = api.call("POST", "/api/posts", {"text": text, "kind": "post"}, chu["token"])
            ids.append(ra["post"]["post_id"])
        api.call("POST", f"/api/users/{minh['user_id']}/follow", {}, lan["token"])
        api.call("POST", f"/api/posts/{ids[1]}/like", {}, lan["token"])
        api.call("POST", f"/api/posts/{ids[0]}/comments",
                 {"text": f"{NHAN} Minh bình luận bài của Lan."}, minh["token"])

    # Ghi ra tep git-ignore; KHONG in mat khau/token.
    out.write_text(json.dumps(users, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, u in users.items():
        print(f"{k}: user_id={u['user_id']} username={u['username']}")
    print("da ghi thong tin dang nhap thu vao", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
