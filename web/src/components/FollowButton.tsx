"use client";

/**
 * Nút theo dõi — dùng cho cả NGƯỜI và TRUYỆN.
 *
 * MỘT thành phần cho hai đối tượng, vì hành vi giao diện giống hệt nhau: một
 * nút hai trạng thái, một con số bên cạnh, và một lần gọi mạng có thể thất bại.
 * Hai bảng dữ liệu tách biệt ở backend (`user_follows` / `story_follows`) là một
 * quyết định về TRUY VẤN, không phải về giao diện.
 *
 * BA điều không hiển nhiên:
 *
 * 1. `aria-pressed` chứ không phải đổi nhãn.
 *
 *    Nút giữ nhãn "Theo dõi" và mang `aria-pressed`. Trình đọc màn hình đọc ra
 *    "Theo dõi, đã bật" — rõ ràng hơn một nút tự đổi thành "Đang theo dõi", vì
 *    với nhãn đổi thì người dùng không biết nhãn đang mô tả TRẠNG THÁI HIỆN TẠI
 *    hay HÀNH ĐỘNG SẼ XẢY RA.
 *
 * 2. Cập nhật LẠC QUAN, và hoàn lại khi lỗi.
 *
 *    Chờ mạng xong mới đổi nút làm cú bấm cảm giác nặng. Đổi ngay rồi hoàn lại
 *    nếu máy chủ từ chối thì cú bấm nhẹ, và trường hợp thất bại vẫn trung thực.
 *
 * 3. Chưa đăng nhập thì DẪN TỚI đăng nhập, không phải hiện lỗi.
 *
 *    Một nút bấm vào rồi báo 401 là một cái bẫy. Đường dẫn mang theo `next` để
 *    người dùng quay về đúng chỗ họ đang đứng.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import { ApiError, social } from "@/lib/api";
import { useSession } from "@/lib/session";
import { loginHref } from "@/lib/nav";
import { formatNumber } from "@/components/ui";

export function FollowButton({
  kind,
  targetId,
  initialFollowing,
  initialCount,
  compact = false,
  label = "Theo dõi",
  onChange,
}: {
  kind: "user" | "story";
  targetId: string;
  initialFollowing: boolean;
  initialCount?: number;
  compact?: boolean;
  label?: string;
  onChange?: (following: boolean, count: number) => void;
}) {
  const { profile } = useSession();
  const pathname = usePathname();
  const [dangTheoDoi, setDangTheoDoi] = useState(initialFollowing);
  const [so, setSo] = useState(initialCount ?? 0);
  const [dangGoi, setDangGoi] = useState(false);
  const [loi, setLoi] = useState("");

  const bam = useCallback(async () => {
    if (dangGoi) return;
    const truoc = dangTheoDoi;
    const soTruoc = so;
    // Lạc quan: đổi ngay, hoàn lại nếu máy chủ từ chối.
    setDangTheoDoi(!truoc);
    setSo(Math.max(0, soTruoc + (truoc ? -1 : 1)));
    setLoi("");
    setDangGoi(true);
    try {
      const goi =
        kind === "user"
          ? truoc
            ? social.unfollowUser(targetId)
            : social.followUser(targetId)
          : truoc
            ? social.unfollowStory(targetId)
            : social.followStory(targetId);
      const ra = await goi;
      // Con số của MÁY CHỦ thắng phép đoán lạc quan: nếu người khác vừa theo
      // dõi cùng lúc, con số thật đã khác.
      setDangTheoDoi(ra.following);
      setSo(ra.follower_count);
      onChange?.(ra.following, ra.follower_count);
    } catch (e) {
      setDangTheoDoi(truoc);
      setSo(soTruoc);
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setDangGoi(false);
    }
  }, [dangGoi, dangTheoDoi, so, kind, targetId, onChange]);

  if (!profile) {
    return (
      <Link
        className={compact ? "btn btn-ghost btn-sm" : "btn btn-primary btn-sm"}
        href={loginHref(pathname)}
      >
        {label}
      </Link>
    );
  }

  return (
    <span className="theo-doi">
      <button
        type="button"
        className={
          dangTheoDoi
            ? "btn btn-ghost btn-sm dang-theo-doi"
            : "btn btn-primary btn-sm"
        }
        aria-pressed={dangTheoDoi}
        disabled={dangGoi}
        onClick={bam}
      >
        {dangTheoDoi ? "Đang theo dõi" : label}
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
