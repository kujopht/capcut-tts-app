/**
 * Nạp lõi mô phỏng TypeScript của Ink Scout vào test bằng esbuild (đóng gói trong bộ nhớ, không ghi tệp): lõi có nhiều tệp import chéo
 * không đuôi, mà `node --test` chỉ gỡ kiểu chứ không phân giải được kiểu import đó. esbuild đã có sẵn trong cây `node_modules` (phụ thuộc của
 * wrangler/next) — CI `npm ci` cùng khoá nên cùng có.
 */
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, "../..");
const require = createRequire(path.join(webRoot, "package.json"));

const cache = new Map();

/** @param {string} entry đường dẫn tương đối từ `web/` (mặc định lõi). */
export async function loadModule(entry = "src/game/inkscout/core/index.ts") {
  if (cache.has(entry)) return cache.get(entry);
  const esbuild = require("esbuild");
  const out = await esbuild.build({
    entryPoints: [path.join(webRoot, entry)],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node22",
    write: false,
    logLevel: "silent",
    tsconfig: path.join(webRoot, "tsconfig.json"),
  });
  const code = out.outputFiles[0].text;
  const mod = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
  cache.set(entry, mod);
  return mod;
}
