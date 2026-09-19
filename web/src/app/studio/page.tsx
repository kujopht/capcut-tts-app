"use client";

/**
 * Fanfic Studio — Tong quan, va tu ban nay la NHA CUA DU AN.
 *
 * Truoc: `/studio` la mot luoi sau cai the cong cu. No tra loi duoc "o day
 * lam duoc nhung gi?" nhung khong tra loi duoc "toi dang lam do dang cai
 * gi?" — va do moi la cau hoi cua nguoi quay lai lan thu hai.
 *
 * TRANG VAN KHONG BAO GIO CHAN. Ghi chu cu o day noi rang mot man hinh xoay
 * vong o `/studio` lam ca bo cong cu co cam giac cham du tung cong cu deu
 * nhanh — dieu do VAN DUNG, nen luoi cong cu ve NGAY va khong doi mang.
 * Danh sach du an la mot khu vuc RIENG co trang thai tai cua no; no hien ra
 * khi san sang, va trang khong dung lai cho no.
 *
 * Danh sach the doc TU `MUC_STUDIO` — cung mang ma thanh ben dung. Chep tay
 * lan hai o day la cach chac chan nhat de mot hom nao do thanh ben ghi "Phụ
 * đề" con the ghi "Subtitle".
 */

import Link from "next/link";
import { useCallback, useState } from "react";
import { studio, type StudioProjectView } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { MUC_STUDIO } from "@/components/StudioShell";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui";

/** Tong quan khong tu quang cao chinh no. */
const THE = MUC_STUDIO.filter((m) => m.href !== "/studio");

export default function StudioOverview() {
  return (
    <section className="stack-5 rise rise-3">
      <DuAnCuaToi />

      <div className="studio-divider" aria-hidden="true">
        <span className="studio-divider-line" />
        <span className="studio-divider-diamond">✦</span>
        <span className="studio-divider-line" />
      </div>

      <div className="stack-2">
        <h2 className="section-title">Hoặc mở thẳng một công cụ</h2>
        <p className="hint">
          Sáu công cụ, một tác phẩm. Mọi thứ bạn tạo ra đều nằm lại trong{" "}
          <Link href="/studio/library">Tác phẩm của tôi</Link>.
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

function DuAnCuaToi() {
  const { profile, loading: dangNapPhien } = useSession();
  const [ten, datTen] = useState("");
  const [dangTao, datDangTao] = useState(false);
  const [loi, datLoi] = useState("");

  const nap = useCallback(() => studio.listProjects(), []);
  const { data, loading, error, reload } = useAsyncData(nap, {
    enabled: Boolean(profile),
  });

  const tao = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const t = ten.trim();
      if (!t) return;
      datDangTao(true);
      datLoi("");
      try {
        await studio.createProject(t);
        datTen("");
        await reload();
      } catch (err) {
        datLoi(err instanceof Error ? err.message : "Không tạo được dự án.");
      } finally {
        datDangTao(false);
      }
    },
    [ten, reload],
  );

  // Khach vang lai: KHONG hien mot khu vuc rong voi nut bi khoa — chi noi
  // mot cau, roi de luoi cong cu ben duoi lam viec cua no.
  if (!dangNapPhien && !profile) {
    return (
      <div className="stack-2">
        <h2 className="section-title">Dự án của bạn</h2>
        <p className="hint">
          <Link href="/login?next=/studio" prefetch={false}>Đăng nhập</Link> để gom nội dung,
          bản dịch, audio và video của một tác phẩm vào một dự án.
        </p>
      </div>
    );
  }

  const ds = data?.projects ?? [];

  return (
    /*
      `card` chu khong phai mot mat kinh rieng: khu nay nam o DAU `/studio`,
      tuc dung cho sang nhat cua tranh nen, va truoc khi co no thi trang bat
      dau bang luoi the — moi the tu mang nen dac, nen khong co chu nao nam
      trai tren may. Dung lai chinh `card` thay vi dinh nghia mot lop gan
      giong: hai be mat gan giong nhau la hai cho co the lech.

      Cach SAI la noi rong lop phu `--toi` cua ca trang — do la ngan sach do
      chu kho dat, va lam ca site toi di de cuu mot doan chu la doi sai thu.
    */
    <section className="stack-3 card" aria-labelledby="sp-du-an">
      <div className="section-head">
        <div className="stack-1">
          <h2 className="section-title" id="sp-du-an">Dự án của bạn</h2>
          <p className="hint">Mỗi dự án nối nội dung, dịch, ảnh, audio, phụ đề và video.</p>
        </div>
      </div>

      <form className="row sp-tao" onSubmit={tao}>
        <input
          className="input"
          placeholder="Tên dự án mới…"
          value={ten}
          onChange={(e) => datTen(e.target.value)}
          aria-label="Tên dự án mới"
          maxLength={120}
        />
        <button type="submit" className="btn btn-primary"
                disabled={!ten.trim() || dangTao}>
          {dangTao ? "Đang tạo…" : "Dự án mới"}
        </button>
      </form>

      {loi ? <ErrorState message={loi} onRetry={() => datLoi("")} /> : null}

      {dangNapPhien || loading ? (
        <SkeletonList count={2} />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : ds.length === 0 ? (
        <EmptyState
          icon="🗂️"
          title="Chưa có dự án nào"
          hint="Tạo một dự án để gom mọi thứ của một tác phẩm về cùng một chỗ."
        />
      ) : (
        <div className="grid sp-the-luoi">
          {ds.map((d) => <TheDuAn key={d.project.project_id} d={d} />)}
        </div>
      )}
    </section>
  );
}

function TheDuAn({ d }: { d: StudioProjectView }) {
  return (
    <Link
      href={`/studio/projects/${d.project.project_id}`}
      className="card card-link sp-the"
      prefetch={false}
    >
      <span className="sp-the-ten">{d.project.title}</span>
      <span className="sp-the-do">
        {d.progress.map((p) => (
          <span key={p.stage} className="sp-the-hang">
            <span className="sp-the-chang">{p.label}</span>
            <span className={`sp-the-so${p.done ? " sp-xong" : ""}`}>
              {/*
                `total === null` = KHONG co mau so that. Hien so luong tran,
                khong bia mot ty le — xem `TienDoChang` o backend.
              */}
              {p.total === null
                ? p.count > 0 ? p.count : "—"
                : p.total === 1
                  ? p.done ? "✓" : "—"
                  : `${p.count}/${p.total}`}
            </span>
          </span>
        ))}
      </span>
      <span className="btn btn-sm sp-the-tiep" aria-hidden="true">Tiếp tục</span>
    </Link>
  );
}
