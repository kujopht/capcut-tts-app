/**
 * Dựng harness QA giao diện Trợ lý AI bằng esbuild (có sẵn trong web/node_modules) -> scripts/qa/ai_ui/out/.
 * Dùng: node scripts/qa/ai_ui/build.mjs
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../..");
const web = path.join(repo, "web");
const require = createRequire(path.join(web, "package.json"));
const esbuild = require("esbuild");

const stubs = path.join(here, "harness/stubs");
const REPLACE = new Map([
  ["@/lib/api", path.join(stubs, "api.ts")],
  ["@/lib/session", path.join(stubs, "session.tsx")],
  ["next/link", path.join(stubs, "next-link.tsx")],
  ["next/navigation", path.join(stubs, "next-navigation.ts")],
]);

const stubPlugin = {
  name: "qa-stubs",
  setup(b) {
    b.onResolve({ filter: /.*/ }, (args) => {
      if (REPLACE.has(args.path)) return { path: REPLACE.get(args.path) };
      // Linh vật Ink Scout luôn tắt trong QA: không kéo mã của nó (và thư viện của nó) vào bundle.
      if (/(^|\/)companion\/AiCompanion$/.test(args.path) || (args.path === "./AiCompanion" && /companion/.test(args.importer))) {
        return { path: path.join(stubs, "ai-companion.tsx") };
      }
      return undefined;
    });
  },
};

export async function buildHarness() {
  const out = path.join(here, "out");
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({
    entryPoints: { entry: path.join(here, "harness/entry.tsx") },
    outdir: out,
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    jsx: "automatic",
    sourcemap: false,
    minify: false,
    logLevel: "warning",
    tsconfig: path.join(web, "tsconfig.json"),
    nodePaths: [path.join(web, "node_modules")],
    loader: { ".css": "css", ".woff2": "dataurl", ".woff": "dataurl", ".svg": "dataurl", ".png": "dataurl", ".webp": "dataurl" },
    // Ảnh nền tuyệt đối (/artwork/...) không có trong harness: để nguyên, trình duyệt sẽ 404 vô hại.
    external: ["/artwork/*", "/fonts/*", "/*.svg", "/*.png", "/*.webp"],
    define: {
      // Mọi `process.env.X` khác (cờ tính năng không liên quan) đọc ra `undefined` thay vì ném ReferenceError trên trình duyệt.
      "process.env": "{}",
      "process.env.NODE_ENV": '"production"',
      "process.env.NEXT_PUBLIC_AI_ASSISTANT_ENABLED": '"1"',
      "process.env.NEXT_PUBLIC_AI_COMPANION_ENABLED": '"0"',
      "process.env.NEXT_PUBLIC_API_BASE": '"http://qa.local"',
    },
    plugins: [stubPlugin],
  });
  fs.copyFileSync(path.join(here, "harness/index.html"), path.join(out, "index.html"));
  return out;
}

if (import.meta.url === `file://${process.argv[1].replace(/\\/g, "/")}` || process.argv[1]?.endsWith("build.mjs")) {
  buildHarness().then((o) => console.log("ok ->", o)).catch((e) => {
    console.error(e.message ?? e);
    process.exit(1);
  });
}
