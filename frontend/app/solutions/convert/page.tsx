import type { Metadata } from "next";
import { MarketingFooter } from "@/components/landing/MarketingFooter";
import { MarketingNav } from "@/components/landing/MarketingNav";
import { ConvertTool } from "@/components/solutions/ConvertTool";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `Convert trial balance (PDF to Excel) — ${APP_NAME}`,
  description:
    "One-time PDF trial balance conversion to Excel. Review extracted rows, pay €19, download. No account required.",
};

export default function SolutionsConvertPage() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <MarketingNav />
      <main>
        <ConvertTool />
      </main>
      <MarketingFooter />
    </div>
  );
}
