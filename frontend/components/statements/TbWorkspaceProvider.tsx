"use client";

/**
 * Shared trial-balance workspace shell for Option A.
 *
 * Mounts once under /dashboard/[tbId]/layout so Ask (CopilotPanel) and its
 * thread survive Dashboard ↔ Statements navigations. Citation chips either
 * scroll/highlight on the current page or push a ?cite= deep link to the
 * other page, then scroll/highlight on arrival.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CopilotPanel } from "./CopilotPanel";
import {
  citeHref,
  dashboardPath,
  flashCiteAnchor,
  statementsPath,
  type CopilotCitePage,
  type CopilotNavigateTarget,
} from "@/lib/copilot-navigation";

type TbWorkspaceContextValue = {
  tbId: string;
  activePage: CopilotCitePage;
  askOpen: boolean;
  openAsk: () => void;
  closeAsk: () => void;
  navigateCitation: (target: CopilotNavigateTarget) => void;
};

const TbWorkspaceContext = createContext<TbWorkspaceContextValue | null>(
  null,
);

export function useTbWorkspace(): TbWorkspaceContextValue {
  const ctx = useContext(TbWorkspaceContext);
  if (!ctx) {
    throw new Error("useTbWorkspace must be used within TbWorkspaceProvider");
  }
  return ctx;
}

/** Safe outside the workspace layout (e.g. performance preview pages). */
export function useTbWorkspaceOptional(): TbWorkspaceContextValue | null {
  return useContext(TbWorkspaceContext);
}

function pageFromPathname(pathname: string, tbId: string): CopilotCitePage {
  return pathname.startsWith(`${dashboardPath(tbId)}/statements`)
    ? "statements"
    : "dashboard";
}

export function TbWorkspaceProvider({
  tbId,
  children,
}: {
  tbId: string;
  children: ReactNode;
}) {
  const pathname = usePathname() ?? dashboardPath(tbId);
  const router = useRouter();
  const searchParams = useSearchParams();
  const [askOpen, setAskOpen] = useState(false);
  const activePage = pageFromPathname(pathname, tbId);

  const openAsk = useCallback(() => setAskOpen(true), []);
  const closeAsk = useCallback(() => setAskOpen(false), []);

  const navigateCitation = useCallback(
    (target: CopilotNavigateTarget) => {
      if (target.page === activePage) {
        // Same-page: optional tab change is handled by the statements page
        // via a custom event so this provider stays free of tab state.
        if (target.tab) {
          window.dispatchEvent(
            new CustomEvent("kastree:set-statements-tab", {
              detail: { tab: target.tab },
            }),
          );
        }
        flashCiteAnchor(target.anchorId, target.tab ? 120 : 0);
        return;
      }

      // Cross-page: keep Ask open (layout does not remount) and deep-link.
      router.push(citeHref(tbId, target));
    },
    [activePage, router, tbId],
  );

  // On arrival (or same-page refresh) honour ?cite= with scroll + highlight.
  useEffect(() => {
    const cite = searchParams?.get("cite");
    if (!cite) return;
    const tab = searchParams?.get("tab");
    if (tab) {
      window.dispatchEvent(
        new CustomEvent("kastree:set-statements-tab", {
          detail: { tab },
        }),
      );
    }
    const delay = tab ? 350 : 120;
    flashCiteAnchor(cite, delay);

    // Strip cite params so refresh does not re-flash; keep tab if present.
    const next = new URLSearchParams(searchParams?.toString() ?? "");
    next.delete("cite");
    const qs = next.toString();
    const base =
      activePage === "statements"
        ? statementsPath(tbId)
        : dashboardPath(tbId);
    router.replace(qs ? `${base}?${qs}` : base, { scroll: false });
  }, [activePage, router, searchParams, tbId]);

  const value = useMemo(
    () => ({
      tbId,
      activePage,
      askOpen,
      openAsk,
      closeAsk,
      navigateCitation,
    }),
    [tbId, activePage, askOpen, openAsk, closeAsk, navigateCitation],
  );

  return (
    <TbWorkspaceContext.Provider value={value}>
      <nav
        className="sticky top-0 z-[70] mb-6 flex flex-wrap gap-1 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80"
        aria-label="Trial balance sections"
        data-testid="tb-workspace-switcher"
      >
        <Link
          href={statementsPath(tbId)}
          className={`px-3 py-2.5 text-sm font-semibold transition-colors ${
            activePage === "statements"
              ? "border-b-2 border-accent text-accent"
              : "text-soft hover:text-ink"
          }`}
          data-testid="tb-switcher-statements"
        >
          Statements
        </Link>
        <Link
          href={dashboardPath(tbId)}
          className={`px-3 py-2.5 text-sm font-semibold transition-colors ${
            activePage === "dashboard"
              ? "border-b-2 border-accent text-accent"
              : "text-soft hover:text-ink"
          }`}
          data-testid="tb-switcher-dashboard"
        >
          Dashboard
        </Link>
      </nav>

      {children}

      <CopilotPanel
        tbId={tbId}
        open={askOpen}
        onClose={closeAsk}
        onNavigateCitation={navigateCitation}
      />
    </TbWorkspaceContext.Provider>
  );
}
