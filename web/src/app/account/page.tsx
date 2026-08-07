"use client";

/** Trang tai khoan: thong tin ho so va han muc su dung. */

import Link from "next/link";
import { useCallback, useState } from "react";
import { useSession } from "@/lib/session";
import { ConfirmDialog, EmptyState, Loading, formatDate, formatNumber } from "@/components/ui";

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
      <header className="stack-2">
        <span className="eyebrow">Tài khoản</span>
        <h1 className="page-title">
          {profile.display_name || profile.email.split("@")[0]}
        </h1>
        <p className="hint">{profile.email}</p>
      </header>

      <section className="card stack">
        <div className="row-between">
          <h2 className="section-title">Gói hiện tại</h2>
          <span className="badge badge-brand">
            {TIER_LABEL[profile.tier] ?? profile.tier}
          </span>
        </div>
        <p className="hint">
          Bản MVP riêng tư — chưa có thanh toán và chưa trừ hạn mức thực tế.
        </p>
      </section>

      <section className="stack">
        <h2 className="section-title">Sử dụng</h2>
        <div className="row">
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

      <section className="card stack">
        <h2 className="section-title">Lối tắt</h2>
        <div className="row">
          <Link className="btn" href="/studio">
            Audio Studio
          </Link>
          <Link className="btn" href="/library">
            Thư viện audio
          </Link>
          <Link className="btn" href="/write">
            Khu vực tác giả
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
