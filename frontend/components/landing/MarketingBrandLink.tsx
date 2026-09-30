import Link from "next/link";
import { KastreeLogo } from "@/components/brand/KastreeLogo";

/**
 * Public marketing brand control — always navigates to `/` (no auth).
 *
 * Do not use ProductSwitcher here: its dashboard default is `/clients`, which
 * Clerk protects and redirects signed-out visitors to `/sign-in`.
 */
export function MarketingBrandLink({
  className = "h-12 w-auto sm:h-14",
}: {
  className?: string;
}) {
  return (
    <Link href="/" className="inline-flex shrink-0">
      <KastreeLogo className={className} />
    </Link>
  );
}
