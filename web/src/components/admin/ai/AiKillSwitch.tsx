"use client";

/**
 * Công tắc khẩn cấp toàn cục cho AI. Chỉ Owner đổi được (server 403 với vai
 * trò thấp hơn — nút ở đây tự vô hiệu hoá để không hứa một hành động sẽ bị
 * từ chối). TẮT AI đòi một bước xác nhận TRONG TRANG (không `window.confirm`)
 * vì hậu quả ảnh hưởng mọi người dùng đang chờ phản hồi AI.
 */

import { useState } from "react";

export function AiKillSwitch({
  aiEnabled,
  laOwner,
  dangGui,
  onDoi,
}: {
  aiEnabled: boolean;
  laOwner: boolean;
  dangGui: boolean;
  onDoi: (batAi: boolean) => void;
}) {
  const [xacNhanTat, setXacNhanTat] = useState(false);

  return (
    <div className="card stack-2">
      <div className="row row-spread">
        <strong>Công tắc khẩn cấp toàn bộ AI</strong>
        <span className={`tt ${aiEnabled ? "tt-duyet" : "tt-treo"}`}>
          {aiEnabled ? "Đang bật" : "ĐANG TẮT"}
        </span>
      </div>
      <p className="hint">
        Tắt sẽ dừng MỌI yêu cầu AI (trợ lý chung, truyện, hỗ trợ, viết) trên
        toàn hệ thống ngay lập tức, không phân biệt provider hay slot.
      </p>
      {!laOwner ? (
        <p className="hint" role="alert">Chỉ Owner mới thay đổi được.</p>
      ) : null}

      {xacNhanTat ? (
        <div className="card ai-admin-xac-nhan stack-2" role="alertdialog" aria-label="Xác nhận tắt AI">
          <strong>Xác nhận tắt toàn bộ AI?</strong>
          <p className="hint">
            Mọi người dùng đang mở trợ lý AI sẽ nhận lỗi &quot;AI đang tắt&quot;
            ngay khi họ gửi tin tiếp theo. Hành động này bật lại được bất cứ
            lúc nào.
          </p>
          <div className="row row-tight">
            <button
              type="button"
              className="btn btn-danger"
              disabled={dangGui}
              onClick={() => {
                setXacNhanTat(false);
                onDoi(false);
              }}
            >
              Xác nhận tắt AI
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setXacNhanTat(false)}>
              Huỷ
            </button>
          </div>
        </div>
      ) : (
        <div className="row row-tight">
          <button
            type="button"
            className="btn btn-danger"
            disabled={!laOwner || dangGui || !aiEnabled}
            onClick={() => setXacNhanTat(true)}
          >
            Tắt toàn bộ AI
          </button>
          <button
            type="button"
            className="btn"
            disabled={!laOwner || dangGui || aiEnabled}
            onClick={() => onDoi(true)}
          >
            Bật AI
          </button>
        </div>
      )}
    </div>
  );
}
