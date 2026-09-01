import Link from "next/link";

/** Plain sign-in link — SSR-visible; does not depend on Clerk client hydration. */
export function SignInNavLink({ className }: { className?: string }) {
  return (
    <Link href="/sign-in" className={className}>
      Sign in
    </Link>
  );
}
