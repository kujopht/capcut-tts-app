"""
Day mot job TTS vao Cloud Tasks — TAT MAC DINH.

VI SAO TACH RA MOT TEP. Duong tao job (`main._tao_job_cho_chuong`) la duong
nong cua production. Them mot lan goi mang vao do la them mot cach lam hong
viec tao job. Nen o day quy tac cung:

  - `FAS_TTS_DISPATCH` khong dat -> `enqueue()` tra ve ngay, KHONG import
    thu vien nao, KHONG mo ket noi nao. Duong tao job y het truoc khi co tep
    nay. Co test khoa lai dieu do.
  - Bat len ma loi -> KHONG bao gio nem len tren. Job da nam ben vung o
    `pending`; day chi la mot cach BAO cho worker biet som. Mat cai bao thi
    duong quet cu van nhat duoc job. Mot su co Cloud Tasks tuyet doi khong
    duoc bien thanh "khong tao duoc audio" truoc mat nguoi dung.

Nghia la: hang doi la mot toi uu ve DO TRE, khong phai nguon su that. Nguon su
that van la trang thai job trong Appwrite, y nhu bay gio.
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


def duoc_bat() -> bool:
    return CHE_DO == "cloudtasks"


def cau_hinh_du() -> bool:
    return bool(QUEUE and QUEUE_LOCATION and GCP_PROJECT and TARGET_URL and OIDC_SA)


def enqueue(job_id: str) -> Optional[str]:
    """
    Bao cho worker biet co job moi. Tra ve ten task, hoac None neu khong day.

    KHONG BAO GIO nem. Xem docstring dau tep: mat cai bao khong phai su co.
    """
    if not duoc_bat():
        return None
    if not cau_hinh_du():
        print("canh bao: FAS_TTS_DISPATCH=cloudtasks nhung thieu cau hinh hang "
              "doi — bo qua, duong quet se nhat job")
        return None
    try:
        from google.cloud import tasks_v2  # import MUON, chi khi that su dung

        client = tasks_v2.CloudTasksClient()
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
            # Mot job chi co mot task, ke ca khi duong tao job bi thu lai.
            "name": client.task_path(GCP_PROJECT, QUEUE_LOCATION, QUEUE,
                                     f"tts-{job_id}"),
        }
        return client.create_task(parent=parent, task=task).name
    except Exception as exc:
        # Bao gom ca `AlreadyExists` khi task trung — dung la khong lam gi.
        print(f"canh bao: khong day duoc job {job_id} vao Cloud Tasks: "
              f"{type(exc).__name__}")
        return None
