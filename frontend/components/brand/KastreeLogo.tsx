/**
 * Official Kastree lockup: bar mark, wordmark, and “Financial Intelligence”.
 * Artwork is the supplied logo; do not restyle the wordmark in CSS.
 */
export function KastreeLogo({ className = "h-14 w-auto" }: { className?: string }) {
  return (
    <img
      src="/brand/kastree-logo.png"
      alt="Kastree Financial Intelligence"
      width={1102}
      height={332}
      className={className}
    />
  );
}
