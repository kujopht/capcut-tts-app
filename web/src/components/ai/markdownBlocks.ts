/**
 * Tách nội dung markdown TỐI GIẢN của trợ lý AI thành các khối — THUẦN (không React, không DOM) để `node --test` khoá được hành vi
 * bằng dữ liệu, còn `markdownLite.tsx` chỉ việc dựng phần tử React tương ứng.
 *
 * Ba loại khối: đoạn văn (các dòng liền nhau), danh sách (`- `/`* `/`1. `), và khối mã rào bằng ```` ``` ````. Khối mã MỞ mà chưa đóng
 * (đang stream, rào đóng chưa tới) vẫn là khối mã (`closed: false`) — người dùng thấy mã ngay khi nó bắt đầu chảy về thay vì thấy
 * ba dấu huyền thô rồi mới "nhảy" thành khối khi rào đóng tới.
 *
 * Cố ý KHÔNG hỗ trợ: tiêu đề, bảng, link tự động, HTML (xem `markdownLite.tsx`). Trước đây khối mã không có: ```` ```js ```` hiện
 * nguyên văn giữa đoạn văn, dòng mã dài làm bong bóng tràn.
 */

export type MdBlock =
  | { kind: "para"; lines: string[] }
  | { kind: "list"; items: string[] }
  | { kind: "code"; lang: string; text: string; closed: boolean };

const LIST_ITEM = /^\s*([-*]|\d+\.)\s+/;
const FENCE_OPEN = /^\s*```([^`\s]*)\s*$/;
const FENCE_CLOSE = /^\s*```\s*$/;
/** Cả khối mã nằm trên MỘT dòng: ```` ```mã``` ```` (model hay viết thế cho đoạn mã ngắn). */
const FENCE_ONE_LINE = /^\s*```([^`]+)```\s*$/;

function proseBlocks(text: string): MdBlock[] {
  const out: MdBlock[] = [];
  // Xuống dòng đầu/cuối đoạn (ngay trước/sau rào mã, hoặc mẩu stream vừa dừng sau "\n") không phải một dòng trống để vẽ.
  for (const doan of text.replace(/^\n+|\n+$/g, "").split(/\n{2,}/)) {
    const lines = doan.split("\n").filter((d) => d.length > 0);
    if (lines.length === 0) continue;
    if (lines.every((d) => LIST_ITEM.test(d))) out.push({ kind: "list", items: lines.map((d) => d.replace(LIST_ITEM, "")) });
    else out.push({ kind: "para", lines: doan.split("\n") });
  }
  return out;
}

export function parseMarkdownLite(content: string): MdBlock[] {
  const lines = content.split("\n");
  const out: MdBlock[] = [];
  let prose: string[] = [];
  const flush = () => {
    if (prose.length) out.push(...proseBlocks(prose.join("\n")));
    prose = [];
  };
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const one = FENCE_ONE_LINE.exec(line);
    if (one) {
      flush();
      out.push({ kind: "code", lang: "", text: one[1].trim(), closed: true });
      continue;
    }
    const open = FENCE_OPEN.exec(line);
    if (!open) {
      prose.push(line);
      continue;
    }
    flush();
    const body: string[] = [];
    let closed = false;
    for (i += 1; i < lines.length; i += 1) {
      if (FENCE_CLOSE.test(lines[i])) {
        closed = true;
        break;
      }
      body.push(lines[i]);
    }
    out.push({ kind: "code", lang: open[1], text: body.join("\n"), closed });
  }
  flush();
  return out;
}
