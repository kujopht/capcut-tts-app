import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import { SessionProvider } from "@/lib/session";
import { ToastProvider } from "@/lib/toast";
import { NavAuth, NavLinks } from "@/components/NavAuth";

export const metadata: Metadata = {
  title: "Fanfic Audio Studio",
  description:
    "Tạo audio từ văn bản bất kỳ và nghe fanfic bằng giọng đọc tiếng Việt.",
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
                <Link href="/" className="brand">
                  <span className="brand-mark" aria-hidden="true">
                    ♫
                  </span>
                  <span>
                    Fanfic <span className="brand-text-sub">Audio Studio</span>
                  </span>
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
                <span className="hint">
                  Giọng đọc chạy cục bộ chưa xác minh giấy phép thương mại.
                </span>
              </div>
            </footer>
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
