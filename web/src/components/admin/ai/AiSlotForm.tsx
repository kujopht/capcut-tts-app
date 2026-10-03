"use client";

/**
 * Form thêm/sửa một slot provider AI.
 *
 * KHÔNG có trường nào nhận API key thật — chỉ `secret_ref` (tên tham chiếu
 * dạng `[A-Z][A-Z0-9_]{2,63}`), backend tự tra biến môi trường
 * `FAS_AI_SECRET_<secret_ref>` mà chủ sở hữu máy chủ đã đặt sẵn.
 *
 * Không có tên provider nào viết cứng ở đây: nhãn, loại nào bắt buộc
 * endpoint, loại nào dùng api_version và mẫu endpoint đều đến từ `meta` của
 * server — chunk JS tải công khai được, API mới là thứ bị chặn quyền.
 */

import { useState } from "react";
import type {
  AiCapabilityTier, AiConfigMeta, AiProviderType, AiSlot, AiSlotInput, AiThinkingMode,
} from "@/lib/admin/aiControl";
import { datetimeLocalSangIso, isoSangDatetimeLocal, nhanThinking } from "@/lib/admin/aiSlotView";

interface LoiTruong {
  field: string;
  message: string;
}

function loiCua(loi: LoiTruong[], truong: string): string | undefined {
  return loi.find((l) => l.field === truong)?.message;
}

/** Dòng lỗi NGAY DƯỚI trường — `role="alert"` để trình đọc màn hình đọc ra. */
function LoiDuoi({ loi, truong }: { loi: LoiTruong[]; truong: string }) {
  const m = loiCua(loi, truong);
  return m ? <span className="ai-admin-loi" role="alert">{m}</span> : null;
}

/** Trường có trong form — lỗi nào KHÔNG thuộc danh sách này hiện ở đầu form
 *  (vd `slot`: dữ liệu sai kiểu) để không lỗi nào bị nuốt. */
const TRUONG_FORM = new Set([
  "slot_id", "provider_type", "label", "secret_ref", "model", "endpoint", "api_version",
  "priority", "weight", "daily_request_cap", "daily_token_cap", "rpm_soft_cap", "tpm_soft_cap",
  "workloads", "price_in_micro_per_mtok", "price_out_micro_per_mtok",
  "tiers", "free_quota_remaining", "free_quota_expires_at", "free_quota_only", "thinking",
]);

