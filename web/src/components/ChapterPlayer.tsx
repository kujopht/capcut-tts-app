"use client";

/**
 * Trinh phat lon o dau trang doc chuong.
 *
 * Ban truoc la mot the `<audio controls>` mac dinh dat trong mot hop nho: no
 * hoat dong, nhung khong noi duoc dang nghe CAI GI, va trong nhu mot tien ich
 * cam vao trang chu khong phai mot phan cua truyen.
 *
 * O day: bia truyen, ten chuong, ten truyen, mot nut phat LON, roi thanh thoi
 * gian. Nut phat la thu to nhat va sang nhat trong ca khoi — day la viec chinh
 * cua trang nay.
 *
 * KHONG tu phat. Trinh duyet chan tu dong phat khi chua co tuong tac, va tu
 * phat mot chuong truyen khi nguoi ta vua mo trang la mot hanh vi tho lo.
 */

import { useAudioEngine, dongHo, TOC_DO } from "./AudioEngine";
import { NovelCover } from "./NovelCover";
import { formatBytes } from "./ui";

export function ChapterPlayer({
  novelId,
  novelTitle,
  coverUrl,
  chapterTitle,
}: {
  novelId: string;
  novelTitle: string;
  coverUrl?: string | null;
  chapterTitle: string;
}) {
  const { trangThai: t, dieuKhien: d } = useAudioEngine();

  if (t.loi) {
    return (
      <div className="alert alert-error" role="alert">
        <span aria-hidden="true">⛔</span>
        <span>{t.loi}</span>
      </div>
    );
  }

  const chua_the_bam = t.dangTai || !t.tep;
  const ty_le = t.thoiLuong > 0 ? (t.thoiDiem / t.thoiLuong) * 100 : 0;

  return (
    <section className="listen-hero" aria-label="Nghe chương này">
      {/* Bia du chua co anh that: lop du phong sinh tu ten truyen, va o co
          nay no du to de trong nhu mot bia that chu khong phai o dem. */}
      <div className="listen-hero-cover">
        <NovelCover
          novelId={novelId}
          title={novelTitle}
          coverUrl={coverUrl}
          size="card"
        />
      </div>

      <div className="listen-hero-body">
        <span className="eyebrow">Đang nghe</span>
        <h2 className="listen-hero-title">{chapterTitle}</h2>
        <p className="hint listen-hero-novel">{novelTitle}</p>

        <div className="listen-controls">
          <button
            type="button"
            className="play-btn"
            onClick={d.batTat}
            disabled={chua_the_bam}
            aria-label={t.dangPhat ? "Tạm dừng" : "Phát"}
          >
            {chua_the_bam ? (
              <span className="spinner" aria-hidden="true" />
            ) : (
              <span className="play-glyph" aria-hidden="true">
                {t.dangPhat ? "❚❚" : "▶"}
              </span>
            )}
          </button>

          <div className="listen-track">
            {/*
              `<input type=range>` chu khong phai mot thanh tu ve: mui ten
              trai/phai tua duoc, trinh doc man hinh doc ra dung la mot thanh
              truot, va gia tri co don vi. Mot `<div>` gan `onClick` khong lam
              duoc thu nao trong so do.
            */}
            <input
              className="seek"
              type="range"
              min={0}
              max={t.thoiLuong || 0}
              step={1}
              value={Math.min(t.thoiDiem, t.thoiLuong || 0)}
              disabled={chua_the_bam || !t.thoiLuong}
              onChange={(e) => d.tua(Number(e.target.value))}
              aria-label="Vị trí phát"
              aria-valuetext={`${dongHo(t.thoiDiem)} trên ${dongHo(t.thoiLuong)}`}
              // Ty le da phat, de CSS to phan ben trai nut truot. La gia tri
              // dong nen phai di qua `style` — giong `<ProgressBar>`.
              style={{ "--p": `${ty_le}%` } as React.CSSProperties}
            />
            <div className="listen-times">
              {/* Thoi gian la CHU, khong chi la do dai mot thanh mau. */}
              <span className="mono">{dongHo(t.thoiDiem)}</span>
              <span className="mono hint">{dongHo(t.thoiLuong)}</span>
            </div>
          </div>
        </div>

        <div className="listen-extra">
          <label className="listen-speed">
            <span className="hint">Tốc độ</span>
            <select
              className="select select-mini"
              value={t.tocDo}
              onChange={(e) => d.datTocDo(Number(e.target.value))}
              disabled={chua_the_bam}
              aria-label="Tốc độ phát"
            >
              {TOC_DO.map((v) => (
                <option key={v} value={v}>
                  {v}×
                </option>
              ))}
            </select>
          </label>

          <label className="listen-vol">
            <span className="hint" aria-hidden="true">
              🔊
            </span>
            <input
              className="vol"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={t.amLuong}
              onChange={(e) => d.datAmLuong(Number(e.target.value))}
              aria-label="Âm lượng"
              aria-valuetext={`${Math.round(t.amLuong * 100)} phần trăm`}
              style={{ "--p": `${t.amLuong * 100}%` } as React.CSSProperties}
            />
          </label>

          <span className="spacer" />

          {t.tep ? (
            <a
              className="btn btn-sm"
              href={t.tep.downloadUrl}
              download={t.tenTep}
            >
              <span aria-hidden="true">⬇</span> Tải MP3
              <span className="hint"> · {formatBytes(t.tep.sizeBytes)}</span>
            </a>
          ) : null}
        </div>

        {/*
          Mot dong chu noi dang o trang thai nao. Thanh mau va nut co doi hinh,
          nhung ca hai deu la tin hieu THI GIAC — dong nay la thu trinh doc man
          hinh doc ra, va cung la thu nguoi khong phan biet duoc mau van hieu.
        */}
        <p className="hint" role="status">
          {t.dangTai
            ? "Đang lấy liên kết audio…"
            : t.daXong
              ? "Đã nghe hết chương."
              : t.dangPhat
                ? `Đang phát · ${Math.round(ty_le)}%`
                : t.daBatDau
                  ? "Đang tạm dừng."
                  : t.sanSang
                    ? "Sẵn sàng phát."
                    : "Đang chuẩn bị…"}
        </p>
      </div>
    </section>
  );
}
