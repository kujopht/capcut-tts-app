"use client";

/**
 * Khối bình luận của trang xem tập Animation (V6, overnight Phase 5) — Y HỆT
 * `ChapterComments` (cùng nút gấp/mở, cùng lý do mặc định desktop mở/mobile
 * gấp), chỉ khác ĐÍCH gọi API. Xem docstring `ChapterComments` để biết đầy đủ
 * lý do thiết kế — không lặp lại ở đây.
 */

import { useEffect, useState } from "react";
import { ApiError, social, type ServerLimits } from "@/lib/api";
import { CommentThread } from "@/components/CommentThread";

export function EpisodeComments({ episodeId }: { episodeId: string }) {
  const [mo, setMo] = useState(false);
  const [daQuyetDinh, setDaQuyetDinh] = useState(false);
  const [tong, setTong] = useState<number | null>(null);
  const [limits, setLimits] = useState<ServerLimits | null>(null);
  const [an, setAn] = useState(false);

  useEffect(() => {
    if (daQuyetDinh) return;
    queueMicrotask(() => {
      setMo(window.innerWidth >= 900);
      setDaQuyetDinh(true);
    });
  }, [daQuyetDinh]);

  useEffect(() => {
    let huy = false;
    social
      .episodeComments(episodeId, "moi", 1, 0)
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
  }, [episodeId]);

  useEffect(() => {
    social.limits().then(setLimits).catch(() => {});
  }, []);

  if (an) return null;

  return (
    <section className="card binh-luan-chuong" aria-label="Bình luận tập">
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
          postId={episodeId}
          targetKind="animation_episode"
          limits={limits}
          placeholder="Bạn nghĩ gì về tập này?"
          onCountChange={(delta) =>
            setTong((t) => Math.max(0, (t ?? 0) + delta))
          }
        />
      ) : null}
    </section>
  );
}
