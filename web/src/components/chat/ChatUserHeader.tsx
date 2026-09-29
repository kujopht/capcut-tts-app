/**
 * Dau cuoc tro chuyen: avatar + khung + ten + cap/danh xung (`CapDoTaiKhoan`, cung dong voi trang ca nhan).
 * Bam vao la mo HO SO FANFIC (`/u/username`). KHONG co cham "dang hoat dong": may chu chua co trang thai
 * truc tuyen that — hien mot cham doan la noi doi nguoi dung.
 */
import Link from "next/link";
import type { ChatIdentity } from "@/lib/api";
import { ChatAvatar, ChatCapDo, tenHien } from "./ChatAvatar";

export function ChatUserHeader({
  identity,
  titleId,
  children,
}: {
  identity: ChatIdentity | undefined;
  titleId?: string;
  children?: React.ReactNode;
}) {
  const ten = tenHien(identity);
  const hoSo = identity?.found && identity.username ? `/u/${identity.username}` : null;
  const than = (
    <>
      <ChatAvatar identity={identity} size="md" />
      <span className="chat-uh-chu">
        <strong id={titleId} className="chat-uh-ten truncate">{ten}</strong>
        <span className="chat-uh-phu truncate"><ChatCapDo identity={identity} /></span>
      </span>
    </>
  );
  return (
    <div className="chat-uh">
      {hoSo ? (
        <Link href={hoSo} className="chat-uh-nguoi" prefetch={false} title={`Xem hồ sơ của ${ten}`}>
          {than}
        </Link>
      ) : (
        <span className="chat-uh-nguoi">{than}</span>
      )}
      {children ? <span className="chat-uh-nut">{children}</span> : null}
    </div>
  );
}
