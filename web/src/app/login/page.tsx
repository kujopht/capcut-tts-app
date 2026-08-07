"use client";

/** Dang nhap / dang ky. Mot form, doi che do bang nut chuyen. */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { Alert, Loading } from "@/components/ui";
import { LogoMark } from "@/components/Logo";

const MIN_PASSWORD = 8;

export default function LoginPage() {
  const router = useRouter();
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
    if (!loading && profile) router.replace("/studio");
  }, [loading, profile, router]);

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
        router.replace("/studio");
      } catch (cause) {
        setError(errorMessage(cause));
      } finally {
        setBusy(false);
      }
    },
    [email, password, displayName, mode, signIn, signUp, router, toast],
  );

  if (loading) {
    return (
      <div className="page">
        <Loading label="Đang kiểm tra phiên đăng nhập…" />
      </div>
    );
  }

  return (
    <div className="page" style={{ maxWidth: 460, margin: "0 auto", width: "100%" }}>
      <header className="stack-2" style={{ textAlign: "center", alignItems: "center" }}>
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

      <div className="seg" role="group" aria-label="Chế độ" style={{ alignSelf: "center" }}>
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

      <p className="hint" style={{ textAlign: "center" }}>
        Chưa muốn đăng nhập?{" "}
        <Link href="/fanfic">Xem trang khám phá Fanfic</Link>
      </p>
    </div>
  );
}
