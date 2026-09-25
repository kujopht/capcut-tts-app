"use client";

/**
 * TRINH PHAT NOI cua trang chuong — mot thanh dinh o day man hinh, doc va
 * dieu khien CUNG mot `useAudioEngine()` voi trinh phat lon o dau che do
 * Nghe. KHONG co the `<audio>` nao o day.
 *
 * Hai hinh dang, do NGUOI DUNG chon (va nho qua cookie cung che do doc):
 *   - day du: bia, ten chuong, ⏮ ↺10 ▶ 10↻ ⏭, thanh tua, toc do, "Theo giọng
 *     đọc", "Ẩn/Hiện truyện chữ", nut thu nho;
 *   - thu nho: mot vien nho (nut phat + ten + gio) — chu chiem gan het man
 *     hinh, trinh phat van o do.
 *
 * Thu nho / mo rong KHONG bao gio dung audio — ca hai chi la lop ve.
 *
 * Dien thoai: CSS xep lai thanh ba hang cho ngon cai (thanh tua tren cung, nut
 * dieu khien 44px o giua, ten + cong tac o duoi), chua `safe-area-inset-bottom`.
 */

import { forwardRef } from "react";
import { dongHo, TOC_DO, BUOC_TUA, useAudioEngine } from "@/components/AudioEngine";
import { NovelCover } from "@/components/NovelCover";
import {
  IconBack10,
  IconChevronDown,
  IconChevronUp,
  IconFollow,
  IconForward10,
  IconNextChapter,
  IconPrevChapter,
  IconTextHide,
  IconTextShow,
} from "@/components/Icons";

export interface ChapterAudioDockProps {
  novelId: string;
  novelTitle: string;
  coverUrl?: string | null;
  chapterTitle: string;
  /** Engine dang giu CHINH chuong nay. `false` = chua nap (bam phat se nap). */
  laBaiNay: boolean;
  thuNho: boolean;
  onThuNho: (v: boolean) => void;
  /** Phat/tam dung theo nghia cua TRANG (nap chuong neu can). */
  onPhat: () => void;
  coTruoc: boolean;
  coSau: boolean;
  onTruoc: () => void;
  onSau: () => void;
  theoBat: boolean;
  onTheo: () => void;
  /** Co cot chu de theo/an/hien khong (chuong chi co audio thi khong). */
  coChu: boolean;
  hienChu: boolean;
  onHienChu: (v: boolean) => void;
  /** Vi tri doan dang doc la UOC LUONG (chuong khong co phu de). */
  uocLuong: boolean;
}

