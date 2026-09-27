/**
 * Avatar trong tin nhan = avatar FANFIC (anh tu tai len hoac chu cai dau)
 * boc khung suu tam dang trang bi — cung hai thanh phan voi `/u/[username]`
 * va bang xep hang, de mot nguoi trong giong NHAU o moi noi.
 */
import { Avatar } from "@/components/Avatar";
import { CosmeticFrame } from "@/components/cosmetics/Cosmetics";
import type { ChatIdentity } from "@/lib/api";

export function tenHien(it: ChatIdentity | undefined): string {
  if (!it) return "…";
  if (!it.found) return "Người dùng không xác định";
  return it.display_name || it.username || "Người dùng Fanfic";
}

export function ChatAvatar({ identity, size = "md" }: { identity: ChatIdentity | undefined; size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`chat-avt chat-avt-${size}`}>
      <CosmeticFrame cosmetic={identity?.found ? identity.avatar_frame ?? null : null}>
        <Avatar name={tenHien(identity)} avatarUrl={identity?.found ? identity.avatar_url : null} className="avatar" />
      </CosmeticFrame>
    </span>
  );
}
