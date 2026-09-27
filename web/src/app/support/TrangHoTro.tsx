"use client";

import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/ui";
import { SupportPanel } from "@/components/support/SupportPanel";
import { duongDanAnToan, maLoi } from "@/lib/support/sanitize";

const ID = /^[A-Za-z0-9_-]{1,64}$/;

export function TrangHoTro() {
  const p = useSearchParams();
  const tu = p.get("from");
  const chuong = p.get("chapter") ?? "";
  const truyen = p.get("novel") ?? "";
  const rm = p.get("rm") ?? "";
  const boiCanh = {
    ...(tu ? { route: duongDanAnToan(tu) } : {}),
    ...(maLoi(p.get("err")) ? { last_error_code: maLoi(p.get("err")) } : {}),
    ...(ID.test(chuong) ? { chapter_id: chuong } : {}),
    ...(ID.test(truyen) ? { novel_id: truyen } : {}),
    ...(["read", "listen", "read_listen"].includes(rm) ? { reader_mode: rm } : {}),
  };
  return (
    <div className="page">
      <PageHeader
        eyebrow="Trợ giúp"
        title="Trợ giúp Fanfic World"
        lead="Hỏi trợ lý hoặc báo lỗi kỹ thuật. Trợ lý kiểm tra hệ thống (chỉ đọc) rồi giải thích — không rõ thì chuyển cho quản trị viên."
      />
      <SupportPanel boiCanhDau={boiCanh} cheDoDau={p.get("mode") === "report" || boiCanh.last_error_code ? "report" : "qa"} />
    </div>
  );
}
