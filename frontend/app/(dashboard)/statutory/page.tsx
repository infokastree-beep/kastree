import { StatutoryWorkbench } from "@/components/statutory/StatutoryWorkbench";

/** Statutory year-end. The workbench hides itself unless the caller is a platform admin. */
export default function StatutoryPage() {
  return <StatutoryWorkbench />;
}
