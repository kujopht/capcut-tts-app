"use client";

/**
 * Trình xem ảnh nhẹ cho bài đăng — một hộp thoại, không phải một trang.
 *
 * BÀN PHÍM là công dân hạng nhất: Escape đóng, mũi tên trái/phải chuyển ảnh,
 * tiêu điểm vào hộp khi mở và TRẢ VỀ nút đã mở khi đóng (không có bước trả
 * này thì người dùng bàn phím rơi về `<body>` và mất chỗ đứng — cùng quy tắc
 * với mọi hộp thoại khác của app).
 *
 * Không zoom, không xoay, không tải gốc: đây là ảnh minh hoạ một bài đăng,
 * không phải một kho ảnh.
 */

import { useCallback, useEffect, useRef } from "react";

export function ImageLightbox({
  urls,
  index,
  onIndex,
  onClose,
}: {
  urls: string[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const hop = useRef<HTMLDivElement | null>(null);
  /** Phần tử giữ tiêu điểm TRƯỚC khi mở — trả về đúng nó khi đóng. */
  const truoc = useRef<HTMLElement | null>(null);

  const dong = useCallback(() => {
    onClose();
    truoc.current?.focus();
  }, [onClose]);

  useEffect(() => {
    truoc.current = document.activeElement as HTMLElement | null;
    hop.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        dong();
      } else if (e.key === "ArrowRight" && urls.length > 1) {
        e.preventDefault();
        onIndex((index + 1) % urls.length);
      } else if (e.key === "ArrowLeft" && urls.length > 1) {
        e.preventDefault();
        onIndex((index + urls.length - 1) % urls.length);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [index, urls.length, onIndex, dong]);

  return (
    <div className="lop-phu" role="presentation" onClick={dong}>
      <div
        className="xem-anh"
        role="dialog"
        aria-modal="true"
        aria-label={`Ảnh ${index + 1} trên ${urls.length}`}
        tabIndex={-1}
        ref={hop}
        onClick={(e) => e.stopPropagation()}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={urls[index]} alt="" />
        <div className="row xem-anh-day">
          {urls.length > 1 ? (
            <>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label="Ảnh trước"
                onClick={() => onIndex((index + urls.length - 1) % urls.length)}
              >
                ←
              </button>
              <span className="hint">
                {index + 1} / {urls.length}
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label="Ảnh sau"
                onClick={() => onIndex((index + 1) % urls.length)}
              >
                →
              </button>
            </>
          ) : null}
          <button type="button" className="btn btn-sm" onClick={dong}>
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
