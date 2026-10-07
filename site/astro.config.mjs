// @ts-check
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import react from "@astrojs/react";
import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

/**
 * The version badge the site displays is read from the library's own
 * `__version__` at build time, so a release bump cannot leave the docs a
 * release behind (which happened once when this was a hand-maintained
 * constant).  Exposed to the source as the `__POWER_PPTX_VERSION__` global
 * via Vite's compile-time `define`, which works in both server-rendered
 * pages and client islands.
 */
function readPackageVersion() {
  const initPy = fileURLToPath(
    new URL("../src/power_pptx/__init__.py", import.meta.url),
  );
  const match = /^__version__\s*=\s*["']([^"']+)["']/m.exec(
    readFileSync(initPy, "utf8"),
  );
  if (!match) {
    throw new Error(`could not find __version__ in ${initPy}`);
  }
  return match[1];
}

const packageVersion = readPackageVersion();

// https://astro.build/config
export default defineConfig({
  site: "https://codehalwell.github.io",
  base: "/power-pptx",
  trailingSlash: "always",
  integrations: [react(), sitemap()],
  vite: {
    define: {
      __POWER_PPTX_VERSION__: JSON.stringify(packageVersion),
    },
    ssr: {
      // MUI/Emotion ship directory imports that Node ESM cannot resolve;
      // let Vite bundle them instead of externalizing to Node.
      noExternal: [/^@mui\//, /^@emotion\//],
    },
  },
  markdown: {
    shikiConfig: {
      themes: {
        light: "github-light",
        dark: "github-dark",
      },
    },
  },
});
