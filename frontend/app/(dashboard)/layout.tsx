"use client";

import Link from "next/link";
import { UserButton } from "@clerk/nextjs";
import { ProductSwitcher } from "@/components/layout/ProductSwitcher";
import { clerkReady } from "@/lib/clerk";

export default function DashboardGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <ProductSwitcher />
            <nav className="flex gap-4 text-sm text-stone-600">
              <Link href="/clients" className="hover:text-stone-900">
                Clients
              </Link>
              <Link href="/upload" className="hover:text-stone-900">
                Upload
              </Link>
            </nav>
          </div>
          {clerkReady ? <UserButton afterSignOutUrl="/" /> : null}
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-4 py-8">{children}</div>
    </div>
  );
}
