/**
 * Khung xuong trang truyen (Product UX Sprint 2).
 *
 * Trang truyen do MAY CHU ve sau khi goi `GET /api/novels/{id}` — do that tren
 * production 2026-09-25: tu duoi 1 giay toi hon 10 giay. Khong co tep nay thi
 * bam mot truyen o Thu vien, trang cu DUNG IM toi khi may chu xong: nguoi doc
 * khong biet minh da bam trung chua. Next hien khung nay NGAY LAP TUC (ranh
 * gioi Suspense cua route), cung bo cuc voi trang that nen khong nhay.
 */

export default function NovelLoading() {
  return (
    <div className="page novel-page" aria-busy="true">
      <nav aria-label="Đường dẫn">
        <span className="hint crumb">← Thư viện</span>
      </nav>
      <header className="novel-head" role="status" aria-label="Đang tải truyện">
        <div className="novel-head-cover">
          <div className="cover cover-portrait sk" />
        </div>
        <div className="stack-2 novel-head-body">
          <div className="sk nsk-line" style={{ width: 120, height: 22 }} />
          <div className="sk nsk-line" style={{ width: "80%", height: 34 }} />
          <div className="sk nsk-line" style={{ width: "55%" }} />
          <div className="row novel-head-actions">
            <div className="sk nsk-btn" />
            <div className="sk nsk-btn" style={{ width: 120 }} />
          </div>
          <div className="sk nsk-line" style={{ width: "92%" }} />
          <div className="sk nsk-line" style={{ width: "88%" }} />
          <div className="sk nsk-line" style={{ width: "60%" }} />
        </div>
      </header>
      <section className="stack" aria-hidden="true">
        <div className="sk nsk-line" style={{ width: 180, height: 24 }} />
        <div className="list list-gon">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="sk" style={{ height: 56 }} />
          ))}
        </div>
      </section>
    </div>
  );
}
