import Link from "next/link";
import { CreateClientForm } from "@/components/clients/CreateClientForm";

export default function NewClientPage() {
  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <Link href="/clients" className="text-sm text-stone-600 hover:text-stone-900">
          ← Back to clients
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Create client</h1>
        <p className="mt-1 text-sm text-stone-600">
          Add a client, then continue to upload a trial balance.
        </p>
      </div>
      <CreateClientForm />
    </div>
  );
}
