"use client";

import { useEffect, useState } from "react";

/**
 * The PDF section, in a frame with no permissions.
 * The document address carries the note fragment so the frame can scroll to it.
 */
export function SectionPreview({
  html,
  scrollAnchor,
  title,
}: {
  html: string;
  scrollAnchor: string | null;
  title: string;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    const hash =
      scrollAnchor != null && /^[A-Za-z0-9_-]+$/.test(scrollAnchor)
        ? `#${scrollAnchor}`
        : "";
    setSrc(`${url}${hash}`);
    return () => URL.revokeObjectURL(url);
  }, [html, scrollAnchor]);

  if (src == null) {
    return null;
  }
  return (
    <iframe
      title={title}
      sandbox=""
      src={src}
      data-testid="statutory-section-preview"
      className="h-[720px] w-full rounded-md border border-line bg-white"
    />
  );
}
