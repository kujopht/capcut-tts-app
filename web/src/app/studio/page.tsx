"use client";

/**
 * Fanfic Studio — Tong quan.
 *
 * Truoc ban nay `/studio` LA Audio Studio. Dieu do lam "Studio" vua la ten
 * cua ca bo cong cu vua la ten cua MOT cong cu trong bo — nen khong cho nao
 * tra loi duoc cau hoi dau tien cua nguoi moi: "o day lam duoc nhung gi?".
 * Audio Studio nay o `/studio/audio`, va cho nay tra loi cau hoi do.
 *
 * Trang CO Y mong. No khong goi API, khong co trang thai tai, khong the
 * hong. Ly do: day la trang dau tien nguoi dung thay khi bam "Studio" tren
 * thanh dieu huong, va mot man hinh xoay vong o day se lam ca bo cong cu co
 * cam giac cham du tung cong cu deu nhanh.
 *
 * Danh sach the doc TU `MUC_STUDIO` — cung mang ma thanh ben dung. Chep tay
 * lan hai o day la cach chac chan nhat de mot hom nao do thanh ben ghi "Phụ
 * đề" con the ghi "Subtitle".
 */

import Link from "next/link";
import { MUC_STUDIO } from "@/components/StudioShell";

/** Tong quan khong tu quang cao chinh no. */
const THE = MUC_STUDIO.filter((m) => m.href !== "/studio");

export default function StudioOverview() {
  return (
    <section className="stack-5">
      <div className="stack-2">
        <h2 className="section-title">Bắt đầu từ đâu?</h2>
        <p className="hint">
          Sáu công cụ, một tác phẩm. Chọn việc bạn đang làm — mọi thứ bạn tạo
          ra đều nằm lại trong <Link href="/studio/library">Tác phẩm của tôi</Link>.
        </p>
      </div>

      <div className="grid studio-the-luoi">
        {THE.map(({ href, nhan, mo_ta, icon: Icon }) => (
          <Link key={href} href={href} className="card card-link studio-the">
            <span className="studio-the-icon" aria-hidden="true">
              <Icon size={22} />
            </span>
            <span className="stack-2">
              <span className="studio-the-nhan">{nhan}</span>
              <span className="hint">{mo_ta}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
