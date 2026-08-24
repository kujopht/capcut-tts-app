"""
Adapter Cloudflare R2 qua API tuong thich S3.

NGUYEN TAC:
- Access key CHI song o backend. Trinh duyet khong bao gio thay.
- Database chi luu OBJECT KEY, khong bao gio luu binary audio.
- Cau hinh sai KHONG duoc am tham lui ve dia cuc bo: nem `R2ConfigError`.

`boto3` duoc import LAZY de backend van chay khi chua cai goi nay.
"""

from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Iterator, Optional

from server.adapters import NotFoundError, StoredObject
from server.config import R2Settings


class R2ConfigError(RuntimeError):
    """Cau hinh R2 thieu, sai, hoac thieu goi boto3."""


class R2StorageAdapter:
    """Luu file lon tren Cloudflare R2."""

    mode = "r2"

    def __init__(self, settings: R2Settings):
        if not settings.configured:
            raise R2ConfigError(
                "Cấu hình R2 chưa đủ. Cần cả bốn biến: R2_ACCOUNT_ID, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET."
            )
        try:
            import boto3  # noqa: WPS433 - co y import lazy
            from botocore.config import Config
        except ImportError as exc:
            raise R2ConfigError(
                "Đã cấu hình R2 nhưng chưa cài boto3. Chạy: pip install boto3"
            ) from exc

        self._settings = settings
        self._bucket = settings.bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
            region_name="auto",
        )

    # -- thao tac -------------------------------------------------------------

    def put(self, key: str, data: bytes, content_type: str = "audio/mpeg") -> str:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )
        return key

    def put_file(self, key: str, source: Any, content_type: str = "audio/mpeg") -> str:
        """
        Tai file LEN R2 tu duong dan tren dia, KHONG doc toan bo vao RAM.

        Track dai (audio import toi ~2GB, den 63 gio) khien `put(key,
        fp.read())` cu (doc het file vao bo nho roi moi goi) tao mot dinh bo
        nho khong can thiet. `upload_file` cua boto3 tu STREAM tu dia va tu
        chuyen sang multipart upload khi file vuot nguong, khong bao gio giu
        toan bo noi dung trong RAM cung mot luc.
        """
        from pathlib import Path

        self._client.upload_file(
            str(Path(source)), self._bucket, key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise NotFoundError(f"Không đọc được object '{key}' từ R2: {exc}") from exc
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def size(self, key: str) -> int:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
            return int(response.get("ContentLength") or 0)
        except Exception:
            return 0

    def delete(self, key: str) -> bool:
        """
        Xoa mot object.

        R2/S3 tra ve 204 ca khi key khong ton tai, nen kiem tra truoc de bao
        dung "co xoa gi khong" — huu ich cho log doi soat.
        """
        existed = self.exists(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)
        return existed

    def list_objects(self, prefix: str = "") -> Iterator[StoredObject]:
        """
        Liet ke moi object, LAT TRANG day du.

        `list_objects_v2` tra toi da 1000 khoa moi lan va bao con nua bang
        `IsTruncated` + `NextContinuationToken`. Goi mot lan roi thoi la mat sach
        object thu 1001 tro di — dung loai loi cat am tham nhu gioi han 25 cua
        Appwrite. Dung paginator cua boto3 de khong tu viet lai vong lap do.

        KHONG tao presigned URL: chi doc metadata cua khoa.
        """
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                modified = item.get("LastModified")
                yield StoredObject(
                    key=str(item.get("Key") or ""),
                    size_bytes=int(item.get("Size") or 0),
                    modified_at=(modified.astimezone(timezone.utc)
                                 .isoformat(timespec="seconds")
                                 if modified is not None else ""),
                )

    def signed_url(self, key: str, expires_seconds: int = 3600,
                   download_name: Optional[str] = None) -> Optional[str]:
        """
        URL ky san, co han su dung.

        Bucket phai la PRIVATE: nguoi dung chi tai duoc qua URL ky nay, va
        backend la noi quyet dinh co cap URL hay khong.

        `download_name` bat trinh duyet TAI VE thay vi phat trong tab, bang
        `Content-Disposition: attachment`. Can cho nut "Tai MP3": thuoc tinh
        `download` cua the <a> bi bo qua khi khac origin.
        """
        params = {"Bucket": self._bucket, "Key": key}
        if download_name:
            safe = download_name.replace('"', "").replace("\\", "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
        try:
            return self._client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=int(expires_seconds),
            )
        except Exception:
            return None

    def healthcheck(self) -> bool:
        """Kiem tra bucket truy cap duoc. Sai cau hinh thi nem loi ro."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception as exc:
            raise R2ConfigError(
                f"Không truy cập được bucket R2 '{self._bucket}': {exc}"
            ) from exc
        return True

    # -- chan doan --------------------------------------------------------
    #
    # Bon ham duoi day CHI phuc vu `/api/admin/_diag/r2-probe` (xem
    # `server/main.py`) — su co 2026-08-23: job TTS bao `completed` (tuc la
    # `put()` o tren khong nem loi) nhung HEAD/GET ngay sau do bao
    # `NoSuchKey`. `put()`/`get()` binh thuong VUT BO response cua boto3
    # (chi tra ve key/bytes), nen khong co cach nao thay duoc ETag/RequestId
    # that su ma R2 tra ve. Cac ham nay KHONG thay the `put()`/`get()` —
    # chung ton tai rieng de chan doan, khong bao gio duoc goi tu duong TTS
    # that.
    #
    # KHONG BAO GIO nem loi: moi ket qua (thanh cong lan that bai) deu tra
    # ve mot dict CHI chua truong khong bi mat (http status, request id,
    # ETag, ma loi) — khong bao gio chua access key/secret key/URL ky.

    def _loi_thanh_dict(self, exc: Exception) -> Dict[str, Any]:
        response = getattr(exc, "response", None) or {}
        error = response.get("Error", {}) if isinstance(response, dict) else {}
        meta = response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
        # botocore luon dinh dang hai truong nay la dict — nhung "khong bao
        # gio nem loi" phai dung ke ca voi mot response di dang bat thuong
        # (vd `Error` la chuoi), khong chi voi hinh dang binh thuong.
        if not isinstance(error, dict):
            error = {}
        if not isinstance(meta, dict):
            meta = {}
        return {
            "tim_thay": False,
            "http_status": meta.get("HTTPStatusCode"),
            "request_id": meta.get("RequestId"),
            "ma_loi": error.get("Code") or type(exc).__name__,
            "thong_diep_loi": error.get("Message"),
        }

    def put_probe(self, key: str, data: bytes,
                  content_type: str = "text/plain") -> Dict[str, Any]:
        """PUT tra ve METADATA THAT cua response, khac `put()` binh thuong
        (vut bo response, chi tra ve `key`). Nem loi neu PUT that bai — goi
        nam trong try/except o noi goi, khong nuot loi o day."""
        resp = self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type,
        )
        meta = resp.get("ResponseMetadata", {})
        return {
            "http_status": meta.get("HTTPStatusCode"),
            "request_id": meta.get("RequestId"),
            "etag": resp.get("ETag"),
        }

    def head_probe(self, key: str) -> Dict[str, Any]:
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            return self._loi_thanh_dict(exc)
        meta = resp.get("ResponseMetadata", {})
        return {
            "tim_thay": True,
            "http_status": meta.get("HTTPStatusCode"),
            "request_id": meta.get("RequestId"),
            "etag": resp.get("ETag"),
            "content_length": resp.get("ContentLength"),
        }

    def get_probe(self, key: str) -> Dict[str, Any]:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            so_byte = len(resp["Body"].read())
        except Exception as exc:
            return self._loi_thanh_dict(exc)
        meta = resp.get("ResponseMetadata", {})
        return {
            "tim_thay": True,
            "http_status": meta.get("HTTPStatusCode"),
            "request_id": meta.get("RequestId"),
            "etag": resp.get("ETag"),
            "so_byte_doc_duoc": so_byte,
        }

    def list_probe(self, prefix: str) -> Dict[str, Any]:
        try:
            resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        except Exception as exc:
            return self._loi_thanh_dict(exc)
        meta = resp.get("ResponseMetadata", {})
        return {
            "http_status": meta.get("HTTPStatusCode"),
            "request_id": meta.get("RequestId"),
            "so_khoa": resp.get("KeyCount"),
            "khoa": [item.get("Key") for item in resp.get("Contents", [])],
        }
