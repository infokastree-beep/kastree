import type { Metadata } from "next";
import { ContactForm } from "@/components/landing/ContactForm";
import { MarketingFooter } from "@/components/landing/MarketingFooter";
import { MarketingNav } from "@/components/landing/MarketingNav";
import { APP_NAME } from "@/lib/constants";

export const metadata: Metadata = {
  title: `Contact — ${APP_NAME}`,
  description: "Contact Kastree about the product, pricing, or your practice.",
};

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <MarketingNav />
      <main>
        <section className="relative overflow-hidden border-b border-line bg-surface-elevated">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--accent-muted)_0%,_transparent_55%),linear-gradient(180deg,_#ffffff_0%,_var(--surface)_100%)]"
          />
          <div className="relative mx-auto max-w-content px-6 pb-16 pt-16 sm:px-8 sm:pb-20 sm:pt-24">
            <p className="font-display text-3xl font-medium tracking-tight text-accent sm:text-4xl">
              {APP_NAME}
            </p>
            <h1 className="font-display mt-6 max-w-3xl text-display-lg text-ink sm:text-display-xl">
              Contact Kastree
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-secondary sm:text-xl">
              Questions about the product, pricing, or your practice — email or
              use the form. We read every message.
            </p>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-content px-6 py-section-sm sm:px-8 sm:py-section">
            <ContactForm />
            <p className="mt-8 max-w-xl text-sm leading-relaxed text-ink-secondary">
              Or email{" "}
              <a
                href="mailto:infokastree@gmail.com"
                className="font-medium text-accent underline-offset-4 hover:underline"
              >
                infokastree@gmail.com
              </a>{" "}
              directly.
            </p>
          </div>
        </section>
      </main>
      <MarketingFooter />
    </div>
  );
}
