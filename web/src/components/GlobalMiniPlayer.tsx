"use client";

/**
 * Thanh phat nho, DOCKED, song xuyen MOI route.
 *
 * Mount MOT LAN trong `app/layout.tsx`, ben ngoai `{children}` — dieu huong
 * giua cac trang khong lam no unmount, va no dung CHUNG the `<audio>` voi
 * `AudioEngineProvider` (khong tao dong co phat thu hai).
 *
 * Thanh nay hien/an theo TUYEN DUONG. Tren chinh trang CHUONG dang phat
 * (`/chapters/[id]` — tu sprint doc/nghe 2026-09-24 la trang doc VA nghe
 * duy nhat; `/listen/[id]` chuyen huong ve do), trinh phat noi cua trang
 * (`reader/ChapterAudioDock`) + trinh phat lon o che do Nghe da lo lieu —
 * hien them thanh nay o do la HAI thanh cung noi mot chuyen. Moi noi KHAC
 * (`/library`, `/community`, `/account`, `/studio`, va trang cua MOT CHUONG
 * KHAC), day la giao dien DUY NHAT cho biet van co audio dang phat.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { useAudioEngine, dongHo } from "./AudioEngine";

export function GlobalMiniPlayer() {
  const { trangThai: t, dieuKhien: d, tieuDe } = useAudioEngine();
  const pathname = usePathname();

  /* Trang CHINH chuong dang phat da co trinh phat rieng — an thanh toan cuc
     de khong trung lap. `/listen/...` giu lai cho khoang khac truoc khi
     chuyen huong kip chay. Moi tuyen duong khac deu can, KE CA trang cua mot
     chuong KHAC (dang doc chuong 7 trong khi nghe chuong 5). */
  const oTrangNgheChuongNay =
    !!t.chapterId &&
    (pathname === `/chapters/${t.chapterId}` || pathname === `/listen/${t.chapterId}`);
  const hien = t.daBatDau && !t.loi && !oTrangNgheChuongNay;

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

        {/* Bam vao ten -> quay lai trang cua chuong dang phat (duong dan
            chinh tac `/chapters/[id]`). Phai DIEU HUONG, vi chuong dang phat
            khong o trang hien tai. Che do doc/nghe da nho trong cookie. */}
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
