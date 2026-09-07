import type { Metadata } from "next";
import Link from "next/link";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `Interim Terms of Use — ${APP_NAME}`,
  description:
    "Interim terms for using Kastree for internal management-accounts review.",
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-content items-center justify-between px-6 py-5 sm:px-8">
          <Link
            href="/"
            className="font-display text-lg font-medium tracking-tight text-ink"
          >
            {APP_NAME}
          </Link>
          <Link
            href="/"
            className="text-sm text-ink-secondary underline-offset-4 hover:underline"
          >
            Home
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
        <p className="text-sm text-ink-secondary">Last updated: 7 September 2026</p>
        <h1 className="mt-3 font-display text-heading-lg text-ink sm:text-[2.25rem]">
          Interim Terms of Use
        </h1>
        <div className="mt-10 max-w-2xl space-y-5 text-base leading-relaxed text-ink-secondary">
          <p>
            Kastree is provided for{" "}
            <strong className="font-medium text-ink">
              internal management-accounts review and analysis only
            </strong>
            . It is not a statutory financial statement, not an audit or
            assurance product, and is not intended for regulatory filing.
          </p>
          <p>
            The service is provided{" "}
            <strong className="font-medium text-ink">“as is”</strong> and “as
            available,” without warranties of any kind to the fullest extent
            permitted by law.
          </p>
          <p>
            To the maximum extent permitted by law, Kastree’s aggregate
            liability arising from use of the service is limited to the fees
            you paid to Kastree for the service in the{" "}
            <strong className="font-medium text-ink">
              twelve (12) months
            </strong>{" "}
            before the claim (or €0 if no fees were paid).
          </p>
          <p>
            Either party may stop using or providing the service at any time
            (including by closing an account or suspending access).
          </p>
          <p>
            These interim terms are governed by the laws of{" "}
            <strong className="font-medium text-ink">Ireland</strong>. For how
            we handle data, see the{" "}
            <Link
              href="/privacy"
              className="text-ink underline-offset-4 hover:underline"
            >
              Privacy Policy
            </Link>
            .
          </p>
          <p className="text-sm text-soft">
            This page is a short interim notice only. A fuller Terms of Service
            and Data Processing Agreement remain in draft pending solicitor
            review and are not yet published.
          </p>
        </div>
      </main>
    </div>
  );
}
