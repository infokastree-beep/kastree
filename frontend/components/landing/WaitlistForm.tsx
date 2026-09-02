"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";

type WaitlistResponse = {
  id: string;
  status: string;
};

type FormState = {
  name: string;
  email: string;
  firm: string;
  role: string;
  approx_client_count: string;
  pain_point: string;
};

const INITIAL: FormState = {
  name: "",
  email: "",
  firm: "",
  role: "",
  approx_client_count: "",
  pain_point: "",
};

export function WaitlistForm() {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">(
    "idle",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("submitting");
    setErrorMessage(null);

    try {
      await apiFetch<WaitlistResponse>("/waitlist", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          email: form.email,
          firm: form.firm,
          role: form.role,
          approx_client_count: form.approx_client_count || null,
          pain_point: form.pain_point || null,
        }),
      });
      setStatus("success");
      setForm(INITIAL);
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiError) {
        const detail =
          typeof err.body === "object" &&
          err.body !== null &&
          "detail" in err.body &&
          typeof (err.body as { detail: unknown }).detail === "string"
            ? (err.body as { detail: string }).detail
            : err.message;
        setErrorMessage(detail);
      } else {
        setErrorMessage("Something went wrong. Please try again.");
      }
    }
  }

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  if (status === "success") {
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-5 text-emerald-950">
        <p className="font-medium">You&apos;re on the list.</p>
        <p className="mt-1 text-sm text-emerald-900/80">
          We&apos;ll reach out when there&apos;s an early-access slot. No mailing-list
          spam.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="font-medium text-stone-700">Name</span>
          <input
            required
            type="text"
            autoComplete="name"
            value={form.name}
            onChange={(e) => updateField("name", e.target.value)}
            className="mt-1 w-full rounded border border-stone-300 bg-white px-3 py-2 text-stone-900"
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium text-stone-700">Work email</span>
          <input
            required
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={(e) => updateField("email", e.target.value)}
            className="mt-1 w-full rounded border border-stone-300 bg-white px-3 py-2 text-stone-900"
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium text-stone-700">Firm / practice name</span>
          <input
            required
            type="text"
            value={form.firm}
            onChange={(e) => updateField("firm", e.target.value)}
            className="mt-1 w-full rounded border border-stone-300 bg-white px-3 py-2 text-stone-900"
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium text-stone-700">Role</span>
          <input
            required
            type="text"
            placeholder="e.g. Partner, manager, fractional CFO"
            value={form.role}
            onChange={(e) => updateField("role", e.target.value)}
            className="mt-1 w-full rounded border border-stone-300 bg-white px-3 py-2 text-stone-900"
          />
        </label>
      </div>
      <label className="block text-sm">
        <span className="font-medium text-stone-700">
          Approx. clients you&apos;d use this for{" "}
          <span className="font-normal text-stone-500">(optional)</span>
        </span>
        <input
          type="text"
          value={form.approx_client_count}
          onChange={(e) => updateField("approx_client_count", e.target.value)}
          className="mt-1 w-full rounded border border-stone-300 bg-white px-3 py-2 text-stone-900"
        />
      </label>
      <label className="block text-sm">
        <span className="font-medium text-stone-700">
          Biggest pain after receiving a trial balance?{" "}
          <span className="font-normal text-stone-500">(optional)</span>
        </span>
        <textarea
          rows={3}
          value={form.pain_point}
          onChange={(e) => updateField("pain_point", e.target.value)}
          className="mt-1 w-full rounded border border-stone-300 bg-white px-3 py-2 text-stone-900"
        />
      </label>
      {status === "error" && errorMessage ? (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={status === "submitting"}
        className="rounded bg-stone-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-60"
      >
        {status === "submitting" ? "Joining…" : "Join waitlist"}
      </button>
      <p className="text-xs text-stone-500">
        We&apos;ll only use this to contact you about Kastree early access.
      </p>
    </form>
  );
}
