"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  CompanyEntityForm,
} from "@/components/clients/CompanyEntityForm";
import type { CompanyEntityFormValues } from "@/lib/company-form";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import { createCompanyEntity } from "@/lib/companies";
import type { ClientCreateRequest, IClient } from "@/types";

type CreateClientFormProps = {
  /** After create, redirect here with `?company=<id>` appended. */
  redirectPath?: string;
  /** Fires when the wizard advances from client group to first company. */
  onStepChange?: (step: Step) => void;
};

type Step = "client" | "company";

export type { Step as CreateClientStep };

export function CreateClientForm({
  redirectPath = "/upload",
  onStepChange,
}: CreateClientFormProps) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [step, setStep] = useState<Step>("client");

  const [clientName, setClientName] = useState("");
  const [createdClient, setCreatedClient] = useState<IClient | null>(null);

  useEffect(() => {
    onStepChange?.(step);
  }, [step, onStepChange]);

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
      setStep("company");
    },
  });

  const createCompanyMutation = useMutation({
    mutationFn: (values: CompanyEntityFormValues) => {
      if (!createdClient) {
        throw new Error("Client not created yet");
      }
      return createCompanyEntity(createdClient.id, values, getToken);
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
      <CompanyEntityForm
        title={`Now add the first company under ${createdClient.name}`}
        intro={
          <p className="text-sm text-stone-600">
            This is a separate legal entity under the client group — not the group name
            itself. You can add more companies later from the client detail page.
          </p>
        }
        namePlaceholder="e.g. MD Trading Ltd"
        currencyHint={
          <p className="text-sm text-stone-600">
            Each company under this client can have its own currency and materiality
            settings — useful if this client has subsidiaries or entities trading in
            different currencies.
          </p>
        }
        submitLabel="Create company & continue"
        isPending={createCompanyMutation.isPending}
        errorMessage={errorMessage}
        onSubmit={(values) => createCompanyMutation.mutate(values)}
        onCancel={() => router.push(`/clients/${createdClient.id}`)}
        cancelLabel="Skip to client detail"
      />
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
