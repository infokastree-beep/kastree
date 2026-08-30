"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { FUNCTIONAL_CURRENCIES } from "@/lib/constants";
import type { ClientCreateRequest, IClient } from "@/types";

type CreateClientFormProps = {
  /** After create, redirect here with `?client=<id>` appended. */
  redirectPath?: string;
};

export function CreateClientForm({ redirectPath = "/upload" }: CreateClientFormProps) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [name, setName] = useState("");
  const [functionalCurrency, setFunctionalCurrency] = useState("GBP");
  const [companyNumber, setCompanyNumber] = useState("");
  const [industry, setIndustry] = useState("");

  const createMutation = useMutation({
    mutationFn: () => {
      const body: ClientCreateRequest = {
        name: name.trim(),
        functional_currency: functionalCurrency,
      };
      const trimmedCompany = companyNumber.trim();
      const trimmedIndustry = industry.trim();
      if (trimmedCompany) {
        body.company_number = trimmedCompany;
      }
      if (trimmedIndustry) {
        body.industry = trimmedIndustry;
      }
      return apiFetch<IClient>("/clients", {
        method: "POST",
        getToken,
        body: JSON.stringify(body),
      });
    },
    onSuccess: (client) => {
      const separator = redirectPath.includes("?") ? "&" : "?";
      router.push(`${redirectPath}${separator}client=${client.id}`);
    },
  });

  const errorMessage =
    createMutation.error instanceof Error ? createMutation.error.message : null;

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim()) return;
        createMutation.mutate();
      }}
    >
      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Name</span>
        <input
          required
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Acme Ltd"
        />
      </label>

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Functional currency</span>
        <select
          className="w-full rounded border border-stone-300 bg-white px-3 py-2"
          value={functionalCurrency}
          onChange={(event) => setFunctionalCurrency(event.target.value)}
        >
          {FUNCTIONAL_CURRENCIES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </label>

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">
          Company number <span className="text-stone-400">(optional)</span>
        </span>
        <input
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={companyNumber}
          onChange={(event) => setCompanyNumber(event.target.value)}
          placeholder="12345678"
        />
      </label>

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">
          Industry <span className="text-stone-400">(optional)</span>
        </span>
        <input
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={industry}
          onChange={(event) => setIndustry(event.target.value)}
          placeholder="Professional services"
        />
      </label>

      {errorMessage ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={!name.trim() || createMutation.isPending}
        className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {createMutation.isPending ? "Creating…" : "Create client"}
      </button>
    </form>
  );
}
