"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { defaultCompanyCurrency } from "@/lib/company-form";
import type { IOrganisation } from "@/types";

export function useDefaultCompanyCurrency(): {
  currency: string;
  ready: boolean;
} {
  const { getToken, isLoaded } = useAuth();
  const query = useQuery({
    queryKey: ["organisation", "me"],
    enabled: isLoaded,
    queryFn: () =>
      apiFetch<IOrganisation>("/organisations/me", { getToken }),
  });
  const ready = isLoaded && (query.isSuccess || query.isError);
  return {
    currency: defaultCompanyCurrency(query.data?.jurisdiction),
    ready,
  };
}
