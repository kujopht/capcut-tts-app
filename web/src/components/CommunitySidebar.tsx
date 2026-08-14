"use client";

/**
 * Cột phải của /community — CHỈ desktop, CSS ẩn dưới 1000px.
 *
 * MỘT khối duy nhất: "Tác giả nổi bật", xếp theo lượt nghe hợp lệ — con số
 * THẬT của hệ thống hạng, không phải "trending" bịa. Không có khối thứ hai
 * cho tới khi có dữ liệu thật đáng hiện: một sidebar đầy khung rỗng đọc ra
 * như một trang chưa xong.
 *
 * Cũng được dùng làm gợi ý theo dõi ở trạng thái trống của bảng tin — cùng
 * một nguồn dữ liệu, hai chỗ hiện.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type PublicProfile } from "@/lib/api";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { Avatar } from "@/components/Avatar";
import { FollowButton } from "@/components/FollowButton";
import { useSession } from "@/lib/session";

export function TacGiaNoiBat({ gon = false }: { gon?: boolean }) {
  const { profile } = useSession();
  const [ds, setDs] = useState<PublicProfile[] | null>(null);

  useEffect(() => {
    let huy = false;
    api
      .searchPeople("", "authors", 8)
      .then((r) => {
        if (huy) return;
        // Sap theo luot nghe hop le — tieu chi THAT va giai thich duoc.
        const xep = [...r.people].sort(
          (a, b) =>
            (b.rank?.qualified_listens ?? 0) - (a.rank?.qualified_listens ?? 0),
        );
        setDs(xep.slice(0, 5));
      })
      .catch(() => {
        if (!huy) setDs([]);
      });
    return () => {
      huy = true;
    };
  }, []);

  /* Loi hoac rong: KHONG hien gi — mot khoi goi y trong tron doc ra nhu mot
     trang chua xong, va bang tin van la nhan vat chinh. */
  if (!ds || ds.length === 0) return null;

  return (
    <section
      className={gon ? "card stack-2" : "card stack-2 sidebar-khoi"}
      aria-labelledby="tac-gia-noi-bat"
    >
      <h2 className="hint sidebar-tieu-de" id="tac-gia-noi-bat">
        Tác giả nổi bật
      </h2>
      <ul className="sidebar-ds">
        {ds.map((p) => (
          <li key={p.user_id} className="sidebar-nguoi">
            <Avatar
              name={p.display_name || p.username}
              avatarUrl={p.avatar_url}
              className="avatar avatar-sm"
            />
            <span className="sidebar-nguoi-chu">
              <Link href={`/u/${p.username}`} className="sidebar-ten">
                {p.display_name || p.username}
              </Link>
              <span className="row" style={{ gap: 4 }}>
                <AuthorBadge size="sm" />
                {p.rank ? <RankBadge rank={p.rank} size="sm" /> : null}
              </span>
            </span>
            {profile && profile.user_id !== p.user_id ? (
              <FollowButton
                kind="user"
                targetId={p.user_id}
                initialFollowing={false}
                compact
              />
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
