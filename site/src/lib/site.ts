/**
 * Central site configuration shared by layouts, pages and React islands.
 * Paths are passed through `withBase()` so the site works under the
 * GitHub Pages base path (`/power-pptx`).
 */
import { withBase } from "./utils";

export const SITE = {
  title: "power-pptx",
  tagline: "Create PowerPoint decks from Python — that actually fit.",
  description:
    "power-pptx is the actively-maintained fork of python-pptx. Build, mutate, lint, theme, animate and render PowerPoint (.pptx) decks from Python — with space-aware authoring so text never overflows its box.",
  version: "2.10.0",
  github: "https://github.com/CodeHalwell/power-pptx",
  pypi: "https://pypi.org/project/power-pptx/",
  upstreamDocs: "https://python-pptx.readthedocs.io/en/latest/",
  license: "MIT",
  python: "3.9 – 3.13",
} as const;

export interface NavLink {
  label: string;
  href: string;
}

export const TOP_NAV: NavLink[] = [
  { label: "Getting Started", href: withBase("/getting-started") },
  { label: "Advanced Usage", href: withBase("/advanced/space-aware-authoring") },
  { label: "Coding Agents", href: withBase("/agents") },
  { label: "API Reference", href: withBase("/api") },
];

export interface SidebarSection {
  title: string;
  items: NavLink[];
}

export const DOCS_SIDEBAR: SidebarSection[] = [
  {
    title: "Introduction",
    items: [
      { label: "Getting Started", href: withBase("/getting-started") },
      { label: "Coding Agents", href: withBase("/agents") },
    ],
  },
  {
    title: "Advanced Usage",
    items: [
      {
        label: "Space-Aware Authoring",
        href: withBase("/advanced/space-aware-authoring"),
      },
      { label: "Geometry & Arrows", href: withBase("/advanced/geometry-and-arrows") },
      { label: "Diagram Recipes", href: withBase("/advanced/diagrams") },
      { label: "Design System", href: withBase("/advanced/design") },
      { label: "Effects & Gradients", href: withBase("/advanced/effects") },
      { label: "Animations & Transitions", href: withBase("/advanced/animations") },
      { label: "Charts", href: withBase("/advanced/charts") },
      { label: "Themes", href: withBase("/advanced/theme") },
      { label: "Compose & Templates", href: withBase("/advanced/compose") },
      { label: "Lint & Audit", href: withBase("/advanced/lint") },
      { label: "Rendering Thumbnails", href: withBase("/advanced/render") },
      { label: "Tables & SmartArt & 3D", href: withBase("/advanced/tables-smartart-3d") },
    ],
  },
  {
    title: "Reference",
    items: [
      { label: "API Reference", href: withBase("/api") },
      { label: "Presentation & Slides", href: withBase("/api/presentation") },
      { label: "Shapes & Geometry", href: withBase("/api/shapes") },
      { label: "Text", href: withBase("/api/text") },
      { label: "Charts", href: withBase("/api/charts") },
      { label: "Design System", href: withBase("/api/design") },
      { label: "Compose, Lint & Render", href: withBase("/api/compose-lint-render") },
      { label: "Enumerations", href: withBase("/api/enumerations") },
    ],
  },
];
