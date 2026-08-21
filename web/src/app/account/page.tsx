"use client";

/** Trang tai khoan: thong tin ho so va han muc su dung. */

import Link from "next/link";
import { useCallback, useState } from "react";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { errorMessage } from "@/lib/session";
import { api } from "@/lib/api";
import { xuLyAnh } from "@/lib/image";
import { MAX_AVATAR_EDGE } from "@/lib/limits";
import { MotifSigil } from "@/components/Ornaments";
import { ConfirmDialog, EmptyState, Loading, formatDate, formatNumber } from "@/components/ui";
import {
  IconSparkles,
  IconCompass,
  IconFeather,
  IconMic,
  IconHeadphones,
  IconKey,
} from "@/components/Icons";
import { CreatorSection } from "@/components/CreatorSection";
import { AccountSocial } from "@/components/AccountSocial";
import { AchievementGrid } from "@/components/AchievementGrid";
import { GamificationPanel } from "@/components/GamificationPanel";
import { QuestPanel } from "@/components/QuestPanel";
import { Avatar } from "@/components/Avatar";

const TIER_LABEL: Record<string, string> = {
  free: "Miễn phí",
  listener_pro: "Người nghe Pro",
  creator_pro: "Tác giả Pro",
  ultra: "Ultra",
};

