"use client";

/**
 * Khong gian lam viec cua MOT du an Studio.
 *
 * Sau chang theo DUNG thu tu quy trinh: Nội dung -> Dịch -> Hình ảnh ->
 * Audio -> Phụ đề -> Video. Moi chang la mot the co ba thu: dang o dau, gan
 * them duoc gi, va di thang toi cong cu tuong ung.
 *
 * Trang nay KHONG tu lam viec cua cong cu nao — no khong tao audio, khong
 * dich, khong render. No la cho NOI chung lai, va moi nut "Mở" deu dua toi
 * dung cong cu da co. Gop chuc nang cua sau cong cu vao mot trang la dung
 * lai chinh cai mo hinh ma du an nay sinh ra de thay the.
 */

import Link from "next/link";
import { use, useCallback, useState } from "react";
import {
  STUDIO_STAGES,
  studio,
  type StudioProgress,
  type StudioProjectView,
  type StudioRef,
  type StudioStage,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { StudioToolHeader } from "@/components/StudioShell";
import { StudioAssetPicker } from "@/components/StudioAssetPicker";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import {
  IconBook,
  IconClapper,
  IconFeather,
  IconFilm,
  IconMic,
  IconSparkles,
} from "@/components/Icons";

/** Cong cu cua tung chang — noi thang toi cai da co, khong lam lai. */
const CONG_CU: Record<StudioStage, { href: string; mo: string; icon: (p: { size?: number }) => React.ReactElement }> = {
  noi_dung: { href: "/studio/write", mo: "Mở trình soạn", icon: IconFeather },
  dich: { href: "/studio/translate", mo: "Mở Dịch", icon: IconBook },
  hinh_anh: { href: "/studio/image", mo: "Mở Hình ảnh", icon: IconSparkles },
  audio: { href: "/studio/audio", mo: "Mở Audio", icon: IconMic },
  phu_de: { href: "/studio/subtitle", mo: "Mở Phụ đề", icon: IconFilm },
  video: { href: "/studio/video", mo: "Mở Video", icon: IconClapper },
};

/**
 * CẢ SÁU chặng đều chọn được từ thư viện, kể cả Nội dung.
 *
 * Trước bản này Nội dung không có đường nào ở giao diện: `novel_id` chỉ đặt
 * được bằng `PATCH`, mà không màn hình nào gọi nó. Hậu quả không dừng ở một
 * ô trống — mẫu số của Audio và Phụ đề là SỐ CHƯƠNG của truyện đã gắn, nên
 * một dự án không gắn được truyện thì vĩnh viễn không hiện được "2/4 chương
 * có audio", đúng thứ tiến độ thật mà cả trang này dựng lên để nói.
 */
const CHON_DUOC: StudioStage[] = [...STUDIO_STAGES];

export default function StudioProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile, loading: dangNapPhien } = useSession();
  const [dangMo, datDangMo] = useState<StudioStage | "">("");
  const [loi, datLoi] = useState("");

  const nap = useCallback(() => studio.getProject(id), [id]);
  const { data, loading, error, reload } = useAsyncData(nap, {
    enabled: Boolean(profile),
  });

  /*
    Nội dung đi qua `PATCH novel_id`, năm chặng còn lại đi qua `refs`.

    Hai đường chứ không phải một, vì hai NGHĨA khác nhau: một dự án có MỘT
    truyện (chọn lần nữa là THAY THẾ), còn năm chặng kia là danh sách (chọn
    lần nữa là THÊM). Gộp chúng lại sau một hàm `attach()` duy nhất sẽ khiến
    "gắn" âm thầm mang nghĩa "ghi đè" ở đúng một chặng — xem `StudioProject`.
  */
  const gan = useCallback(
    async (chang: StudioStage, refId: string) => {
      datLoi("");
      try {
        if (chang === "noi_dung") await studio.patchProject(id, { novel_id: refId });
        else await studio.attach(id, chang, refId);
        await reload();
        datDangMo("");
      } catch (e) {
        datLoi(e instanceof Error ? e.message : "Không gắn được.");
      }
    },
    [id, reload],
  );

  const go = useCallback(
    async (chang: StudioStage, refId: string) => {
      datLoi("");
      try {
        if (chang === "noi_dung") await studio.patchProject(id, { novel_id: "" });
        else await studio.detach(id, chang, refId);
        await reload();
      } catch (e) {
        datLoi(e instanceof Error ? e.message : "Không gỡ được.");
      }
    },
    [id, reload],
  );

  if (dangNapPhien) return <Loading />;

  if (!profile) {
    /*
      `prefetch={false}` PHAI nam CUNG DONG voi `href` o duoi: bo kiem
      `static-link-prefetch` quet theo TUNG DONG, nen xuong dong giua hai
      thuoc tinh se lam no bao thieu.
    */
    return (
      <div className="studio-tool">
        <StudioToolHeader />
        <EmptyState
          icon="🗂️"
          title="Đăng nhập để mở dự án"
          action={
            <Link className="btn btn-primary" href="/login?next=/studio" prefetch={false}>
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  if (loading) return <Loading />;
  if (error || !data) {
    return (
      <div className="studio-tool">
        <StudioToolHeader />
        <ErrorState message={error || "Không mở được dự án."} onRetry={reload} />
      </div>
    );
  }

  const { project, progress, refs } = data as StudioProjectView;
  const theoChang: Record<string, StudioProgress> = Object.fromEntries(
    progress.map((p) => [p.stage, p]),
  );

  return (
    <div className="studio-tool sp">
      <StudioToolHeader
        title={project.title}
        lead={project.description || "Dự án Studio — nối các công cụ lại."}
        action={
          <Link className="btn btn-ghost" href="/studio" prefetch={false}>
            ← Tất cả dự án
          </Link>
        }
      />

      {loi ? <ErrorState message={loi} onRetry={() => datLoi("")} /> : null}

      <ol className="sp-chang-ds">
        {STUDIO_STAGES.map((chang, i) => {
          const p = theoChang[chang];
          const cc = CONG_CU[chang];
          const Icon = cc.icon;
          const daGan = refs?.[chang] ?? [];
          return (
            <li key={chang} className={`sp-chang${p?.done ? " sp-chang-xong" : ""}`}>
              <div className="sp-chang-dau">
                <span className="sp-chang-so" aria-hidden="true">{i + 1}</span>
                <span className="sp-chang-ten">
                  <Icon size={16} /> {p?.label ?? chang}
                </span>
                <span className="sp-chang-do">
                  <TienDo p={p} />
                </span>
                <span className="sp-chang-nut">
                  {CHON_DUOC.includes(chang) ? (
                    <button
                      type="button"
                      className="btn btn-sm"
                      aria-expanded={dangMo === chang}
                      onClick={() => datDangMo(dangMo === chang ? "" : chang)}
                    >
                      {chang === "noi_dung"
                        ? project.novel_id ? "Đổi truyện" : "Chọn truyện"
                        : "Thêm"}
                    </button>
                  ) : null}
                  {/*
                    Video mang theo `?studio=` de ban video tao ra duoc GAN
                    NGUOC vao du an nay — khong co no thi nguoi dung phai
                    quay ve day bam "Thêm" de tim lai chinh thu vua tao.
                  */}
                  <Link
                    className="btn btn-sm btn-ghost"
                    href={
                      chang === "video"
                        ? `${cc.href}?studio=${encodeURIComponent(project.project_id)}`
                        : cc.href
                    }
                    prefetch={false}
                  >
                    {cc.mo}
                  </Link>
                </span>
              </div>

              {daGan.length > 0 ? (
                <ul className="sp-gan-ds">
                  {daGan.map((x) => (
                    <li key={x.id} className="sp-gan">
                      <Nhan x={x} />
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        onClick={() => void go(chang, x.id)}
                        aria-label={`Gỡ ${x.label || x.id} khỏi dự án`}
                      >
                        Gỡ
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              {dangMo === chang ? (
                <StudioAssetPicker
                  stage={chang}
                  projectId={project.project_id}
                  onPick={(refId) => gan(chang, refId)}
                  onClose={() => datDangMo("")}
                  emptyHint={`Tạo ở ${cc.mo.replace("Mở ", "")} rồi quay lại.`}
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/**
 * Một mục đã gắn.
 *
 * Tên trước, mã sau và chỉ khi không có tên. Bản trước in thẳng `trk_9f2a…`
 * lên màn hình chính của dự án — đúng thứ máy cần và đúng thứ người không
 * đọc được.
 *
 * `missing` = tài sản đã bị xoá ở công cụ khác. Nói thẳng thay vì giấu: mục
 * này vẫn chiếm một dòng trong dự án, và người dùng cần thấy nó để gỡ ra.
 */
function Nhan({ x }: { x: StudioRef }) {
  if (x.missing) {
    return (
      <span className="stack-1 sp-gan-nhan">
        <code className="truncate sp-gan-ma">{x.id}</code>
        <span className="hint">không còn trong thư viện</span>
      </span>
    );
  }
  return (
    <span className="stack-1 sp-gan-nhan">
      <span className="truncate">{x.label || x.id}</span>
      {x.detail ? <span className="hint">{x.detail}</span> : null}
    </span>
  );
}

/**
 * Tien do MOT chang.
 *
 * `total === null` nghia la KHONG CO mau so that — hien so luong tran chu
 * khong bia mot ty le. Xem `TienDoChang` o backend.
 */
function TienDo({ p }: { p?: StudioProgress }) {
  if (!p) return null;
  if (p.total === null) {
    return <span className="hint">{p.count > 0 ? `${p.count} mục` : "chưa có"}</span>;
  }
  if (p.total === 1) {
    return (
      <span className={p.done ? "sp-xong" : "hint"}>
        {p.done ? "✓ đã có" : "chưa có"}
      </span>
    );
  }
  return (
    <span className={p.done ? "sp-xong" : "hint"}>
      {p.count}/{p.total}
    </span>
  );
}
