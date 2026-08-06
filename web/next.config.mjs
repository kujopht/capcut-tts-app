/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend giu moi bi mat. Bien duy nhat lo ra trinh duyet la URL API.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
  },
};
export default nextConfig;
