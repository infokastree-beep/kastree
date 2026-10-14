"use client";

import { formatStoredAmount } from "@/lib/currency";

const ROWS = [
  ["Net assets", "key-figure-net-assets"],
  ["Profit", "key-figure-profit"],
  ["Turnover", "key-figure-turnover"],
  ["Balance sheet total", "key-figure-balance-sheet"],
] as const;

export function KeyFiguresCard({
  currency,
  netAssets,
  profit,
  turnover,
  balanceSheetTotal,
}: {
  currency: string | null;
  netAssets: string | null;
  profit: string | null;
  turnover: string | null;
  balanceSheetTotal: string | null;
}) {
  const stored = {
    "key-figure-net-assets": netAssets,
    "key-figure-profit": profit,
    "key-figure-turnover": turnover,
    "key-figure-balance-sheet": balanceSheetTotal,
  };
  return (
    <section className="mt-4" data-testid="statutory-key-figures">
      <h3 className="text-sm font-semibold">Key figures</h3>
      <dl className="mt-2 grid max-w-xl gap-2 text-sm text-ink">
        {ROWS.map(([label, testId]) => {
          const amount = stored[testId];
          return (
            <div key={testId} className="flex justify-between gap-4">
              <dt>{label}</dt>
              <dd data-testid={testId} data-stored={amount ?? ""}>
                {formatStoredAmount(amount, currency)}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
