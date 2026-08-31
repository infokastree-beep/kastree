"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { FUNCTIONAL_CURRENCIES } from "@/lib/constants";
import type {
  ClientCreateRequest,
  CompanyCreateRequest,
  CompanyUpdateRequest,
  IClient,
  ICompany,
} from "@/types";

type CreateClientFormProps = {
  /** After create, redirect here with `?company=<id>` appended. */
  redirectPath?: string;
};

type Step = "client" | "company";

const DEFAULT_MATERIALITY_PCT = "10.00";
const DEFAULT_MATERIALITY_ABS = "1000.00";

export function CreateClientForm({ redirectPath = "/upload" }: CreateClientFormProps) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [step, setStep] = useState<Step>("client");

  const [clientName, setClientName] = useState("");
  const [createdClient, setCreatedClient] = useState<IClient | null>(null);

  const [companyName, setCompanyName] = useState("");
  const [functionalCurrency, setFunctionalCurrency] = useState("GBP");
  const [companyNumber, setCompanyNumber] = useState("");
  const [industry, setIndustry] = useState("");
  const [materialityPct, setMaterialityPct] = useState(DEFAULT_MATERIALITY_PCT);
  const [materialityAbs, setMaterialityAbs] = useState(DEFAULT_MATERIALITY_ABS);

  const createClientMutation = useMutation({
    mutationFn: () => {
      const body: ClientCreateRequest = { name: clientName.trim() };
      return apiFetch<IClient>("/clients", {
        method: "POST",
        getToken,
        body: JSON.stringify(body),
      });
    },
    onSuccess: (client) => {
      setCreatedClient(client);
      setCompanyName(clientName.trim());
      setStep("company");
    },
  });

  const createCompanyMutation = useMutation({
    mutationFn: async () => {
      if (!createdClient) {
        throw new Error("Client not created yet");
      }
      const body: CompanyCreateRequest = {
        name: companyName.trim(),
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
      const company = await apiFetch<ICompany>(
        `/clients/${createdClient.id}/companies`,
        {
          method: "POST",
          getToken,
          body: JSON.stringify(body),
        },
      );

      const pctChanged = materialityPct !== DEFAULT_MATERIALITY_PCT;
      const absChanged = materialityAbs !== DEFAULT_MATERIALITY_ABS;
      if (pctChanged || absChanged) {
        const update: CompanyUpdateRequest = {};
        if (pctChanged) {
          update.materiality_threshold_pct = materialityPct;
        }
        if (absChanged) {
          update.materiality_threshold_abs = materialityAbs;
        }
        return apiFetch<ICompany>(`/companies/${company.id}`, {
          method: "PUT",
          getToken,
          body: JSON.stringify(update),
        });
      }
      return company;
    },
    onSuccess: (company) => {
      const separator = redirectPath.includes("?") ? "&" : "?";
      router.push(`${redirectPath}${separator}company=${company.id}`);
    },
  });

  const errorMessage =
    (step === "client"
      ? createClientMutation.error
      : createCompanyMutation.error) instanceof Error
      ? (step === "client"
          ? createClientMutation.error
          : createCompanyMutation.error)!.message
      : null;

  if (step === "company" && createdClient) {
    return (
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (!companyName.trim()) return;
          createCompanyMutation.mutate();
        }}
      >
        <p className="text-sm text-stone-600">
          Client group <span className="font-medium text-stone-900">{createdClient.name}</span>{" "}
          created. Add the first company entity below — you can add more later from the client
          detail page.
        </p>

        <label className="block text-sm">
          <span className="mb-1 block text-stone-600">Company name</span>
          <input
            required
            type="text"
            className="w-full rounded border border-stone-300 px-3 py-2"
            value={companyName}
            onChange={(event) => setCompanyName(event.target.value)}
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

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block text-stone-600">Materiality %</span>
            <input
              type="number"
              min="0"
              step="0.01"
              className="w-full rounded border border-stone-300 px-3 py-2"
              value={materialityPct}
              onChange={(event) => setMaterialityPct(event.target.value)}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-stone-600">Materiality absolute</span>
            <input
              type="number"
              min="0"
              step="0.01"
              className="w-full rounded border border-stone-300 px-3 py-2"
              value={materialityAbs}
              onChange={(event) => setMaterialityAbs(event.target.value)}
            />
          </label>
        </div>

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

        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={!companyName.trim() || createCompanyMutation.isPending}
            className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {createCompanyMutation.isPending ? "Creating…" : "Create company & continue"}
          </button>
          <button
            type="button"
            disabled={createCompanyMutation.isPending}
            onClick={() => router.push(`/clients/${createdClient.id}`)}
            className="rounded border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700"
          >
            Skip to client detail
          </button>
        </div>
      </form>
    );
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!clientName.trim()) return;
        createClientMutation.mutate();
      }}
    >
      <p className="text-sm text-stone-600">
        Start with a client group name (e.g. a family or holding structure). You will add the
        first company entity in the next step.
      </p>

      <label className="block text-sm">
        <span className="mb-1 block text-stone-600">Client group name</span>
        <input
          required
          type="text"
          className="w-full rounded border border-stone-300 px-3 py-2"
          value={clientName}
          onChange={(event) => setClientName(event.target.value)}
          placeholder="Smith Family Group"
        />
      </label>

      {errorMessage ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={!clientName.trim() || createClientMutation.isPending}
        className="rounded bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {createClientMutation.isPending ? "Creating…" : "Continue"}
      </button>
    </form>
  );
}
