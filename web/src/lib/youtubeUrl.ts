/**
 * Phan tich URL YouTube phia TRINH DUYET — dung cho XEM TRUOC truoc khi gui
 * (Phase 2, animation-youtube-polish-v1). Day KHONG PHAI nguon su that: server
 * (`server/animation_domain.py::parse_youtube_id`) van la noi xac nhan cuoi
 * cung khi gui form — ham nay chi de hien thi anh dai dien/loi NGAY khi go,
 * tranh nguoi dung phai bam gui roi moi biet URL sai.
 *
 * PHAI khop CHINH XAC logic phia server (cung danh sach domain, cung thu tu
 * uu tien watch/youtu.be/embed-shorts-live/query `v`) — lech nhau se khien
 * xem truoc noi "hop le" nhung server tu choi, hoac nguoc lai.
 *
 * KHONG BAO GIO tai/goi mang toi YouTube o day — chi phan tich CHUOI.
 */

const YOUTUBE_ID_RE = /^[A-Za-z0-9_-]{11}$/;

const YOUTUBE_HOSTS = new Set([
  "youtube.com", "www.youtube.com", "m.youtube.com",
  "youtube-nocookie.com", "www.youtube-nocookie.com",
  "youtu.be", "www.youtu.be",
]);

export function parseYoutubeVideoId(raw: string): string | null {
  if (!raw) return null;
  const candidate = raw.trim();
  if (YOUTUBE_ID_RE.test(candidate)) return candidate;

  let parsed: URL;
  try {
    parsed = new URL(candidate.includes("//") ? candidate : `//${candidate}`, "https://placeholder.invalid");
  } catch {
    return null;
  }
  const host = parsed.hostname.toLowerCase();
  if (!YOUTUBE_HOSTS.has(host)) return null;

  if (host === "youtu.be" || host === "www.youtu.be") {
    const vid = parsed.pathname.replace(/^\/+/, "").split("/")[0] ?? "";
    return YOUTUBE_ID_RE.test(vid) ? vid : null;
  }

  const pathParts = parsed.pathname.split("/").filter(Boolean);
  if (pathParts.length > 1 && ["embed", "shorts", "live"].includes(pathParts[0])) {
    const vid = pathParts[1];
    return YOUTUBE_ID_RE.test(vid) ? vid : null;
  }

  const vidParam = parsed.searchParams.get("v");
  return vidParam && YOUTUBE_ID_RE.test(vidParam) ? vidParam : null;
}

export function youtubeThumbnailUrl(videoId: string): string {
  return `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
}

/** Domain iframe nhung DUY NHAT duoc phep — dung o test/CSP de xac nhan
    khong noi nao khac trong app tu tao mot nguon nhung khac. */
export const YOUTUBE_EMBED_ORIGIN = "https://www.youtube-nocookie.com";
