"use client";

/**
 * Nút tim truyện — bản sao của `FollowButton` cho lượt thích.
 *
 * Giữ đúng ba điều không hiển nhiên của nút gốc:
 *
 * 1. `aria-pressed` chứ không đổi nhãn thành trạng thái.
 * 2. Cập nhật LẠC QUAN, hoàn lại khi lỗi; con số của MÁY CHỦ thắng phép đoán.
 * 3. Chưa đăng nhập thì DẪN TỚI đăng nhập, không hiện lỗi 401.
 *
 * Khác nút theo dõi ở một điểm: tim KHÔNG gửi thông báo cho tác giả, nên
 * nút này không hứa hẹn gì ngoài con số.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import { ApiError, social } from "@/lib/api";
import { useSession } from "@/lib/session";
import { loginHref } from "@/lib/nav";
import { formatNumber } from "@/components/ui";

export function LikeButton({
  targetId,
  initialLiked,
  initialCount,
  phu = false,
  onChange,
}: {
  targetId: string;
  initialLiked: boolean;
  initialCount?: number;
  /**
   * Nút PHỤ (viền, không tim đặc) — dùng khi cạnh đó đã có một hành động
   * chính, vd trang truyện: "Đọc tiếp" mới là việc chính.
   */
  phu?: boolean;
  onChange?: (liked: boolean, count: number) => void;
}) {
  const nutChinh = phu ? "btn btn-outline btn-sm" : "btn btn-primary btn-sm";
  const { profile } = useSession();
  const pathname = usePathname();
  const [daTim, setDaTim] = useState(initialLiked);
  const [so, setSo] = useState(initialCount ?? 0);
  const [dangGoi, setDangGoi] = useState(false);
  const [loi, setLoi] = useState("");

  const bam = useCallback(async () => {
    if (dangGoi) return;
    const truoc = daTim;
    const soTruoc = so;
    // Lạc quan: đổi ngay, hoàn lại nếu máy chủ từ chối.
    setDaTim(!truoc);
    setSo(Math.max(0, soTruoc + (truoc ? -1 : 1)));
    setLoi("");
    setDangGoi(true);
    try {
      const ra = truoc
        ? await social.unlikeStory(targetId)
        : await social.likeStory(targetId);
      // Con số của MÁY CHỦ thắng phép đoán lạc quan.
      setDaTim(ra.liked);
      setSo(ra.like_count);
      onChange?.(ra.liked, ra.like_count);
    } catch (e) {
      setDaTim(truoc);
      setSo(soTruoc);
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setDangGoi(false);
    }
  }, [dangGoi, daTim, so, targetId, onChange]);

  if (!profile) {
    return (
      <Link className={nutChinh} href={loginHref(pathname)} prefetch={false}>
        ❤ Tim
      </Link>
    );
  }

  return (
    <span className="theo-doi">
      <button
        type="button"
        className={daTim ? "btn btn-ghost btn-sm dang-theo-doi" : nutChinh}
        aria-pressed={daTim}
        disabled={dangGoi}
        onClick={bam}
      >
        {daTim ? "❤ Đã tim" : "❤ Tim"}
      </button>
      {initialCount === undefined ? null : (
        <span className="hint theo-doi-so">{formatNumber(so)}</span>
      )}
      {loi ? (
        <span className="hint loi" role="status">
          {loi}
        </span>
      ) : null}
    </span>
  );
}
