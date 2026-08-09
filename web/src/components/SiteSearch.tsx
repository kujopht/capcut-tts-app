"use client";

/**
 * O tim kiem trong header.
 *
 * CO Y NHO. Truoc day khong co o tim nao o header, va cach de nhat la dan mot
 * thanh tim khong lo giua trang chu — nhung day la trang de DOC truyen, khong
 * phai cong cu tra cuu. Thanh tim to chiem cho cua thu nguoi doc thuc su can
 * thay: bia va ten truyen.
 *
 * KHONG tu tim. Form nay chi DIEU HUONG sang `/fanfic?q=...`, noi da co san
 * toan bo phan tim/loc/phan trang do BACKEND lam (xem `L2` trong
 * `tests/final-polish.test.mjs`). Nhan ban mot duong tim thu hai o day la cach
 * chac chan de hai ben lech nhau.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

export function SiteSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");

  return (
    <form
      className="site-search"
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        const needle = q.trim();
        router.push(needle ? `/fanfic?q=${encodeURIComponent(needle)}` : "/fanfic");
      }}
    >
      <label className="sr-only" htmlFor="site-search-input">
        Tìm truyện
      </label>
      <input
        id="site-search-input"
        className="input input-search"
        type="search"
        placeholder="Tìm truyện…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <button type="submit" className="btn btn-ghost btn-sm site-search-go">
        Tìm
      </button>
    </form>
  );
}