export const ChapterAudioDock = forwardRef<HTMLDivElement, ChapterAudioDockProps>(
  function ChapterAudioDock(p, ref) {
    const { trangThai: t, dieuKhien: d } = useAudioEngine();
    const cua = p.laBaiNay;
    const dangPhat = cua && t.dangPhat;
    const thoiDiem = cua ? t.thoiDiem : 0;
    const thoiLuong = cua ? t.thoiLuong : 0;
    const dangTai = cua && t.dangTai;
    const ty_le = thoiLuong > 0 ? Math.min(1, thoiDiem / thoiLuong) : 0;
    const coTheTua = cua && !!t.tep && thoiLuong > 0;
    const loi = cua ? t.loi : "";

    const trangThaiChu = loi
      ? loi
      : dangTai
        ? "Đang lấy liên kết audio…"
        : cua && t.daXong
          ? "Đã nghe hết chương."
          : dangPhat
            ? // KHONG kem gio: dong nay la `role="status"` (vung doc to), doi
              // moi giay la trinh doc man hinh doc lien tuc. Gio nam o thanh tua.
              "Đang phát."
            : cua && t.daBatDau
              ? "Đang tạm dừng."
              : "Sẵn sàng phát.";

    const nutPhat = (
      <button
        type="button"
        className={`play-btn dock-play${dangPhat ? " is-playing" : ""}`}
        onClick={p.onPhat}
        disabled={dangTai}
        aria-label={dangPhat ? "Tạm dừng" : "Phát"}
        aria-keyshortcuts="k"
        title={dangPhat ? "Tạm dừng (K)" : "Phát (K)"}
      >
        {dangTai ? (
          <span className="spinner" aria-hidden="true" />
        ) : (
          <span className="play-glyph" aria-hidden="true">
            {dangPhat ? "❚❚" : "▶"}
          </span>
        )}
      </button>
    );

    const vach = (
      <div className="dock-bar" aria-hidden="true">
        <div className="dock-bar-fill" style={{ transform: `scaleX(${ty_le})` }} />
      </div>
    );

    if (p.thuNho) {
      return (
        <div
          ref={ref}
          className="dock dock-mini"
          role="region"
          aria-label="Trình phát chương (thu gọn)"
          data-khong-tinh-cuon=""
        >
          {vach}
          {nutPhat}
          <button type="button" className="dock-mini-title" onClick={() => p.onThuNho(false)}>
            <span className="truncate">{cua && t.daBatDau ? p.chapterTitle : "Nghe chương này"}</span>
            <span className="hint mono dock-mini-time">
              {cua && thoiLuong > 0 ? `${dongHo(thoiDiem)} / ${dongHo(thoiLuong)}` : p.novelTitle}
            </span>
          </button>
          <button
            type="button"
            className="dock-icon-btn"
            onClick={() => p.onThuNho(false)}
            aria-label="Mở rộng trình phát"
            title="Mở rộng trình phát"
          >
            <IconChevronUp size={18} />
          </button>
          <p className="sr-only" role="status">{trangThaiChu}</p>
        </div>
      );
    }

    return (
      <div ref={ref} className="dock" role="region" aria-label="Trình phát chương" data-khong-tinh-cuon="">
        {vach}
        <div className="dock-info">
          <div className="dock-cover" aria-hidden="true">
            <NovelCover novelId={p.novelId} title={p.novelTitle} coverUrl={p.coverUrl} size="card" />
          </div>
          <div className="dock-titles">
            <strong className="truncate dock-title">{p.chapterTitle}</strong>
            <span className="hint truncate dock-novel">{p.novelTitle}</span>
          </div>
        </div>

        <div className="dock-controls" role="group" aria-label="Điều khiển phát">
          <button
            type="button"
            className="dock-icon-btn"
            onClick={p.onTruoc}
            disabled={!p.coTruoc}
            aria-label="Chương trước"
            title="Chương trước"
          >
            <IconPrevChapter size={18} />
          </button>
          <button
            type="button"
            className="dock-icon-btn"
            onClick={() => d.tuaTuongDoi(-BUOC_TUA)}
            disabled={!coTheTua}
            aria-label="Lùi 10 giây"
            aria-keyshortcuts="j"
            title="Lùi 10 giây (J)"
          >
            <IconBack10 size={22} />
          </button>
          {nutPhat}
          <button
            type="button"
            className="dock-icon-btn"
            onClick={() => d.tuaTuongDoi(BUOC_TUA)}
            disabled={!coTheTua}
            aria-label="Tới 10 giây"
            aria-keyshortcuts="l"
            title="Tới 10 giây (L)"
          >
            <IconForward10 size={22} />
          </button>
          <button
            type="button"
            className={`dock-icon-btn${cua && t.daXong && p.coSau ? " is-cta" : ""}`}
            onClick={p.onSau}
            disabled={!p.coSau}
            aria-label="Chương sau"
            title="Chương sau"
          >
            <IconNextChapter size={18} />
          </button>
        </div>

        <div className="dock-seek">
          <span className="mono hint dock-time">{dongHo(thoiDiem)}</span>
          {/*
            `<input type=range>` that: mui ten trai/phai tua duoc, Home/End nhay
            dau/cuoi, trinh doc man hinh doc ra la mot thanh truot kem gio.
          */}
          <input
            className="seek dock-seek-range"
            type="range"
            min={0}
            max={thoiLuong || 0}
            step={1}
            value={Math.min(thoiDiem, thoiLuong || 0)}
            disabled={!coTheTua}
            onChange={(e) => d.tua(Number(e.target.value))}
            aria-label="Vị trí phát"
            aria-valuetext={`${dongHo(thoiDiem)} trên ${dongHo(thoiLuong)}`}
            style={{ "--p": `${ty_le * 100}%` } as React.CSSProperties}
          />
          <span className="mono hint dock-time">{dongHo(thoiLuong)}</span>
        </div>

        <div className="dock-tools">
          <select
            className="select select-mini dock-speed"
            value={t.tocDo}
            onChange={(e) => d.datTocDo(Number(e.target.value))}
            aria-label="Tốc độ phát"
            title="Tốc độ phát"
          >
            {TOC_DO.map((v) => (
              <option key={v} value={v}>
                {v}×
              </option>
            ))}
          </select>
          {p.coChu ? (
            <>
              <button
                type="button"
                className={`dock-chip${p.theoBat ? " is-on" : ""}`}
                onClick={p.onTheo}
                aria-pressed={p.theoBat}
                // Ten doc duoc KHONG phu thuoc nhan chu: man hep an nhan (chi
                // con bieu tuong), va `display: none` cung xoa nhan khoi cay
                // tiep can.
                aria-label="Theo giọng đọc"
                disabled={!p.hienChu}
                title={
                  p.uocLuong
                    ? "Tự cuộn tới đoạn đang đọc. Vị trí đoạn được ước lượng theo độ dài chữ."
                    : "Tự cuộn tới đoạn đang đọc"
                }
              >
                <IconFollow size={16} />
                <span className="dock-chip-label">Theo giọng đọc</span>
              </button>
              <button
                type="button"
                className="dock-chip"
                onClick={() => p.onHienChu(!p.hienChu)}
                aria-label={p.hienChu ? "Ẩn truyện chữ" : "Hiện truyện chữ"}
                title={p.hienChu ? "Ẩn truyện chữ" : "Hiện truyện chữ"}
              >
                {p.hienChu ? <IconTextHide size={16} /> : <IconTextShow size={16} />}
                <span className="dock-chip-label">{p.hienChu ? "Ẩn truyện chữ" : "Hiện truyện chữ"}</span>
              </button>
            </>
          ) : null}
          <button
            type="button"
            className="dock-icon-btn"
            onClick={() => p.onThuNho(true)}
            aria-label="Thu nhỏ trình phát"
            title="Thu nhỏ trình phát"
          >
            <IconChevronDown size={18} />
          </button>
        </div>

        {loi ? (
          <p className="dock-error" role="alert">
            <span aria-hidden="true">⛔</span> {loi}
          </p>
        ) : (
          <p className="sr-only" role="status">{trangThaiChu}</p>
        )}
      </div>
    );
  },
);
