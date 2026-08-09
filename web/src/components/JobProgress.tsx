"use client";

/**
 * Khung tien do cua mot job TTS — MOT ban duy nhat cho ca `/write` va `/studio`.
 *
 * Y nghia cua cac con so nam o `lib/jobs.ts::tienDoJob`; cho nay chi ve. Tach
 * ra vi hai trang tung tu ve lay va da lech nhau that: `/write` hien
 * "Đang xử lý · 71%" kem "5 / 7 phần", con `/studio` hien mot thanh chay vo
 * dinh voi 8% bia ra.
 *
 * Cac nut hanh dong (nghe lai, thu lai, tao cai khac) KHONG o day: chung khac
 * nhau that giua hai trang. Chi phan doc — trang thai va tien do — la chung.
 */

import type { ReactNode } from "react";
import type { TtsJob } from "@/lib/api";
import { tienDoJob } from "@/lib/jobs";
import { JobBadge, ProgressBar } from "./ui";

/** Trang thai job -> hau to lop cua khung. CHI de to mau, khong suy ra so. */
const VE_THEO: Record<string, string> = {
  pending: "job-box-live",
  running: "job-box-live",
  completed: "job-box-done",
  failed: "job-box-failed",
};

export function JobProgress({
  job,
  tieuDe,
  ghiChu,
}: {
  job: TtsJob;
  /** Dong chu ben trai hang dau, vi du ten chuong. */
  tieuDe?: ReactNode;
  /** Giai thich them, vi du vi sao job dang xep hang. */
  ghiChu?: ReactNode;
}) {
  const tien_do = tienDoJob(job);
  // Job that bai thi khong ve thanh: trang goi se hien Alert kem nguyen nhan.
  const co_thanh = job.status !== "failed";
  const xong = job.status === "completed";

  return (
    <div
      className={`job-box ${VE_THEO[job.status] ?? "job-box-live"}`}
      aria-live="polite"
    >
      <div className="row-between">
        <span className="hint">{tieuDe ?? "Tiến trình tạo audio"}</span>
        <JobBadge status={job.status} />
      </div>

      {co_thanh ? (
        <>
          {/*
            `progress-done` tat vet sang chay tren thanh. Mot vet sang vinh
            vien sau khi job da xong la nhieu loan: no noi rang con viec dang
            chay trong khi khong con.
          */}
          <div className={xong ? "progress-done" : undefined}>
            <ProgressBar
              percent={tien_do.percent}
              indeterminate={!tien_do.biet_tong}
              label={tien_do.nhan}
            />
          </div>
          <div className="job-figures">
            <span className="job-percent">
              {tien_do.biet_tong ? `${tien_do.percent}%` : tien_do.nhan}
            </span>
            {tien_do.chi_tiet ? (
              <span className="hint">{tien_do.chi_tiet}</span>
            ) : null}
          </div>
        </>
      ) : null}

      {ghiChu}
    </div>
  );
}
