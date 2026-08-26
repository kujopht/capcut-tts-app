"""
Universal Story Scraper — nen tang, KHONG phai mot tinh nang bat/xuat ban.

Muc tieu: nhan MOT url truyen/chuong hoac url trang muc luc, tra ve chuong
duoc chuan hoa sach. KHONG tu dong xuat ban, KHONG vuot dang nhap/CAPTCHA/
paywall, KHONG crawl hang loat — xem `docs/reports/` cho bao cao overnight
giai thich pham vi.

Cay quyet dinh phan tang — LUON thu tang thap truoc, chi len tang tiep
theo khi tang duoi that su khong xu ly duoc (khong phai "de chac an"):

  URL vao
    |
    v
  Tier 0 — HTTP truc tiep + meta/JSON-LD (http_fetcher.py, html_extract.py)
    |  dung `GenericIndexAdapter`/`JsonLdAwareAdapter` (adapters/).
    |  KHONG can trinh duyet. Du cho da so site tinh voi cau truc on dinh.
    |
    +-- tim duoc chuong bang mau href/CSS đa cau hinh? --[co]--> XONG
    |
    +--[khong: mau cu khong con khop MOT lien ket nao — thuong la site
    |          da doi giao dien]
    v
  Tier 1 — Scrapling (`adapters/scrapling_adapter.py`, ScraplingAdapter)
    |  Ban co ban (KHONG cai them extras trinh duyet) — chi lxml/cssselect/
    |  orjson/w3lib/tld, KHONG Playwright. Da kiem chung truc tiep (xem
    |  docs/reports/): `.save()`/`.relocate()` dinh vi lai duoc mot phan tu
    |  DA LUU DAU VAN TAY tu lan quet truoc, du site doi HET class VA the
    |  bao ngoai — GenericIndexAdapter (Tier 0) khong co duong lui nay.
    |  CHI hoat dong neu DA co it nhat MOT lan quet thanh cong truoc do de
    |  luu dau van tay; lan dau tien tren mot site moi hoan toan, Tier 1
    |  khong co gi hon Tier 0.
    |
    +-- co dau van tay cu VA relocate tim duoc chuong? --[co]--> XONG
    |
    +--[khong: chua tung quet thanh cong LAN NAO tren site nay, hoac noi
    |          dung can trich xuat chi xuat hien SAU KHI JavaScript chay
    |          (React/Vue client-render, infinite-scroll, nut "xem them"
    |          can bam) — ca hai truong hop nay KHONG the parse tu HTML
    |          tinh du dung engine parse nao]
    v
  Tier 2 — trinh duyet render (CHUA TRIEN KHAI)
    |  Ung vien: Playwright (Python) danh cho JS-render CO KIEM SOAT
    |  (khong can nguy trang chong phat hien) tren trang PUBLIC — da co
    |  san trong repo o phia web/ (Node, dev-dependency test), CAN cai
    |  rieng ban Python (`playwright` pip + `playwright install chromium`)
    |  neu dung o server/. CloakBrowser (nguy trang chong phat hien manh
    |  hon Playwright thuong) la ung vien Tier 2/3 rieng — CHI xet toi khi
    |  co MOT nguon THAT, cong khai, khong dang nhap, ma Playwright thuong
    |  van bi chan (fingerprinting/bot-detection) — chua co nguon nao nhu
    |  vay duoc xac dinh trong dem nay, nen KHONG cai dat.
    |  KHONG BAO GIO dung Tier 2 de vuot dang nhap/CAPTCHA/paywall — ngoai
    |  pham vi tuyet doi, xem canh bao dau file.
    |
    +-- trang render duoc VA trich xuat duoc sau khi cho JS chay? --[co]--> XONG
    |
    v
  Tier 3 — thu cong/khong ho tro. Bao cao ro cho nguoi van hanh BIET nguon
           nay can xu ly tay, KHONG duoc am tham bo qua hay tra du lieu
           rong nhu the da thanh cong.

`contract.py` dinh nghia giao dien trung lap nha cung cap (`StoryProvider`)
va cac kieu du lieu chuan hoa (bao gom `ScraperTier` — moi adapter tu khai
tier cua no). `dedupe.py` la co che chong trung/resume/phat hien revision.
`adapters/` la cac trien khai cu the, kiem thu bang fixture cuc bo — xem
server/tests/test_story_scraper_*.py.
"""
