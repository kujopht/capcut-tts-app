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

/**
 * Dong danh xung — CUNG THU TU voi trang ca nhan (`/u/[username]`):
 * "✦ {danh hieu} · Lv. {bac}". Mot nguoi phai doc giong nhau o moi noi.
 */
export function danhXung(it: ChatIdentity | undefined): string | null {
  if (!it?.found || !it.level) return null;
  return it.equipped_title ? `✦ ${it.equipped_title} · Lv. ${it.level}` : `Lv. ${it.level}`;
}

export function ChatAvatar({ identity, size = "md" }: { identity: ChatIdentity | undefined; size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`chat-avt chat-avt-${size}`}>
      <CosmeticFrame cosmetic={identity?.found ? identity.avatar_frame ?? null : null}>
        {/* Nguoi khong xac dinh: "?" trung tinh — khong phai chu cai dau cua dong "Nguoi dung khong xac dinh". */}
        <Avatar name={identity && !identity.found ? "?" : tenHien(identity)}
          avatarUrl={identity?.found ? identity.avatar_url : null} className="avatar" />
      </CosmeticFrame>
    </span>
  );
}
