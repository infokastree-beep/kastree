"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";

type WaitlistSignupRow = {
  name: string;
  email: string;
  firm: string;
  role: string;
  created_at: string;
};

type OrganisationRow = {
  name: string;
  subscription_tier: string;
  subscription_status: string;
  created_at: string;
};

type UserRow = {
  email: string;
  role: string;
  organisation_name: string;
  created_at: string;
};

type AdminOverview = {
  waitlist_count: number;
  waitlist_signups: WaitlistSignupRow[];
  organisations_count: number;
  organisations: OrganisationRow[];
  users_count: number;
  users: UserRow[];
};

function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function AdminTable({
  title,
  count,
  headers,
  rows,
}: {
  title: string;
  count: number;
  headers: string[];
  rows: string[][];
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">
        {title} <span className="text-stone-500">({count})</span>
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-stone-600">No rows yet.</p>
      ) : (
        <div className="overflow-x-auto rounded border border-stone-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-stone-50 text-stone-700">
              <tr>
                {headers.map((header) => (
                  <th key={header} className="px-3 py-2 font-medium">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${title}-${index}`} className="border-t border-stone-200">
                  {row.map((cell, cellIndex) => (
                    <td key={`${title}-${index}-${cellIndex}`} className="px-3 py-2">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function AdminOverviewPage() {
  const { getToken, isSignedIn } = useAuth();
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isSignedIn) {
      setLoading(false);
      setError("Sign in to view admin data.");
      return;
    }
    let cancelled = false;
    setLoading(true);
    apiFetch<AdminOverview>("/admin/overview", { getToken })
      .then((overview) => {
        if (!cancelled) {
          setData(overview);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 403) {
            setError("You don't have permission to view this page.");
          } else if (err instanceof ApiError) {
            setError(err.message);
          } else {
            setError("Could not load admin data.");
          }
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [getToken, isSignedIn]);

  if (loading) {
    return <p className="text-sm text-stone-600">Loading admin data…</p>;
  }

  if (error) {
    return <p className="text-sm text-red-700">{error}</p>;
  }

  if (!data) {
    return null;
  }

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="mt-1 text-sm text-stone-600">
          Waitlist signups, organisations, and users across the platform.
        </p>
      </div>

      <AdminTable
        title="Waitlist signups"
        count={data.waitlist_count}
        headers={["Name", "Email", "Firm", "Role", "Signed up"]}
        rows={data.waitlist_signups.map((row) => [
          row.name,
          row.email,
          row.firm,
          row.role,
          formatWhen(row.created_at),
        ])}
      />

      <AdminTable
        title="Organisations"
        count={data.organisations_count}
        headers={["Name", "Tier", "Status", "Created"]}
        rows={data.organisations.map((row) => [
          row.name,
          row.subscription_tier,
          row.subscription_status,
          formatWhen(row.created_at),
        ])}
      />

      <AdminTable
        title="Users"
        count={data.users_count}
        headers={["Email", "Role", "Organisation", "Created"]}
        rows={data.users.map((row) => [
          row.email,
          row.role,
          row.organisation_name,
          formatWhen(row.created_at),
        ])}
      />
    </div>
  );
}
