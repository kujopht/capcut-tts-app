# Ghi chú bảo mật — Authorized Import (2026-08-31)

## Phát hiện: `server/translation_import.py::_tu_docx` dùng `xml.etree.ElementTree` thô

Trong lúc xây `server/import_pipeline/formats.py` cho luồng Authorized
Import, đã đối chiếu với `server/translation_import.py` (tính năng dịch,
đã tồn tại trước) vì cả hai đều trích văn bản từ DOCX/EPUB tải lên. Phát
hiện: `_tu_docx()` ở đó dùng thẳng `from xml.etree import ElementTree as ET`
để parse `word/document.xml` — **dữ liệu từ một file người dùng tải lên,
không được tin**.

So sánh với quy ước đã có sẵn trong CHÍNH kho này: `server/youtube_websub.py`
xử lý Atom XML nhận từ hub PubSubHubbub (cũng là dữ liệu từ Internet) và
dùng `defusedxml` thay vì `xml.etree.ElementTree` trực tiếp, với lý do ghi
rõ trong comment: `xml.etree.ElementTree` của thư viện chuẩn không chặn
được "billion laughs"/quadratic blowup. `defusedxml` đã là dependency thật
của backend (`server/requirements.txt`), không cần thêm gì để sửa.

**Mức độ thật:** DoS qua entity expansion (làm treo/chậm tiến trình xử lý
một request), KHÔNG phải XXE dạng đọc file/SSRF — `xml.etree.ElementTree`
mặc định không phân giải external entity qua mạng, chỉ có nguy cơ mở rộng
entity nội bộ (billion laughs). Vẫn là một lỗ hổng thật, chỉ là hẹp hơn XXE
đầy đủ.

**Vì sao KHÔNG sửa trong phiên làm việc này:** mission "AUTHORIZED FANFIC
INGESTION" mục 10 nói rõ "Do not reopen infrastructure" — `translation_
import.py` là code của một tính năng KHÁC (dịch thuật), không thuộc phạm
vi phiên này. `server/import_pipeline/formats.py` (code MỚI viết cho
Authorized Import) đã dùng `defusedxml.ElementTree` đúng ngay từ đầu, nên
luồng "Import my fanfic" không có lỗ hổng này.

**Việc cần làm sau (không phải bây giờ):** đổi `server/translation_
import.py::_tu_docx` sang `defusedxml.ElementTree.fromstring` thay vì
`xml.etree.ElementTree.fromstring` — một dòng import + một dòng gọi, không
đổi hành vi/interface. Nên kèm một test tái hiện tải trọng entity-expansion
để chứng minh sửa đúng, cùng nguyên tắc với các bản vá bảo mật khác trong
repo này (test hồi quy trước khi coi là xong).
