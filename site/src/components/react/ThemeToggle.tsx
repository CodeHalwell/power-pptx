import { Monitor, Moon, Sun } from "lucide-react";
import { applyTheme, useSiteTheme } from "@/lib/theme";

/**
 * shadcn-style icon button that toggles between light (default) and dark.
 * Self-contained: reads and writes the `<html class="dark">` + localStorage
 * state directly, since React context cannot cross Astro island boundaries.
 * Renders a neutral icon until hydrated to avoid a mismatch.
 */
export default function ThemeToggle() {
  const theme = useSiteTheme();

  const toggle = () => {
    if (theme === null) return;
    applyTheme(theme === "dark" ? "light" : "dark");
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {theme === null ? (
        <Monitor className="h-4 w-4" aria-hidden="true" />
      ) : theme === "dark" ? (
        <Sun className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Moon className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  );
}
