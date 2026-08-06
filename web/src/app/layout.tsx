import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fanfic Audio Studio",
  description: "Nền tảng nghe audio tiểu thuyết và fanfic. Bản MVP riêng tư.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>
        <a className="skip-link" href="#main">
          Bỏ qua điều hướng
        </a>
        <header className="nav">
          <div className="shell nav-inner">
            <Link href="/" className="brand" aria-label="Fanfic Audio Studio — trang chủ">
              <span className="brand-mark" aria-hidden="true">
                ♪
              </span>
              <span>Fanfic Audio Studio</span>
            </Link>
            <nav className="nav-links" aria-label="Điều hướng chính">
              <Link href="/library">Thư viện</Link>
              <Link href="/studio">Creator Studio</Link>
              <Link href="/login">Đăng nhập</Link>
            </nav>
          </div>
        </header>
        <main id="main" className="shell">
          {children}
        </main>
        <footer className="shell" style={{ padding: "48px 20px", color: "var(--text-faint)", fontSize: 13 }}>
          <p>
            Bản MVP kỹ thuật, dùng riêng. Chưa sẵn sàng thương mại — chưa có
            thanh toán và chưa xác minh giấy phép cho giọng đọc chạy cục bộ.
          </p>
        </footer>
      </body>
    </html>
  );
}
