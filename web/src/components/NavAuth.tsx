"use client";

/** Phan dieu huong phu thuoc phien dang nhap. */

import Link from "next/link";
import { useSession } from "@/lib/session";

export function NavAuth() {
  const { profile, loading, signOut } = useSession();

  if (loading) {
    return (
      <span className="hint" style={{ padding: "7px 12px" }} role="status">
        ...
      </span>
    );
  }

  if (!profile) {
    return <Link href="/login">Đăng nhập</Link>;
  }

  return (
    <>
      <span
        className="hint"
        style={{ padding: "7px 12px" }}
        title={profile.email}
      >
        {profile.display_name}
      </span>
      <button
        type="button"
        className="btn"
        style={{ padding: "6px 12px", fontSize: 13 }}
        onClick={signOut}
      >
        Đăng xuất
      </button>
    </>
  );
}
