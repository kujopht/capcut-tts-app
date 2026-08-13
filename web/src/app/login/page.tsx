"use client";

/** Dang nhap / dang ky. Mot form, doi che do bang nut chuyen. */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { Alert, Loading } from "@/components/ui";
import { LogoMark } from "@/components/Logo";
import { safeNext } from "@/lib/nav";
import { api } from "@/lib/api";
import { FacebookIcon, GoogleIcon } from "@/components/ProviderIcons";
import { FACEBOOK_LOGIN_ENABLED, GOOGLE_LOGIN_ENABLED } from "@/lib/oauth";

const MIN_PASSWORD = 8;

/**
 * `useSearchParams` bat trang phai co ranh gioi Suspense khi Next dung san
 * trang. Thieu no thi `next build` bao loi chu khong phai loi luc chay.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<div className="page"><Loading /></div>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  /*
    Noi can quay lai sau khi dang nhap. TRUOC DAY trang nay luon day nguoi
    dung sang `/studio` — dung o thoi Audio Studio la mat tien, sai bay gio:
    ai bam "Viết truyện" roi dang nhap se bi tha vao mot cong cu khac han.

    `safeNext` chan open redirect. Xem ghi chu o `lib/nav.ts` — kiem o day la
    CHUA DU, backend cung phai kiem vi no nhan `next` truc tiep tu URL.
  */
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  // `?error=oauth` do backend dat khi nha cung cap tu choi. Chi la mot co,
  // khong mang chi tiet nao tu Appwrite.
  const oauthError = params.get("error") === "oauth";
  const toast = useToast();
  const { profile, loading, signIn, signUp } = useSession();

  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Da dang nhap thi khong o lai trang nay
  useEffect(() => {
    if (!loading && profile) router.replace(next);
  }, [loading, profile, router, next]);

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!email.includes("@")) {
        setError("Email không hợp lệ.");
        return;
      }
      if (password.length < MIN_PASSWORD) {
        setError(`Mật khẩu phải có ít nhất ${MIN_PASSWORD} ký tự.`);
        return;
      }
      setBusy(true);
      setError("");
      try {
        if (mode === "in") {
          await signIn(email, password);
          toast.ok("Đã đăng nhập.");
        } else {
          await signUp(email, password, displayName);
          toast.ok("Tạo tài khoản thành công.");
        }
        router.replace(next);
      } catch (cause) {
        setError(errorMessage(cause));
      } finally {
        setBusy(false);
      }
    },
    [email, password, displayName, mode, signIn, signUp, router, toast, next],
  );

  if (loading) {
    return (
      <div className="page">
        <Loading label="Đang kiểm tra phiên đăng nhập…" />
      </div>
    );
  }

  return (
    <div className="page auth-page">
      <header className="auth-head">
        <LogoMark size={54} title="Fanfic Audio Studio" />
        <h1 className="page-title">
          {mode === "in" ? "Đăng nhập" : "Tạo tài khoản"}
        </h1>
        <p className="hint">
          {mode === "in"
            ? "Đăng nhập để tạo audio và quản lý truyện của bạn."
            : "Tạo tài khoản miễn phí để bắt đầu."}
        </p>
      </header>

      <div className="seg auth-seg" role="group" aria-label="Chế độ">
        <button
          type="button"
          className="seg-item"
          aria-pressed={mode === "in"}
          onClick={() => {
            setMode("in");
            setError("");
          }}
        >
          Đăng nhập
        </button>
        <button
          type="button"
          className="seg-item"
          aria-pressed={mode === "up"}
          onClick={() => {
            setMode("up");
            setError("");
          }}
        >
          Đăng ký
        </button>
      </div>

      {/*
        OAuth dat TRUOC form email. Voi phan lon nguoi dung, mot lan bam la
        xong, con go email + mat khau moi la duong dai — dat duong ngan o duoi
        la bat ho doc qua ca cai ho khong dung.

        Day la DIEU HUONG that (`window.location.href`), khong phai `fetch`:
        buoc sau la mot chuoi chuyen tiep qua Appwrite roi qua nha cung cap,
        va no phai xay ra trong thanh dia chi.
      */}
      <div className="card stack-2">
        {oauthError ? (
          <Alert kind="error">
            Đăng nhập bằng nhà cung cấp không thành công. Vui lòng thử lại.
          </Alert>
        ) : null}
        {GOOGLE_LOGIN_ENABLED ? (
          <button
            type="button"
            className="btn btn-block btn-provider"
            onClick={() => {
              window.location.href = api.oauthStartUrl("google", next);
            }}
          >
            <GoogleIcon /> Tiếp tục với Google
          </button>
        ) : null}
        {/*
          Facebook dang TAT. Nut nay KHONG bi xoa — no doc co o `lib/oauth.ts`,
          va toan bo phan hien thuc phia sau van con nguyen. Bat lai la doi mot
          bien moi truong chu khong phai viet lai ma nguon.
        */}
        {FACEBOOK_LOGIN_ENABLED ? (
          <button
            type="button"
            className="btn btn-block btn-provider"
            onClick={() => {
              window.location.href = api.oauthStartUrl("facebook", next);
            }}
          >
            <FacebookIcon /> Tiếp tục với Facebook
          </button>
        ) : null}
      </div>

      <div className="or-line" role="separator">
        <span>hoặc</span>
      </div>

      <form className="card stack" onSubmit={submit}>
        <div className="field">
          <label className="label" htmlFor="login-email">
            Email
          </label>
          <input
            id="login-email"
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label className="label" htmlFor="login-password">
            Mật khẩu
          </label>
          <input
            id="login-password"
            className="input"
            type="password"
            autoComplete={mode === "in" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={MIN_PASSWORD}
            aria-describedby="login-password-hint"
            required
          />
          <span className="hint" id="login-password-hint">
            Ít nhất {MIN_PASSWORD} ký tự.
          </span>
        </div>

        {mode === "up" ? (
          <div className="field">
            <label className="label" htmlFor="login-name">
              Tên hiển thị <span className="hint">(tuỳ chọn)</span>
            </label>
            <input
              id="login-name"
              className="input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              maxLength={120}
            />
          </div>
        ) : null}

        {error ? <Alert kind="error">{error}</Alert> : null}

        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? <span className="spinner" aria-hidden="true" /> : null}
          {mode === "in" ? "Đăng nhập" : "Tạo tài khoản"}
        </button>
      </form>

      <p className="hint auth-foot">
        Chưa muốn đăng nhập?{" "}
        <Link href="/fanfic">Xem trang khám phá Fanfic</Link>
      </p>
    </div>
  );
}
