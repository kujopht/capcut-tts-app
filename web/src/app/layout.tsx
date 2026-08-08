import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import { SessionProvider } from "@/lib/session";
import { ToastProvider } from "@/lib/toast";
import { NavAuth, NavLinks } from "@/components/NavAuth";
import { Logo } from "@/components/Logo";

const DESCRIPTION =
  "Tạo audio từ văn bản bất kỳ và nghe fanfic bằng giọng đọc tiếng Việt.";

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

            <header className="site-header">
              <div className="wrap">
                <Link href="/" className="brand" aria-label="Fanfic Audio Studio — trang chủ">
                  <Logo size={30} />
                </Link>
                <NavLinks />
                <span className="spacer" />
                <NavAuth />
              </div>
            </header>

            <main id="main">
              <div className="wrap">{children}</div>
            </main>

            <footer className="site-footer">
              <div className="wrap row-between">
                <span>
                  Fanfic Audio Studio — bản MVP riêng tư, chưa thương mại.
                </span>
                {/*
                  Câu cũ ở đây là "Giọng đọc chạy cục bộ chưa xác minh giấy
                  phép thương mại." Chủ dự án đã cho phép công bố các giọng
                  NghiTTS và chịu trách nhiệm về quyền sử dụng, nên câu đó
                  không còn đúng. Thay bằng một sự thật kỹ thuật người dùng
                  cần biết: một số giọng xử lý trên máy riêng, nên có thể phải
                  chờ.
                */}
                <span className="hint">
                  Một số giọng được xử lý trên máy riêng nên có thể phải chờ.
                </span>
              </div>
            </footer>
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
