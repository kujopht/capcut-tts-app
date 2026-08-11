"use client";

/**
 * Chuông thông báo trên thanh điều hướng.
 *
 * BA quyết định, và lý do của từng cái:
 *
 * 1. CHỈ hỏi con số, không hỏi danh sách, cho tới khi người dùng bấm.
 *
 *    Cái chuông này có mặt ở MỌI trang. Nếu nó tải cả danh sách thì mỗi lần đổi
 *    trang là một truy vấn kèm phép tra hồ sơ cho từng người gây ra thông báo —
 *    trong khi phần lớn thời gian con số là 0 và không ai mở nó ra.
 *
 * 2. KHÔNG polling theo chu kỳ.
 *
 *    Một `setInterval(30s)` trông vô hại, nhưng nó là một truy vấn mỗi ba mươi
 *    giây cho MỖI tab đang mở của MỖI người dùng — kể cả tab bị bỏ quên hai ngày
 *    ở một cửa sổ nền. Con số được làm mới khi người dùng đổi trang và khi họ mở
 *    bảng, và đó là hai lúc họ thực sự nhìn vào nó. Thời gian thực cần WebSocket,
 *    và đó là một dự án riêng.
 *
 * 3. Ẩn hoàn toàn khi chưa đăng nhập.
 *
 *    Một cái chuông luôn trống dẫn tới trang đăng nhập là một lời mời rỗng.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, social, type Notification } from "@/lib/api";
import { useSession } from "@/lib/session";
import { khiNao } from "@/lib/time";

/** Câu mô tả cho từng loại. Người gây ra được ghép vào trước. */
function moTa(n: Notification): string {
  switch (n.kind) {
    case "follow":
      return "đã theo dõi bạn";
    case "post_like":
      return "đã thích bài của bạn";
    case "post_comment":
      return "đã bình luận bài của bạn";
    case "comment_reply":
      return "đã trả lời bình luận của bạn";
    case "story_chapter":
      return "vừa đăng chương mới";
    case "author_approved":
      return "Đơn tác giả của bạn đã được duyệt";
    case "author_rejected":
      return "Đơn tác giả của bạn chưa được duyệt";
    default:
      return "có hoạt động mới";
  }
}

/** Thông báo hệ thống không có người gây ra, nên không có tên ai ở đầu câu. */
function laHeThong(n: Notification): boolean {
  return n.kind === "author_approved" || n.kind === "author_rejected";
}

/** Nơi bấm vào thông báo sẽ dẫn tới. */
function dichDen(n: Notification): string {
  if (laHeThong(n)) return "/creator/apply";
  switch (n.subject_kind) {
    case "post":
      return `/posts/${n.subject_id}`;
    case "comment":
      // Bình luận nằm trong một bài; backend cho `subject_id` là comment_id nên
      // trang bài đăng tự cuộn tới nó qua neo `#`.
      return `/notifications#${n.subject_id}`;
    case "novel":
      return `/novels/${n.subject_id}`;
    case "user":
      return n.actor?.username ? `/u/${n.actor.username}` : "/notifications";
    default:
      return "/notifications";
  }
}

