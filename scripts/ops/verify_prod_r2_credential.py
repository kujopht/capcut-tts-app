#!/usr/bin/env python3
"""
Kiem bo khoa R2 PRODUCTION trong GCP Secret Manager — CHI DOC, KHONG GHI.

    python scripts/ops/verify_prod_r2_credential.py

Doc ba secret (`tts-r2-account-id`, `tts-r2-prod-access-key-id`,
`tts-r2-prod-secret-access-key`) bang `gcloud`, roi hoi R2 ba cau khong pha
gi. Gia tri bi mat KHONG BAO GIO duoc in, khong bao gio ghi xuong dia, va
khong bao gio nam trong tham so tien trinh (`gcloud` duoc goi bang argv rieng,
khong qua shell).

VI SAO CHI DOC. Cach chac chan nhat de chung minh mot khoa GHI duoc la ghi thu
mot object roi xoa. Tren `fanfic-prod` thi khong: day la bucket audio THAT cua
nguoi dung, va mot lan xoa sai duong dan la mat du lieu. Nen o day chi chung
minh: xac thuc duoc, thay dung bucket, doc duoc danh sach. Quyen GHI se duoc
chung minh o buoc 1 cua canary — mot job that, mot object that, kiem duoc bang
mat — chu khong bang mot phep thu ghi-roi-xoa tren du lieu that.

Ma thoat: 0 dat, 1 khong dat, 2 loi moi truong.
"""
from __future__ import annotations

import subprocess
import sys

GCP_PROJECT = "gen-lang-client-0793420657"
BUCKET_MONG_DOI = "fanfic-prod"

SECRETS = {
    "account_id": "tts-r2-account-id",
    "access_key_id": "tts-r2-prod-access-key-id",
    "secret_access_key": "tts-r2-prod-secret-access-key",
}


def doc_secret(ten: str) -> str:
    """Doc mot secret. Gia tri di qua stdout cua tien trinh con, khong qua shell."""
    r = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         f"--secret={ten}", f"--project={GCP_PROJECT}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        # `stderr` cua gcloud khi thieu secret khong chua gia tri nao — an toan
        # de in, va no la thong tin can thiet de biet phai tao secret nao.
        raise SystemExit(f"khong doc duoc secret {ten!r}: "
                         f"{r.stderr.strip().splitlines()[-1] if r.stderr else '?'}")
    # `.strip()` co y: mot xuong dong lac vao khoa se lam chu ky S3 sai, va
    # thong bao loi luc do khong he goi ten nguyen nhan.
    return r.stdout.strip()


def main() -> int:
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        print("thieu boto3 — pip install -r server/requirements.txt", file=sys.stderr)
        return 2

    gia_tri = {k: doc_secret(v) for k, v in SECRETS.items()}
    for k, v in gia_tri.items():
        if not v:
            print(f"KHONG DAT: secret cho {k} rong", file=sys.stderr)
            return 1
        # In DO DAI, khong bao gio in gia tri. Do dai la du de phat hien mot lan
        # dan thieu ky tu hay dan ca dong lenh vao.
        print(f"  {k:18} do dai {len(v)} ky tu")

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{gia_tri['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=gia_tri["access_key_id"],
        aws_secret_access_key=gia_tri["secret_access_key"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        region_name="auto",
    )

    loi = []

    # 1. XAC THUC + thay bucket. `HeadBucket` khong doc noi dung, khong ghi.
    try:
        client.head_bucket(Bucket=BUCKET_MONG_DOI)
        print(f"  head_bucket({BUCKET_MONG_DOI})   OK")
    except Exception as exc:
        loi.append(f"head_bucket({BUCKET_MONG_DOI}) that bai: "
                   f"{type(exc).__name__}: {str(exc)[:160]}")

    # 2. DOC duoc danh sach. `MaxKeys=1` de khong keo ve mot kho lon.
    try:
        r = client.list_objects_v2(Bucket=BUCKET_MONG_DOI, Prefix="audio/", MaxKeys=1)
        so = r.get("KeyCount", 0)
        print(f"  list_objects_v2(audio/) OK — thay {so} khoa (gioi han 1)")
        if so == 0:
            loi.append("bucket production khong co object nao duoi 'audio/' — "
                       "gan nhu chac chan la sai bucket hoac sai tai khoan")
    except Exception as exc:
        loi.append(f"list_objects_v2 that bai: {type(exc).__name__}: "
                   f"{str(exc)[:160]}")

    # 3. KHONG duoc thay bucket staging bang khoa nay.
    #
    # Khong phai phep kiem trang tri: mot khoa co pham vi ca hai bucket lam cho
    # phep ghep kho/bucket o `Settings._kiem_ghep_kho_va_bucket` mat mot lop
    # bao ve — cau hinh sai se van ghi duoc, chi khac la ghi sai cho. Bao ra de
    # nguoi van hanh biet, khong tu dong coi la truot.
    try:
        client.head_bucket(Bucket="fanfic-staging")
        print("  CANH BAO: khoa nay thay CA 'fanfic-staging' — pham vi rong "
              "hon can thiet cho canary")
    except Exception:
        print("  pham vi hep dung muc: khong voi tay sang fanfic-staging")

    if loi:
        print("\nKHONG DAT:", file=sys.stderr)
        for x in loi:
            print("  -", x, file=sys.stderr)
        return 1
    print("\nDAT — khoa xac thuc duoc va doc duoc fanfic-prod. "
          "Quyen GHI se duoc chung minh o buoc 1 cua canary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
