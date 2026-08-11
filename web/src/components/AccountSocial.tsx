"use client";

/**
 * Tóm tắt xã hội của chính mình, ở `/account`.
 *
 * HAI nhóm, và ranh giới giữa chúng có ý nghĩa:
 *
 *   ai cũng có       người theo dõi · đang theo dõi · bài viết · truyện theo dõi
 *   tác giả đã duyệt hạng · lượt nghe hợp lệ · truyện đã xuất bản
 *
 * Nhóm thứ hai KHÔNG hiện cho người chưa nộp đơn. Một ô "Hạng: chưa có" là một
 * lời mời vào một hệ thống họ không ở trong — nó đọc ra như một thứ bị thiếu chứ
 * không phải một thứ không áp dụng.
 *
 * KHÔNG có quyền lợi nào theo hạng ở giai đoạn này. Hạng chỉ là một con số uy
 * tín; xem `docs/AUTHOR_RANK.md`.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { social, type AccountSocial as TomTat } from "@/lib/api";
import { formatNumber } from "@/components/ui";
import { RankBadge } from "@/components/AuthorBadge";

function O({ nhan, so }: { nhan: string; so: number }) {
  return (
    <div className="stat">
      <strong className="stat-value">{formatNumber(so)}</strong>
      <span className="stat-label">{nhan}</span>
    </div>
  );
}

export function AccountSocial() {
  const [tt, setTt] = useState<TomTat | null>(null);
  const [loi, setLoi] = useState(false);

  useEffect(() => {
    let huy = false;
    social
      .accountSocial()
      .then((r) => {
        if (!huy) setTt(r);
      })
      .catch(() => {
        if (!huy) setLoi(true);
      });
    return () => {
      huy = true;
    };
  }, []);

  /*
    Không tải được thì KHÔNG hiện gì cả, và không hiện lỗi.

    Đây là một khối phụ trên trang tài khoản; những thứ chính (email, gói, hạn
    mức) vẫn ở đó. Một thông báo lỗi đỏ cho vài con số thống kê làm cả trang đọc
    ra như đang hỏng, trong khi mọi thứ người dùng vào đây để làm vẫn chạy.
  */
  if (loi) return null;

  return (
    <section className="stack" aria-labelledby="acc-xa-hoi">
      <h2 className="section-title" id="acc-xa-hoi">
        Cộng đồng của bạn
      </h2>

      {tt === null ? (
        <div className="stat-grid" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className="sk" style={{ height: 64 }} />
          ))}
        </div>
      ) : (
        <>
          <div className="stat-grid">
            <O nhan="Người theo dõi" so={tt.follower_count} />
            <O nhan="Đang theo dõi" so={tt.following_count} />
            <O nhan="Bài viết" so={tt.post_count} />
            <O nhan="Truyện theo dõi" so={tt.followed_stories} />
          </div>

          {/* Nhóm thứ hai — chỉ tác giả đã duyệt. Xem ghi chú đầu tệp. */}
          {tt.rank ? (
            <div className="stat-grid">
              <div className="stat">
                <RankBadge rank={tt.rank} />
                <span className="stat-label">Hạng hiện tại</span>
              </div>
              <O nhan="Lượt nghe hợp lệ" so={tt.qualified_listens ?? 0} />
              <O nhan="Truyện đã xuất bản" so={tt.published_novels ?? 0} />
            </div>
          ) : null}

          <div className="row" style={{ gap: 8 }}>
            <Link className="btn btn-ghost btn-sm" href="/community">
              Tới Cộng đồng
            </Link>
            <Link className="btn btn-ghost btn-sm" href="/notifications">
              Thông báo
              {tt.unread_notifications > 0
                ? ` (${tt.unread_notifications})`
                : null}
            </Link>
          </div>
        </>
      )}
    </section>
  );
}
