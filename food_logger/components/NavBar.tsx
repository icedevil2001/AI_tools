"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/log", label: "Log meal" },
  { href: "/episode", label: "Symptom" },
  { href: "/history", label: "History" },
];

/**
 * Fixed bottom tab bar. Bottom placement is deliberate: this is used
 * one-handed, and the top of a phone screen is the hardest place to reach.
 */
export function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="fixed inset-x-0 bottom-0 z-10 border-t border-ink/10 bg-cream/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
      <ul className="mx-auto flex max-w-md">
        {TABS.map((tab) => {
          const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
          return (
            <li key={tab.href} className="flex-1">
              <Link
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={[
                  "block py-4 text-center text-sm",
                  active ? "font-semibold text-ink" : "text-ink/50",
                ].join(" ")}
              >
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
