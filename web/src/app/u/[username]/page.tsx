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
import { Avatar } from "@/components/Avatar";
import { EmptyState, ErrorState, Loading, formatNumber } from "@/components/ui";
import { IconHeadphones, IconUser } from "@/components/Icons";
import { FollowButton } from "@/components/FollowButton";
import { ProfileTabs } from "./ProfileTabs";

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
  const xh = p.social;

  return (
    <div className="page">
      <header className="account-hero ho-so-hero">
        <Avatar
          name={p.display_name || p.username}
          avatarUrl={p.avatar_url}
          className="account-avatar"
        />

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

          {/*
            Ba con so, va MOT nut. Nut khong hien khi dang xem trang cua chinh
            minh: mot nut "Theo doi" tro vao chinh nguoi dang bam la vo nghia, va
            backend cung tu choi no.
          */}
          {xh ? (
            <p className="ho-so-so-hang">
              <span>
                <strong>{formatNumber(xh.follower_count)}</strong> người theo dõi
              </span>
              <span>
                <strong>{formatNumber(xh.following_count)}</strong> đang theo dõi
              </span>
              <span>
                <strong>{formatNumber(xh.post_count)}</strong> bài viết
              </span>
              {xh.is_self ? null : (
                <FollowButton
                  kind="user"
                  targetId={p.user_id}
                  initialFollowing={xh.following}
                />
              )}
            </p>
          ) : null}
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

      <ProfileTabs
        userId={p.user_id}
        novels={truyen}
        isAuthor={p.is_author}
        postCount={xh?.post_count ?? 0}
      />

    </div>
  );
}
