import { StatementsDashboard } from "@/components/statements/StatementsDashboard";

/** Dashboard — tabs + generate action are Client Components. */
export default function DashboardPage({
  params,
}: {
  params: { tbId: string };
}) {
  return <StatementsDashboard tbId={params.tbId} />;
}
