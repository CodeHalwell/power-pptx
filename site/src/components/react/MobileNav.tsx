import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { DOCS_SIDEBAR, SITE, TOP_NAV } from "@/lib/site";

/**
 * Mobile navigation drawer (shadcn-style sheet). Renders the top-level nav
 * plus the full docs sidebar for small screens.
 */
export default function MobileNav({ currentPath }: { currentPath: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <div className="lg:hidden">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation menu"
        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-muted-foreground shadow-sm hover:bg-accent hover:text-accent-foreground"
      >
        <Menu className="h-4 w-4" aria-hidden="true" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-border bg-background shadow-xl">
            <div className="flex h-14 items-center justify-between border-b border-border px-4">
              <span className="font-semibold">{SITE.title}</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation menu"
                className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto px-4 py-4">
              <ul className="space-y-1 pb-4">
                {TOP_NAV.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      onClick={() => setOpen(false)}
                      className={`block rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent ${
                        currentPath.startsWith(link.href)
                          ? "bg-accent text-accent-foreground"
                          : "text-muted-foreground"
                      }`}
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
              {DOCS_SIDEBAR.map((section) => (
                <div key={section.title} className="pb-4">
                  <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {section.title}
                  </p>
                  <ul className="space-y-1">
                    {section.items.map((item) => (
                      <li key={item.href}>
                        <a
                          href={item.href}
                          onClick={() => setOpen(false)}
                          className={`block rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-accent ${
                            currentPath === item.href
                              ? "bg-accent font-medium text-accent-foreground"
                              : "text-muted-foreground"
                          }`}
                        >
                          {item.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </nav>
          </div>
        </div>
      )}
    </div>
  );
}
