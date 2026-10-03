import type { EndingKind, MemoryId } from "./types";

/**
 * Toàn bộ chữ trong game (tiếng Việt). Lõi chỉ phát `caption {id}`; lớp giao diện tra bảng này. Mỗi dòng ngắn: kể chuyện bằng
 * môi trường + Echo, không dán tường chữ. `touch` = biến thể cho màn hình cảm ứng (nếu khác).
 */
export interface Caption {
  /** Người nói (nếu có). */
  who?: string;
  text: string;
  touch?: string;
  /** Thời gian hiện (ms); mặc định theo độ dài. */
  ms?: number;
}

export const CAPTIONS: Readonly<Record<string, Caption>> = {
  // --- hướng dẫn (biển chỉ dẫn) ---
  "tut.move": { text: "← → hoặc A/D để đi. Space để nhảy — giữ lâu thì nhảy cao hơn.", touch: "Chạm ◀ ▶ để đi, ⤒ để nhảy — giữ lâu thì nhảy cao hơn." },
  "tut.jump": { text: "Hố gai phía trước: nhảy qua. Rơi xuống chỉ mất 1 máu và được đưa về chỗ đứng gần nhất.", touch: "Hố gai phía trước: nhảy qua. Rơi xuống chỉ mất 1 máu." },
  "tut.attack": { text: "J để chém bằng Glyph Blade. Bấm J ba lần liên tiếp để ra combo.", touch: "Chạm ⚔ để chém. Chạm ba lần liên tiếp để ra combo." },
  "tut.pulse": { text: "Mỗi nhát chém trúng tích 1 Ink. Đủ 3 Ink: bấm K để gọi Memory Pulse — nó làm kẻ địch choáng và lộ ra những dòng chữ ẩn.", touch: "Mỗi nhát chém trúng tích 1 Ink. Đủ 3 Ink: chạm ✦ để gọi Memory Pulse — nó làm kẻ địch choáng và lộ ra những dòng chữ ẩn." },
  "hall.sign": { text: "Bản thảo dán trên kệ: \"Mọi trang ở đây đều chưa kết thúc. Xin đừng gọi chúng là rác.\"" },
  "hall.ledge": { text: "Một gờ đá cao ở tận cùng sảnh, với tới được không? Khe hở quá rộng để nhảy thường." },
  "stacks.sign": { text: "Nhãn kệ: \"DÃY CHƯA ĐẶT TÊN — 4.311 bản nháp\"" },

  // --- Echo (bóng ma bản thảo) ---
  "echo.1": { who: "Echo", text: "Ngươi còn đứng được sao, Ink Scout? Mấy trang ở đây chỉ chịu hiện ra khi ngươi gọi chúng bằng Memory Pulse. Tìm chữ ẩn trên tường." },
  "echo.glyph": { who: "Bản nháp ẩn", text: "\"Nếu một câu chuyện chưa có hồi kết, nó có thôi là câu chuyện không?\" — Bản nháp số 0001." },
  "shrine.echo": { who: "Echo", text: "Đền Lề Trang. Nơi Tác giả viết ghi chú bên lề… Bệ thờ kia vẫn còn giữ một bước chân." },
  "secret.echo": { who: "Echo", text: "Ngươi lên được tận đây? Đúng rồi — Kho này luôn cất ký ức ở những nơi cần quay lại mới thấy." },
  "bookmark.echo": { who: "Echo", text: "Phía sau là Redactor. Nó từng là Người Gác. Ngươi nhớ được bao nhiêu thì ngươi hiểu nó bấy nhiêu." },

  // --- Echo của Broken Character ---
  "broken.engage": { who: "Broken Character", text: "Ta… là nhân vật chính. Hay là ai khác? Đừng… đừng viết lại ta." },
  "broken.half": { who: "Broken Character", text: "Đau quá. Câu thoại nào đã bị xoá?" },
  "broken.die": { who: "Broken Character", text: "Cảm ơn… vì đã đọc tới đây." },

  // --- boss ---
  "boss.intro": { who: "Redactor", text: "BẢN THẢO CHƯA HOÀN CHỈNH. XOÁ." },
  "boss.intro.m2": { who: "Redactor", text: "Ngươi đã đọc những trang ta giấu… Vậy thì ngươi biết tại sao ta phải XOÁ." },
  "boss.phase2": { who: "Redactor", text: "KHÔNG PHẢI MỘT TRANG. TẤT CẢ. XOÁ HẾT." },
  "boss.phase2.m2": { who: "Redactor", text: "Ta cũng từng khâu từng trang lại… cho tới khi không còn ai viết tiếp." },
  "boss.collapse": { who: "Redactor", text: "KÝ ỨC… ĐANG… VỠ." },
  "boss.collapse.m2": { who: "Redactor", text: "Ký ức ngươi mang… làm chúng nứt. Dừng lại đi!" },
  "boss.defeat": { who: "Redactor", text: "…Một trang nữa… còn dở." },
  "boss.defeat.m2": { who: "Redactor", text: "Ta từng là Người Gác. Ta chỉ… quên cách sửa." },
  "boss.defeat.m3": { who: "Redactor", text: "Ngươi mang đủ ba ký ức. Ngươi có thể quyết định ta sẽ thành gì." },

  // --- thông báo hệ thống ---
  "checkpoint": { text: "Dấu Trang đã lưu. Máu được hồi đầy." },
  "ability.marginStep": { text: "Bạn nhận được MARGIN STEP — lướt ngắn theo hướng đang giữ. Có khung bất tử đầu lướt." },
};

