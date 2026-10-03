import { SAVE_KEY, defaultSave, sanitizeSave, type SaveData, type SaveStore } from "../core/save";

/**
 * Lưu trữ cục bộ trong trình duyệt. KHÔNG mạng, KHÔNG Appwrite. Mọi truy cập `localStorage` đều bọc try/catch (cửa sổ riêng tư, tắt dữ liệu trang
 * web, hết dung lượng) — khi không dùng được thì game vẫn chơi bình thường, chỉ không nhớ tiến trình. Dữ liệu đọc ra luôn đi qua `sanitizeSave`.
 */
export class LocalStorageStore implements SaveStore {
  /** `true` sau lần ghi/đọc thất bại gần nhất — để giao diện báo "không lưu được". */
  failed = false;

  constructor(private readonly key: string = SAVE_KEY) {}

  async load(): Promise<SaveData | null> {
    try {
      const raw = window.localStorage.getItem(this.key);
      if (raw === null) return null;
      return sanitizeSave(JSON.parse(raw));
    } catch {
      this.failed = true;
      return null;
    }
  }

  async save(data: SaveData): Promise<void> {
    try {
      window.localStorage.setItem(this.key, JSON.stringify(data));
      this.failed = false;
    } catch {
      this.failed = true;
    }
  }

  async clear(): Promise<void> {
    try {
      window.localStorage.removeItem(this.key);
    } catch {
      this.failed = true;
    }
  }
}

/** Đọc nhanh (đồng bộ) để thẻ game biết có "Tiếp tục" hay không mà không tải runtime. */
export function peekSave(key: string = SAVE_KEY): SaveData | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? null : sanitizeSave(JSON.parse(raw));
  } catch {
    return null;
  }
}

export { defaultSave };
