"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import {
  UNREVIEWED_WORDING_BANNER,
  type StatutoryUser,
} from "@/lib/statutory-gate";

export function UnreviewedWordingNotice() {
  return (
    <p
      className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-ink"
      data-testid="unreviewed-wording-banner"
      role="status"
    >
      {UNREVIEWED_WORDING_BANNER}
    </p>
  );
}

export function UnreviewedWordingBanner() {
  const { getToken, isSignedIn } = useAuth();
  const meQuery = useQuery({
    queryKey: ["users", "me"],
    queryFn: () => apiFetch<StatutoryUser>("/users/me", { getToken }),
    enabled: isSignedIn,
  });
  const access = meQuery.data?.product2_access;
  if (!access || access.source !== "admin" || access.wording_signed_off) {
    return null;
  }
  return <UnreviewedWordingNotice />;
}
