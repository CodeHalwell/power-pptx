import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Prefix a site-internal path with the Astro base path so links work when
 * the site is served from a sub-path (GitHub Pages project sites).
 */
export function withBase(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const clean = path.replace(/^\//, "");
  return clean === "" ? `${base}/` : `${base}/${clean}/`;
}

