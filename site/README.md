# power-pptx documentation site

The [power-pptx](https://github.com/CodeHalwell/power-pptx) documentation site,
built with **Astro**, **TypeScript**, **React**, **shadcn-style** UI primitives
(Tailwind + class-variance-authority) and **MUI** (Material UI) for interactive
islands. Light mode by default, with a persisted dark-mode toggle.

## Develop

```bash
cd site
npm install
npm run dev        # http://localhost:4321/power-pptx/
```

## Build

```bash
npm run build      # static output in dist/ (base path /power-pptx)
npm run preview    # serve the production build locally
```

The site deploys to GitHub Pages via `.github/workflows/pages.yml` on pushes to
`master` that touch `site/**`.

## Layout

```
src/
  layouts/BaseLayout.astro   # HTML shell: header, footer, no-flash theme init
  layouts/DocsLayout.astro   # docs chrome: sidebar + prose
  components/ui/             # shadcn-style primitives (button, card, badge)
  components/react/          # client islands (theme, mobile nav, MUI showcase)
  components/Code.astro      # code block (snippet passed as a string prop)
  lib/site.ts                # navigation + site metadata (single source)
  pages/                     # home, getting-started, agents, advanced/*, api/*
```

## Theming

Design tokens are CSS custom properties (`--background`, `--primary`, …) in
`src/styles/global.css`; `.dark` overrides them. The `ThemeProvider` React
island toggles the `dark` class on `<html>` and persists the choice in
`localStorage`; an inline script in `BaseLayout.astro` restores it before first
paint. The MUI showcase derives its palette mode from the same context.
