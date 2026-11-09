"use client";

import dynamic from "next/dynamic";

/**
 * Cầu nối tải lười: vỏ giao diện chỉ được nạp khi route game được hiển thị (không SSR — game chỉ chạy trên trình duyệt). Mã runtime/canvas còn tách
 * thêm một lớp nữa: `InkScoutShell` chỉ `import()` nó khi người chơi bấm Chơi.
 */
const Shell = dynamic(() => import("./InkScoutShell"), {
  ssr: false,
  loading: () => (
    <div className="page" role="status">
      <p className="hint">Đang tải game…</p>
    </div>
  ),
});

export default function InkScoutLoader() {
  return <Shell />;
}
