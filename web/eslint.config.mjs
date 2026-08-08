// Next.js 16 xuat truc tiep flat config, khong can FlatCompat.
import next from "eslint-config-next";

const config = [
  ...next,
  { ignores: [".next/**", "node_modules/**", "out/**", "next-env.d.ts"] },
];

export default config;
