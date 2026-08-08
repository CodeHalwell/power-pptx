// @ts-check
import react from "@astrojs/react";
import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

// https://astro.build/config
export default defineConfig({
  site: "https://codehalwell.github.io",
  base: "/power-pptx",
  trailingSlash: "always",
  integrations: [react(), sitemap()],
  vite: {
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
