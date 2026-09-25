/**
 * Khung xuong trang chuong (Product UX Sprint 2).
 *
 * Trang chuong cho `getChapter` (~2 giay khi may chu khoe) roi cho muc luc toi
 * `CHO_DS_CHUONG_MS`. Khong co khung nay thi bam "Đọc tiếp" o Thu vien / trang
 * truyen, trang cu dung im trong luc do. Khung giu bo cuc cot doc (tieu de,
 * dong du kien, cac doan) nen chu that hien ra khong nhay.
 *
 * Trinh phat audio song o LAYOUT (`AudioEngine`), khong nam trong trang nay —
 * dang nghe roi sang chuong khac thi am thanh khong bi ngat boi khung nay.
 */

export default function ChapterLoading() {
  return (
    <div className="page reader-page-sk" aria-busy="true">
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <span className="hint crumb">← Về truyện</span>
      </nav>
      <header className="stack-2 reader-head" role="status" aria-label="Đang tải chương">
        <div className="sk nsk-line" style={{ width: "70%", height: 34 }} />
        <div className="sk nsk-line" style={{ width: "40%" }} />
        <div className="row" style={{ gap: 8 }}>
          <div className="sk nsk-btn" style={{ width: 110 }} />
          <div className="sk nsk-btn" style={{ width: 70 }} />
          <div className="sk nsk-btn" style={{ width: 110 }} />
        </div>
      </header>
      <div className="stack-2 reader-sk-text" aria-hidden="true">
        {[96, 92, 98, 64, 0, 95, 90, 97, 71, 0, 93, 88, 52].map((w, i) =>
          w ? (
            <div key={i} className="sk nsk-line" style={{ width: `${w}%` }} />
          ) : (
            <div key={i} style={{ height: 10 }} />
          ),
        )}
      </div>
    </div>
  );
}
