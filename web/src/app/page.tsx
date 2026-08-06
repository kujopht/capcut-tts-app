import Link from "next/link";

export default function LandingPage() {
  return (
    <>
      <section style={{ padding: "72px 0 48px", textAlign: "center" }}>
        <h1 style={{ fontSize: 42, fontWeight: 800, margin: "0 0 16px", lineHeight: 1.2 }}>
          Biến truyện chữ thành audio
        </h1>
        <p style={{ fontSize: 18, color: "var(--text-dim)", maxWidth: 620, margin: "0 auto 32px" }}>
          Viết hoặc nhập tiểu thuyết, chọn giọng đọc, rồi tạo audio ngay trong
          trình duyệt. Nghe lại bất cứ lúc nào.
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
          <Link href="/studio" className="btn btn-primary">
            Bắt đầu tạo audio
          </Link>
          <Link href="/library" className="btn">
            Xem thư viện
          </Link>
        </div>
      </section>

      <section className="grid" aria-label="Tính năng chính">
        {[
          { icon: "✍️", title: "Viết & nhập truyện", body: "Tạo tiểu thuyết, thêm chương và chỉnh sửa trực tiếp trong Creator Studio." },
          { icon: "🎙️", title: "Nhiều nguồn giọng", body: "CapCut, Edge TTS và Piper chạy cục bộ — chọn giọng phù hợp cho từng truyện." },
          { icon: "🎧", title: "Nghe mọi lúc", body: "Audio hoàn tất được lưu lại và phát ngay trên trang chi tiết chương." },
        ].map((f) => (
          <article className="card" key={f.title}>
            <div style={{ fontSize: 26, marginBottom: 10 }} aria-hidden="true">{f.icon}</div>
            <h2 style={{ fontSize: 16, margin: "0 0 6px" }}>{f.title}</h2>
            <p className="hint" style={{ margin: 0 }}>{f.body}</p>
          </article>
        ))}
      </section>

      <section className="card" style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 16, marginTop: 0 }}>Trạng thái dự án</h2>
        <p className="hint" style={{ marginBottom: 0 }}>
          Đây là bản MVP kỹ thuật chạy riêng tư. Chưa có thanh toán, chưa phát
          hành thương mại. Giọng đọc chạy cục bộ chưa xác minh giấy phép nên chỉ
          bật ở chế độ phát triển.
        </p>
      </section>
    </>
  );
}
