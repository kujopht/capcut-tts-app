"use client";

/** Nhap fanfic co quyen tu tep; base64 hoa hoan toan trong trinh duyet. */

import Link from "next/link";
import { useState, type ChangeEvent, type FormEvent } from "react";
import {
  api,
  type AuthorizedImportFormat,
  type AuthorizedImportResult,
  type AuthorizedImportRightsBasis,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { Alert, Loading } from "@/components/ui";
import { IconBook } from "@/components/Icons";

const MAX_FILE_BYTES = 15 * 1024 * 1024;
const ACCEPTED_FORMATS = new Set<AuthorizedImportFormat>([
  "txt",
  "html",
  "epub",
  "docx",
  "zip",
]);

function dinhDangTep(tep: File): AuthorizedImportFormat | null {
  const duoi = tep.name.split(".").pop()?.toLowerCase() ?? "";
  return ACCEPTED_FORMATS.has(duoi as AuthorizedImportFormat)
    ? (duoi as AuthorizedImportFormat)
    : null;
}

/**
 * FileReader tao Data URL ngay trong tab; chi lay phan sau dau phay de body
 * dung chinh contract JSON base64 cua backend, khong gui multipart/MIME prefix.
 */
function docTepThanhBase64(tep: File): Promise<string> {
  return new Promise((giai, tuChoi) => {
    const doc = new FileReader();
    doc.onload = () => {
      const ketQua = String(doc.result ?? "");
      const dauPhay = ketQua.indexOf(",");
      if (dauPhay < 0) {
        tuChoi(new Error("Không đọc được dữ liệu trong tệp."));
        return;
      }
      giai(ketQua.slice(dauPhay + 1));
    };
    doc.onerror = () => tuChoi(new Error("Không đọc được tệp."));
    doc.readAsDataURL(tep);
  });
}

function tachFandom(raw: string): string[] {
  return [...new Set(raw.split(",").map((ten) => ten.trim()).filter(Boolean))];
}

export default function ImportPage() {
  const { profile, loading: dangTaiPhien } = useSession();
  const toast = useToast();
  const [tep, setTep] = useState<File | null>(null);
  const [tieuDe, setTieuDe] = useState("");
  const [fandom, setFandom] = useState("");
  const [quyen, setQuyen] = useState<AuthorizedImportRightsBasis | "">("");
  const [loiTep, setLoiTep] = useState("");
  const [dangNhap, setDangNhap] = useState(false);
  const [ketQua, setKetQua] = useState<AuthorizedImportResult | null>(null);

  if (dangTaiPhien) {
    return (
      <div className="page">
        <Loading label="Đang tải…" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="page auth-page">
        <header className="auth-head">
          <h1 className="page-title">Nhập fanfic của tôi</h1>
          <p className="hint">Bạn cần đăng nhập trước khi nhập tác phẩm.</p>
        </header>
        <Link
          className="btn btn-primary btn-block"
          href="/login?next=/import"
          prefetch={false}
        >
          Đăng nhập
        </Link>
      </div>
    );
  }

  function chonTep(event: ChangeEvent<HTMLInputElement>) {
    const tepMoi = event.target.files?.[0] ?? null;
    setKetQua(null);
    setLoiTep("");

    if (!tepMoi) {
      setTep(null);
      return;
    }
    if (!dinhDangTep(tepMoi)) {
      setTep(null);
      setLoiTep("Chỉ nhận tệp .txt, .html, .epub, .docx hoặc .zip.");
      event.target.value = "";
      return;
    }
    if (tepMoi.size > MAX_FILE_BYTES) {
      setTep(null);
      setLoiTep("Tệp lớn hơn 15 MB. Hãy chia nhỏ hoặc nén lại trước khi nhập.");
      event.target.value = "";
      return;
    }

    setTep(tepMoi);
    setTieuDe((hienTai) => hienTai || tepMoi.name.replace(/\.[^.]+$/, ""));
  }

  async function gui(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setKetQua(null);

    const format = tep ? dinhDangTep(tep) : null;
    if (!tep || !format) {
      setLoiTep("Hãy chọn một tệp đúng định dạng trước khi nhập.");
      return;
    }
    if (tep.size > MAX_FILE_BYTES) {
      setLoiTep("Tệp lớn hơn 15 MB. Hãy chia nhỏ hoặc nén lại trước khi nhập.");
      return;
    }
    if (!quyen) {
      toast.error("Hãy xác nhận quyền đăng tác phẩm trước khi nhập.");
      return;
    }

    setDangNhap(true);
    setLoiTep("");
    try {
      const base64 = await docTepThanhBase64(tep);
      const moi = await api.importAuthorizedWork({
        filename: tep.name,
        format,
        base64,
        title: tieuDe.trim(),
        rightsBasis: quyen,
        fandomNames: tachFandom(fandom),
        publicationMode: "full_text",
      });
      setKetQua(moi);
      toast.ok(`Đã nhập ${moi.chapters.length} chương vào bản nháp.`);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setDangNhap(false);
    }
  }

  return (
    <div className="page" data-hero-theme="write">
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <Link href="/authors" className="hint crumb" prefetch={false}>
          ← Dành cho tác giả
        </Link>
      </nav>

      <header className="page-head">
        <div className="page-head-body stack-2">
          <span className="eyebrow eyebrow-icon">
            <IconBook size={17} /> Khu vực tác giả
          </span>
          <h1 className="page-title">Nhập fanfic của tôi</h1>
          <p className="lead lead-narrow">
            Tải tác phẩm bạn có quyền đăng lên Fanfic World. Truyện và các
            chương sẽ được tạo dưới dạng bản nháp để bạn kiểm tra trước.
          </p>
        </div>
      </header>

      <div className="split-narrow page-lam-viec">
        <aside className="stack">
          <section className="card stack-2">
            <h2 className="section-title">Trước khi tải lên</h2>
            <ul className="quy-dinh">
              <li>Định dạng: TXT, HTML, EPUB, DOCX hoặc ZIP.</li>
              <li>Tệp tối đa 15 MB để trình duyệt không bị treo khi mã hóa.</li>
              <li>Tên fandom chưa nhận ra sẽ được báo lại sau khi nhập.</li>
              <li>Tác phẩm luôn bắt đầu ở trạng thái bản nháp.</li>
            </ul>
          </section>
        </aside>

        <section className="stack-5">
          <form className="card stack" onSubmit={gui}>
            <div className="field">
              <label className="label" htmlFor="import-file">
                Tệp tác phẩm
              </label>
              <input
                id="import-file"
                className="input"
                type="file"
                accept=".txt,.html,.epub,.docx,.zip"
                onChange={chonTep}
                aria-describedby={
                  loiTep ? "import-file-hint import-file-error" : "import-file-hint"
                }
                required
              />
              <p className="hint" id="import-file-hint">
                Chọn một tệp không quá 15 MB.
              </p>
              {loiTep ? (
                <div id="import-file-error">
                  <Alert kind="error">{loiTep}</Alert>
                </div>
              ) : null}
            </div>

            <div className="field">
              <label className="label" htmlFor="import-title">
                Tên tác phẩm
              </label>
              <input
                id="import-title"
                className="input"
                value={tieuDe}
                onChange={(event) => setTieuDe(event.target.value)}
                maxLength={200}
                required
              />
            </div>

            <div className="field">
              <label className="label" htmlFor="import-fandoms">
                Fandom <span className="hint">(không bắt buộc)</span>
              </label>
              <input
                id="import-fandoms"
                className="input"
                value={fandom}
                onChange={(event) => setFandom(event.target.value)}
                placeholder="Naruto, My Hero Academia"
                aria-describedby="import-fandoms-hint"
              />
              <p className="hint" id="import-fandoms-hint">
                Nếu có nhiều fandom, ngăn cách bằng dấu phẩy.
              </p>
            </div>

            <fieldset className="field">
              <legend className="label">Quyền đăng tác phẩm</legend>
              <label className="dong-y">
                <input
                  type="radio"
                  name="rights-basis"
                  value="author"
                  checked={quyen === "author"}
                  onChange={() => setQuyen("author")}
                  required
                />
                <span>Tôi là tác giả của tác phẩm này.</span>
              </label>
              <label className="dong-y">
                <input
                  type="radio"
                  name="rights-basis"
                  value="permission_granted"
                  checked={quyen === "permission_granted"}
                  onChange={() => setQuyen("permission_granted")}
                  required
                />
                <span>Tôi được tác giả cho phép đăng tác phẩm này.</span>
              </label>
            </fieldset>

            <div className="row">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={dangNhap || !tep || !tieuDe.trim() || !quyen}
              >
                {dangNhap ? "Đang đọc và nhập tệp…" : "Nhập tác phẩm"}
              </button>
            </div>
          </form>

          {ketQua ? (
            <Alert kind={ketQua.fandom_match.unmatched.length ? "warn" : "ok"}>
              <span className="stack-2">
                <strong>Đã nhập tác phẩm thành công.</strong>
                {ketQua.fandom_match.unmatched.length ? (
                  <span>
                    Chưa nhận ra fandom: {ketQua.fandom_match.unmatched.join(", ")}.
                    Các tên này chưa được gắn vào truyện; hãy mở truyện để kiểm tra
                    và chỉnh lại.
                  </span>
                ) : (
                  <span>Tất cả tên fandom đã được đối chiếu thành công.</span>
                )}
                <Link
                  className="btn btn-primary"
                  href={`/novels/${ketQua.novel.novel_id}`}
                  prefetch={false}
                >
                  Mở truyện vừa nhập
                </Link>
              </span>
            </Alert>
          ) : null}
        </section>
      </div>
    </div>
  );
}
