import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chính sách riêng tư | Fanfic Worldz",
  description:
    "Chính sách riêng tư của fanfic.world và ứng dụng Fanfic Worldz Uploader: dữ liệu nào được thu thập, dùng để làm gì, và không bao giờ bị bán hay chia sẻ.",
};

export default function PrivacyPage() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "32px 20px 64px", lineHeight: 1.7 }}>
      <h1>Chính sách riêng tư</h1>
      <p>
        <em>Cập nhật lần cuối: 30/10/2026.</em>
      </p>
      <p>
        Trang này mô tả cách fanfic.world và ứng dụng Fanfic Worldz Uploader
        xử lý thông tin của bạn. Ngắn gọn: chúng tôi chỉ dùng dữ liệu để vận
        hành dịch vụ đọc, nghe và đăng tải fanfic — không bán, không cho thuê,
        không chia sẻ dữ liệu cá nhân của bạn cho bên thứ ba vì mục đích
        quảng cáo.
      </p>

      <h2>1. Thông tin tài khoản</h2>
      <p>
        Khi bạn đăng ký hoặc đăng nhập, bạn cung cấp địa chỉ email và tên hiển
        thị. Thông tin này dùng để duy trì tài khoản của bạn, ghi nhận tiến độ
        đọc/nghe, và xác nhận quyền lợi tài khoản (ví dụ: tài khoản đã xác minh
        email được nhận gói Premium miễn phí trong giai đoạn hiện tại).
      </p>

      <h2>2. Nội dung bạn tạo và đăng tải</h2>
      <p>
        Truyện, chương, bình luận và các nội dung bạn đăng trên fanfic.world
        được hiển thị theo đúng chế độ xuất bản mà bạn chọn (công khai hoặc
        bản nháp). Nội dung công khai ai cũng có thể đọc và nghe theo quyền
        truy cập của từng tác phẩm.
      </p>

      <h2>3. Ứng dụng Fanfic Worldz Uploader và YouTube</h2>
      <p>
        Fanfic Worldz Uploader là công cụ đăng tải video lên kênh YouTube do
        chính bạn sở hữu. Khi bạn kết nối kênh, ứng dụng được cấp quyền để:
      </p>
      <ul>
        <li>tải video lên kênh YouTube mà bạn đã chọn,</li>
        <li>đặt ảnh thumbnail cho video,</li>
        <li>tạo và sắp xếp video vào playlist của kênh.</li>
      </ul>
      <p>
        Ứng dụng chỉ thực hiện các thao tác trên khi bạn yêu cầu, và chỉ trên
        kênh bạn đã kết nối. Mã truy cập (token) OAuth được lưu trữ an toàn và
        không bao giờ được chia sẻ cho bên thứ ba. Bạn có thể thu hồi quyền
        truy cập bất cứ lúc nào từ trang quản lý tài khoản Google của mình.
      </p>

      <h2>4. Dữ liệu không thu thập</h2>
      <p>
        Chúng tôi không bán dữ liệu cá nhân, không dùng dữ liệu của bạn để chạy
        quảng cáo nhắm mục tiêu, và không chia sẻ danh sách người dùng với bất
        kỳ đối tác quảng cáo nào.
      </p>

      <h2>5. Thay đổi chính sách</h2>
      <p>
        Nếu chính sách này thay đổi, ngày cập nhật ở đầu trang sẽ được đổi theo
        và nội dung mới sẽ áp dụng từ thời điểm đăng tải.
      </p>

      <h2>6. Liên hệ</h2>
      <p>
        Mọi thắc mắc về chính sách này, vui lòng liên hệ qua fanfic.world.
      </p>
    </main>
  );
}
