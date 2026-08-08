// Next.js 16 xuat truc tiep flat config, khong can FlatCompat.
import next from "eslint-config-next";

const config = [
  ...next,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "out/**",
      "next-env.d.ts",
      // Artefact do `opennextjs-cloudflare build` sinh ra: worker đã bundle,
      // asset đã minify, shim của adapter. Lint chúng chỉ ra lỗi của công cụ
      // khác — đã thấy thật: "Definition for rule
      // '@typescript-eslint/no-explicit-any' was not found" trong config sinh
      // tự động, và cảnh báo `window.location.href` trong chunk đã minify.
      // Không có gì ở đây do người viết nên không có gì để sửa.
      ".open-next/**",
      ".wrangler/**",
      "cloudflare-env.d.ts",
    ],
  },
];

export default config;
