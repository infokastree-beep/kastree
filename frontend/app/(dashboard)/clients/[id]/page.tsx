import { ClientDetail } from "@/components/clients/ClientDetail";

export default function ClientDetailPage({
  params,
}: {
  params: { id: string };
}) {
  return <ClientDetail clientId={params.id} />;
}
