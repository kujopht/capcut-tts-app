"""
Bo test backend - chay HERMETIC, khong bao gio cham toi cloud that.

VI SAO CAN FILE NAY:

`server/main.py` doc cau hinh va chon adapter NGAY LUC IMPORT. Tu khi
`server/config.py` biet nap `server/.env`, mot may co file cau hinh tro toi
Appwrite/R2 that se khien toan bo bo test chay vao cloud that - vua cho ket
qua sai, vua co nguy co GHI DE du lieu that.

Vi vay ep che do mock/local TRUOC KHI bat ky module test nao duoc nap. Package
nay luon duoc import truoc cac module con, nen day la diem sam nhat.

Cac test noi rieng ve viec nap `.env` va ve lua chon backend tu quan ly bien
moi truong cua chung (luu lai trong `setUp`, tra lai trong `tearDown`).
"""

import os

#: Khong nap file `.env` nao. Bo test noi ve HANH VI CUA CODE, khong ve cau
#: hinh cuc bo cua tung may.
os.environ["FAS_ENV_FILE"] = ""

#: Ep mock/local. Ghi de ca bien da export trong shell - mot phien lam viec
#: dang smoke test cloud van phai chay duoc bo test ma khong cham vao cloud.
os.environ["DATA_BACKEND"] = "mock"
os.environ["STORAGE_BACKEND"] = "local"

#: Khong de credential that ro ri vao tien trinh test.
for _name in (
    "APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "APPWRITE_API_KEY",
    "APPWRITE_DATABASE_ID",
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
):
    os.environ.pop(_name, None)
del _name

#: Middleware gioi han theo TANG (`server/rate_limit.py`, tu 7f8e80a ngay 2026-09-23) dem theo IP cho
#: TOAN TIEN TRINH, va moi `TestClient` deu la IP "testclient". Ca bo test chay ~70 s nen chi rieng
#: cac `setUp` dang ky + dang nhap qua HTTP da vuot 60 request Tier A/phut (vd `test_admin`: 74 test x
#: 4 request trong 1,4 s) -> 429 -> `KeyError: 'token'` o 54 module. Do la ly do CI backend cua `main` do
#: tu 2026-09-23. Tran rat cao o day chi cho TIEN TRINH TEST; mac dinh production (60/120/600) khong doi
#: va `test_rate_limiting` tu dat tran nho cua no roi TRA LAI gia tri nay (khoa bang
#: `test_mac_dinh_production_khong_doi`).
for _name in ("FAS_RATE_LIMIT_TIER_A", "FAS_RATE_LIMIT_TIER_B", "FAS_RATE_LIMIT_TIER_C"):
    os.environ.setdefault(_name, "1000000")
del _name
