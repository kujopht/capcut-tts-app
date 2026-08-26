"use client";

/**
 * Khu CREATOR o trang tai khoan.
 *
 * Nam trong tai khoan chu khong phai mot trang rieng: danh tinh tac gia LA mot
 * phan cua danh tinh nguoi dung, va tach ra thanh mot trang nua se bat nguoi ta
 * nho them mot cho.
 *
 * Nam trang thai, nam hinh dang khac nhau. Cai chung phai tranh: mot khoi duy
 * nhat noi "Trang thai: pending" — do la mot truong du lieu duoc in ra man hinh,
 * khong phai mot cau tra loi cho cau hoi ma nguoi dung dang co ("toi lam duoc gi
 * bay gio?").
 */

import Link from "next/link";
import { useCallback, useState } from "react";
import { ApiError, api, type CreatorState } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { AuthorBadge, RankBadge, RankProgressBar } from "@/components/AuthorBadge";
import { IconFeather, IconHeadphones, IconUser } from "@/components/Icons";
import { formatNumber } from "@/components/ui";

export function CreatorSection() {
  const { profile } = useSession();
  const nap = useCallback(
    () => (profile ? api.creatorMe() : Promise.resolve(null)),
    [profile],
  );
  const { data, loading, reload } = useAsyncData<CreatorState | null>(nap);

  if (!profile || loading || !data) return null;

  return (
    <section className="stack" aria-labelledby="acc-creator">
      <h2 className="section-title section-title-icon" id="acc-creator">
        <IconFeather size={19} /> Danh tính tác giả
      </h2>
      <OTenCongKhai trangThai={data} onXong={reload} />
      <ONoiDung trangThai={data} />
    </section>
  );
}

/**
 * O chon ten cong khai.
 *
 * Hien RIENG va hien TRUOC moi thu khac khi chua co ten: chua co username thi
 * chua co trang cong khai, va moi thu khac trong khu nay — huy hieu, hang, danh
 * sach truyen — deu tro toi mot trang khong ton tai.
 */
function OTenCongKhai({
  trangThai,
  onXong,
}: {
  trangThai: CreatorState;
  onXong: () => void;
}) {
  const toast = useToast();
  const [go, setGo] = useState<string | undefined>();
  const [dangLuu, setDangLuu] = useState(false);
  const ten = go ?? trangThai.username_suggestion ?? "";

  if (trangThai.username) {
    return (
      <div className="card stack-2 ten-cong-khai">
        <div className="row row-spread">
          <span className="hint eyebrow-icon">
            <IconUser size={15} /> Tên công khai
          </span>
          <Link className="btn btn-sm" href={`/u/${trangThai.username}`}>
            Xem trang của bạn
          </Link>
        </div>
        <strong className="mono ten-lon">@{trangThai.username}</strong>
      </div>
    );
  }

  async function luu(e: React.FormEvent) {
    e.preventDefault();
    setDangLuu(true);
    try {
      await api.setUsername(ten);
      toast.ok("Đã đặt tên công khai.");
      onXong();
    } catch (cause) {
      toast.error(
        cause instanceof ApiError ? cause.message : "Không đặt được tên.",
      );
    } finally {
      setDangLuu(false);
    }
  }

  return (
    <form className="card stack-2" onSubmit={luu}>
      <label className="label" htmlFor="acc-username">
        Chọn tên công khai
      </label>
      <p className="hint">
        Đây là địa chỉ trang cá nhân của bạn: <code>/u/tên-của-bạn</code>. Chưa
        chọn thì bạn chưa có trang công khai — và chúng tôi{" "}
        <strong>không tự lấy tên từ email</strong> của bạn.
      </p>
      <div className="row">
        <input
          id="acc-username"
          className="input"
          value={ten}
          onChange={(e) => setGo(e.target.value)}
          maxLength={24}
          autoComplete="off"
          spellCheck={false}
          aria-describedby="acc-username-hint"
        />
        <button className="btn btn-primary" disabled={dangLuu || ten.length < 3}>
          {dangLuu ? "Đang lưu…" : "Đặt tên"}
        </button>
      </div>
      <p className="hint" id="acc-username-hint">
        3–24 ký tự, chỉ chữ không dấu, số, gạch dưới và gạch ngang.
      </p>
    </form>
  );
}

/** Phan doi theo trang thai duyet. */
function ONoiDung({ trangThai }: { trangThai: CreatorState }) {
  const s = trangThai.author_status;

  if (s === "approved") {
    return (
      <div className="card stack">
        <div className="row row-spread creator-dinh">
          <span className="ho-so-hh">
            <AuthorBadge />
            {trangThai.rank ? <RankBadge rank={trangThai.rank} /> : null}
          </span>
          <Link className="btn btn-sm" href="/write" prefetch={false}>
            Khu vực tác giả
          </Link>
        </div>

        <div className="stat-grid">
          <div className="stat">
            <span className="stat-value">
              {formatNumber(trangThai.qualified_listens ?? 0)}
            </span>
            <span className="stat-label">Lượt nghe hợp lệ</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {formatNumber(trangThai.published_novels ?? 0)}
            </span>
            <span className="stat-label">Truyện đã xuất bản</span>
          </div>
        </div>

        {trangThai.rank ? <RankProgressBar rank={trangThai.rank} /> : null}

        <p className="hint eyebrow-icon">
          <IconHeadphones size={15} />
          Một lượt nghe được tính khi người khác nghe ít nhất 30 giây, và mỗi
          người chỉ tính một lần cho mỗi chương trong 24 giờ.
        </p>
      </div>
    );
  }

  if (s === "pending") {
    return (
      <div className="card stack-2">
        <span className="badge">Đang chờ duyệt</span>
        <p className="hint">
          Trong lúc chờ, bạn <strong>vẫn viết và sửa bản nháp bình thường</strong>
          . Chỉ nút xuất bản là còn khoá.
        </p>
        <div className="row">
          <Link className="btn btn-sm" href="/write" prefetch={false}>
            Tiếp tục viết
          </Link>
        </div>
      </div>
    );
  }

  if (s === "suspended") {
    return (
      <div className="card stack-2">
        <span className="badge badge-warn">Tạm dừng xuất bản</span>
        <p className="hint">
          Truyện bạn đã xuất bản <strong>vẫn công khai</strong> và người đọc vẫn
          nghe được. Chỉ việc xuất bản mới là bị dừng.
        </p>
      </div>
    );
  }

  return (
    <div className="card stack-2">
      <h3 className="section-title">
        {s === "rejected" ? "Đơn tác giả chưa được duyệt" : "Bạn cũng viết fanfic?"}
      </h3>
      {s === "rejected" && trangThai.application?.reviewer_note ? (
        <blockquote className="ghi-chu-duyet">
          {trangThai.application.reviewer_note}
        </blockquote>
      ) : (
        <p className="hint">
          Ai cũng viết và lưu bản nháp được. Đăng ký tác giả là bước cần cho việc
          xuất bản công khai.
        </p>
      )}
      <div className="row">
        {trangThai.can_apply ? (
          <Link className="btn btn-primary btn-sm" href="/creator/apply?next=/account" prefetch={false}>
            {s === "rejected" ? "Gửi lại đơn" : "Đăng ký tác giả"}
          </Link>
        ) : (
          <span className="hint">{trangThai.apply_blocked_reason}</span>
        )}
      </div>
    </div>
  );
}
