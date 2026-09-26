"use client";

/**
 * Cắt + phóng một ảnh trước khi lưu (avatar vuông / ảnh bìa 3:1).
 *
 * Kéo bằng chuột HOẶC ngón tay (Pointer Events, `touch-action: none` trên
 * khung), phóng bằng thanh trượt hoặc con lăn; bàn phím: mũi tên để kéo, +/-
 * để phóng — khung nhận tiêu điểm được. Ảnh luôn PHỦ KÍN khung (toán ở
 * `lib/profileImage.ts`), không bao giờ lưu ra một mép trống.
 *
 * Avatar hiện mặt nạ TRÒN — đúng hình người khác sẽ thấy ở bài đăng/bình luận.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  PHONG_TOI_DA,
  doiPhong,
  keo,
  khungDau,
  tiLePhu,
  xuatAnhCat,
  type AnhCat,
  type KhungCat,
} from "@/lib/profileImage";

export function ImageCropper({
  img,
  kieu,
  outW,
  outH,
  onDone,
  onCancel,
}: {
  img: HTMLImageElement;
  kieu: "avatar" | "banner";
  outW: number;
  outH: number;
  onDone: (anh: AnhCat) => void;
  onCancel: () => void;
}) {
  const khung = useRef<HTMLDivElement | null>(null);
  const [k, setK] = useState<KhungCat | null>(null);
  const [dangXuat, setDangXuat] = useState(false);
  const [loi, setLoi] = useState("");
  const keoTu = useRef<{ id: number; x: number; y: number } | null>(null);

  /* Do khung THAT tren man hinh (co gian theo be rong) roi dat khung dau. */
  useEffect(() => {
    const el = khung.current;
    if (!el) return;
    const dat = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w > 0 && h > 0) setK(khungDau(img.naturalWidth, img.naturalHeight, w, h));
    };
    dat();
    const ro = new ResizeObserver(dat);
    ro.observe(el);
    return () => ro.disconnect();
  }, [img]);

  const xong = useCallback(async () => {
    if (!k || dangXuat) return;
    setDangXuat(true);
    setLoi("");
    try {
      onDone(await xuatAnhCat(img, k, outW, outH));
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không xử lý được ảnh.");
    } finally {
      setDangXuat(false);
    }
  }, [k, dangXuat, img, outW, outH, onDone]);

  const s = k ? tiLePhu(k) * k.phong : 1;

  return (
    <div className={`cat-anh cat-anh-${kieu}`}>
      <div
        ref={khung}
        className="cat-anh-khung"
        role="application"
        tabIndex={0}
        aria-label={`Khung cắt ${kieu === "avatar" ? "ảnh đại diện" : "ảnh bìa"}. Kéo để di chuyển, mũi tên để dịch, dấu cộng trừ để phóng.`}
        onPointerDown={(e) => {
          if (!k) return;
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          keoTu.current = { id: e.pointerId, x: e.clientX, y: e.clientY };
        }}
        onPointerMove={(e) => {
          const t = keoTu.current;
          if (!t || t.id !== e.pointerId) return;
          const dx = e.clientX - t.x;
          const dy = e.clientY - t.y;
          keoTu.current = { id: e.pointerId, x: e.clientX, y: e.clientY };
          setK((cu) => (cu ? keo(cu, dx, dy) : cu));
        }}
        onPointerUp={() => {
          keoTu.current = null;
        }}
        onPointerCancel={() => {
          keoTu.current = null;
        }}
        onWheel={(e) => {
          setK((cu) => (cu ? doiPhong(cu, cu.phong * (e.deltaY < 0 ? 1.08 : 1 / 1.08)) : cu));
        }}
        onKeyDown={(e) => {
          const buoc = e.shiftKey ? 40 : 10;
          const map: Record<string, [number, number]> = {
            ArrowLeft: [buoc, 0],
            ArrowRight: [-buoc, 0],
            ArrowUp: [0, buoc],
            ArrowDown: [0, -buoc],
          };
          if (map[e.key]) {
            e.preventDefault();
            const [dx, dy] = map[e.key];
            setK((cu) => (cu ? keo(cu, dx, dy) : cu));
          } else if (e.key === "+" || e.key === "=") {
            e.preventDefault();
            setK((cu) => (cu ? doiPhong(cu, cu.phong + 0.1) : cu));
          } else if (e.key === "-") {
            e.preventDefault();
            setK((cu) => (cu ? doiPhong(cu, cu.phong - 0.1) : cu));
          }
        }}
      >
        {k ? (
          // eslint-disable-next-line @next/next/no-img-element -- anh blob cuc bo trong khung cat
          <img
            src={img.src}
            alt=""
            draggable={false}
            className="cat-anh-img"
            style={{ width: k.anhW * s, height: k.anhH * s, transform: `translate(${k.x}px, ${k.y}px)` }}
          />
        ) : null}
        {kieu === "avatar" ? <span className="cat-anh-mat-na" aria-hidden="true" /> : null}
      </div>

      <label className="cat-anh-phong">
        <span className="hint">Phóng to</span>
        <input
          type="range"
          min={1}
          max={PHONG_TOI_DA}
          step={0.01}
          value={k?.phong ?? 1}
          onChange={(e) => setK((cu) => (cu ? doiPhong(cu, Number(e.target.value)) : cu))}
          aria-label="Mức phóng"
        />
      </label>

      {loi ? (
        <p className="hint loi" role="alert">
          {loi}
        </p>
      ) : null}

      <div className="row cat-anh-nut">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
          Huỷ
        </button>
        <button type="button" className="btn btn-primary btn-sm" disabled={!k || dangXuat} onClick={() => void xong()}>
          {dangXuat ? "Đang xử lý…" : "Dùng ảnh này"}
        </button>
      </div>
    </div>
  );
}
