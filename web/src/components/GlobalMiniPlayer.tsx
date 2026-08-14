"use client";

/**
 * Thanh phat nho, DOCKED, song xuyen MOI route.
 *
 * Mount MOT LAN trong `app/layout.tsx`, ben ngoai `{children}` — dieu huong
 * giua cac trang khong lam no unmount, va no dung CHUNG the `<audio>` voi
 * `AudioEngineProvider` (khong tao dong co phat thu hai).
 *
 * Khac voi `MiniPlayer.tsx` (thanh nho O TRONG trang doc chuong, hien/an
 * theo VI TRI CUON cua trinh phat lon): thanh nay hien/an theo TUYEN DUONG.
 * Tren chinh trang doc chuong dang phat, `ChapterPlayer` (to) + `MiniPlayer`
 * (theo cuon) da lo lieu — hien them thanh nay o do la trung lap. Moi noi
 * KHAC (`/fanfic`, `/community`, `/account`, `/write`...), day la giao dien
 * DUY NHAT cho biet van co audio dang phat.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { useAudioEngine, dongHo } from "./AudioEngine";

export function GlobalMiniPlayer() {
  const { trangThai: t, dieuKhien: d, tieuDe } = useAudioEngine();
  const pathname = usePathname();

  /* Trang doc CHINH chuong nay da co ChapterPlayer + MiniPlayer rieng cua
     no — an thanh toan cuc de khong trung lap. Moi tuyen duong khac deu can. */
  const oTrangDocChuongNay =
    !!t.chapterId && pathname === `/chapters/${t.chapterId}`;
  const hien = t.daBatDau && !t.loi && !oTrangDocChuongNay;

  /* Chua cho o cuoi trang khi thanh nay noi len — cung ly do voi
     `MiniPlayer.tsx`: `position: fixed` khong chiem cho trong luong. */
  useEffect(() => {
    document.body.classList.toggle("co-mini", hien);
    return () => document.body.classList.remove("co-mini");
  }, [hien]);

  if (!hien) return null;

  const ty_le = t.thoiLuong > 0 ? (t.thoiDiem / t.thoiLuong) * 100 : 0;

  return (
    <div className="mini" role="region" aria-label="Trình phát thu gọn">
      <div className="wrap mini-wrap">
        <button
          type="button"
          className={`play-btn play-btn-sm${t.dangPhat ? " is-playing" : ""}`}
          onClick={d.batTat}
          aria-label={t.dangPhat ? "Tạm dừng" : "Phát"}
        >
          <span className="play-glyph" aria-hidden="true">
            {t.dangPhat ? "❚❚" : "▶"}
          </span>
        </button>

        {/* Bam vao ten -> quay lai trang doc chuong dang phat. Khac
            `MiniPlayer.tsx` (cuon trong CUNG trang): o day phai DIEU HUONG,
            vi chuong dang phat khong con o trang hien tai. */}
        <Link href={`/chapters/${t.chapterId}`} className="mini-title">
          <span className="truncate">{tieuDe}</span>
          <span className="hint mono mini-time">
            {dongHo(t.thoiDiem)} / {dongHo(t.thoiLuong)}
          </span>
        </Link>

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

      <div className="mini-bar" aria-hidden="true">
        <div className="mini-bar-fill" style={{ width: `${ty_le}%` }} />
      </div>
    </div>
  );
}
