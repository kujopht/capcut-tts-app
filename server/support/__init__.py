"""
Fanfic AI Support V1 — hoi dap + chan doan loi CHI DOC + bao cao cho quan tri.

Ba nguyen tac khong duoc pha (moi nguyen tac co bai test canh o
`server/tests/test_support_*.py`):

1. CONG CU DO MAY CHU CHON, KHONG PHAI MO HINH. Danh sach cong cu chan doan la
   mot bang co dinh trong `tools.py`; `engine.py` chon cong cu bang QUY TAC tat
   dinh tu ngu canh (trang, chuong, ma loi) va tu khoa. Mo hinh ngon ngu (neu
   co cau hinh) chi VIET LOI GIAI THICH tu ket qua da lam sach — no khong co
   cong cu nao, khong goi duoc URL, khong chay duoc lenh. "Prompt injection"
   vi vay khong mo them duoc gi: cai khong ton tai thi khong goi duoc.
2. CHI DOC, TRONG TIEN TRINH. Khong cong cu nao nhan URL, khong cong cu nao goi
   mang ra ngoai, khong cong cu nao ghi/xoa/khoi dong lai gi. Moi cong cu di qua
   dung ham kiem quyen DOC da co cua san pham (`_may_read`, `_can_read_chapter`)
   — ai khong doc duoc mot chuong thi cung khong chan doan duoc chuong do.
3. KHONG BAO GIO TRA BI MAT. Moi chuoi tu client lan tu cong cu di qua
   `sanitize.sach_chuoi` truoc khi luu, truoc khi dua cho mo hinh va truoc khi
   tra ve; ket qua cong cu chi co truong da liet ke (co/khong, dem, ma trang
   thai), khong bao gio co khoa, token, URL ky hay email.

Luu tru: `store.InMemorySupportStore` (bo nho, co gioi han, co han luu). Chua co
schema Appwrite — xem `docs/support/SUPPORT_STORAGE_PROPOSAL.md`; KHONG migrate.
Co tinh nang: `FAS_SUPPORT_V1=1` (mac dinh TAT -> moi route tra 503).
"""
