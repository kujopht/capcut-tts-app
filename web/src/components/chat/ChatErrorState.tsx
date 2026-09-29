"use client";

/**
 * Trang thai loi/ket noi CUA CHAT — moi ma loi mot cau NOI THAT, kem dung hanh
 * dong lam duoc. Khong bao gio mot khung trong im lang, khong bao gio "Có lỗi
 * xảy ra" chung chung.
 */
import Link from "next/link";
import type { ChatErrorCode, ChatStatus, KickReason } from "@/lib/chat/types";
import { useChat } from "./ChatProvider";
import { ChatEmptyState } from "./ChatEmptyState";

const CAU_LOI: Record<ChatErrorCode, { title: string; hint: string }> = {
  not_configured: {
    title: "Tin nhắn chưa được bật",
    hint: "Máy chủ Fanfic World chưa cấu hình dịch vụ tin nhắn. Đây không phải lỗi của bạn.",
  },
  unauthorized: {
    title: "Phiên đăng nhập đã hết hạn",
    hint: "Đăng nhập lại để dùng tin nhắn.",
  },
  rate_limited: {
    title: "Bạn mở tin nhắn quá nhiều lần",
    hint: "Chờ vài phút rồi thử lại.",
  },
  network: {
    title: "Không kết nối được máy chủ",
    hint: "Kiểm tra kết nối mạng rồi thử lại.",
  },
  sdk_load: {
    title: "Không tải được thành phần tin nhắn",
    hint: "Có thể mạng đang chặn tệp tải về. Thử lại sau giây lát.",
  },
  login: {
    title: "Không đăng nhập được dịch vụ tin nhắn",
    hint: "Dịch vụ tin nhắn từ chối phiên này. Thử lại; nếu vẫn lỗi, hãy tải lại trang.",
  },
  expired: {
    title: "Phiên tin nhắn đã hết hạn",
    hint: "Không làm mới được phiên. Thử lại để kết nối lại.",
  },
};

const CAU_BI_DAY: Record<KickReason, string> = {
  multi_instance: "Tin nhắn đang mở ở một tab khác của trình duyệt này.",
  multi_device: "Tài khoản của bạn vừa mở tin nhắn trên một thiết bị khác.",
  session_expired: "Phiên tin nhắn đã hết hạn.",
  server: "Máy chủ đã đóng phiên tin nhắn này.",
  unknown: "Phiên tin nhắn ở tab này đã bị đóng.",
};

/** Tra `null` khi khong co gi can bao (dang san sang / chua mo). */
export function ChatErrorState({ status, compact = false }: { status: ChatStatus; compact?: boolean }) {
  const { errorCode, kickReason, thuLai, dungOTabNay } = useChat();

  if (status === "connecting") {
    return (
      <div className={`chat-trang-thai${compact ? " chat-trang-thai-gon" : ""}`} role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" /> Đang kết nối tin nhắn…
      </div>
    );
  }
  if (status === "kicked") {
    return (
      <ChatEmptyState icon="🔁" title="Tin nhắn đang mở ở nơi khác"
        hint={`${CAU_BI_DAY[kickReason ?? "unknown"]} Mỗi lúc chỉ một nơi nhận tin nhắn.`}>
        <button type="button" className="btn btn-primary btn-sm" onClick={dungOTabNay}>
          Dùng tin nhắn ở tab này
        </button>
      </ChatEmptyState>
    );
  }
  if (status === "error" && errorCode) {
    const c = CAU_LOI[errorCode];
    return (
      <ChatEmptyState icon="⚠️" title={c.title} hint={c.hint}>
        {errorCode === "unauthorized" ? (
          <Link href="/login?next=/messages" className="btn btn-primary btn-sm" prefetch={false}>
            Đăng nhập
          </Link>
        ) : errorCode === "not_configured" ? null : (
          <button type="button" className="btn btn-secondary btn-sm" onClick={thuLai}>
            Thử lại
          </button>
        )}
      </ChatEmptyState>
    );
  }
  return null;
}

/** Dai trang thai mong phia tren o soan tin khi mat mang/dang noi lai. */
export function ChatNetBanner({ status }: { status: ChatStatus }) {
  if (status === "offline") {
    return <div className="chat-mang chat-mang-mat" role="status">Mất kết nối mạng — tin nhắn sẽ gửi được khi có mạng trở lại.</div>;
  }
  if (status === "reconnecting") {
    return <div className="chat-mang" role="status"><span className="spinner" aria-hidden="true" /> Đang kết nối lại…</div>;
  }
  return null;
}
