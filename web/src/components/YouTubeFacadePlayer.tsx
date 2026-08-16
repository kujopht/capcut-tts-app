"use client";

/**
 * Trinh phat FACADE cho mot video YouTube (overnight Phase 5, V6, Phan 5C).
 *
 * VAN DE: nhung mot iframe YouTube ngay khi trang tai xong nghia la trinh
 * duyet nguoi xem tai ve toan bo script theo doi/quang cao cua YouTube TRUOC
 * ca khi ho quyet dinh co xem hay khong.
 *
 * CACH LAM: hien GIAO DIEN CUA FANFIC truoc (anh dai dien tinh + nut Play) —
 * iframe CHI duoc dung vao DOM sau khi nguoi dung bam Play. Day la ly do
 * component nay khong bao gio render `<iframe>` truoc khi `daBam` la `true`.
 *
 * KHONG lam gi vuot qua muc do nay:
 * - Dung `youtube-nocookie.com`, KHONG dung `youtube.com/embed` — mien it
 *   theo doi hon cho nguoi CHUA bam Play (van la YouTube sau khi da bam).
 * - Truyen `origin` DUNG voi `window.location.origin` — tai lieu IFrame API
 *   hien tai yeu cau tham so nay khop de postMessage hoat dong dung.
 * - KHONG dung `modestbranding` (tham so cu, YouTube da ngung tuan thu no
 *   hoan toan tren giao dien nhung).
 * - KHONG phu CSS len tren iframe DANG PHAT de che ten kenh/tieu de/logo/nut
 *   dieu khien — do la vi pham dieu khoan nhung YouTube, va component nay CO
 *   Y khong lam vay: sau khi bam Play, do la giao dien THAT CUA YOUTUBE.
 */

import { useState } from "react";
import { IconPlay } from "@/components/Icons";
import { YOUTUBE_EMBED_ORIGIN, youtubeThumbnailUrl } from "@/lib/youtubeUrl";

export { youtubeThumbnailUrl };

export function YouTubeFacadePlayer({
  videoId,
  title,
  autoPlay = true,
  iframeId,
  onPlay,
}: {
  videoId: string;
  title: string;
  /** Tu phat NGAY sau khi nguoi dung bam Play (khong tu phat truoc do). */
  autoPlay?: boolean;
  /**
   * `id` gan cho `<iframe>` — CHI can khi trang muon dieu khien qua YouTube
   * IFrame API sau nay (vi du bao cao tien do xem, Phan 5I). Bo qua thi
   * component van la mot trinh phat facade day du, chi khong dieu khien
   * duoc tu ben ngoai.
   */
  iframeId?: string;
  onPlay?: () => void;
}) {
  const [daBam, setDaBam] = useState(false);

  if (daBam) {
    const goc =
      typeof window !== "undefined" ? window.location.origin : "";
    const params = new URLSearchParams({
      autoplay: autoPlay ? "1" : "0",
      rel: "0",
      ...(iframeId ? { enablejsapi: "1" } : {}),
      ...(goc ? { origin: goc } : {}),
    });
    return (
      <div className="yt-facade">
        <iframe
          id={iframeId}
          src={`https://www.youtube-nocookie.com/embed/${videoId}?${params.toString()}`}
          title={title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
        />
      </div>
    );
  }

  return (
    // `.yt-facade` PHAI la mot phan tu RIENG bao ngoai `.yt-facade-play`,
    // khong duoc gop chung mot the: `.yt-facade` la `position: relative`
    // (khung neo), con `.yt-facade-play` la `position: absolute; inset: 0`
    // (lop phu vua khit). Gop ca hai lop vao MOT the khien thuoc tinh
    // `position` tren cung mot phan tu bi `.yt-facade-play` de len sau trong
    // stylesheet ghi de mat `position: relative` cua `.yt-facade` — luc do
    // nut Play mat neo, tu nhay ra ngoai theo khoi cha xa nhat co dat
    // `transform` (moi trang `.page` deu co, qua animation vao-trang), phu
    // kin ca tieu de/dieu huong tap nam phia tren trong flow binh thuong.
    <div className="yt-facade">
      <button
        type="button"
        className="yt-facade-play"
        onClick={() => {
          setDaBam(true);
          onPlay?.();
        }}
        aria-label={`Phát ${title}`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- anh tu YouTube,
            khong phai asset cua Fanfic; next/image doi cau hinh domain rieng
            cho mot the hien duy nhat khong dang. */}
        <img src={youtubeThumbnailUrl(videoId)} alt="" />
        <span className="yt-facade-play-icon">
          <IconPlay size={28} />
        </span>
      </button>
    </div>
  );
}
