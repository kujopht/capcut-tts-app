/**
 * Mọi thứ Fanfic AI Support cần trên trang THƯỜNG, nạp LƯỜI qua MỘT điểm
 * `import()` duy nhất (`components/SupportGate.tsx`) — chỉ khi bật cờ.
 *
 * Một điểm nạp = một stub loader. Không `next/dynamic`: runtime của nó (~6 KB
 * thô) vào bundle của MỌI trang dù cờ tắt (đo thật trên bản build).
 */
import { datBoNgheLoiApi } from "@/lib/api";
import { caiBoThuLoi, ghiLoi } from "@/lib/support/collector";

export { SupportHint } from "./SupportHint";

/**
 * Gắn bộ thu lỗi: sự kiện lỗi JS + lỗi API (mạng hỏng / 5xx). Không thăm dò,
 * không request nào lúc bình thường. Lỗi của chính `/api/support/*` bị bỏ qua —
 * báo lỗi về việc báo lỗi hỏng là một vòng lặp. Trả về hàm gỡ bộ nghe API.
 */
export function ganBoThuLoi(): () => void {
  caiBoThuLoi();
  datBoNgheLoiApi((path, status, code) => {
    if (path.startsWith("/api/support/")) return;
    ghiLoi({
      kind: "api_error",
      code: status === 0 ? "api_network" : "api_5xx",
      message: `${path.split("?")[0]} ${status || "network"}${code ? ` ${code}` : ""}`,
    });
  });
  return () => datBoNgheLoiApi(null);
}
