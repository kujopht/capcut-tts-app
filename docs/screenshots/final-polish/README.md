# Ảnh lượt hoàn thiện cuối (L2, L3, L4, breadcrumb)

Desktop 1440×900, mobile 390×844. Backend chạy chế độ `appwrite` + `r2` thật.

| Ảnh | Cho thấy điều gì |
|---|---|
| `truoc-l2-fanfic-desktop.png` | Trước: không có thanh phân trang, đếm "3 truyện", lọc chạy trong trình duyệt |
| `truoc-l2-fanfic-mobile.png` | Trước, ở mobile |
| `sau-l2-fanfic-desktop.png` | Sau: 12 thẻ, "1–12 trong 14 truyện", "Trang 1 / 2", nút *Trang trước* bị vô hiệu |
| `sau-l2-fanfic-desktop-trang2.png` | Trang 2: 2 thẻ, nút *Trang sau* bị vô hiệu |
| `sau-l2-fanfic-mobile.png` | Sau, ở mobile — thanh phân trang tự xuống dòng |
| `sau-l3-studio-desktop.png` | Sau: badge "Lịch sử audio" khớp với khung "Tiến trình" |
| `sau-l4-home-desktop.png` | Sau: quầng sáng lấy từ token, không còn style inline |
| `sau-l4-home-mobile.png` | Sau, ở mobile |
| `breadcrumb-novel-mobile-hinh-anh-khong-doi.png` | Breadcrumb: **ảnh trước và sau giống nhau từng byte** |
| `sau-breadcrumb-chapter-mobile.png` | Breadcrumb ở trang chương, kèm cảnh báo M4 |

## Vì sao breadcrumb chỉ có một ảnh

Bản sửa mở rộng vùng bấm bằng một lớp `::after` đặt tuyệt đối — lớp này **không
tham gia layout**, nên trông y hệt trước. Ảnh chụp trước và sau giống nhau từng
byte (đã kiểm bằng md5), nên giữ hai bản chỉ gây hiểu nhầm là "không sửa gì".

Bằng chứng cho bản sửa này là **số đo**, không phải ảnh:

| Hạng mục | Trước | Sau |
|---|---|---|
| Chiều cao chữ | 20px | 20px |
| Chiều cao hàng `<nav>` | 23px | 23px |
| Bấm được cách tâm 20px lên trên | không | **có** |
| Bấm được cách tâm 20px xuống dưới | không | **có** |

Đo bằng `document.elementFromPoint()` ở khung 390×844 trên cả `/novels/[id]` và
`/chapters/[id]`.
