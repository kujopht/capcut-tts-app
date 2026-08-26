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
import { IconHeadphones, IconShield, IconUser } from "@/components/Icons";
import { FollowButton } from "@/components/FollowButton";
import { BadgeIcon, CosmeticFrame, OrnamentIcon } from "@/components/cosmetics/Cosmetics";
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
            <Link className="btn btn-primary" href="/fanfic" prefetch={false}>
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
  const gam = p.gamification;
  const khungAvatar = gam?.equipped_cosmetics.find((c) => c.slot === "avatar_frame");
  const huyHieu = gam?.equipped_cosmetics.find((c) => c.slot === "badge");
  const hoaVan = gam?.equipped_cosmetics.find((c) => c.slot === "profile_ornament");

  return (
    <div className="page">
      <header className="account-hero ho-so-hero">
        <CosmeticFrame cosmetic={khungAvatar}>
          <Avatar
            name={p.display_name || p.username}
            avatarUrl={p.avatar_url}
            className="account-avatar"
          />
        </CosmeticFrame>

        <div className="stack-2 account-hero-body">
          <span className="eyebrow eyebrow-icon">
            <IconUser size={17} /> Trang cá nhân
          </span>
          <h1 className="page-title">{p.display_name || p.username}</h1>
          <p className="hint ho-so-ten">@{p.username}</p>

          {/*
            Danh xung/bac (V4 visual completion, vong 2) — TRUC RIENG, tach
            khoi huy hieu tac gia/hang ben duoi. "✦" chi la mot dau tach thi
            giac, khong phai vat pham.
          */}
          {gam ? (
            <p className="hint ho-so-danh-xung">
              {hoaVan ? (
                <span aria-hidden="true" className="ho-so-hoa-van">
                  <OrnamentIcon assetRef={hoaVan.asset_ref} size={16} />
                </span>
              ) : (
                "✦"
              )}{" "}
              {gam.equipped_title} · Lv. {gam.level}
              {huyHieu ? (
                <span
                  className="ho-so-huy-hieu"
                  title={huyHieu.name}
                  aria-label={huyHieu.name}
                >
                  <BadgeIcon assetRef={huyHieu.asset_ref} size={16} />
                </span>
              ) : null}
            </p>
          ) : null}

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

      {/*
        Thanh tuu CONG KHAI — CHI nhung cai DA MO (khong ve ca danh sach
        khoa, tranh trang ca nhan thanh mot bang "chua lam duoc gi"). An
        hoan toan khi chua co gi — cung nguyen tac voi module Tiep tuc o
        trang chu.
      */}
      {gam && gam.achievements.some((a) => a.unlocked) ? (
        <section className="stack-2" aria-labelledby="ho-so-thanh-tuu">
          <h2 className="section-title section-title-icon" id="ho-so-thanh-tuu">
            <IconShield size={19} /> Thành tựu
          </h2>
          <div className="bento-grid">
            {gam.achievements
              .filter((a) => a.unlocked)
              .map((a) => (
                <div key={a.key} className={`achievement-card do-hiem-${a.rarity}`}>
                  <span className="achievement-card-icon" aria-hidden="true">
                    {a.icon}
                  </span>
                  <span className="progress-card-body">
                    <strong>{a.name}</strong>
                  </span>
                </div>
              ))}
          </div>
        </section>
      ) : null}

      <ProfileTabs
        userId={p.user_id}
        novels={truyen}
        isAuthor={p.is_author}
        postCount={xh?.post_count ?? 0}
      />

    </div>
  );
}
