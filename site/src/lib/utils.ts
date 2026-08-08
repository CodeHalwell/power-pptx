import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Prefix a site-internal path with the Astro base path so links work when
 * the site is served from a sub-path (GitHub Pages project sites).
 * Page routes get a trailing slash (the site builds with
 * `trailingSlash: "always"`); file paths keep their exact name — a trailing
 * slash would turn e.g. `favicon.svg` into a 404.
 */
export function withBase(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const clean = path.replace(/^\//, "");
  if (clean === "") return `${base}/`;
  const isFile = /\.[a-z0-9]+$/i.test(clean);
  return isFile ? `${base}/${clean}` : `${base}/${clean}/`;
}

