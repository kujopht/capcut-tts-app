"""
Day mot job TTS vao Cloud Tasks — TAT MAC DINH.

VI SAO TACH RA MOT TEP. Duong tao job (`main._tao_job_cho_chuong`) la duong
nong cua production. Them mot lan goi mang vao do la them mot cach lam hong
viec tao job. Nen o day quy tac cung:

  - `FAS_TTS_DISPATCH` khong dat -> `enqueue()` tra ve ngay, KHONG import
    thu vien nao, KHONG mo ket noi nao. Duong tao job y het truoc khi co tep
    nay. Co test khoa lai dieu do.
  - Bat len ma loi -> NEM `DispatchError`. Xem muc duoi.

## VI SAO KHONG CON NUOT LOI (doi 2026-09-07)

Ban dau ham nay bat MOI exception va tra `None`, voi ly le: job da nam ben
vung o `pending` nen duong quet se nhat duoc.

Ly le do sai o dung mot diem, va diem do thanh su co that HAI LAN trong mot
ngay:

  1. THIEU GOI `google-cloud-tasks` nuot y het mot su co tam thoi.
  2. THIEU CREDENTIAL GCP tren Render (`DefaultCredentialsError`) cung the:
     ba lan tao job qua API production deu tra 201, hang doi VAN RONG.

Ca hai lan, "degradation" chinh la thu lam loi tro nen VO HINH — va no vo hinh
duoc VI duong quet dang ganh. Ngay dung worker AWS, cung mot loi im lang do
bien thanh "khong con gi tao audio".

Nen nay loi enqueue NEM. Muon job van tao duoc khi Cloud Tasks su co thi TAT
`FAS_TTS_DISPATCH` — mot quyet dinh tuong minh, khong phai mot nhanh `except`
am tham.

## CREDENTIAL: NAP TUONG MINH, KHONG DUA VAO ADC

`CloudTasksClient()` khong tham so se di tim Application Default Credentials.
Tren GCE/Cloud Run co san; tren Render KHONG CO GI — dung nguyen nhan su co
(2). Nen o day doc thang `FAS_TTS_TASKS_SA_JSON` (noi dung JSON cua khoa
service account, Render giu nhu secret). Thieu bien do -> nem, khong am tham
roi ve ADC.
"""
from __future__ import annotations

import json
import os
from typing import Optional

#: Che do dieu phoi. `""` (mac dinh) = TAT. `"cloudtasks"` = day sang hang doi.
CHE_DO = os.environ.get("FAS_TTS_DISPATCH", "").strip().lower()

QUEUE = os.environ.get("FAS_TTS_TASKS_QUEUE", "")
QUEUE_LOCATION = os.environ.get("FAS_TTS_TASKS_LOCATION", "")
GCP_PROJECT = os.environ.get("FAS_TTS_TASKS_PROJECT", "")
TARGET_URL = os.environ.get("FAS_TTS_TASKS_TARGET_URL", "")
OIDC_SA = os.environ.get("FAS_TTS_TASKS_OIDC_SA", "")

#: Noi dung JSON cua khoa service account dung de DAY task. Doc tuong minh
#: thay vi dua vao ADC — tren Render khong co ADC.
SA_JSON = os.environ.get("FAS_TTS_TASKS_SA_JSON", "").strip()


class DispatchError(RuntimeError):
    """Khong day duoc task. NEM chu khong tra None — xem docstring dau tep."""


def duoc_bat() -> bool:
    return CHE_DO == "cloudtasks"


def cau_hinh_du() -> bool:
    return bool(QUEUE and QUEUE_LOCATION and GCP_PROJECT and TARGET_URL and OIDC_SA)


def enqueue(job_id: str) -> Optional[str]:
    """
    Bao cho worker biet co job moi. Tra ve TEN TASK khi thanh cong.

    Tra `None` CHI khi dieu phoi dang TAT. Moi truong hop khac ma khong day
    duoc deu NEM `DispatchError` — xem docstring dau tep.
    """
    if not duoc_bat():
        return None
    if not cau_hinh_du():
        raise DispatchError(
            "FAS_TTS_DISPATCH=cloudtasks nhung thieu cau hinh hang doi "
            "(FAS_TTS_TASKS_QUEUE/LOCATION/PROJECT/TARGET_URL/OIDC_SA)")
    if not SA_JSON:
        raise DispatchError(
            "thieu FAS_TTS_TASKS_SA_JSON — tien trinh nay khong co credential "
            "GCP. KHONG roi ve ADC: tren Render khong co ADC, va lan truoc "
            "chinh dieu do lam moi task bi mat trong im lang.")
    try:
        from google.cloud import tasks_v2
        from google.oauth2 import service_account
    except ImportError as exc:
        raise DispatchError(
            "thieu goi google-cloud-tasks — xem server/requirements.txt") from exc

    try:
        thong_tin = json.loads(SA_JSON)
    except Exception as exc:
        raise DispatchError("FAS_TTS_TASKS_SA_JSON khong phai JSON hop le") from exc

    cred = service_account.Credentials.from_service_account_info(thong_tin)
    client = tasks_v2.CloudTasksClient(credentials=cred)
    parent = client.queue_path(GCP_PROJECT, QUEUE_LOCATION, QUEUE)
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": TARGET_URL,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"job_id": job_id}).encode("utf-8"),
            "oidc_token": {"service_account_email": OIDC_SA,
                           "audience": TARGET_URL},
        },
        # Id tat dinh -> Cloud Tasks tu chan trung trong cua so khu trung.
        "name": client.task_path(GCP_PROJECT, QUEUE_LOCATION, QUEUE,
                                 f"tts-{job_id}"),
    }
    try:
        return client.create_task(parent=parent, task=task).name
    except Exception as exc:
        # `AlreadyExists` la KHONG PHAI loi: task cho job nay da co. Day la
        # duong thu-lai binh thuong cua `POST /api/jobs`, khong duoc nem.
        if type(exc).__name__ == "AlreadyExists":
            return f"da-co:tts-{job_id}"
        raise DispatchError(
            f"khong day duoc job {job_id} vao Cloud Tasks: "
            f"{type(exc).__name__}") from exc
