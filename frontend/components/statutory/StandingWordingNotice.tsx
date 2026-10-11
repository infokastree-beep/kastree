"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import {
  STANDING_NOTICE_EVENT,
  STANDING_WORDING_NOTICE,
  readStandingNoticeCollapsed,
  showStandingWordingNotice,
  writeStandingNoticeCollapsed,
  type StatutoryUser,
} from "@/lib/statutory-gate";

export function StandingWordingNoticePanel({
  show,
  statement,
  onReveal,
  onHide,
  collapsed,
  error,
}: {
  show: boolean;
  statement: string | null;
  onReveal: () => void;
  onHide: () => void;
  collapsed: boolean;
  error?: string | null;
}) {
  const [open, setOpen] = useState(false);
  if (!show || collapsed) {
    return null;
  }
  return (
    <div
      className="flex items-start justify-between gap-3 border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm text-amber-950"
      data-testid="standing-wording-notice"
      role="status"
    >
      <div className="min-w-0 space-y-1">
        <p>{STANDING_WORDING_NOTICE}</p>
        <button
          type="button"
          className="underline"
          data-testid="standing-wording-meaning"
          onClick={() => {
            setOpen((current) => !current);
            if (!open) {
              onReveal();
            }
          }}
        >
          What does this mean?
        </button>
        {open && statement ? (
          <p data-testid="standing-wording-acknowledgement">{statement}</p>
        ) : null}
        {open && error ? (
          <p className="text-red-800" data-testid="standing-wording-error">
            {error}
          </p>
        ) : null}
      </div>
      <button
        type="button"
        className="shrink-0 underline"
        data-testid="standing-wording-hide"
        onClick={onHide}
      >
        Hide
      </button>
    </div>
  );
}

export function StandingWordingNotice({ place }: { place: string }) {
  const { getToken, isSignedIn } = useAuth();
  const meQuery = useQuery({
    queryKey: ["users", "me"],
    queryFn: () => apiFetch<StatutoryUser>("/users/me", { getToken }),
    enabled: isSignedIn,
  });
  const [collapsed, setCollapsed] = useState(false);
  const [statement, setStatement] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => {
      setCollapsed(readStandingNoticeCollapsed(window.sessionStorage));
    };
    sync();
    window.addEventListener(STANDING_NOTICE_EVENT, sync);
    return () => window.removeEventListener(STANDING_NOTICE_EVENT, sync);
  }, []);

  async function reveal(): Promise<void> {
    if (statement) {
      return;
    }
    try {
      const position = await apiFetch<{ statement: string }>("/beta", { getToken });
      setStatement(position.statement);
    } catch {
      setError("The acknowledgement could not be loaded.");
    }
  }

  function hide(): void {
    writeStandingNoticeCollapsed(window.sessionStorage);
    window.dispatchEvent(new Event(STANDING_NOTICE_EVENT));
  }

  return (
    <div data-testid={`standing-wording-notice-${place}`}>
      <StandingWordingNoticePanel
        show={showStandingWordingNotice(meQuery.data)}
        statement={statement}
        collapsed={collapsed}
        onReveal={() => {
          void reveal();
        }}
        onHide={hide}
        error={error}
      />
    </div>
  );
}

export function StandingWordingNoticePreview() {
  const [collapsed, setCollapsed] = useState(false);
  const [statement, setStatement] = useState<string | null>(null);

  useEffect(() => {
    setCollapsed(readStandingNoticeCollapsed(window.sessionStorage));
  }, []);

  if (collapsed) {
    return null;
  }

  return (
    <StandingWordingNoticePanel
      show
      collapsed={false}
      statement={statement}
      onReveal={() => {
        setStatement(
          "Preview only. The live notice loads the acknowledgement from the practice position.",
        );
      }}
      onHide={() => {
        writeStandingNoticeCollapsed(window.sessionStorage);
        setCollapsed(true);
      }}
    />
  );
}
