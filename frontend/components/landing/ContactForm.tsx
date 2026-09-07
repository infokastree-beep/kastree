"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type Status = "idle" | "submitting" | "success" | "error";

export function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("submitting");
    setError(null);
    try {
      await apiFetch<{ status: string }>("/contact", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          message: message.trim(),
        }),
      });
      setStatus("success");
      setName("");
      setEmail("");
      setMessage("");
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(
          "We couldn't send your message. Email infokastree@gmail.com directly.",
        );
      }
    }
  }

  if (status === "success") {
    return (
      <p
        className="rounded-md border border-accent/30 bg-accent-muted px-4 py-3 text-sm text-ink"
        role="status"
      >
        Thanks — we&apos;ll get back to you.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="max-w-xl space-y-5">
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-ink">Name</span>
        <input
          type="text"
          required
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border border-line bg-surface-elevated px-3 py-2.5 text-ink outline-none transition-colors focus:border-accent"
          autoComplete="name"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-ink">Email</span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-md border border-line bg-surface-elevated px-3 py-2.5 text-ink outline-none transition-colors focus:border-accent"
          autoComplete="email"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-ink">Message</span>
        <textarea
          required
          maxLength={5000}
          rows={6}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="w-full resize-y rounded-md border border-line bg-surface-elevated px-3 py-2.5 text-ink outline-none transition-colors focus:border-accent"
        />
      </label>
      {error ? (
        <p className="text-sm text-red-800" role="alert">
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={status === "submitting"}
        className="inline-flex rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-60"
      >
        {status === "submitting" ? "Sending…" : "Send message"}
      </button>
    </form>
  );
}
