"use client";

/**
 * Avatar + khung sưu tầm ĐANG TRANG BỊ — MỘT component cho mọi nơi hiện một
 * người: thanh điều hướng, bài đăng, bình luận, hồ sơ, sảnh game, bảng xếp
 * hạng (Social & Play V1).
 *
 * Trước đây mỗi nơi tự ghép `<CosmeticFrame><Avatar/></CosmeticFrame>` và tự
 * lọc `slot === "avatar_frame"` — bài đăng thì quên ghép, nên cùng một người có
 * khung ở bình luận mà không có khung ở bài viết. Đổi khung trong trình sửa hồ
 * sơ phải hiện GIỐNG NHAU ở mọi nơi; muốn vậy thì chỉ được có một chỗ vẽ.
 *
 * Khung chỉ là TRANG TRÍ: không chặn chữ, không nhận chuột (xem
 * `.cosmetic-frame-svg` trong globals.css), không đổi kích thước ô avatar.
 */

import Link from "next/link";
import type { CosmeticItem } from "@/lib/api";
import { hoSoHref } from "@/lib/communityFeed";
import { Avatar } from "@/components/Avatar";
import { CosmeticFrame } from "@/components/cosmetics/Cosmetics";

export interface NguoiHienThi {
  user_id?: string;
  username?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  equipped_cosmetics?: CosmeticItem[] | null;
}

export function khungDangDeo(u: NguoiHienThi | null | undefined): CosmeticItem | null {
  return u?.equipped_cosmetics?.find((c) => c.slot === "avatar_frame") ?? null;
}

export function tenHienThi(u: NguoiHienThi | null | undefined, duPhong = "Người dùng"): string {
  return u?.display_name || u?.username || duPhong;
}

export function UserAvatar({
  user,
  className = "avatar",
  link = false,
  /** Ghi đè khung (xem trước trong trình sửa hồ sơ). `undefined` = khung đang đeo. */
  frame,
}: {
  user: NguoiHienThi | null | undefined;
  className?: string;
  link?: boolean;
  frame?: CosmeticItem | null;
}) {
  const ten = tenHienThi(user, "?");
  const khung = frame === undefined ? khungDangDeo(user) : frame;
  const hinh = (
    <CosmeticFrame cosmetic={khung}>
      <Avatar name={ten} avatarUrl={user?.avatar_url} className={className} />
    </CosmeticFrame>
  );
  const href = link ? hoSoHref(user) : "";
  if (!href) return hinh;
  return (
    <Link href={href} className="user-avatar-link" aria-label={`Hồ sơ của ${ten}`}>
      {hinh}
    </Link>
  );
}
