import { UploadForm } from "@/components/upload/UploadForm";

/** Upload page — interactive dropzone lives in a Client Component. */
export default function UploadPage({
  searchParams,
}: {
  searchParams?: { company?: string };
}) {
  return <UploadForm initialCompanyId={searchParams?.company ?? ""} />;
}
