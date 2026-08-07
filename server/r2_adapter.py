"""
Adapter Cloudflare R2 qua API tuong thich S3.

NGUYEN TAC:
- Access key CHI song o backend. Trinh duyet khong bao gio thay.
- Database chi luu OBJECT KEY, khong bao gio luu binary audio.
- Cau hinh sai KHONG duoc am tham lui ve dia cuc bo: nem `R2ConfigError`.

`boto3` duoc import LAZY de backend van chay khi chua cai goi nay.
"""

from __future__ import annotations

from typing import Any, Optional

from server.adapters import NotFoundError
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

    def put_file(self, key: str, source: Any) -> str:
        from pathlib import Path

        with open(Path(source), "rb") as fp:
            return self.put(key, fp.read())

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
