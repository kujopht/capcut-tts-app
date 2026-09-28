"""
Cong cu Appwrite STAGING (Appwrite Cloud, project `fanfic-staging`) — KHONG PHAI production.

Ba nguyen tac, moi cai co bai test canh (`server/tests/test_staging_guard.py`):

1. MOT DICH DUY NHAT. `guard.DICH_DUYET` ghim CHINH XAC endpoint + project ID da duoc
   chu du an duyet. Moi script o day goi `guard.kiem_dich()` TRUOC bat ky request nao, va
   `guard.xac_minh_song()` (chi doc) TRUOC bat ky thao tac ghi nao.
2. KHONG BAO GIO DUNG BIEN `APPWRITE_*` CUA TIEN TRINH GOI. Toa do staging chi den tu
   `FAS_STAGING_*` (hoac tep ghi chu cua chu du an qua `FAS_STAGING_SECRETS_FILE`), va chi
   duoc chuyen thanh `APPWRITE_*` trong moi truong CUA TIEN TRINH CON, sau khi guard dat.
3. KHONG IN BI MAT. `bi_mat.CauHinhStaging` an khoa khoi `repr`, va moi dong log/bao cao
   di qua `CauHinhStaging.an()` truoc khi ra man hinh hay ra tep.
"""
