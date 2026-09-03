"use client";

import Link from "next/link";
import { UserButton } from "@clerk/nextjs";
import { AdminNavLink } from "@/components/layout/AdminNavLink";
import { ProductSwitcher } from "@/components/layout/ProductSwitcher";
import { clerkReady } from "@/lib/clerk";

export default function DashboardGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b border-line/80 bg-surface-elevated/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div className="flex items-center gap-6">
            <ProductSwitcher />
            <nav className="flex gap-4 text-sm font-medium text-ink-secondary">
              <Link
                href="/clients"
                className="transition-colors hover:text-accent"
              >
                Clients
              </Link>
              <Link
                href="/upload"
                className="transition-colors hover:text-accent"
              >
                Upload
              </Link>
              <AdminNavLink />
            </nav>
          </div>
          {clerkReady ? <UserButton afterSignOutUrl="/" /> : null}
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">{children}</div>
    </div>
  );
}