export interface MemoryText {
  title: string;
  lines: readonly string[];
  /** Phần thưởng cơ chế của ký ức này. */
  boon: string;
}

export const MEMORY_TEXT: Readonly<Record<MemoryId, MemoryText>> = {
  1: {
    title: "Ký Ức I — Tác Giả",
    lines: [
      "Có người đã dựng Kho này.",
      "Không để cất những câu chuyện hoàn chỉnh,",
      "mà để cất những câu chuyện chưa viết xong.",
      "\"Chưa xong, không có nghĩa là không đáng tồn tại.\"",
    ],
    boon: "Tối đa máu +1. Ink Scout nhớ mình được tạo ra để gìn giữ.",
  },
  2: {
    title: "Ký Ức II — Sụp Đổ",
    lines: [
      "Bản thảo dở dang chồng lên nhau quá nhiều.",
      "Chúng mâu thuẫn, cắn xé, rồi thối thành thứ mực đỏ",
      "mà không ai còn viết tiếp: sự nhiễu loạn.",
    ],
    boon: "Memory Pulse lan rộng hơn (56 → 80 px).",
  },
  3: {
    title: "Ký Ức III — Người Gác",
    lines: [
      "Redactor không sinh ra để xoá.",
      "Nó được tạo ra để sửa — khâu lại những trang rách.",
      "Khi không còn ai viết tiếp, nó chỉ còn biết cắt bỏ.",
    ],
    boon: "Memory Pulse chỉ tốn 2 Ink.",
  },
};

export interface EndingText {
  title: string;
  pages: readonly string[];
}

export const ENDING_CHOICE = {
  prompt: "Bạn đã nhớ đủ ba ký ức. Redactor đang tan thành những dòng mực. Bạn sẽ…",
  erase: { label: "XOÁ", hint: "Xoá hẳn tàn dư của Redactor. Kho yên, nhưng nó sẽ không còn nữa." },
  restore: { label: "KHÔI PHỤC", hint: "Viết lại nó thành Người Gác ban đầu. Cả hai cùng đi tiếp." },
} as const;

export const ENDINGS: Readonly<Record<EndingKind | "basic2", EndingText>> = {
  basic: {
    title: "Kết Thúc — Kho Vẫn Còn",
    pages: [
      "Redactor đổ xuống, hoá thành mảnh giấy vụn.",
      "Kho Lưu Trữ vẫn còn đó. Những bản thảo vẫn thở.",
      "Nhưng sự nhiễu loạn sâu bên dưới… chưa ai giải quyết.",
      "Ink Scout ngẩng nhìn: những trang dở dang vẫn đang chờ.",
    ],
  },
  basic2: {
    title: "Kết Thúc — Một Phần Sự Thật",
    pages: [
      "Redactor đổ xuống. Trước khi tan, nó thì thầm: \"Ta từng là Người Gác.\"",
      "Ngươi hiểu một nửa câu chuyện: nó cắt vì đã quá mệt để sửa.",
      "Kho Lưu Trữ vẫn còn. Nhưng sự nhiễu loạn bên dưới chưa được giải.",
      "Còn một ký ức đang chờ ngươi tìm thấy…",
    ],
  },
  erase: {
    title: "Kết Thúc — XOÁ",
    pages: [
      "Ink Scout đưa Glyph Blade xuống, một nét gạch cuối.",
      "Redactor tan hết. Sự nhiễu loạn tắt lịm.",
      "Kho Lưu Trữ yên ắng — an toàn, nhưng trống trải.",
      "Có những trang không còn ai giữ chỗ cho nó nữa.",
    ],
  },
  restore: {
    title: "Kết Thúc — KHÔI PHỤC",
    pages: [
      "Ink Scout viết lại tên cho nó: \"Người Gác\".",
      "Các mảnh rách khâu lại. Mực đỏ ngả sang vàng nhạt.",
      "Một dáng người cầm bút bước ra: THE CURATOR.",
      "\"Còn rất nhiều chương nữa… Hãy cùng ta tìm chúng.\"",
    ],
  },
};

export function memoryCaption(id: string, memories: number): Caption | undefined {
  const variant = memories >= 3 ? CAPTIONS[`${id}.m3`] : undefined;
  if (variant) return variant;
  const v2 = memories >= 2 ? CAPTIONS[`${id}.m2`] : undefined;
  return v2 ?? CAPTIONS[id];
}
