"use client";

/** Dang nhap / dang ky. Phien do backend cap; frontend khong giu bi mat nao. */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { Alert } from "@/components/states";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const { profile, signIn, signUp } = useSession();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [identityMode, setIdentityMode] = useState<string>("");

  // Noi ro dang dung danh tinh mock hay Appwrite that - khong duoc gia vo.
  useEffect(() => {
    api
      .health()
      .then((h) => setIdentityMode(String(h.identity ?? "")))
      .catch(() => setIdentityMode(""));
  }, []);

  useEffect(() => {
    if (profile) router.push("/studio");
  }, [profile, router]);

  function validate(): string {
    if (!email.trim() || !email.includes("@")) return "Email không hợp lệ.";
    if (password.length < 8) return "Mật khẩu phải có ít nhất 8 ký tự.";
    return "";
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await signIn(email.trim(), password);
      else await signUp(email.trim(), password, displayName.trim());
      router.push("/studio");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 430, margin: "56px auto" }}>
      <h1 style={{ fontSize: 26, marginBottom: 6 }}>
        {mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
      </h1>
      <p className="page-sub">
        {mode === "login"
          ? "Đăng nhập để vào Creator Studio."
          : "Tạo tài khoản để bắt đầu viết và tạo audio."}
      </p>

      {identityMode === "mock" ? (
        <Alert kind="warn">
          Đang dùng danh tính <strong>mock cục bộ</strong>, chưa kết nối
          Appwrite. Tài khoản chỉ tồn tại trong lúc backend đang chạy.
        </Alert>
      ) : null}

      <form className="card" onSubmit={submit} noValidate>
        {error ? <Alert kind="error">{error}</Alert> : null}

        {mode === "register" ? (
          <div className="field">
            <label className="label" htmlFor="display-name">
              Tên hiển thị
            </label>
            <input
              id="display-name"
              className="input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="nickname"
              placeholder="Tuỳ chọn"
            />
          </div>
        ) : null}

        <div className="field">
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            className="input"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="ban@example.com"
          />
        </div>

        <div className="field">
          <label className="label" htmlFor="password">
            Mật khẩu
          </label>
          <input
            id="password"
            className="input"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={
              mode === "login" ? "current-password" : "new-password"
            }
            placeholder="Ít nhất 8 ký tự"
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={busy}
          style={{ width: "100%", justifyContent: "center" }}
        >
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" /> Đang xử lý...
            </>
          ) : mode === "login" ? (
            "Đăng nhập"
          ) : (
            "Tạo tài khoản"
          )}
        </button>
      </form>

      <p style={{ textAlign: "center", marginTop: 18 }}>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError("");
          }}
        >
          {mode === "login"
            ? "Chưa có tài khoản? Đăng ký"
            : "Đã có tài khoản? Đăng nhập"}
        </button>
      </p>

      <p className="hint" style={{ textAlign: "center" }}>
        <Link href="/library">Xem thư viện mà không cần đăng nhập</Link>
      </p>
    </div>
  );
}
