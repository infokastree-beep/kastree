import Link from "next/link";
import { APP_NAME, DISCLAIMER_TEXT } from "@/lib/constants";

const FOOTER_LINKS = [
  { href: "/solutions/convert", label: "Convert" },
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
] as const;

export function MarketingFooter() {
  return (
    <footer className="border-t border-line bg-[var(--ink)] text-[var(--accent-muted)]">
      <div className="mx-auto max-w-content px-6 py-10 text-xs leading-relaxed sm:px-8">
        <p className="opacity-80">{DISCLAIMER_TEXT}</p>
        <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 font-medium text-white/90">
          <span>
            © {new Date().getFullYear()} {APP_NAME}
          </span>
          {FOOTER_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-white/70 underline-offset-4 hover:text-white hover:underline"
            >
              {link.label}
            </Link>
          ))}
        </p>
      </div>
    </footer>
  );
}
