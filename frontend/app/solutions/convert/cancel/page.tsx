import type { Metadata } from "next";
import Link from "next/link";
import { MarketingFooter } from "@/components/landing/MarketingFooter";
import { MarketingNav } from "@/components/landing/MarketingNav";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `Checkout cancelled — ${APP_NAME}`,
};

export default function ConvertCancelPage() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <MarketingNav />
      <main className="mx-auto max-w-xl space-y-4 px-6 py-16 sm:px-8">
        <h1 className="font-display text-3xl tracking-tight">Checkout cancelled</h1>
        <p className="text-ink-secondary">
          No charge was made. You can return to Convert and try again whenever
          you are ready.
        </p>
        <Link
          href="/solutions/convert"
          className="inline-block rounded bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
        >
          Back to Convert
        </Link>
      </main>
      <MarketingFooter />
    </div>
  );
}
