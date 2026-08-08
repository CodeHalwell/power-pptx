// @ts-check
// Astro (Vite) picks this up automatically and runs every CSS file through
// Tailwind so `@tailwind` / `@apply` in src/styles/global.css are compiled.
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
