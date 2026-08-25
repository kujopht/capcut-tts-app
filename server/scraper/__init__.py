"""
Universal Story Scraper — nen tang, KHONG phai mot tinh nang bat/xuat ban.

Muc tieu: nhan MOT url truyen/chuong hoac url trang muc luc, tra ve chuong
duoc chuan hoa sach. KHONG tu dong xuat ban, KHONG vuot dang nhap/CAPTCHA/
paywall, KHONG crawl hang loat — xem `docs/reports/` cho bao cao overnight
giai thich pham vi.

Kien truc phan tang, uu tien re truoc dat:

  Tier 0 — HTTP truc tiep + JSON-LD/meta/RSS (server/scraper/http_fetcher.py,
           server/scraper/html_extract.py). KHONG can trinh duyet.
  Tier 1 — HTML parser ben vung hon (chua trien khai — Scrapling da duoc
           danh gia, xem docs/reports/; chi them phu thuoc nay khi co mot
           nguon that Tier 0 khong xu ly duoc).
  Tier 2 — trinh duyet render (chua trien khai — Playwright, cung ly do).
  Tier 3 — thu cong/khong ho tro.

`contract.py` dinh nghia giao dien trung lap nha cung cap (`StoryProvider`)
va cac kieu du lieu chuan hoa. `dedupe.py` la co che chong trung/resume.
`adapters/` la cac trien khai cu the, kiem thu bang fixture cuc bo — xem
server/tests/test_story_scraper_*.py.
"""
