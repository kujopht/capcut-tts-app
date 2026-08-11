"use client";

/**
 * Khối bình luận của trang đọc chương.
 *
 * MỘT nút "Bình luận (N)" gấp/mở được, đứng ngay dưới trình phát — KHÔNG phải
 * hàng trăm bình luận chen trước phần chữ. Việc đọc phải yên tĩnh: người mở
 * trang này để đọc/nghe chương, và cuộc trò chuyện là thứ họ GHÉ vào, không
 * phải thứ chắn đường.
 *
 * Mặc định: desktop MỞ (màn đủ rộng, khối đứng cạnh không đè lên gì), mobile
 * GẤP (mỗi pixel dọc là một đoạn văn bị đẩy xuống). Quyết định một lần lúc
 * mount — không nhảy qua lại khi xoay máy giữa chừng.
 *
 * Con số trên nút lấy từ CHÍNH trang đầu của danh sách (`total` của API) —
 * không có endpoint đếm riêng để lệch với nội dung thật.
 */

import { useEffect, useState } from "react";
import { ApiError, social, type ServerLimits } from "@/lib/api";
import { CommentThread } from "@/components/CommentThread";

export function ChapterComments({ chapterId }: { chapterId: string }) {
  const [mo, setMo] = useState(false);
  const [daQuyetDinh, setDaQuyetDinh] = useState(false);
  const [tong, setTong] = useState<number | null>(null);
  const [limits, setLimits] = useState<ServerLimits | null>(null);
  const [an, setAn] = useState(false);

  /* Mac dinh theo be rong man hinh, quyet dinh MOT lan. Trong effect vi
     `window` khong ton tai luc render tren may chu. */
  useEffect(() => {
    if (daQuyetDinh) return;
    queueMicrotask(() => {
      setMo(window.innerWidth >= 900);
      setDaQuyetDinh(true);
    });
  }, [daQuyetDinh]);

  /* Con so cho nut gap — mot trang dau, chi de dem. Loi ==> AN ca khoi:
     chuong nhap tra 404, va mot khoi binh luan tren ban nhap cua chinh tac
     gia chi gay hieu lam (binh luan cong khai chi co o truyen da xuat ban). */
  useEffect(() => {
    let huy = false;
    social
      .chapterComments(chapterId, "moi", 1, 0)
      .then((r) => {
        if (!huy) setTong(r.total);
      })
      .catch((e) => {
        if (huy) return;
        if (e instanceof ApiError && e.status === 404) setAn(true);
        else setTong(0);
      });
    return () => {
      huy = true;
    };
  }, [chapterId]);

  useEffect(() => {
    social.limits().then(setLimits).catch(() => {});
  }, []);

  if (an) return null;

  return (
    <section className="card binh-luan-chuong" aria-label="Bình luận chương">
      <button
        type="button"
        className="binh-luan-chuong-nut"
        aria-expanded={mo}
        onClick={() => setMo((v) => !v)}
      >
        <span aria-hidden="true">💬</span>
        <strong>
          Bình luận{tong !== null ? ` (${tong})` : ""}
        </strong>
        <span className="hint binh-luan-chuong-mui" aria-hidden="true">
          {mo ? "▲" : "▼"}
        </span>
      </button>

      {mo && daQuyetDinh ? (
        <CommentThread
          postId={chapterId}
          targetKind="chapter"
          limits={limits}
          placeholder="Bạn nghĩ gì về chương này?"
          onCountChange={(delta) =>
            setTong((t) => Math.max(0, (t ?? 0) + delta))
          }
        />
      ) : null}
    </section>
  );
}
