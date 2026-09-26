"use client";

/**
 * Một bản audio ĐÃ TẠO XONG trong "Audio gần đây" của Audio Studio
 * (Social & Play V1).
 *
 * Chỉ bản `completed` có mặt ở đây (`/api/video-studio/audio-library` chỉ trả
 * track đã có tệp) — một job thất bại không bao giờ thành một thẻ "thành công".
 *
 * Nói THẬT, không có trình phát giả:
 *   * thời lượng là con số máy chủ đo được (`duration_seconds`), không phải
 *     "0:00 / --:--" trong lúc chưa bấm phát;
 *   * giọng hiển thị bằng đúng tên trong sổ đăng ký (kể cả bí danh Ngọc Huyền);
 *   * liên kết tải chỉ xin khi người dùng bấm — N thẻ không còn là N yêu cầu ký
 *     URL ngay lúc mở trang.
 *
 * Phát qua ĐỘNG CƠ ÂM THANH TOÀN CỤC (một chủ sở hữu tiếng đọc), không thêm
 * thẻ `<audio>` nào.
 */

import Link from "next/link";
import { useState } from "react";
import type { VideoAudioChoice, Voice } from "@/lib/api";
import { audioFileName, resolveAudio } from "@/lib/audio";
import { errorMessage } from "@/lib/session";
import { voiceOptionLabel } from "@/lib/voices";
import { khiNao } from "@/lib/time";
import { dongHo, useAudioEngine } from "@/components/AudioEngine";

export function RecentAudioCard({ a, voices }: { a: VideoAudioChoice; voices: Voice[] }) {
  const engine = useAudioEngine();
  const [dangLayTai, setDangLayTai] = useState(false);
  const [loi, setLoi] = useState("");
  const laBaiNay = engine?.trangThai?.chapterId === a.chapter_id;
  const dangPhat = laBaiNay && Boolean(engine?.trangThai?.dangPhat);
  const thoiDiem = laBaiNay ? engine?.trangThai?.thoiDiem ?? 0 : 0;
  const giong = voices.find((v) => v.voice_id === a.voice_id);
  const tenGiong = giong ? voiceOptionLabel(giong) : a.voice_id;
  const thoiLuong = a.duration_seconds > 0 ? dongHo(a.duration_seconds) : "";
  const tieuDe = a.chapter_title || "Bản audio";

  const taiXuong = async () => {
    if (dangLayTai) return;
    setDangLayTai(true);
    setLoi("");
    try {
      const r = await resolveAudio(a.chapter_id);
      const link = document.createElement("a");
      link.href = r.downloadUrl;
      link.download = audioFileName(tieuDe);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) {
      setLoi(errorMessage(e));
    } finally {
      setDangLayTai(false);
    }
  };

  return (
    <article className="audio-item audio-gan-day" aria-labelledby={`au-${a.track_id}`}>
      <div className="audio-gan-day-chu">
        <strong id={`au-${a.track_id}`} className="audio-gan-day-ten">
          {tieuDe}
        </strong>
        <span className="hint audio-gan-day-meta">
          {tenGiong} · {khiNao(a.created_at)}
          {thoiLuong ? ` · ${thoiLuong}` : null}
        </span>
        {laBaiNay ? (
          <span className="hint" role="status">
            {dangPhat ? "Đang phát" : "Tạm dừng"} · {dongHo(thoiDiem)}
            {thoiLuong ? ` / ${thoiLuong}` : null}
          </span>
        ) : null}
        {loi ? (
          <span className="trang-thai-loi" role="alert">
            {loi}
          </span>
        ) : null}
      </div>
      <div className="audio-gan-day-nut">
        <button
          type="button"
          className="btn btn-sm btn-primary"
          aria-label={dangPhat ? `Tạm dừng: ${tieuDe}` : `Phát: ${tieuDe}`}
          onClick={() => (laBaiNay ? engine?.dieuKhien.batTat() : engine?.dieuKhien.phat(a.chapter_id, tieuDe, { tuPhat: true }))}
        >
          {dangPhat ? "⏸ Tạm dừng" : "▶ Phát"}
        </button>
        <button
          type="button"
          className="btn btn-sm"
          disabled={dangLayTai}
          onClick={() => void taiXuong()}
          aria-label={`Tải MP3: ${tieuDe}`}
        >
          {dangLayTai ? "Đang lấy…" : "⬇ Tải MP3"}
        </button>
        <Link className="btn btn-sm btn-ghost" href={`/studio/media?audio=${encodeURIComponent(a.track_id)}`} prefetch={false}>
          Chỉnh với video
        </Link>
      </div>
    </article>
  );
}
