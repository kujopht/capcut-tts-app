import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const WEB = fileURLToPath(new URL("../../../web/", import.meta.url));
const require = createRequire(WEB + "package.json");
const esbuild = require("esbuild");
const res = await esbuild.build({
  stdin: {
    contents: `
      import * as core from "./src/game/inkscout/core/index.ts";
      import { createBot, FULL_GOALS, MIN_GOALS } from "./tests/helpers/bot.mjs";
      window.__INK_BOT__ = { core, createBot, FULL_GOALS, MIN_GOALS };
    `,
    resolveDir: WEB,
    loader: "js",
  },
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2022",
  write: false,
  tsconfig: WEB + "tsconfig.json",
});
const outDir = fileURLToPath(new URL("./out/", import.meta.url));
mkdirSync(outDir, { recursive: true });
const out = outDir + "bot_bundle.js";
writeFileSync(out, res.outputFiles[0].text);
console.log("bundle bytes", res.outputFiles[0].text.length);
