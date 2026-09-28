"use client";

/**
 * /messages — khong gian Tin nhan day du.
 *
 * DESKTOP: trai = danh sach hoi thoai, giua = cuoc tro chuyen, phai = thong
 *   tin nguoi kia (>=1200px).
 * DI DONG: danh sach; chon mot nguoi thi cuoc tro chuyen phu toan man hinh,
 *   o soan tin co dinh day man hinh. `?c=<userID chat>` nam tren URL nen nut
 *   Back/cu chi vuot cua trinh duyet tra ve danh sach dung nhu nguoi ta doi.
 *
 * Vao trang = nguoi dung CHU DONG mo tin nhan -> `moChat("messages-page")`.
 */
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";
import { EmptyState, Loading, PageHeader } from "@/components/ui";
import { CHAT_V1_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";
import { useChat } from "@/components/chat/ChatProvider";
import { ChatAvatar, ChatCapDo, tenHien } from "@/components/chat/ChatAvatar";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { ChatEmptyState } from "@/components/chat/ChatEmptyState";
import { ChatErrorState, ChatNetBanner } from "@/components/chat/ChatErrorState";
import { ChatThread, KhungCho } from "@/components/chat/ChatThread";
import { ChatThreadMenu } from "@/components/chat/ChatThreadMenu";
import { ChatUserHeader } from "@/components/chat/ChatUserHeader";
import { ConversationList } from "@/components/chat/ConversationList";

export default function MessagesPage() {
  return (
    <Suspense fallback={<div className="page"><Loading /></div>}>
      <KhongGianTinNhan />
    </Suspense>
  );
}

function KhongGianTinNhan() {
  const { profile, loading } = useSession();
  const { moChat, status, openThread, identityOf } = useChat();
  const params = useSearchParams();
  const router = useRouter();
  const peer = params.get("c");
  const daMoRef = useRef(false);
  const daMoPeerRef = useRef<string | null>(null);
  const tuDanhSachRef = useRef(false);
  const coNoiDung = status === "ready" || status === "reconnecting" || status === "offline";

  useEffect(() => {
    if (!profile || daMoRef.current) return;
    daMoRef.current = true;
    void moChat("messages-page");
  }, [profile, moChat]);

  useEffect(() => {
    if (!peer || !coNoiDung || daMoPeerRef.current === peer) return;
    daMoPeerRef.current = peer;
    openThread(peer);
  }, [peer, coNoiDung, openThread]);

  if (!CHAT_V1_ENABLED) {
    return (
      <div className="page">
        <PageHeader title="Tin nhắn" />
        <EmptyState icon="💬" title="Tin nhắn chưa mở" hint="Tính năng nhắn tin sẽ sớm có mặt trên Fanfic." />
      </div>
    );
  }
  if (loading) return <div className="page"><Loading /></div>;
  if (!profile) {
    return (
      <div className="page">
        <PageHeader title="Tin nhắn" />
        <EmptyState
          icon="💬"
          title="Cần đăng nhập"
          hint="Đăng nhập để nhắn tin với bạn đọc và tác giả khác."
          action={<Link href="/login?next=/messages" className="btn btn-primary" prefetch={false}>Đăng nhập</Link>}
        />
      </div>
    );
  }

  const it = peer ? identityOf(peer) : undefined;
  const ten = tenHien(it);
  const chon = (p: string) => {
    tuDanhSachRef.current = true;
    router.push(`/messages?c=${encodeURIComponent(p)}`);
  };
  const quayLai = () => {
    daMoPeerRef.current = null;
    if (tuDanhSachRef.current) router.back();
    else router.replace("/messages");
  };

  return (
    <div className="page chat-trang">
      <div className="chat-trang-dau">
        <h1 className="page-title">Tin nhắn</h1>
      </div>
      <div className={`chat-khong-gian${peer ? " chat-co-hoi-thoai" : ""}`}>
        <aside className="chat-cot chat-cot-ds" aria-label="Danh sách cuộc trò chuyện">
          <ChatErrorState status={status} />
          <ChatNetBanner status={status} />
          <ConversationList activePeerId={peer} onSelect={chon} />
        </aside>

        <section className="chat-cot chat-cot-tin" aria-label={peer ? `Trò chuyện với ${ten}` : "Cuộc trò chuyện"}>
          {peer ? (
            <>
              <div className="chat-cot-tin-dau">
                <button type="button" className="chat-nut chat-nut-lui" onClick={quayLai} aria-label="Quay lại danh sách">
                  <span aria-hidden="true">←</span>
                </button>
                <ChatUserHeader identity={it}>
                  {coNoiDung ? <ChatThreadMenu key={peer} peerId={peer} peerName={ten} /> : null}
                </ChatUserHeader>
              </div>
              <ChatNetBanner status={status} />
              {coNoiDung ? <ChatThread peerId={peer} /> : status === "connecting" ? <KhungCho /> : (
                <div className="chat-tin-hop chat-tin-hop-rong"><ChatErrorState status={status} /></div>
              )}
              {status === "error" || status === "kicked" ? null : (
                <ChatComposer peerId={peer} peerName={it?.found ? ten : undefined} autoFocus />
              )}
            </>
          ) : (
            <ChatEmptyState
              title="Chọn một cuộc trò chuyện"
              hint="Tin nhắn chỉ hai người trong cuộc trò chuyện nhìn thấy."
            />
          )}
        </section>

        <aside className="chat-cot chat-cot-ttin" aria-label="Thông tin người trò chuyện">
          {peer && it ? (
            <div className="chat-ttin">
              <ChatAvatar identity={it} size="lg" />
              <strong className="chat-ttin-ten">{ten}</strong>
              {it.found && it.username ? <span className="hint">@{it.username}</span> : null}
              <ChatCapDo identity={it} />
              {it.found && it.username ? (
                <Link href={`/u/${it.username}`} className="btn btn-outline btn-sm" prefetch={false}>
                  Xem hồ sơ
                </Link>
              ) : null}
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