export function AiSlotForm({
  slot,
  meta,
  nhanLoai,
  dangGui,
  loiTruong,
  onLuu,
  onHuy,
}: {
  /** `undefined` = form TẠO MỚI; có giá trị = form SỬA (khoá slot_id/provider_type). */
  slot?: AiSlot;
  meta: AiConfigMeta;
  /** Nhãn hiển thị theo loại, từ `config.provider_types` của server. */
  nhanLoai: Record<string, string>;
  dangGui: boolean;
  loiTruong: LoiTruong[];
  onLuu: (payload: AiSlotInput) => void;
  onHuy: () => void;
}) {
  const suaSlot = !!slot;
  const [slotId, setSlotId] = useState(slot?.slot_id ?? "");
  const [providerType, setProviderType] = useState<AiProviderType>(slot?.provider_type ?? meta.provider_types[0]);
  const [label, setLabel] = useState(slot?.label ?? "");
  const [secretRef, setSecretRef] = useState(slot?.secret_ref ?? "");
  const [model, setModel] = useState(slot?.model ?? "");
  const [enabled, setEnabled] = useState(slot?.enabled ?? true);
  const [endpoint, setEndpoint] = useState(slot?.endpoint ?? "");
  const [apiVersion, setApiVersion] = useState(slot?.api_version ?? "");
  const [priority, setPriority] = useState(slot?.priority ?? 50);
  const [weight, setWeight] = useState(slot?.weight ?? 10);
  const [dailyRequestCap, setDailyRequestCap] = useState(slot?.daily_request_cap ?? 0);
  const [dailyTokenCap, setDailyTokenCap] = useState(slot?.daily_token_cap ?? 0);
  const [rpmSoftCap, setRpmSoftCap] = useState(slot?.rpm_soft_cap ?? 0);
  const [tpmSoftCap, setTpmSoftCap] = useState(slot?.tpm_soft_cap ?? 0);
  const [workloads, setWorkloads] = useState<string[]>(slot?.workloads ?? ["general"]);
  const [priceIn, setPriceIn] = useState(slot?.price_in_micro_per_mtok ?? 0);
  const [priceOut, setPriceOut] = useState(slot?.price_out_micro_per_mtok ?? 0);
  const [tiers, setTiers] = useState<AiCapabilityTier[]>(slot?.tiers ?? []);
  // Số dư hạn mức miễn phí giữ dạng CHUỖI để phân biệt "để trống" (= không biết) với 0.
  const [quotaRemaining, setQuotaRemaining] = useState(
    slot?.free_quota_remaining != null ? String(slot.free_quota_remaining) : "",
  );
  const [quotaExpires, setQuotaExpires] = useState(isoSangDatetimeLocal(slot?.free_quota_expires_at));
  const [quotaOnly, setQuotaOnly] = useState(slot?.free_quota_only ?? false);
  const [thinking, setThinking] = useState<AiThinkingMode>(slot?.thinking ?? "provider_default");

  // Loại mà server khai báo "luôn tạo ở trạng thái tắt": ô bật bị khoá khi TẠO MỚI (bật bằng thao tác riêng sau khi Kiểm tra).
  const taoMacDinhTat = !suaSlot && (meta.created_disabled_types ?? []).includes(providerType);
  const canEndpoint = meta.requires_endpoint.includes(providerType);
  const canApiVersion = meta.uses_api_version.includes(providerType);
  // Ô thinking chỉ hiện cho loại mà MÁY CHỦ khai báo có điều khiển này (không viết cứng tên provider).
  const canThinking = (meta.thinking_types ?? []).includes(providerType);
  const goiYEndpoint = meta.endpoint_hints[providerType] ?? "";
  // Ví dụ dựng từ loại đang chọn — không viết cứng tên provider nào.
  const viDuRef = `${providerType.toUpperCase()}_PROJECT_01`;
  const loiKhac = loiTruong.filter((l) => !TRUONG_FORM.has(l.field));

  const doiWorkload = (w: string, on: boolean) => {
    setWorkloads((cur) => (on ? [...cur, w] : cur.filter((x) => x !== w)));
  };

  const doiTier = (t: AiCapabilityTier, on: boolean) => {
    setTiers((cur) => (on ? [...cur.filter((x) => x !== t), t] : cur.filter((x) => x !== t)));
  };

  const nop = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: AiSlotInput = {
      label,
      secret_ref: secretRef,
      model,
      enabled: taoMacDinhTat ? false : enabled,
      // Loại không hiện ô endpoint thì GIỮ giá trị cũ (mặc định rỗng = endpoint chuẩn).
      endpoint: canEndpoint ? endpoint : (slot?.endpoint ?? ""),
      api_version: canApiVersion ? apiVersion : "",
      priority,
      weight,
      daily_request_cap: dailyRequestCap,
      daily_token_cap: dailyTokenCap,
      rpm_soft_cap: rpmSoftCap,
      tpm_soft_cap: tpmSoftCap,
      workloads,
      price_in_micro_per_mtok: priceIn,
      price_out_micro_per_mtok: priceOut,
      tiers,
      // Để trống = "không biết" (null), KHÔNG phải 0. Thời điểm ảnh chụp do MÁY CHỦ đóng dấu, không gửi từ đây.
      free_quota_remaining: quotaRemaining.trim() === "" ? null : Number(quotaRemaining),
      free_quota_expires_at: datetimeLocalSangIso(quotaExpires),
      free_quota_only: quotaOnly,
      // Loại không có điều khiển này thì KHÔNG gửi trường (máy chủ từ chối giá trị khác provider_default).
      ...(canThinking ? { thinking } : {}),
    };
    if (!suaSlot) {
      payload.slot_id = slotId;
      payload.provider_type = providerType;
    }
    onLuu(payload);
  };

  return (
    <form className="card stack-2 ai-admin-form" onSubmit={nop} noValidate>
      <h3 className="section-title-sm">{suaSlot ? `Sửa slot ${slot.slot_id}` : "Thêm slot mới"}</h3>
      {loiKhac.length ? (
        <div className="ai-admin-loi-dau" role="alert">
          {loiKhac.map((l) => <span key={`${l.field}:${l.message}`}>{l.field}: {l.message}</span>)}
        </div>
      ) : null}

      <div className="stack-2">
        <label className="stack-1">
          <span className="hint">Slot ID</span>
          <input
            className="input"
            value={slotId}
            disabled={suaSlot}
            onChange={(e) => setSlotId(e.target.value)}
            placeholder={`vd: ${providerType.replace(/_/g, "-")}-01`}
            maxLength={27}
            required
          />
          <span className="hint">2–27 ký tự a-z, 0-9, “-”, “_”.</span>
          <LoiDuoi loi={loiTruong} truong="slot_id" />
        </label>

        <label className="stack-1">
          <span className="hint">Loại provider</span>
          <select
            className="select"
            value={providerType}
            disabled={suaSlot}
            onChange={(e) => setProviderType(e.target.value as AiProviderType)}
          >
            {meta.provider_types.map((t) => (
              <option key={t} value={t}>{nhanLoai[t] ?? t}</option>
            ))}
          </select>
          <LoiDuoi loi={loiTruong} truong="provider_type" />
        </label>

        <label className="stack-1">
          <span className="hint">Nhãn hiển thị</span>
          <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} required />
          <LoiDuoi loi={loiTruong} truong="label" />
        </label>

        <label className="stack-1">
          <span className="hint">Tên tham chiếu khoá (secret_ref)</span>
          <input
            className="input"
            value={secretRef}
            onChange={(e) => setSecretRef(e.target.value.toUpperCase())}
            placeholder={`vd: ${viDuRef}`}
            required
          />
          <span className="hint">
            Không nhập API key ở đây — chủ máy chủ đặt giá trị thật vào biến môi
            trường <code>FAS_AI_SECRET_{secretRef || "…"}</code>. Tên phải bắt đầu
            bằng <code>{providerType.toUpperCase()}_</code>: khoá gắn với loại provider.
          </span>
          <LoiDuoi loi={loiTruong} truong="secret_ref" />
        </label>

        <label className="stack-1">
          <span className="hint">Model</span>
          <input className="input" value={model} onChange={(e) => setModel(e.target.value)}
            placeholder="tên model đúng như provider công bố" required />
          <LoiDuoi loi={loiTruong} truong="model" />
        </label>

        <label className="row row-tight">
          <input type="checkbox" checked={taoMacDinhTat ? false : enabled} disabled={taoMacDinhTat}
            onChange={(e) => setEnabled(e.target.checked)} />
          <span>Bật slot này</span>
        </label>
        {taoMacDinhTat ? (
          <span className="hint">
            Slot loại này luôn được tạo ở trạng thái TẮT. Tạo xong, bấm Kiểm tra rồi mới Sửa để bật — bật là thao tác riêng.
          </span>
        ) : null}

        {canEndpoint ? (
          <label className="stack-1">
            <span className="hint">Endpoint</span>
            <input className="input" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} required />
            {goiYEndpoint ? <span className="hint">Dạng hợp lệ: {goiYEndpoint}</span> : null}
            <LoiDuoi loi={loiTruong} truong="endpoint" />
          </label>
        ) : null}

        {canApiVersion ? (
          <label className="stack-1">
            <span className="hint">API version</span>
            <input className="input" value={apiVersion} onChange={(e) => setApiVersion(e.target.value)}
              placeholder="vd: 2024-10-21" />
            <LoiDuoi loi={loiTruong} truong="api_version" />
          </label>
        ) : null}

        <div className="ai-admin-2cot">
          <label className="stack-1">
            <span className="hint">Ưu tiên (0-99, nhỏ hơn thử trước)</span>
            <input className="input" type="number" min={0} max={99} value={priority}
              onChange={(e) => setPriority(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="priority" />
          </label>
          <label className="stack-1">
            <span className="hint">Trọng số (1-100)</span>
            <input className="input" type="number" min={1} max={100} value={weight}
              onChange={(e) => setWeight(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="weight" />
          </label>
        </div>

        <div className="ai-admin-2cot">
          <label className="stack-1">
            <span className="hint">Trần yêu cầu/ngày (0 = không giới hạn)</span>
            <input className="input" type="number" min={0} value={dailyRequestCap}
              onChange={(e) => setDailyRequestCap(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="daily_request_cap" />
          </label>
          <label className="stack-1">
            <span className="hint">Trần token/ngày (0 = không giới hạn)</span>
            <input className="input" type="number" min={0} value={dailyTokenCap}
              onChange={(e) => setDailyTokenCap(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="daily_token_cap" />
          </label>
        </div>

        <div className="ai-admin-2cot">
          <label className="stack-1">
            <span className="hint">Trần mềm RPM (0 = không giới hạn)</span>
            <input className="input" type="number" min={0} value={rpmSoftCap}
              onChange={(e) => setRpmSoftCap(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="rpm_soft_cap" />
          </label>
          <label className="stack-1">
            <span className="hint">Trần mềm TPM (0 = không giới hạn)</span>
            <input className="input" type="number" min={0} value={tpmSoftCap}
              onChange={(e) => setTpmSoftCap(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="tpm_soft_cap" />
          </label>
        </div>

        <div className="ai-admin-2cot">
          <label className="stack-1">
            <span className="hint">Giá vào (micro-USD/1M token)</span>
            <input className="input" type="number" min={0} value={priceIn}
              onChange={(e) => setPriceIn(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="price_in_micro_per_mtok" />
          </label>
          <label className="stack-1">
            <span className="hint">Giá ra (micro-USD/1M token)</span>
            <input className="input" type="number" min={0} value={priceOut}
              onChange={(e) => setPriceOut(Number(e.target.value))} />
            <LoiDuoi loi={loiTruong} truong="price_out_micro_per_mtok" />
          </label>
        </div>

        <fieldset className="stack-1">
          <legend className="hint">Workload cho phép</legend>
          <div className="row">
            {meta.workloads.map((w) => (
              <label key={w} className="row row-tight">
                <input
                  type="checkbox"
                  checked={workloads.includes(w)}
                  onChange={(e) => doiWorkload(w, e.target.checked)}
                />
                <span>{w}</span>
              </label>
            ))}
          </div>
          <LoiDuoi loi={loiTruong} truong="workloads" />
        </fieldset>

        {canThinking ? (
          <label className="stack-1">
            <span className="hint">Thinking (suy luận của model)</span>
            <select className="input" value={thinking} onChange={(e) => setThinking(e.target.value as AiThinkingMode)}>
              {(meta.thinking_modes ?? ["provider_default"]).map((m) => (
                <option key={m} value={m}>{nhanThinking(m)}</option>
              ))}
            </select>
            <span className="hint">
              Model lai (hybrid) thường MẶC ĐỊNH bật suy luận: tốn token và độ trễ, và với giới hạn token nhỏ có thể không trả
              lời gì. &ldquo;Tắt&rdquo; gửi lệnh tắt tường minh; &ldquo;Mặc định&rdquo; không gửi gì. Nội dung suy luận không bao giờ
              hiện ra cho người dùng, dù chọn gì.
            </span>
            <LoiDuoi loi={loiTruong} truong="thinking" />
          </label>
        ) : null}

        <details className="stack-2">
          <summary className="hint">Tầng năng lực &amp; hạn mức miễn phí (tuỳ chọn)</summary>
          <fieldset className="stack-1">
            <legend className="hint">Tầng năng lực slot phục vụ</legend>
            <div className="row">
              {(meta.capability_tiers ?? []).map((t) => (
                <label key={t} className="row row-tight">
                  <input type="checkbox" checked={tiers.includes(t)} onChange={(e) => doiTier(t, e.target.checked)} />
                  <span>{t}</span>
                </label>
              ))}
            </div>
            <span className="hint">
              Tầng mô tả LOẠI việc model làm được — không phải tên model, cũng không phải gói đăng ký của người dùng. Để trống
              = chưa phân loại. EMBEDDING dùng API khác nên slot chỉ-EMBEDDING không nhận lượt chat.
            </span>
            <LoiDuoi loi={loiTruong} truong="tiers" />
          </fieldset>

          <div className="ai-admin-2cot">
            <label className="stack-1">
              <span className="hint">Số dư hạn mức miễn phí (token) — số bạn đọc từ trang nhà cung cấp</span>
              <input className="input" type="number" min={0} value={quotaRemaining} placeholder="để trống = không biết"
                onChange={(e) => setQuotaRemaining(e.target.value)} />
              <LoiDuoi loi={loiTruong} truong="free_quota_remaining" />
            </label>
            <label className="stack-1">
              <span className="hint">Hạn dùng của hạn mức miễn phí</span>
              <input className="input" type="datetime-local" value={quotaExpires}
                onChange={(e) => setQuotaExpires(e.target.value)} />
              <LoiDuoi loi={loiTruong} truong="free_quota_expires_at" />
            </label>
          </div>
          <label className="row row-tight">
            <input type="checkbox" checked={quotaOnly} onChange={(e) => setQuotaOnly(e.target.checked)} />
            <span>Chỉ dùng hạn mức miễn phí (khoá an toàn: hết số dư hoặc quá hạn thì KHÔNG BAO GIỜ dùng slot)</span>
          </label>
          <span className="hint">
            Đây là ẢNH CHỤP do bạn nhập, không tự cập nhật; máy chủ ghi lại thời điểm bạn đổi số dư. Khoá chỉ-miễn-phí trừ lượng
            slot đã phục vụ từ ngày nhập + dự phòng 5%, và từ chối khi số liệu quá 31 ngày — nhưng rào chặn phí thật là chế độ
            &ldquo;chỉ dùng hạn mức miễn phí&rdquo; ở trang nhà cung cấp, hãy bật cả hai. Chưa có logic nào tự tiêu hạn mức sắp hết hạn trước
            — tính năng đó đã cài sẵn nhưng đang TẮT.
          </span>
          <LoiDuoi loi={loiTruong} truong="free_quota_only" />
        </details>
      </div>

      <div className="row row-tight">
        <button type="submit" className="btn btn-primary" disabled={dangGui}>
          {suaSlot ? "Lưu thay đổi" : "Tạo slot"}
        </button>
        <button type="button" className="btn btn-sm" onClick={onHuy} disabled={dangGui}>
          Huỷ
        </button>
      </div>
    </form>
  );
}
