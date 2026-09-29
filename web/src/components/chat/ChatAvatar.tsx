/**
 * Avatar trong tin nhan = `UserAvatar` (avatar FANFIC + khung suu tam DANG trang bi) — CUNG component voi
 * thanh dieu huong, bai dang, binh luan, ho so (#229 "one identity everywhere"): mot nguoi trong giong
 * NHAU o moi noi. Cap/danh xung = `CapDoTaiKhoan` (kieu gon), cung cho voi trang ca nhan.
 */
import { CapDoTaiKhoan } from "@/components/CapDoTaiKhoan";
import { UserAvatar } from "@/components/UserAvatar";
import type { ChatIdentity } from "@/lib/api";

export function tenHien(it: ChatIdentity | undefined): string {
  if (!it) return "…";
  if (!it.found) return "Người dùng không xác định";
  return it.display_name || it.username || "Người dùng Fanfic";
}

/** Chuoi danh xung cho aria/tieu de: "Lv. N · danh hieu" — cung thu tu voi `CapDoTaiKhoan`. */
export function danhXung(it: ChatIdentity | undefined): string | null {
  if (!it?.found || !it.level) return null;
  return it.equipped_title ? `Lv. ${it.level} · ${it.equipped_title}` : `Lv. ${it.level}`;
}

/** Dong cap/danh xung hien thi — `CapDoTaiKhoan` gon (nhu ho so cong khai: khong XP). */
export function ChatCapDo({ identity }: { identity: ChatIdentity | undefined }) {
  if (!identity?.found || !identity.level) return null;
  return <CapDoTaiKhoan level={identity.level} title={identity.equipped_title} />;
}

export function ChatAvatar({ identity, size = "md" }: { identity: ChatIdentity | undefined; size?: "sm" | "md" | "lg" }) {
  const la = !identity?.found;
  return (
    <span className={`chat-avt chat-avt-${size}`}>
      {/* Nguoi khong xac dinh: "?" trung tinh — khong phai chu cai dau cua dong "Nguoi dung khong xac dinh". */}
      <UserAvatar
        user={la ? { display_name: "?" } : {
          user_id: identity?.user_id ?? undefined,
          username: identity?.username,
          display_name: tenHien(identity),
          avatar_url: identity?.avatar_url,
        }}
        frame={la ? null : identity?.avatar_frame ?? null}
      />
    </span>
  );
}
