"use client";

/**
 * Thanh phat nho dinh o day man hinh.
 *
 * KHONG co the `<audio>` rieng. No doc cung mot `useAudioEngine()` voi trinh
 * phat lon o dau trang, nen bam dung o day thi trinh phat tren cung dung theo
 * — chung la mot.
 *
 * CHI hien khi ca hai dieu cung dung:
 *   1. nguoi dung DA tung bam phat — mot thanh dieu khien noi len khi chua ai
 *      nghe gi la mot thanh cong cu thua;
 *   2. trinh phat lon da cuon khuat — con nhin thay no thi thanh nay chi lam
 *      hai cho cung noi mot chuyen.
 *
 * Dieu kien (2) do `IntersectionObserver` tra loi, khong phai do `scrollY`:
 * chieu cao dau trang doi theo do dai ten chuong, nen mot con so pixel co dinh
 * se sai o dung nhung chuong co ten dai.
 */

import { useEffect, useRef, useState } from "react";
import { useAudioEngine, dongHo } from "./AudioEngine";

export function MiniPlayer({
  /** Phan tu can theo doi — chinh la trinh phat lon. */
  moc,
}: {
  moc: React.RefObject<HTMLElement | null>;
}) {
  const { trangThai: t, dieuKhien: d, tieuDe } = useAudioEngine();
  const [khuat, setKhuat] = useState(false);
  const nut = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const el = moc.current;
    if (!el) return;
    const theo_doi = new IntersectionObserver(
      ([muc]) => setKhuat(!muc.isIntersecting),
      { rootMargin: "-72px 0px 0px 0px" },
    );
    theo_doi.observe(el);
    return () => theo_doi.disconnect();
  }, [moc]);

  const hien = t.daBatDau && khuat && !t.loi;

  /*
    Chua cho o cuoi trang khi thanh nay noi len.

    No la `position: fixed` nen khong chiem cho trong luong — khong chua thi no
    de len 66px cuoi cung cua trang, va dong cuoi chan trang bi khuat vinh vien
    du cuon het co.

    Dat lop tren `<body>` vi day la thu duy nhat bao trum ca `<main>` lan
    `<footer>`; ca hai deu nam ngoai cay React cua trang nay.
  */
  useEffect(() => {
    document.body.classList.toggle("co-mini", hien);
    return () => document.body.classList.remove("co-mini");
  }, [hien]);

  if (!hien) return null;

  const ty_le = t.thoiLuong > 0 ? (t.thoiDiem / t.thoiLuong) * 100 : 0;

  return (
    <div className="mini" role="region" aria-label="Trình phát thu gọn">
      <div className="wrap mini-wrap">
        {/* `is-playing` cung dieu khien quang cua ca thanh — xem `.mini:has()`
            o `globals.css`. Dung thi thanh nay lui ve lam mot vach lang. */}
        <button
          ref={nut}
          type="button"
          className={`play-btn play-btn-sm${t.dangPhat ? " is-playing" : ""}`}
          onClick={d.batTat}
          aria-label={t.dangPhat ? "Tạm dừng" : "Phát"}
        >
          <span className="play-glyph" aria-hidden="true">
            {t.dangPhat ? "❚❚" : "▶"}
          </span>
        </button>

        {/*
          Bam vao ten thi cuon nguoc len trinh phat lon. La `<button>` that,
          khong phai `<div onClick>`: ban phim toi duoc va trinh doc man hinh
          doc ra dung la mot nut.
        */}
        <button
          type="button"
          className="mini-title"
          onClick={() =>
            moc.current?.scrollIntoView({ behavior: "smooth", block: "center" })
          }
        >
          <span className="truncate">{tieuDe}</span>
          <span className="hint mono mini-time">
            {dongHo(t.thoiDiem)} / {dongHo(t.thoiLuong)}
          </span>
        </button>

        <input
          className="seek mini-seek"
          type="range"
          min={0}
          max={t.thoiLuong || 0}
          step={1}
          value={Math.min(t.thoiDiem, t.thoiLuong || 0)}
          disabled={!t.thoiLuong}
          onChange={(e) => d.tua(Number(e.target.value))}
          aria-label="Vị trí phát"
          aria-valuetext={`${dongHo(t.thoiDiem)} trên ${dongHo(t.thoiLuong)}`}
          style={{ "--p": `${ty_le}%` } as React.CSSProperties}
        />
      </div>

      {/* Vach tien do mong sat mep tren — doc duoc ca khi thanh truot bi thu
          hep o dien thoai. */}
      <div className="mini-bar" aria-hidden="true">
        <div className="mini-bar-fill" style={{ width: `${ty_le}%` }} />
      </div>
    </div>
  );
}
