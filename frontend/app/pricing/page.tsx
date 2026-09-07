import type { Metadata } from "next";
import { Suspense } from "react";
import { PricingPage } from "@/components/landing/PricingPage";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `Pricing — ${APP_NAME}`,
  description:
    "Simple pricing for accounting practices. Full Kastree toolkit on every plan — limits by client count only.",
};

export default function PricingRoutePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-surface px-6 py-16 text-ink-secondary">
          Loading pricing…
        </div>
      }
    >
      <PricingPage />
    </Suspense>
  );
}
