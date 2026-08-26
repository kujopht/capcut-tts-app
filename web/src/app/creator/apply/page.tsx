"use client";

/**
 * Dang ky tac gia.
 *
 * Trang nay mo ra khi nguoi dung bam "Xuat ban" ma chua duoc duyet — thay vi mot
 * loi 403 tro troi. Do la ca ly do no ton tai: cho do la mot khoanh khac nguoi
 * ta VUA viet xong mot chuong va dang muon dua no ra, nen thu ho can khong phai
 * mot thong bao tu choi ma la buoc tiep theo.
 *
 * KHONG hoi thong tin danh tinh doi thuc: khong so CMND, khong ngay sinh, khong
 * dia chi. Muc dich cua buoc duyet la chan spam va noi dung sai quy dinh, khong
 * phai lap mot ho so cong dan — va du lieu khong thu thap la du lieu khong the
 * bi ro ri.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { ApiError, api, type CreatorState } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { AuthorBadge } from "@/components/AuthorBadge";
import { IconFeather, IconKey } from "@/components/Icons";
import { ErrorState, Loading } from "@/components/ui";

/**
 * The loai goi y. Nguoi dung van go duoc the rieng — day chi la loi moi, khong
 * phai mot danh sach dong.
 */
const THE_GOI_Y = [
  "One Piece",
  "Naruto",
  "Nguyên tác khác",
  "Giả tưởng",
  "Lãng mạn",
  "Phiêu lưu",
  "Hài hước",
  "Trinh thám",
];

export default function CreatorApplyPage() {
  return (
    <Suspense fallback={<div className="page"><Loading /></div>}>
      <NoiDung />
    </Suspense>
  );
}

