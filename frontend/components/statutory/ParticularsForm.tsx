"use client";

import { useEffect, useState } from "react";
import type { CompanyDetails } from "@/components/statutory/CompanyDetailsForm";

export type ParticularsWrite = {
  related_party_particulars: string | null;
  directors_remuneration_particulars: string | null;
  loan_terms_particulars: string | null;
  guarantee_particulars: string | null;
  subsequent_events_particulars: string | null;
  share_classes: {
    class_name: string;
    authorised_number: number | null;
    issued_number: number;
    nominal_value: string;
  }[];
};

type ClassDraft = {
  class_name: string;
  authorised_number: string;
  issued_number: string;
  nominal_value: string;
};

const FIELD =
  "rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink disabled:opacity-50";

function textValue(value: string | null | undefined): string {
  return value ?? "";
}

function blankToNull(value: string): string | null {
  const text = value.trim();
  return text === "" ? null : text;
}

function wholeOrNull(value: string): number | null {
  const text = value.trim();
  if (text === "") {
    return null;
  }
  return Number(text);
}

function classesFrom(details: CompanyDetails): ClassDraft[] {
  if (details.share_classes.length === 0) {
    return [
      { class_name: "", authorised_number: "", issued_number: "", nominal_value: "" },
    ];
  }
  return details.share_classes.map((row) => ({
    class_name: row.class_name,
    authorised_number:
      row.authorised_number == null ? "" : String(row.authorised_number),
    issued_number: String(row.issued_number),
    nominal_value: row.nominal_value,
  }));
}

