"use client";

/** Trang tai khoan: thong tin ho so va han muc su dung. */

import Link from "next/link";
import { useCallback, useState } from "react";
import { useSession } from "@/lib/session";
import { ConfirmDialog, EmptyState, Loading, formatDate, formatNumber } from "@/components/ui";
import { IconSparkles, IconCompass } from "@/components/Icons";

const TIER_LABEL: Record<string, string> = {
  free: "Miễn phí",
  listener_pro: "Người nghe Pro",
  creator_pro: "Tác giả Pro",
  ultra: "Ultra",
};

export default function AccountPage() {
  const { profile, loading, signOut } = useSession();
  const [confirmOut, setConfirmOut] = useState(false);

  const doSignOut = useCallback(() => {
    setConfirmOut(false);
    signOut();
  }, [signOut]);

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
    <div className="page">
      {/*
        Danh thiep: anh dai dien, ten, email, goi. Bon manh thong tin nay truoc
        day nam o bon khoi roi rac; gom lai mot cho thi doc duoc trong mot lan
        nhin, va do la ca viec cua trang tai khoan.
      */}
      <header className="account-hero">
        <span className="account-avatar" aria-hidden="true">
          {(profile.display_name || profile.email).slice(0, 2).toUpperCase()}
        </span>
        <div className="stack-2 account-hero-body">
          <span className="eyebrow">Tài khoản</span>
          <h1 className="page-title">
            {profile.display_name || profile.email.split("@")[0]}
          </h1>
          <p className="hint">{profile.email}</p>
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
          <IconSparkles size={17} /> Sử dụng
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

      <section className="stack" aria-labelledby="acc-loi-tat">
        <h2 className="section-title section-title-icon" id="acc-loi-tat">
          <IconCompass size={17} /> Lối tắt
        </h2>
        <div className="quick-grid">
          <Link className="quick-card" href="/write">
            <span className="quick-icon" aria-hidden="true">
              ✍️
            </span>
            <strong>Khu vực tác giả</strong>
            <span className="hint">Tạo truyện, thêm chương, xuất bản.</span>
          </Link>
          <Link className="quick-card" href="/studio">
            <span className="quick-icon" aria-hidden="true">
              🎙
            </span>
            <strong>Audio Studio</strong>
            <span className="hint">Dán văn bản bất kỳ và tạo MP3.</span>
          </Link>
          <Link className="quick-card" href="/library">
            <span className="quick-icon" aria-hidden="true">
              🎧
            </span>
            <strong>Thư viện audio</strong>
            <span className="hint">Mọi bản audio bạn đã tạo.</span>
          </Link>
        </div>
      </section>

      <section className="card stack">
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
    </div>
  );
}
