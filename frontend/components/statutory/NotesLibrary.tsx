"use client";

import { groupByNoteClass, NOTE_CLASS_ORDER } from "@/lib/section-preview";
import type { NoteLibraryRow } from "@/lib/note-library";

export function NotesLibrary({
  rows,
  canEdit,
  busy,
  onAction,
}: {
  rows: readonly NoteLibraryRow[];
  canEdit: boolean;
  busy: boolean;
  onAction: (
    blockId: string,
    action: "omit" | "restore" | "add" | "remove",
  ) => Promise<void>;
}) {
  const locked = busy || !canEdit;
  const groups = groupByNoteClass(rows, NOTE_CLASS_ORDER);
  return (
    <section className="space-y-3" data-testid="statutory-note-library">
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Notes library
      </h2>
      {groups.map((group) => (
        <section
          key={group.id}
          className="space-y-2"
          data-testid={`statutory-library-class-${group.id}`}
        >
          <h3 className="text-sm font-semibold text-ink">{group.label}</h3>
          <ul className="space-y-2">
            {group.items.map((row) => (
              <li
                key={row.block_id}
                className="space-y-2 rounded-md border border-line bg-surface-elevated px-4 py-3"
                data-testid={`statutory-note-${row.block_id}`}
              >
                <p className="text-sm font-semibold text-ink">
                  <span className="mr-2 text-xs font-semibold uppercase tracking-[0.08em] text-soft">
                    {row.kind}
                  </span>
                  {row.title}
                </p>
                <p className="text-sm text-ink-secondary">{row.sentence}</p>
                <div className="flex flex-wrap gap-2">
                  {row.can_omit ? (
                    <button
                      type="button"
                      disabled={locked}
                      className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                      onClick={() => void onAction(row.block_id, "omit")}
                    >
                      Omit as immaterial
                    </button>
                  ) : null}
                  {row.can_restore ? (
                    <button
                      type="button"
                      disabled={locked}
                      className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                      onClick={() => void onAction(row.block_id, "restore")}
                    >
                      Put it back
                    </button>
                  ) : null}
                  {row.can_add ? (
                    <button
                      type="button"
                      disabled={locked}
                      className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                      onClick={() => void onAction(row.block_id, "add")}
                    >
                      Add this block
                    </button>
                  ) : null}
                  {row.can_remove ? (
                    <button
                      type="button"
                      disabled={locked}
                      className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
                      onClick={() => void onAction(row.block_id, "remove")}
                    >
                      Remove the addition
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </section>
  );
}
