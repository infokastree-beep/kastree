import Link from "next/link";

/** Where a practice starts a statutory draft. The old workbench is not this page. */
export function StatutoryPointer() {
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Statutory drafts</h1>
      <p className="text-sm text-stone-700" data-testid="statutory-pointer">
        {"Statutory drafts start from a company's Statements page"}
      </p>
      <Link
        href="/clients"
        className="text-sm font-medium text-accent underline"
      >
        Clients
      </Link>
    </div>
  );
}
