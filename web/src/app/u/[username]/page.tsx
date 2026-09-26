"use client";

/**
 * Trang CONG KHAI cua mot nguoi dung.
 *
 * KHONG can dang nhap de xem. Va khong bao gio lo email, goi cuoc, quota, hay
 * trang thai duyet — danh sach truong cong khai nam o backend
 * (`creator.public_profile`), va o day chi ve nhung gi no cap.
 *
 * `/u/ten` chu khong phai `/users/ten`: ngan hon, go duoc bang tay, va `u` da
 * nam trong danh sach ten bi giu lai nen khong ai lay duoc username do. Social
 * & Play V1: `/u/<user_id>` cung mo duoc — nguoi chua chon username van co mot
 * trang ho so bat bien, va moi avatar/ten o bang tin dan ve DUNG trang nay.
 *
 * Chu ho so thay "Sua ho so"; nguoi khac thay Theo doi + menu Bao cao/An/Chan
 * (chi khi may chu bao ho tro). Khong so nguoi theo doi nao bi bia: ba con so o
 * day la dem that cua may chu.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, social, type PublicProfile, type ServerLimits } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { AuthorBadge, RankBadge } from "@/components/AuthorBadge";
import { ConfirmDialog, EmptyState, ErrorState, Loading, formatNumber } from "@/components/ui";
import { IconHeadphones, IconUser } from "@/components/Icons";
import { FollowButton } from "@/components/FollowButton";
import { BadgeIcon, OrnamentIcon } from "@/components/cosmetics/Cosmetics";
import { UserAvatar, tenHienThi } from "@/components/UserAvatar";
import { ReportDialog } from "@/components/ReportDialog";
import { ProfileEditor } from "@/components/ProfileEditor";
import { ProfileTabs } from "./ProfileTabs";

/** Menu ⋯ cua nguoi xem ho so NGUOI KHAC. */
function MenuHoSo({
  p,
  limits,
  onDoi,
}: {
  p: PublicProfile;
  limits: ServerLimits | null;
  onDoi: () => void;
}) {
  const toast = useToast();
  const cap = limits?.capabilities ?? {};
  const [mo, setMo] = useState(false);
  const [baoCao, setBaoCao] = useState(false);
  const [hoi, setHoi] = useState<null | "chan" | "bo-chan" | "an" | "bo-an">(null);
  const [dangLam, setDangLam] = useState(false);
  const hop = useRef<HTMLDivElement | null>(null);
  const nut = useRef<HTMLButtonElement | null>(null);
  const qh = p.viewer_relation ?? { blocked: false, muted: false };
  const ten = tenHienThi(p);

  useEffect(() => {
    if (!mo) return;
    const onDown = (e: MouseEvent) => {
      if (!hop.current?.contains(e.target as Node)) setMo(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMo(false);
        nut.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [mo]);

  if (!cap.user_reports && !cap.blocks) return null;

  const lam = async () => {
    if (!hoi || dangLam) return;
    setDangLam(true);
    try {
      if (hoi === "chan") await social.block(p.user_id);
      if (hoi === "bo-chan") await social.unblock(p.user_id);
      if (hoi === "an") await social.mute(p.user_id);
      if (hoi === "bo-an") await social.unmute(p.user_id);
      toast.ok(
        hoi === "chan" ? `Đã chặn ${ten}.` : hoi === "bo-chan" ? `Đã bỏ chặn ${ten}.` : hoi === "an" ? `Đã ẩn bài của ${ten}.` : `Đã bỏ ẩn ${ten}.`,
      );
      setHoi(null);
      onDoi();
    } catch (e) {
      setHoi(null);
      toast.push("error", e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setDangLam(false);
    }
  };

  const muc = (nhan: string, fn: () => void) => (
    <button
      type="button"
      className="menu-item"
      role="menuitem"
      onClick={() => {
        setMo(false);
        fn();
      }}
    >
      {nhan}
    </button>
  );

  return (
    <div className="menu ho-so-menu" ref={hop}>
      <button
        ref={nut}
        type="button"
        className="btn btn-ghost btn-sm"
        aria-haspopup="menu"
        aria-expanded={mo}
        aria-label={`Tuỳ chọn với ${ten}`}
        onClick={() => setMo((v) => !v)}
      >
        ⋯
      </button>
      {mo ? (
        <div className="menu-panel" role="menu" aria-label={`Tuỳ chọn với ${ten}`}>
          {cap.user_reports ? muc("🚩 Báo cáo người dùng", () => setBaoCao(true)) : null}
          {cap.blocks ? (qh.muted ? muc("🔔 Bỏ ẩn bài", () => setHoi("bo-an")) : muc("🔕 Ẩn bài của họ", () => setHoi("an"))) : null}
          {cap.blocks ? (qh.blocked ? muc("Bỏ chặn", () => setHoi("bo-chan")) : muc("⛔ Chặn", () => setHoi("chan"))) : null}
        </div>
      ) : null}
      {baoCao ? <ReportDialog targetKind="user" targetId={p.user_id} targetName={ten} onClose={() => setBaoCao(false)} /> : null}
      <ConfirmDialog
        open={hoi !== null}
        title={
          hoi === "chan" ? `Chặn ${ten}?` : hoi === "bo-chan" ? `Bỏ chặn ${ten}?` : hoi === "an" ? `Ẩn bài của ${ten}?` : `Bỏ ẩn ${ten}?`
        }
        body={
          hoi === "chan"
            ? "Hai bạn sẽ không thấy bài của nhau trong bảng tin và không thể thích, bình luận hay theo dõi nhau. Họ không nhận được thông báo nào."
            : hoi === "an"
              ? "Bài của họ không còn hiện trong bảng tin của bạn. Họ không biết điều này."
              : "Bạn có thể đổi lại bất cứ lúc nào."
        }
        confirmLabel={hoi === "chan" ? "Chặn" : hoi === "an" ? "Ẩn" : "Đồng ý"}
        danger={hoi === "chan"}
        busy={dangLam}
        onConfirm={() => void lam()}
        onCancel={() => setHoi(null)}
      />
    </div>
  );
}

export default function PublicProfilePage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = use(params);
  const { profile: toi } = useSession();
  const nap = useCallback(() => api.publicProfile(decodeURIComponent(username)), [username]);
  const { data, loading, error, missing, reload } = useAsyncData(nap);
  const [limits, setLimits] = useState<ServerLimits | null>(null);
  const [suaHoSo, setSuaHoSo] = useState(false);

  useEffect(() => {
    social.limits().then(setLimits).catch(() => {});
  }, []);

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
  const huyHieu = gam?.equipped_cosmetics.find((c) => c.slot === "badge");
  const hoaVan = gam?.equipped_cosmetics.find((c) => c.slot === "profile_ornament");
  const laToi = Boolean(xh?.is_self || (toi && toi.user_id === p.user_id));
  const mayChuV1 = Boolean(limits?.capabilities);
  const fandoms = limits?.community_fandoms ?? [];
  const ten = tenHienThi(p);

  return (
    <div className="page ho-so-trang" data-accent={p.accent ?? undefined}>
      <header className="ho-so-dau-v1">
        <div
          className="ho-so-bia"
          role="img"
          aria-label={p.banner_url ? `Ảnh bìa của ${ten}` : undefined}
          aria-hidden={p.banner_url ? undefined : true}
          style={p.banner_url ? { backgroundImage: `url("${p.banner_url}")` } : undefined}
        />
        <div className="ho-so-dau-than">
          <UserAvatar user={{ ...p, equipped_cosmetics: gam?.equipped_cosmetics ?? [] }} className="account-avatar ho-so-avatar" />

          <div className="stack-2 ho-so-dau-chu">
            <span className="eyebrow eyebrow-icon">
              <IconUser size={17} /> Trang cá nhân
            </span>
            <h1 className="page-title ho-so-ten-lon">{ten}</h1>
            {p.username ? <p className="hint ho-so-ten">@{p.username}</p> : null}

            {/*
              Danh xung/bac — TRUC RIENG, tach khoi huy hieu tac gia/hang. "✦"
              chi la mot dau tach thi giac, khong phai vat pham.
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
                  <span className="ho-so-huy-hieu" title={huyHieu.name} aria-label={huyHieu.name}>
                    <BadgeIcon assetRef={huyHieu.asset_ref} size={16} />
                  </span>
                ) : null}
              </p>
            ) : null}

            {p.is_author ? (
              <p className="ho-so-hh">
                <AuthorBadge />
                {p.rank ? <RankBadge rank={p.rank} /> : null}
              </p>
            ) : null}

            {p.bio ? <p className="lead lead-narrow ho-so-bio">{p.bio}</p> : null}

            {p.fandom_ids?.length ? (
              <p className="ho-so-fandom-hang" aria-label="Fandom yêu thích">
                {p.fandom_ids.map((id) => (
                  <Link key={id} href={`/community?fandom=${encodeURIComponent(id)}`} className="chip chip-static" prefetch={false}>
                    {fandoms.find((f) => f.id === id)?.label ?? id}
                  </Link>
                ))}
              </p>
            ) : null}

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
              </p>
            ) : null}

            <div className="row ho-so-hanh-dong">
              {laToi ? (
                mayChuV1 ? (
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => setSuaHoSo(true)}>
                    Sửa hồ sơ
                  </button>
                ) : (
                  <Link href="/account" className="btn btn-ghost btn-sm" prefetch={false}>
                    Sửa ở trang Tài khoản
                  </Link>
                )
              ) : (
                <>
                  {xh && !p.viewer_relation?.blocked ? (
                    <FollowButton kind="user" targetId={p.user_id} initialFollowing={xh.following} />
                  ) : null}
                  {toi ? <MenuHoSo p={p} limits={limits} onDoi={reload} /> : null}
                </>
              )}
            </div>
            {p.viewer_relation?.blocked ? (
              <p className="hint">Bạn đang chặn người này. Bài của họ không hiện trong bảng tin của bạn.</p>
            ) : null}
          </div>

          {p.is_author && p.rank ? (
            <div className="stack-2 account-hero-plan ho-so-so">
              <span className="hint eyebrow-icon">
                <IconHeadphones size={15} /> Lượt nghe hợp lệ
              </span>
              <strong className="ho-so-dem">{formatNumber(p.rank.qualified_listens)}</strong>
            </div>
          ) : null}
        </div>
      </header>

      <ProfileTabs
        userId={p.user_id}
        novels={truyen}
        isAuthor={p.is_author}
        postCount={xh?.post_count ?? 0}
        achievements={gam?.achievements ?? []}
      />

      {suaHoSo ? (
        <ProfileEditor
          limits={limits}
          onClose={() => setSuaHoSo(false)}
          onSaved={() => {
            setSuaHoSo(false);
            reload();
          }}
        />
      ) : null}
    </div>
  );
}
