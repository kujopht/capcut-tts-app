/**
 * Dau cuoc tro chuyen: avatar + ten + "✦ danh hieu · Lv. N" (cung dong voi
 * trang ca nhan). Bam vao la mo HO SO FANFIC (`/u/username`) — khong bao gio
 * mot trang ho so cua Tencent.
 */
import Link from "next/link";
import type { ChatIdentity } from "@/lib/api";
import { ChatAvatar, danhXung, tenHien } from "./ChatAvatar";

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
  const phu = danhXung(identity);
  const than = (
    <>
      <ChatAvatar identity={identity} size="md" />
      <span className="chat-uh-chu">
        <strong id={titleId} className="chat-uh-ten truncate">{ten}</strong>
        {phu ? <span className="hint chat-uh-phu truncate">{phu}</span> : null}
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