export function ParticularsForm({
  details,
  canEdit,
  busy,
  activeAnchor,
  error,
  saved,
  onSave,
}: {
  details: CompanyDetails;
  canEdit: boolean;
  busy: boolean;
  activeAnchor: string | null;
  error: string | null;
  saved: string | null;
  onSave: (body: ParticularsWrite) => void;
}) {
  const locked = !canEdit || busy;
  const [classes, setClasses] = useState<ClassDraft[]>(() => classesFrom(details));
  const [related, setRelated] = useState(textValue(details.related_party_particulars));
  const [remuneration, setRemuneration] = useState(
    textValue(details.directors_remuneration_particulars),
  );
  const [loans, setLoans] = useState(textValue(details.loan_terms_particulars));
  const [guarantees, setGuarantees] = useState(textValue(details.guarantee_particulars));
  const [events, setEvents] = useState(textValue(details.subsequent_events_particulars));

  useEffect(() => {
    if (activeAnchor == null || activeAnchor === "") {
      return;
    }
    document.getElementById(activeAnchor)?.scrollIntoView({ block: "start" });
  }, [activeAnchor]);

  function updateClass(index: number, patch: Partial<ClassDraft>): void {
    setClasses((rows) =>
      rows.map((row, position) => (position === index ? { ...row, ...patch } : row)),
    );
  }

  function save(): void {
    const share_classes = classes
      .filter((row) => row.class_name.trim() !== "")
      .map((row) => ({
        class_name: row.class_name.trim(),
        authorised_number: wholeOrNull(row.authorised_number),
        issued_number: wholeOrNull(row.issued_number) ?? 0,
        nominal_value: row.nominal_value.trim(),
      }));
    onSave({
      related_party_particulars: blankToNull(related),
      directors_remuneration_particulars: blankToNull(remuneration),
      loan_terms_particulars: blankToNull(loans),
      guarantee_particulars: blankToNull(guarantees),
      subsequent_events_particulars: blankToNull(events),
      share_classes,
    });
  }

  return (
    <form
      className="space-y-6"
      data-testid="particulars-form"
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <fieldset id="share-capital" className="space-y-3" disabled={locked}>
        <legend className="text-sm font-semibold text-ink">Share capital by class</legend>
        <p className="text-sm text-ink-secondary">
          Issued amount is calculated from the number of shares and the nominal value.
          Leave authorised blank when the company has no authorised maximum.
        </p>
        {classes.map((row, index) => (
          <div key={index} className="grid gap-2 sm:grid-cols-4">
            <input
              value={row.class_name}
              onChange={(event) => updateClass(index, { class_name: event.target.value })}
              placeholder="Class"
              className={FIELD}
              data-testid={`share-class-name-${index}`}
            />
            <input
              value={row.authorised_number}
              onChange={(event) =>
                updateClass(index, { authorised_number: event.target.value })
              }
              placeholder="Authorised"
              inputMode="numeric"
              className={FIELD}
              data-testid={`share-class-authorised-${index}`}
            />
            <input
              value={row.issued_number}
              onChange={(event) => updateClass(index, { issued_number: event.target.value })}
              placeholder="Issued"
              inputMode="numeric"
              className={FIELD}
              data-testid={`share-class-issued-${index}`}
            />
            <input
              value={row.nominal_value}
              onChange={(event) => updateClass(index, { nominal_value: event.target.value })}
              placeholder="Nominal value"
              className={FIELD}
              data-testid={`share-class-nominal-${index}`}
            />
          </div>
        ))}
        <button
          type="button"
          disabled={locked}
          onClick={() =>
            setClasses((rows) => [
              ...rows,
              {
                class_name: "",
                authorised_number: "",
                issued_number: "",
                nominal_value: "",
              },
            ])
          }
          className="text-sm font-semibold text-ink"
        >
          Add a class
        </button>
      </fieldset>

      <Slot
        id="related-parties"
        label="Related parties"
        help="Required when related-party transactions are answered yes."
        value={related}
        disabled={locked}
        testId="particulars-related-parties"
        onChange={setRelated}
      />
      <Slot
        id="directors-remuneration"
        label="Directors' remuneration"
        help="Required when directors served. Companies Act 2014, sections 305 and 306. The wording is researched from the public Act and is not signed off."
        value={remuneration}
        disabled={locked}
        testId="particulars-directors-remuneration"
        onChange={setRemuneration}
      />
      <Slot
        id="loans-and-credit"
        label="Loans and credit"
        help="Required when loans or credit with connected persons, or agreements to enter them, are answered yes. Companies Act 2014, sections 307 and 308."
        value={loans}
        disabled={locked}
        testId="particulars-loans-and-credit"
        onChange={setLoans}
      />
      <Slot
        id="guarantees"
        label="Guarantees"
        help="Required when guarantees or security are answered yes."
        value={guarantees}
        disabled={locked}
        testId="particulars-guarantees"
        onChange={setGuarantees}
      />
      <Slot
        id="subsequent-events"
        label="Post-balance-sheet events"
        help="Required when material events after the balance sheet date are answered yes."
        value={events}
        disabled={locked}
        testId="particulars-subsequent-events"
        onChange={setEvents}
      />

      {error ? (
        <p className="text-sm text-red-800" data-testid="particulars-error">
          {error}
        </p>
      ) : null}
      {saved ? (
        <p className="text-sm text-ink-secondary" data-testid="particulars-saved">
          {saved}
        </p>
      ) : null}
      {canEdit ? (
        <button
          type="submit"
          disabled={locked}
          data-testid="particulars-save"
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-50"
        >
          Save particulars
        </button>
      ) : null}
    </form>
  );
}

function Slot({
  id,
  label,
  help,
  value,
  disabled,
  testId,
  onChange,
}: {
  id: string;
  label: string;
  help: string;
  value: string;
  disabled: boolean;
  testId: string;
  onChange: (value: string) => void;
}) {
  return (
    <label id={id} className="flex max-w-xl flex-col gap-1.5 text-sm">
      <span className="font-semibold text-ink">{label}</span>
      <span className="text-ink-secondary">{help}</span>
      <textarea
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={FIELD}
        data-testid={testId}
      />
    </label>
  );
}
