"use client";

/**
 * Trang CONG KHAI cua mot nguoi dung.
 *
 * KHONG can dang nhap de xem. Va khong bao gio lo email, goi cuoc, quota, hay
 * trang thai duyet — danh sach truong cong khai nam o backend
 * (`creator.public_profile`), va o day chi ve nhung gi no cap.
 *
 * `/u/ten` chu khong phai `/users/ten`: ngan hon, go duoc bang tay, va `u` da
 * nam trong danh sach ten bi giu lai nen khong ai lay duoc username do.
 */

import Link from "next/link";
import { use, useCallback } from "react";
import { api, type PublicProfile } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { StoryCard } from "@/components/StoryCard";
import { EmptyState, ErrorState, Loading, formatNumber } from "@/components/ui";
import { IconBook, IconHeadphones, IconUser } from "@/components/Icons";

export default function PublicProfilePage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = use(params);
  const nap = useCallback(() => api.publicProfile(username), [username]);
  const { data, loading, error, missing, reload } = useAsyncData(nap);

  if (loading) return <div className="page"><Loading /></div>;

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy người dùng này"
          hint="Có thể họ chưa chọn tên công khai, hoặc đường dẫn bị gõ sai."
          action={
            <Link className="btn btn-primary" href="/fanfic">
              Về trang khám phá
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được trang."} onRetry={reload} />
      </div>
    );
  }

  const p: PublicProfile = data.profile;
  const truyen = p.novels ?? [];

  return (
    <div className="page">
      <header className="account-hero ho-so-hero">
        <span className="account-avatar" aria-hidden="true">
          {(p.display_name || p.username).slice(0, 2).toUpperCase()}
        </span>

        <div className="stack-2 account-hero-body">
          <span className="eyebrow eyebrow-icon">
            <IconUser size={17} /> Trang cá nhân
          </span>
          <h1 className="page-title">{p.display_name || p.username}</h1>
          <p className="hint ho-so-ten">@{p.username}</p>

          {/*
            HAI huy hieu, hai chuyen khac nhau:
              tac gia — da duoc duyet xuat ban (moderation)
              hang    — uy tin theo so luot nghe hop le
            Chung duoc ve khac nhau co y — xem `AuthorBadge.tsx`.
          */}
          {p.is_author ? (
            <p className="ho-so-hh">
              <AuthorBadge />
              {p.rank ? <RankBadge rank={p.rank} /> : null}
            </p>
          ) : null}

          {p.bio ? <p className="lead lead-narrow ho-so-bio">{p.bio}</p> : null}
        </div>

        {p.is_author && p.rank ? (
          <div className="stack-2 account-hero-plan ho-so-so">
            <span className="hint eyebrow-icon">
              <IconHeadphones size={15} /> Lượt nghe hợp lệ
            </span>
            <strong className="ho-so-dem">
              {formatNumber(p.rank.qualified_listens)}
            </strong>
          </div>
        ) : null}
      </header>

      <section className="stack" aria-labelledby="ho-so-truyen">
        <h2 className="section-title section-title-icon" id="ho-so-truyen">
          <IconBook size={19} /> Truyện đã xuất bản
        </h2>

        {truyen.length === 0 ? (
          <EmptyState
            icon="📖"
            title={
              p.is_author
                ? "Chưa có truyện nào được xuất bản"
                : "Người này chưa xuất bản truyện nào"
            }
            hint="Bản nháp không hiện ở trang công khai."
          />
        ) : (
          <div className="story-grid">
            {truyen.map((n) => (
              <StoryCard key={n.novel_id} novel={n} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
