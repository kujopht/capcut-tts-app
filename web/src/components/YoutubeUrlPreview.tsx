"use client";

/**
 * Xem truoc URL YouTube TRUOC KHI GUI form (Phan 2, animation-youtube-polish-v1).
 *
 * Dung `parseYoutubeVideoId` (client-side, xem `lib/youtubeUrl.ts`) CHI de
 * phan hoi ngay khi go — server (`parse_youtube_id`) van la noi xac nhan
 * cuoi cung luc gui. KHONG tai/goi mang toi YouTube: anh dai dien la mot the
 * <img> tro thang toi `i.ytimg.com`, trinh duyet tu tai, component nay khong
 * proxy hay download gi ca.
 *
 * Rong (`url` chua go gi) thi khong hien gi — tranh doa nguoi dung bang loi
 * ngay khi mo form.
 */

import { parseYoutubeVideoId, youtubeThumbnailUrl } from "@/lib/youtubeUrl";

export function YoutubeUrlPreview({ url }: { url: string }) {
  const raw = url.trim();
  if (!raw) return null;

  const videoId = parseYoutubeVideoId(raw);
  if (!videoId) {
    return (
      <p className="hint" role="alert" style={{ color: "var(--danger)" }}>
        Không đọc được ID video YouTube từ đường dẫn này.
      </p>
    );
  }

  return (
    <div className="row row-tight yt-url-preview">
      {/* eslint-disable-next-line @next/next/no-img-element -- anh tu YouTube,
          khong phai asset cua Fanfic. */}
      <img
        src={youtubeThumbnailUrl(videoId)}
        alt=""
        width={120}
        height={68}
        className="yt-url-preview-thumb"
      />
      <span className="hint">Đã nhận diện video, ID: {videoId}</span>
    </div>
  );
}
