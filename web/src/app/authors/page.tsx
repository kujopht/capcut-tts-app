import Link from "next/link";

export default function AuthorsPage() {
  return (
    <div className="page" data-hero-theme="write">
      <header className="page-head">
        <div className="page-head-body stack-2">
          <span className="eyebrow">Dành cho tác giả</span>
          <h1 className="page-title">Đăng tác phẩm fanfic của bạn lên Fanfic World</h1>
          <p className="lead lead-narrow">
            Mang truyện bạn đã viết đến một nơi đọc, nghe và khám phá được xây
            riêng cho cộng đồng fanfic Việt Nam.
          </p>
        </div>
      </header>

      <section className="card stack" aria-labelledby="authors-benefits">
        <div className="stack-2">
          <h2 className="section-title" id="authors-benefits">
            Một tác phẩm, nhiều cách để đến với độc giả
          </h2>
          <p className="hint">
            Fanfic World giúp bạn bắt đầu từ bản thảo sẵn có và mở rộng trải
            nghiệm theo nhịp của mình. Bạn có thể chọn dùng những công cụ phù
            hợp với tác phẩm, không cần làm mọi thứ cùng lúc.
          </p>
        </div>
        <ul className="quy-dinh">
          <li>Trang đọc truyện có sẵn, rõ ràng trên cả máy tính và điện thoại.</li>
          <li>Công cụ dịch sang tiếng Việt cho tác phẩm phù hợp.</li>
          <li>Audiobook TTS để độc giả có thể nghe truyện.</li>
          <li>Ảnh bìa AI để hoàn thiện diện mạo tác phẩm.</li>
          <li>Số liệu người đọc giúp bạn hiểu tác phẩm đang được đón nhận ra sao.</li>
          <li>Trợ lý AI hỏi–đáp về truyện đang được định hướng cho tương lai.</li>
        </ul>
        <div className="row">
          <Link className="btn btn-primary" href="/import" prefetch={false}>
            Nhập fanfic của tôi
          </Link>
          <Link className="btn" href="/write" prefetch={false}>
            Viết một truyện mới
          </Link>
        </div>
      </section>
    </div>
  );
}