export default function AccountPage() {
  const { profile, loading, signOut, updateProfile } = useSession();
  const [confirmOut, setConfirmOut] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [savingAvatar, setSavingAvatar] = useState(false);
  const [xpRefreshKey, setXpRefreshKey] = useState(0);
  const toast = useToast();

  const doSignOut = useCallback(() => {
    setConfirmOut(false);
    signOut();
  }, [signOut]);

  const doDeleteAccount = useCallback(async () => {
    setDeletingAccount(true);
    try {
      await api.deleteAccount();
      // KHÔNG gọi `router.push` — `signOut()` xoá `profile` khỏi session,
      // và trang này TỰ chuyển sang màn "Bạn chưa đăng nhập" (xem nhánh
      // `if (!profile)` bên dưới), đúng y hệt luồng đăng xuất thường. Gọi
      // lại `api.logout()` bên trong `signOut()` cho một tài khoản đã xoá
      // là vô hại — nó đã tự dung thứ lỗi mạng/401 ở đó.
      await signOut();
    } catch (cause) {
      setDeletingAccount(false);
      setConfirmDelete(false);
      toast.error(errorMessage(cause));
    }
  }, [signOut, toast]);

  const chonAvatar = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const tep = event.target.files?.[0];
      event.target.value = "";
      if (!tep) return;
      setSavingAvatar(true);
      try {
        const anh = await xuLyAnh(tep, MAX_AVATAR_EDGE);
        if (!anh) {
          toast.error("Không đọc được ảnh này.");
          return;
        }
        const result = await api.setAvatar({
          base64: anh.base64,
          mime: anh.mime,
          width: anh.width,
          height: anh.height,
        });
        URL.revokeObjectURL(anh.xemTruoc);
        updateProfile(result.profile);
        toast.ok("Đã cập nhật avatar.");
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setSavingAvatar(false);
      }
    },
    [toast, updateProfile],
  );

  const xoaAvatar = useCallback(async () => {
    setSavingAvatar(true);
    try {
      const result = await api.removeAvatar();
      updateProfile(result.profile);
      toast.ok("Đã gỡ avatar.");
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setSavingAvatar(false);
    }
  }, [toast, updateProfile]);

  if (loading) {
    return (
      <div className="page">
        <Loading label="Đang tải hồ sơ…" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="page">
        <h1 className="page-title">Tài khoản</h1>
        <EmptyState
          icon="🔐"
          title="Bạn chưa đăng nhập"
          action={
            <Link className="btn btn-primary" href="/login">
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  return (
    // Themed Page Hero — Tai khoan: xanh lam-tim + indigo, KIEM CHE hon cac
    // trang noi dung khac (day la ho so ca nhan, khong phai mot "the gioi"
    // can the hien ro).
    <div className="page" data-hero-theme="account">
      {/*
        Danh thiep: anh dai dien, ten, email, goi. Bon manh thong tin nay truoc
        day nam o bon khoi roi rac; gom lai mot cho thi doc duoc trong mot lan
        nhin, va do la ca viec cua trang tai khoan.
      */}
      <header className="account-hero">
        <span className="account-hero-motif" aria-hidden="true">
          <MotifSigil />
        </span>
        <label
          className="min0"
          style={{ cursor: savingAvatar ? "wait" : "pointer" }}
          title="Đổi avatar"
        >
          <Avatar
            name={profile.display_name || profile.email}
            avatarUrl={profile.avatar_url}
            className="account-avatar"
          />
          <input
            type="file"
            accept="image/*"
            hidden
            disabled={savingAvatar}
            onChange={chonAvatar}
          />
        </label>
        <div className="stack-2 account-hero-body">
          <span className="eyebrow">Tài khoản</span>
          <h1 className="page-title">
            {profile.display_name || profile.email.split("@")[0]}
          </h1>
          <p className="hint">{profile.email}</p>
          {profile.avatar_url ? (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={xoaAvatar}
              disabled={savingAvatar}
              style={{ alignSelf: "flex-start" }}
            >
              {savingAvatar ? <span className="spinner" aria-hidden="true" /> : null}
              Gỡ avatar
            </button>
          ) : null}
        </div>
        <div className="stack-2 account-hero-plan">
          <span className="badge badge-brand">
            {TIER_LABEL[profile.tier] ?? profile.tier}
          </span>
          <span className="hint">
            Bản MVP riêng tư — chưa có thanh toán và chưa trừ hạn mức thực tế.
          </span>
        </div>
      </header>

      <section className="stack" aria-labelledby="acc-su-dung">
        <h2 className="section-title section-title-icon" id="acc-su-dung">
          <IconSparkles size={19} /> Sử dụng
        </h2>
        {/*
          KHONG ve thanh tien do hay cap do o day. Ca ba con so deu la so DEM,
          khong co han muc nao de chia cho — ve mot thanh "đã dùng 40%" se phai
          bia ra cai mau so.
        */}
        <div className="stat-grid">
          <div className="stat">
            <span className="stat-value">
              {formatNumber(profile.tts_characters_used)}
            </span>
            <span className="stat-label">Ký tự đã tổng hợp</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {formatNumber(profile.listened_minutes)}
            </span>
            <span className="stat-label">Phút đã nghe</span>
          </div>
          <div className="stat">
            <span className="stat-value">{formatDate(profile.created_at)}</span>
            <span className="stat-label">Ngày tham gia</span>
          </div>
        </div>
        <p className="hint">
          Hai chỉ số đầu do máy chủ quản lý và hiện chưa được cập nhật tự động.
        </p>
      </section>

      {/*
        KHU CREATOR. Dat TRUOC "Lối tắt": voi mot nguoi da la tac gia, hang va so
        luot nghe la thu ho vao trang nay de xem; con loi tat thi ho da thuoc.
      */}
      <AccountSocial />

      <AchievementGrid />

      {/*
        Nhan qua nhiem vu cong THAT XP, nhung `QuestPanel`/`GamificationPanel`
        la hai component doc lap voi hai lan `useAsyncData` rieng — khong co
        cai do, "Cap do" se hien XP cu cho toi khi tai lai trang. `xpRefreshKey`
        la tin hieu don gian nhat de bao GamificationPanel tai lai, khong can
        dung mot store/context chi cho mot gia tri.
      */}
      <QuestPanel onXpChange={() => setXpRefreshKey((k) => k + 1)} />

      <GamificationPanel refreshKey={xpRefreshKey} />

      <CreatorSection />

      {/*
        V4 visual completion, Phan 8: NGAN CACH bang mat "TUY CHINH HO SO
        CONG KHAI" (moi thu o tren — thanh tuu, cap do, danh xung, vat
        pham, danh tinh tac gia) voi "CAI DAT TAI KHOAN" (loi tat, phien
        dang nhap) o duoi. Cung mot trang, nhung hai y dinh khac nhau.
      */}
      <hr className="divider" />
      <h2 className="section-title">Cài đặt tài khoản</h2>

      <section className="stack" aria-labelledby="acc-loi-tat">
        <h2 className="section-title section-title-icon" id="acc-loi-tat">
          <IconCompass size={19} /> Lối tắt
        </h2>
        <div className="quick-grid">
          <Link className="quick-card" href="/write">
            <span className="quick-icon" aria-hidden="true">
              <IconFeather size={19} />
            </span>
            <strong>Khu vực tác giả</strong>
            <span className="hint">Tạo truyện, thêm chương, xuất bản.</span>
          </Link>
          <Link className="quick-card" href="/studio">
            <span className="quick-icon" aria-hidden="true">
              <IconMic size={19} />
            </span>
            <strong>Audio Studio</strong>
            <span className="hint">Dán văn bản bất kỳ và tạo MP3.</span>
          </Link>
          <Link className="quick-card" href="/library">
            <span className="quick-icon" aria-hidden="true">
              <IconHeadphones size={19} />
            </span>
            <strong>Thư viện audio</strong>
            <span className="hint">Mọi bản audio bạn đã tạo.</span>
          </Link>
        </div>
      </section>

      {/* V4 visual completion, Phan C: `surface-secondary` thay `card` — mot
          cau + mot nut khong can toan bo be day kinh cua `.page > .card`. */}
      <section className="surface-secondary stack card-tight">
        <h2 className="section-title">Phiên đăng nhập</h2>
        <p className="hint">
          Đăng xuất sẽ xoá phiên khỏi trình duyệt này. Dữ liệu của bạn vẫn giữ
          nguyên trên máy chủ.
        </p>
        <div className="row">
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => setConfirmOut(true)}
          >
            Đăng xuất
          </button>
        </div>
      </section>

      <ConfirmDialog
        open={confirmOut}
        title="Đăng xuất khỏi thiết bị này?"
        body="Bạn sẽ cần đăng nhập lại để tạo audio hoặc quản lý truyện."
        confirmLabel="Đăng xuất"
        danger
        onConfirm={doSignOut}
        onCancel={() => setConfirmOut(false)}
      />

      {/* Vung nguy hiem — tach rieng khoi "Phien dang nhap" o tren: dang xuat
          giu du lieu, xoa tai khoan thi khong. */}
      <section className="surface-secondary stack card-tight">
        <h2 className="section-title">Xoá tài khoản</h2>
        <p className="hint">
          Xoá vĩnh viễn tài khoản cùng truyện, chương, audio, bài đăng và mọi
          dữ liệu khác của bạn. Thao tác này{" "}
          <strong>không hoàn tác được</strong>.
        </p>
        <div className="row">
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => setConfirmDelete(true)}
          >
            Xoá tài khoản
          </button>
        </div>
      </section>

      <ConfirmDialog
        open={confirmDelete}
        danger
        title="Xoá vĩnh viễn tài khoản này?"
        body={
          <>
            <p>
              Toàn bộ <strong>truyện, chương, audio, bài đăng</strong> và mọi
              dữ liệu khác của <strong>{profile.display_name || profile.email}</strong>{" "}
              sẽ bị xoá — kể cả truyện đã xuất bản đang có người đọc.
            </p>
            <p className="mt-2">
              Thao tác này <strong>không hoàn tác được</strong>.
            </p>
          </>
        }
        confirmLabel="Xoá vĩnh viễn"
        busy={deletingAccount}
        onConfirm={doDeleteAccount}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}
