import { MappingReview } from "@/components/mapping/MappingReview";

/** Mapping page — polling + inline overrides are Client Components. */
export default function MappingPage({
  params,
}: {
  params: { tbId: string };
}) {
  return <MappingReview tbId={params.tbId} />;
}
