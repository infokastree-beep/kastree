import Link from "next/link";
import { PRODUCTS, formatProductLabel } from "@/lib/products";

/**
 * Public marketing brand control — always navigates to `/` (no auth).
 *
 * Do not use ProductSwitcher here: its dashboard default is `/clients`, which
 * Clerk protects and redirects signed-out visitors to `/sign-in`.
 */
export function MarketingBrandLink({
  className = "font-display text-base font-semibold tracking-tight text-accent transition-colors hover:opacity-80 sm:text-lg",
}: {
  className?: string;
}) {
  const product = PRODUCTS[0];
  const label = product ? formatProductLabel(product) : "Kastree";

  return (
    <Link href="/" className={className}>
      {label}
    </Link>
  );
}
