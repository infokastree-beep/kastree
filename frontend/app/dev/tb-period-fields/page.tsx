"use client";

import { UploadForm } from "@/components/upload/UploadForm";

/**
 * Auth-free preview of the upload period fields.
 * Visit /dev/tb-period-fields while checking Period start on both upload kinds.
 */
export default function TbPeriodFieldsPreviewPage() {
  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-xl font-medium text-stone-900">Upload period fields</h1>
      <UploadForm />
    </main>
  );
}
