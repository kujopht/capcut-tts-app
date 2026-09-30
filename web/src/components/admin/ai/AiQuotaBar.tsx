"use client";

/**
 * Một thanh tiến độ hạn mức dùng chung (yêu cầu/token/chi phí hôm nay so với
 * trần) — vẽ bằng CSS thuần (không thư viện), tôn trọng
 * `prefers-reduced-motion` (transition tắt qua `.ai-quota-bar-fill` trong
 * globals.css).
 *
 * `cap <= 0` nghĩa là CHƯA ĐẶT TRẦN (0 = không giới hạn ở API) — hiện "Không
 * giới hạn" thay vì một thanh 0% gây hiểu lầm là đã dùng hết.
 */
export function AiQuotaBar({
  nhan,
  daDung,
  tran,
  dinhDang,
}: {
  nhan: string;
  daDung: number;
  tran: number;
  /** Định dạng số hiển thị — mặc định `toLocaleString("vi-VN")`. */
  dinhDang?: (n: number) => string;
}) {
  const fmt = dinhDang ?? ((n: number) => n.toLocaleString("vi-VN"));
  const khongGioiHan = tran <= 0;
  const phanTram = khongGioiHan ? 0 : Math.min(100, Math.round((daDung / tran) * 100));
  const vuotTran = !khongGioiHan && daDung > tran;

  return (
    <div className="ai-quota-bar">
      <div className="row row-spread">
        <span className="hint">{nhan}</span>
        <span className="hint">
          {khongGioiHan
            ? `${fmt(daDung)} · không giới hạn`
            : `${fmt(daDung)} / ${fmt(tran)} (${phanTram}%)`}
        </span>
      </div>
      {khongGioiHan ? null : (
        <div
          className="ai-quota-bar-track"
          role="progressbar"
          aria-label={nhan}
          aria-valuenow={phanTram}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={`ai-quota-bar-fill${vuotTran ? " ai-quota-bar-fill-vuot" : ""}`}
            style={{ width: `${phanTram}%` }}
          />
        </div>
      )}
    </div>
  );
}
