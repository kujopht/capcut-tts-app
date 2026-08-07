import Link from "next/link";

/** Trang chu: hai the tinh nang lon, khong chia doi man hinh 50/50. */

export default function HomePage() {
  return (
    <div className="page">
      <section className="stack" style={{ maxWidth: 720, paddingTop: "var(--s4)" }}>
        <span className="eyebrow">Nền tảng audio tiếng Việt</span>
        <h1 className="page-title">
          Biến chữ thành giọng đọc, và nghe fanfic mọi lúc
        </h1>
        <p className="lead">
          Dán bất kỳ đoạn văn nào để tạo audio ngay, hoặc khám phá những truyện
          đã được cộng đồng xuất bản. Hai khu vực tách bạch, dùng chung một
          thư viện audio của bạn.
        </p>
      </section>

      <section className="grid-2" aria-label="Hai khu vực chính">
        <Link href="/studio" className="feature" style={{ "--glow": "#7c8cff3d" } as React.CSSProperties}>
          <span className="feature-icon" aria-hidden="true">
            🎙️
          </span>
          <h2>Tạo audio</h2>
          <p className="muted">
            Dán văn bản tuỳ ý, chọn giọng đọc và tốc độ, rồi tải file MP3 về
            máy. Theo dõi tiến trình theo thời gian thực và xem lại toàn bộ
            lịch sử đã tạo.
          </p>
          <span className="feature-cta">
            Mở Audio Studio <span aria-hidden="true">→</span>
          </span>
        </Link>

        <Link href="/fanfic" className="feature" style={{ "--glow": "#4dd6c133" } as React.CSSProperties}>
          <span className="feature-icon" aria-hidden="true">
            📚
          </span>
          <h2>Khám phá Fanfic</h2>
          <p className="muted">
            Tìm truyện theo tên hoặc thẻ, đọc từng chương và nghe bản audio đi
            kèm. Là tác giả, bạn viết truyện, tạo audio cho từng chương rồi
            xuất bản khi sẵn sàng.
          </p>
          <span className="feature-cta">
            Xem thư viện truyện <span aria-hidden="true">→</span>
          </span>
        </Link>
      </section>

      <section className="grid" aria-label="Cách hoạt động">
        {[
          {
            icon: "⚡",
            title: "Tạo nhanh",
            body: "Dán chữ, chọn giọng, bấm tạo. Tiến trình hiện ngay theo thời gian thực.",
          },
          {
            icon: "🔒",
            title: "Riêng tư mặc định",
            body: "Mọi thứ bạn tạo là bản nháp. Chỉ bạn nghe được cho tới khi tự xuất bản.",
          },
          {
            icon: "⬇",
            title: "Tải về được",
            body: "Audio hoàn tất đều tải xuống MP3 và nghe lại bất cứ lúc nào.",
          },
        ].map((item) => (
          <article key={item.title} className="card stack-2">
            <span aria-hidden="true" style={{ fontSize: 22 }}>
              {item.icon}
            </span>
            <h3 style={{ fontSize: "var(--t-md)" }}>{item.title}</h3>
            <p className="hint">{item.body}</p>
          </article>
        ))}
      </section>
    </div>
  );
}