function NoiDung() {
  const router = useRouter();
  const params = useSearchParams();
  const { profile, loading: dangTaiPhien } = useSession();
  const toast = useToast();

  /*
    `useAsyncData` chu khong tu viet `useEffect` + `setState`: quy tac
    `react-hooks/set-state-in-effect` cam goi `setState` DONG BO trong than
    effect, va hook do la cho du an nay da giai quyet dieu do mot lan.
  */
  const nap = useCallback(
    () => (profile ? api.creatorMe() : Promise.resolve(null)),
    [profile],
  );
  const { data: trangThai, loading: dangTai, error: loi, reload: tai } =
    useAsyncData<CreatorState | null>(nap);

  /*
    Cac o nhap: `undefined` = NGUOI DUNG CHUA GO GI, nen lay gia tri tu don cu.
    Chuoi rong la mot gia tri THAT — nguoi dung vua xoa het o do — va phan biet
    hai thu nay la ly do o day dung `?? mac_dinh` chu khong phai `|| mac_dinh`.
  */
  const don = trangThai?.application ?? null;
  const [butDanhGo, setButDanh] = useState<string | undefined>();
  const [gioiThieuGo, setGioiThieu] = useState<string | undefined>();
  const [tieuSuGo, setTieuSu] = useState<string | undefined>();
  const [theGo, setThe] = useState<string[] | undefined>();
  const [dongY, setDongY] = useState(false);
  const [dangGui, setDangGui] = useState(false);

  const butDanh = butDanhGo ?? don?.pen_name ?? "";
  const gioiThieu = gioiThieuGo ?? don?.intro ?? "";
  const tieuSu = tieuSuGo ?? don?.bio ?? trangThai?.bio ?? "";
  const the = theGo ?? don?.genres ?? [];

  if (dangTaiPhien || dangTai) {
    return <div className="page"><Loading /></div>;
  }

  if (!profile) {
    return (
      <div className="page auth-page">
        <header className="auth-head">
          <h1 className="page-title">Đăng ký tác giả</h1>
          <p className="hint">Bạn cần đăng nhập trước khi gửi đơn.</p>
        </header>
        <Link className="btn btn-primary btn-block" href="/login?next=/creator/apply" prefetch={false}>
          Đăng nhập
        </Link>
      </div>
    );
  }

  if (loi) {
    return <div className="page"><ErrorState message={loi} onRetry={tai} /></div>;
  }

  const status = trangThai?.author_status ?? "none";
  const quayVe = params.get("next") || "/write";

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    setDangGui(true);
    try {
      await api.applyAuthor({
        pen_name: butDanh.trim(),
        bio: tieuSu.trim(),
        genres: the,
        intro: gioiThieu.trim(),
        accepted_rules: dongY,
      });
      toast.ok("Đã gửi đơn. Bạn vẫn viết và sửa bản nháp bình thường.");
      await tai();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Không gửi được đơn.");
    } finally {
      setDangGui(false);
    }
  }

  return (
    <div className="page">
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <Link href={quayVe} className="hint crumb">
          ← Quay lại
        </Link>
      </nav>

      <header className="page-head">
        <div className="page-head-body stack-2">
          <span className="eyebrow eyebrow-icon">
            <IconFeather size={17} /> Khu vực tác giả
          </span>
          <h1 className="page-title">Đăng ký tác giả</h1>
          <p className="lead lead-narrow">
            Ai cũng viết và lưu bản nháp được. Đăng ký tác giả là bước cần cho
            việc <strong>xuất bản công khai</strong> — để truyện đến được với
            người đọc khác.
          </p>
        </div>
      </header>

      {status === "approved" ? (
        <section className="card stack">
          <h2 className="section-title section-title-icon">
            <IconKey size={19} /> Bạn đã là tác giả
          </h2>
          <p>
            <AuthorBadge /> Bạn xuất bản truyện được rồi.
          </p>
          <div className="row">
            <Link className="btn btn-primary" href="/write" prefetch={false}>
              Về khu vực tác giả
            </Link>
          </div>
        </section>
      ) : status === "pending" ? (
        <section className="card stack">
          <h2 className="section-title">Đơn của bạn đang chờ duyệt</h2>
          <p className="hint">
            Trong lúc chờ, bạn <strong>vẫn viết và sửa bản nháp bình thường</strong>
            . Chỉ nút xuất bản là còn khoá.
          </p>
          {trangThai?.application ? (
            <dl className="don-tom-tat">
              <dt>Bút danh</dt>
              <dd>{trangThai.application.pen_name}</dd>
              <dt>Gửi lúc</dt>
              <dd>{new Date(trangThai.application.created_at).toLocaleString("vi-VN")}</dd>
            </dl>
          ) : null}
          <div className="row">
            <Link className="btn" href="/write" prefetch={false}>
              Tiếp tục viết bản nháp
            </Link>
          </div>
        </section>
      ) : status === "suspended" ? (
        <section className="card stack">
          <h2 className="section-title">Quyền xuất bản đang bị tạm dừng</h2>
          <p className="hint">
            Truyện bạn đã xuất bản <strong>vẫn công khai</strong> và người đọc vẫn
            nghe được. Chỉ việc xuất bản mới là bị dừng.
          </p>
        </section>
      ) : (
        <div className="split-narrow page-lam-viec">
          <aside className="stack">
            {status === "rejected" && trangThai?.application ? (
              <section className="card stack-2">
                <h2 className="section-title">Đơn trước chưa được duyệt</h2>
                {trangThai.application.reviewer_note ? (
                  <blockquote className="ghi-chu-duyet">
                    {trangThai.application.reviewer_note}
                  </blockquote>
                ) : null}
                {!trangThai.can_apply ? (
                  <p className="hint">{trangThai.apply_blocked_reason}</p>
                ) : (
                  <p className="hint">Bạn sửa lại rồi gửi lần nữa được.</p>
                )}
              </section>
            ) : null}

            <section className="card stack-2">
              <h2 className="section-title">Quy định xuất bản</h2>
              <ul className="quy-dinh">
                <li>Chỉ đăng truyện do chính bạn viết.</li>
                <li>Ghi rõ nguyên tác nếu là fanfic.</li>
                <li>Không đăng nội dung vi phạm pháp luật.</li>
                <li>Không spam, không đăng lại hàng loạt.</li>
              </ul>
              <p className="hint">
                Đây là bản MVP riêng tư. Chưa có thanh toán, và tài khoản của bạn
                không bị thu thêm thông tin cá nhân nào.
              </p>
            </section>
          </aside>

          <section className="stack-5">
            <form className="card stack" onSubmit={gui}>
              <div className="field">
                <label className="label" htmlFor="ap-but">
                  Bút danh <span className="hint">(tên hiện với người đọc)</span>
                </label>
                <input
                  id="ap-but"
                  className="input"
                  value={butDanh}
                  onChange={(e) => setButDanh(e.target.value)}
                  maxLength={60}
                  required
                  autoComplete="off"
                />
              </div>

              <div className="field">
                <label className="label" htmlFor="ap-tieu-su">
                  Giới thiệu ngắn <span className="hint">(hiện trên trang của bạn)</span>
                </label>
                <textarea
                  id="ap-tieu-su"
                  className="textarea textarea-sm"
                  value={tieuSu}
                  onChange={(e) => setTieuSu(e.target.value)}
                  maxLength={400}
                  rows={3}
                />
              </div>

              <fieldset className="field">
                <legend className="label">Bạn viết về gì</legend>
                <div className="the-chon">
                  {THE_GOI_Y.map((t) => {
                    const chon = the.includes(t);
                    return (
                      <button
                        key={t}
                        type="button"
                        className={`chip${chon ? " chip-chon" : ""}`}
                        aria-pressed={chon}
                        onClick={() =>
                          setThe(
                            the.includes(t)
                              ? the.filter((x) => x !== t)
                              : the.length >= 8
                                ? the
                                : [...the, t],
                          )
                        }
                      >
                        {t}
                      </button>
                    );
                  })}
                </div>
                <p className="hint">Chọn tối đa 8 thẻ. Có thể bỏ trống.</p>
              </fieldset>

              <div className="field">
                <label className="label" htmlFor="ap-gioi-thieu">
                  Vài dòng về bạn và truyện bạn định viết
                </label>
                <textarea
                  id="ap-gioi-thieu"
                  className="textarea"
                  value={gioiThieu}
                  onChange={(e) => setGioiThieu(e.target.value)}
                  maxLength={1000}
                  rows={6}
                  required
                  aria-describedby="ap-gt-hint"
                />
                <p className="hint" id="ap-gt-hint">
                  Không cần dài. Vài câu thật là đủ.
                </p>
              </div>

              <label className="dong-y">
                <input
                  type="checkbox"
                  checked={dongY}
                  onChange={(e) => setDongY(e.target.checked)}
                />
                <span>Tôi đã đọc và đồng ý với quy định xuất bản.</span>
              </label>

              <div className="row">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={dangGui || !dongY || trangThai?.can_apply === false}
                >
                  {dangGui ? "Đang gửi…" : "Gửi đơn"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => router.push(quayVe)}
                >
                  Để sau
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
