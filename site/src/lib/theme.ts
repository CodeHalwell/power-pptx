import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

/**
 * Astro hydrates each `client:*` island as its own React root, so React
 * context cannot be shared between islands. The theme therefore lives in the
 * DOM instead: `<html class="dark">` (set before paint by the inline script in
 * BaseLayout) is the single source of truth, persisted in localStorage.
 */

/** Apply a theme: `<html>` class + `color-scheme` + persistence. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  try {
    window.localStorage.setItem("theme", theme);
  } catch {
    // Storage unavailable (private mode); the theme still applies to this page.
  }
}

/**
 * React hook mirroring the `<html class="dark">` state into any island.
 * Returns null until mounted so SSR markup never disagrees with the client.
 */
export function useSiteTheme(): Theme | null {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const root = document.documentElement;
    const read = () => setTheme(root.classList.contains("dark") ? "dark" : "light");
    read();
    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return theme;
}
