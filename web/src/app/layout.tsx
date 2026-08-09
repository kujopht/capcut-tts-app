import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import { SessionProvider } from "@/lib/session";
import { ToastProvider } from "@/lib/toast";
import { NavAuth, NavLinks } from "@/components/NavAuth";
import { SiteSearch } from "@/components/SiteSearch";
import { Logo } from "@/components/Logo";

// Mo ta cu noi ve viec tao audio truoc tien. San pham nay la nen tang doc va
// nghe fanfic; Audio Studio la cong cu phu. Mo ta cung phai noi theo thu tu do.
const DESCRIPTION =
  "Đọc và nghe fanfic tiếng Việt. Khám phá truyện do cộng đồng xuất bản, nghe bằng giọng đọc tự nhiên.";

export const metadata: Metadata = {
  // `template` de moi trang tu dat tieu de rieng ma van giu ten san pham
  title: { default: "Fanfic Audio Studio", template: "%s · Fanfic Audio Studio" },
  description: DESCRIPTION,
  applicationName: "Fanfic Audio Studio",
  // `icon.svg`, `apple-icon.tsx` va `opengraph-image.tsx` trong cung thu muc
  // duoc Next tu gan vao <head> — khong khai bao tay o day.
  openGraph: {
    type: "website",
    siteName: "Fanfic Audio Studio",
    title: "Fanfic Audio Studio",
    description: DESCRIPTION,
    locale: "vi_VN",
  },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b0d12",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>
        <SessionProvider>
          <ToastProvider>
            <a className="skip-link" href="#main">
              Bỏ qua điều hướng
            </a>

            {/*
              Thu tu trong header la thu tu uu tien cua san pham: thuong hieu,
              ba muc doc/nghe, roi moi den tim kiem va cong cu. Audio Studio
              KHONG con o thanh chinh — no nam trong menu ben phai, va
              `/studio` giu nguyen duong dan lan chuc nang.
            */}
            <header className="site-header">
              <div className="wrap">
                <Link href="/" className="brand" aria-label="Fanfic World — trang chủ">
                  <Logo size={30} />
                </Link>
                <NavLinks />
                <span className="spacer" />
                <SiteSearch />
                <NavAuth />
              </div>
            </header>

            <main id="main">
              <div className="wrap">{children}</div>
            </main>

            {/*
              Footer CHI dan toi cac route CO THAT trong `src/app/`. Cac muc
              quen thuoc cua mot footer — Dieu khoan, Bao mat, Lien he — deu
              bi bo, vi tao lien ket toi trang chua ton tai la mot lien ket
              hong, va tao trang phap ly gia con te hon: no ngu y mot cam ket
              phap ly khong ai viet.
            */}
            <footer className="site-footer">
              <div className="wrap footer-grid">
                <div className="stack-2 footer-brand">
                  <Logo size={26} />
                  <p className="hint">
                    Nền tảng đọc và nghe fanfic tiếng Việt. Bản MVP riêng tư,
                    chưa thương mại.
                  </p>
                </div>

                <nav className="footer-col" aria-label="Đọc truyện">
                  <h2 className="footer-title">Đọc truyện</h2>
                  <Link href="/" className="footer-link">
                    Trang chủ
                  </Link>
                  <Link href="/fanfic" className="footer-link">
                    Khám phá
                  </Link>
                  <Link href="/library" className="footer-link">
                    Thư viện của bạn
                  </Link>
                </nav>

                <nav className="footer-col" aria-label="Sáng tác">
                  <h2 className="footer-title">Sáng tác</h2>
                  <Link href="/write" className="footer-link">
                    Khu vực tác giả
                  </Link>
                  <Link href="/studio" className="footer-link">
                    Audio Studio
                  </Link>
                  <Link href="/account" className="footer-link">
                    Tài khoản
                  </Link>
                </nav>
              </div>

              <div className="wrap footer-note">
                {/*
                  Câu này đã đổi hai lần, mỗi lần vì một sự thật đã thay đổi:

                  1. "Giọng đọc chạy cục bộ chưa xác minh giấy phép thương
                     mại." — chủ dự án đã cho phép công bố các giọng NghiTTS
                     và chịu trách nhiệm về quyền sử dụng.
                  2. Câu thay thế nói một số giọng xử lý trên máy cá nhân nên
                     có thể phải chờ — đúng khi worker còn chạy trên laptop
                     chủ dự án. Production chạy worker 24/7 trên Google Compute
                     Engine, nên cách nói đó vừa sai vừa gợi ý rằng người dùng
                     phải có máy của riêng họ.

                  Câu hiện tại chỉ nói điều còn đúng: xếp hàng là có thật, và
                  đóng trang không làm mất job.
                */}
                <span className="hint">
                  Giọng NghiTTS xử lý trên máy chủ và có thể phải xếp hàng.
                </span>
              </div>
            </footer>
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