export function NotificationBell() {
  const { profile } = useSession();
  const pathname = usePathname();
  const [chuaDoc, setChuaDoc] = useState(0);
  const [mo, setMo] = useState(false);
  const [ds, setDs] = useState<Notification[] | null>(null);
  const hop = useRef<HTMLDivElement | null>(null);
  const nut = useRef<HTMLButtonElement | null>(null);

  const dong = useCallback(() => setMo(false), []);

  /*
    Làm mới con số khi đổi trang. `pathname` trong danh sách phụ thuộc chính là
    cơ chế đó — không cần thêm một bộ đếm nào.

    Lỗi ở đây KHÔNG hiện ra: một con số không tải được thì cái chuông chỉ đơn
    giản là không có dấu, và đó là thứ nhỏ hơn nhiều so với một thông báo lỗi đỏ
    trên thanh điều hướng của mọi trang.
  */
  useEffect(() => {
    // KHONG dat lai `chuaDoc` o day: thanh phan nay tra `null` khi chua dang
    // nhap, nen con so do khong bao gio duoc ve. Mot `setState` dong bo trong
    // than effect chi de sua mot gia tri khong ai thay la mot vong ve thua —
    // va quy tac `react-hooks/set-state-in-effect` cam dieu do, co ly.
    if (!profile) return;
    let huy = false;
    social
      .unreadCount()
      .then((r) => {
        if (!huy) setChuaDoc(r.unread);
      })
      .catch(() => {});
    return () => {
      huy = true;
    };
  }, [profile, pathname]);

  /* Đóng khi bấm ra ngoài, và Escape trả tiêu điểm về nút mở — nếu không, tiêu
     điểm rơi về `<body>` và người dùng bàn phím mất chỗ đứng. */
  useEffect(() => {
    if (!mo) return;
    const onDown = (e: MouseEvent) => {
      if (!hop.current?.contains(e.target as Node)) dong();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      dong();
      nut.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [mo, dong]);

  const moBang = useCallback(() => {
    setMo((v) => !v);
    if (ds !== null) return;
    social
      .notifications(false, 8)
      .then((r) => {
        setDs(r.items);
        setChuaDoc(r.unread);
      })
      .catch((e) => {
        // Danh sách rỗng + một dòng nói rõ, thay vì một bảng trống im lặng.
        setDs([]);
        if (e instanceof ApiError) setChuaDoc(0);
      });
  }, [ds]);

  const docHet = useCallback(() => {
    social
      .markAllRead()
      .then((r) => {
        setChuaDoc(r.unread);
        setDs((truoc) =>
          truoc ? truoc.map((n) => ({ ...n, read: true })) : truoc,
        );
      })
      .catch(() => {});
  }, []);

  if (!profile) return null;

  return (
    <div className="menu" ref={hop}>
      <button
        ref={nut}
        type="button"
        className="bell"
        aria-haspopup="menu"
        aria-expanded={mo}
        /* Nhãn kèm con số: người dùng trình đọc màn hình cần biết CÓ BAO NHIÊU,
           không chỉ là "có thông báo". */
        aria-label={
          chuaDoc > 0 ? `Thông báo, ${chuaDoc} chưa đọc` : "Thông báo"
        }
        onClick={moBang}
      >
        <span aria-hidden="true">🔔</span>
        {chuaDoc > 0 ? (
          <span className="bell-dot" aria-hidden="true">
            {chuaDoc > 9 ? "9+" : chuaDoc}
          </span>
        ) : null}
      </button>
      {mo ? (
        <div className="menu-panel bell-panel" role="menu" aria-label="Thông báo">
          <div className="bell-head">
            <strong className="hint">Thông báo</strong>
            {chuaDoc > 0 ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={docHet}>
                Đánh dấu đã đọc
              </button>
            ) : null}
          </div>
          {ds === null ? (
            <div className="bell-empty hint">Đang tải…</div>
          ) : ds.length === 0 ? (
            <div className="bell-empty hint">
              Chưa có thông báo nào. Theo dõi vài tác giả để biết khi họ đăng
              chương mới.
            </div>
          ) : (
            <>
              {ds.map((n) => (
                <Link
                  key={n.notification_id}
                  href={dichDen(n)}
                  className={n.read ? "menu-item bell-item" : "menu-item bell-item bell-moi"}
                  role="menuitem"
                  onClick={dong}
                >
                  <span className="bell-text">
                    {laHeThong(n) ? null : (
                      <strong>
                        {n.actor?.display_name || n.actor?.username || "Ai đó"}{" "}
                      </strong>
                    )}
                    {moTa(n)}
                    {n.preview ? (
                      <em className="bell-preview"> “{n.preview}”</em>
                    ) : null}
                  </span>
                  <span className="hint bell-luc">{khiNao(n.created_at)}</span>
                </Link>
              ))}
              <div className="menu-sep" role="separator" />
              <Link
                href="/notifications"
                className="menu-item"
                role="menuitem"
                onClick={dong}
              >
                Xem tất cả thông báo
              </Link>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
