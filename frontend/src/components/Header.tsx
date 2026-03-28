"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Header() {
  const pathname = usePathname();

  const linkClass = (href: string) => {
    const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
    return `text-sm font-medium transition-colors ${
      active
        ? "text-white"
        : "text-white/70 hover:text-white"
    }`;
  };

  return (
    <header className="sticky top-0 z-50 bg-nu-purple shadow-md">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-white font-bold text-lg">
          <span className="text-xl">🐾</span>
          <span>NU Events</span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link href="/" className={linkClass("/")}>
            Events
          </Link>
          <Link href="/organizations" className={linkClass("/organizations")}>
            Organizations
          </Link>
        </nav>
      </div>
    </header>
  );
}
