import type { Metadata } from "next";
import { Suspense } from "react";
import { ConvertSuccessClient } from "@/components/solutions/ConvertSuccessClient";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `Conversion complete — ${APP_NAME}`,
};

export default function ConvertSuccessPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-surface px-6 py-16 text-ink-secondary">
          Confirming payment…
        </div>
      }
    >
      <ConvertSuccessClient />
    </Suspense>
  );
}
