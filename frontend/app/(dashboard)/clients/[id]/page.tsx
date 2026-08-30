/** Placeholder — client detail is out of scope for the core-loop demo. */

export default function ClientDetailPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <main>
      <h1 className="text-xl font-semibold">Client</h1>
      <p className="mt-2 text-sm text-stone-600">id: {params.id}</p>
    </main>
  );
}
