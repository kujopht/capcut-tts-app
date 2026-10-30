"use client";

/**
 * Trang dang ky Premium (rieng, theo yeu cau 2026-10-30).
 *
 * - Premium = tier ULTRA: mo khoa cac tap sau tap dau moi bo (cap theo
 *   tap, backend gate `gate:premium-after-N`).
 * - Giai doan dau MIEN PHI cho tai khoan da xac minh Gmail: dang ky bang
 *   Google duoc Appwrite danh dau da xac minh ngay.
 * - Tool TTS trong Studio TAM THOI van mien phi cho moi nguoi — khong
 *   thuoc pham vi Premium, ghi ro de khong ai tuong no bi khoa.
 * - Premium CHI tinh khi doc/nghe truyen; khong khoa tool khac.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSession, errorMessage } from "@/lib/session";
import { api } from "@/lib/api";
import { GOOGLE_LOGIN_ENABLED } from "@/lib/oauth";
import { EmptyState, Loading } from "@/components/ui";

const TIER_LABEL: Record<string, string> = {
  free: "Miễn phí",
  listener_pro: "Người nghe Pro",
  creator_pro: "Tác giả Pro",
  ultra: "Premium",
};

function laPremium(tier: string | undefined) {
  return tier === "listener_pro" || tier === "ultra";
}

interface TrangThaiPremium {
  tier: string;
  email: string;
  email_verified: boolean;
}

export default function PremiumPage() {
  const { profile, loading, updateProfile } = useSession();
  const [status, setStatus] = useState<TrangThaiPremium | null>(null);
  const [dangKichHoat, setDangKichHoat] = useState(false);
  const [thongBao, setThongBao] = useState("");

  const taiStatus = useCallback(async () => {
    try {
      setStatus(await api.premiumStatus());
    } catch (err) {
      setThongBao(errorMessage(err));
    }
  }, []);

  // Chi setState trong callback bat dong bo (sau await) — khong setState
  // dong bo trong than effect (quy tac react-hooks/set-state-in-effect).
  useEffect(() => {
    if (loading || !profile) return;
    let huy = false;
    void (async () => {
      try {
        const s = await api.premiumStatus();
        if (!huy) setStatus(s);
      } catch (err) {
        if (!huy) setThongBao(errorMessage(err));
      }
    })();
    return () => {
      huy = true;
    };
  }, [loading, profile]);

  const kichHoat = async () => {
    setDangKichHoat(true);
    setThongBao("");
    try {
      const r = await api.premiumActivate();
      if (r.already) {
        setThongBao("Tài khoản của bạn đã là Premium.");
      } else {
        setThongBao(
          "Kích hoạt Premium thành công! Giờ bạn nghe và đọc được full tất cả các tập.",
        );
      }
      const me = await api.me();
      updateProfile(me.profile);
      await taiStatus();
    } catch (err) {
      setThongBao(errorMessage(err));
    } finally {
      setDangKichHoat(false);
    }
  };

  if (loading || (profile && !status && !thongBao)) {
    return (
      <div className="page">
        <Loading />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="page">
        <EmptyState
          icon="⭐"
          title="Premium — nghe full mọi bộ truyện"
          action={
            <>
              <Link className="btn btn-primary" href="/login" prefetch={false}>
                Đăng nhập
              </Link>
              {GOOGLE_LOGIN_ENABLED ? (
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => {
                    window.location.href = api.oauthStartUrl("google", "/premium");
                  }}
                >
                  Đăng ký bằng Google
                </button>
              ) : null}
            </>
          }
        />
      </div>
    );
  }

  const premium = status ? laPremium(status.tier) : laPremium(profile.tier);

  if (!status) {
    return (
      <div className="page">
        <h1>Premium</h1>
        <p>Không tải được trạng thái Premium.</p>
        {thongBao ? <p className="hint">{thongBao}</p> : null}
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void taiStatus()}
        >
          Thử lại
        </button>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Premium</h1>
      <p className="hint">
        Gói hiện tại của bạn:{" "}
        <strong>{TIER_LABEL[status?.tier ?? profile.tier] ?? profile.tier}</strong>
      </p>

      <ul>
        <li>Nghe và đọc full tất cả các tập — không còn giới hạn tập đầu.</li>
        <li>Áp dụng cho mọi bộ truyện có khóa premium.</li>
        <li>Giai đoạn đầu: miễn phí cho tài khoản đã xác minh Gmail.</li>
        <li>
          Tool TTS trong Studio vẫn miễn phí cho mọi người (tạm thời, không
          thuộc Premium).
        </li>
      </ul>

      {premium ? (
        <>
          <p>
            ⭐ Bạn đang là Premium. Vào thư viện và nghe tiếp thôi — không còn
            tập nào bị khóa.
          </p>
          <Link className="btn btn-primary" href="/library" prefetch={false}>
            Về Thư viện
          </Link>
        </>
      ) : status && !status.email_verified ? (
        <>
          <p>
            Tài khoản của bạn (<strong>{status.email}</strong>) chưa xác minh
            Gmail nên chưa kích hoạt được Premium. Cách nhanh nhất hiện nay:
            đăng nhập bằng Google để xác minh ngay.
          </p>
          {GOOGLE_LOGIN_ENABLED ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                window.location.href = api.oauthStartUrl("google", "/premium");
              }}
            >
              Đăng nhập bằng Google
            </button>
          ) : null}
        </>
      ) : (
        <>
          <p>
            Tài khoản của bạn đã xác minh Gmail — bấm nút dưới để kích hoạt
            Premium miễn phí ngay.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            disabled={dangKichHoat}
            onClick={() => void kichHoat()}
          >
            {dangKichHoat ? "Đang kích hoạt…" : "Kích hoạt Premium miễn phí"}
          </button>
        </>
      )}

      {thongBao ? <p className="hint">{thongBao}</p> : null}
    </div>
  );
}
