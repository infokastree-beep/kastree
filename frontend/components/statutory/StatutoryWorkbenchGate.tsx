"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { StatutoryPointer } from "@/components/statutory/StatutoryPointer";
import { StatutoryWorkbench } from "@/components/statutory/StatutoryWorkbench";

type UserMe = {
  is_platform_admin: boolean;
};

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong";
}

/** Old workbench for platform administrators. Everyone else sees the pointer. */
export function StatutoryWorkbenchGate() {
  const { getToken, isSignedIn } = useAuth();
  const meQuery = useQuery({
    queryKey: ["users", "me"],
    queryFn: () => apiFetch<UserMe>("/users/me", { getToken }),
    enabled: isSignedIn,
  });

  if (!isSignedIn) {
    return <p className="text-sm text-stone-600">Sign in to continue.</p>;
  }
  if (meQuery.isLoading) {
    return <p className="text-sm text-stone-600">Loading…</p>;
  }
  if (meQuery.error) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        {messageFrom(meQuery.error)}
      </p>
    );
  }
  if (meQuery.data?.is_platform_admin !== true) {
    return <StatutoryPointer />;
  }

  return (
    <div className="space-y-6">
      <p
        className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
        data-testid="statutory-internal-banner"
      >
        Internal testing only
      </p>
      <StatutoryWorkbench />
    </div>
  );
}
