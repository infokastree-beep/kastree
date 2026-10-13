"use client";

import Link from "next/link";
import { useState } from "react";
import { StatutoryLoadError } from "@/components/statutory/StatutoryLoadError";
import { directorsReportWrite } from "@/lib/section-inputs";

export type ShareHolding = {
  undertaking: string;
  shares: number;
  amount: string;
};

export type ShareInterestEnd = {
  interested: boolean;
  holdings: ShareHolding[];
};

export type ShareInterest = {
  name: string;
  role: "director" | "secretary";
  at_start: ShareInterestEnd;
  at_end: ShareInterestEnd;
};

/** Facts returned with company details and sent back on save. */
export type DirectorsReportFacts = {
  accounting_records_location: string | null;
  interim_dividend: string | null;
  recommended_dividend: string | null;
  share_interests: ShareInterest[];
  own_shares_particulars: string | null;
  subsequent_events_particulars: string | null;
  research_development_relevant: boolean | null;
  research_development_detail: string | null;
  political_donations_relevant: boolean | null;
  political_donations_detail: string | null;
  accounting_period_change_filed: boolean | null;
};

export type DirectorsReportWrite = DirectorsReportFacts;

type HoldingDraft = {
  undertaking: string;
  shares: string;
  amount: string;
};

type EndDraft = {
  interested: boolean;
  holdings: HoldingDraft[];
};

type PersonDraft = {
  name: string;
  role: "director" | "secretary";
  at_start: EndDraft;
  at_end: EndDraft;
};

const FIELD =
  "rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink disabled:opacity-50";

function textValue(value: string | null | undefined): string {
  return value ?? "";
}

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function emptyEnd(): EndDraft {
  return { interested: false, holdings: [] };
}

function emptyPerson(): PersonDraft {
  return {
    name: "",
    role: "director",
    at_start: emptyEnd(),
    at_end: emptyEnd(),
  };
}

function endFrom(end: ShareInterestEnd): EndDraft {
  return {
    interested: end.interested,
    holdings: end.holdings.map((holding) => ({
      undertaking: holding.undertaking,
      shares: String(holding.shares),
      amount: holding.amount,
    })),
  };
}

function peopleFrom(details: DirectorsReportFacts): PersonDraft[] {
  return details.share_interests.map((person) => ({
    name: person.name,
    role: person.role,
    at_start: endFrom(person.at_start),
    at_end: endFrom(person.at_end),
  }));
}

function triValue(value: boolean | null): string {
  if (value === true) {
    return "yes";
  }
  if (value === false) {
    return "no";
  }
  return "";
}

function triFrom(value: string): boolean | null {
  if (value === "yes") {
    return true;
  }
  if (value === "no") {
    return false;
  }
  return null;
}

function wholeShares(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  return Number(trimmed);
}

function endWrite(end: EndDraft): ShareInterestEnd | string {
  const holdings: ShareHolding[] = [];
  for (const row of end.holdings) {
    const undertaking = row.undertaking.trim();
    const amount = row.amount.trim();
    const sharesText = row.shares.trim();
    if (undertaking === "" && amount === "" && sharesText === "") {
      continue;
    }
    const shares = wholeShares(sharesText);
    if (shares === null || undertaking === "" || amount === "") {
      return "Record the undertaking, the number of shares, and the amount for each interest.";
    }
    holdings.push({ undertaking, shares, amount });
  }
  if (end.interested && holdings.length === 0) {
    return "Record the shares and the amount for each interest.";
  }
  if (!end.interested && holdings.length > 0) {
    return "A person with no interest does not record a holding.";
  }
  return { interested: end.interested, holdings };
}

export type DirectorsReportPart = "records" | "interests" | "other";

export function DirectorsReportForm({
  part,
  details,
  canEdit,
  busy,
  error,
  saved,
  onSave,
}: {
  part: DirectorsReportPart;
  details: DirectorsReportFacts;
  canEdit: boolean;
  busy: boolean;
  error: string | null;
  saved: string | null;
  onSave: (next: DirectorsReportWrite) => void;
}) {
  const locked = !canEdit || busy;
  const [location, setLocation] = useState(
    textValue(details.accounting_records_location),
  );
  const [interim, setInterim] = useState(textValue(details.interim_dividend));
  const [recommended, setRecommended] = useState(
    textValue(details.recommended_dividend),
  );
  const [people, setPeople] = useState<PersonDraft[]>(peopleFrom(details));
  const [ownShares, setOwnShares] = useState(
    textValue(details.own_shares_particulars),
  );
  const [events, setEvents] = useState(
    textValue(details.subsequent_events_particulars),
  );
  const [research, setResearch] = useState(
    triValue(details.research_development_relevant),
  );
  const [researchDetail, setResearchDetail] = useState(
    textValue(details.research_development_detail),
  );
  const [political, setPolitical] = useState(
    triValue(details.political_donations_relevant),
  );
  const [politicalDetail, setPoliticalDetail] = useState(
    textValue(details.political_donations_detail),
  );
  const [periodChange, setPeriodChange] = useState(
    triValue(details.accounting_period_change_filed),
  );
  const [formError, setFormError] = useState<string | null>(null);

  function updatePerson(index: number, next: PersonDraft): void {
    setPeople((current) =>
      current.map((person, item) => (item === index ? next : person)),
    );
  }

  function updateEnd(
    index: number,
    which: "at_start" | "at_end",
    next: EndDraft,
  ): void {
    const person = people[index];
    if (person === undefined) {
      return;
    }
    updatePerson(index, { ...person, [which]: next });
  }

  function submit(): void {
    if (part === "records") {
      setFormError(null);
      onSave(
        directorsReportWrite(details, {
          accounting_records_location: blankToNull(location),
          interim_dividend: blankToNull(interim),
          recommended_dividend: blankToNull(recommended),
        }),
      );
      return;
    }
    if (part === "other") {
      setFormError(null);
      const researchRelevant = triFrom(research);
      const politicalRelevant = triFrom(political);
      onSave(
        directorsReportWrite(details, {
          own_shares_particulars: blankToNull(ownShares),
          subsequent_events_particulars: blankToNull(events),
          research_development_relevant: researchRelevant,
          research_development_detail:
            researchRelevant === true ? blankToNull(researchDetail) : null,
          political_donations_relevant: politicalRelevant,
          political_donations_detail:
            politicalRelevant === true ? blankToNull(politicalDetail) : null,
          accounting_period_change_filed: triFrom(periodChange),
        }),
      );
      return;
    }
    const interests: ShareInterest[] = [];
    for (const person of people) {
      const name = person.name.trim();
      if (name === "") {
        continue;
      }
      const atStart = endWrite(person.at_start);
      if (typeof atStart === "string") {
        setFormError(atStart);
        return;
      }
      const atEnd = endWrite(person.at_end);
      if (typeof atEnd === "string") {
        setFormError(atEnd);
        return;
      }
      interests.push({
        name,
        role: person.role,
        at_start: atStart,
        at_end: atEnd,
      });
    }
    setFormError(null);
    onSave(directorsReportWrite(details, { share_interests: interests }));
  }

  return (
    <form
      className="space-y-4"
      data-testid="directors-report-inputs"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Directors&apos; report
      </h2>
      <p className="text-sm text-ink-secondary" data-testid="directors-report-scope">
        Companies Act 2014, sections 326, 328 and 329. A blank required item
        blocks a final draft. Enter 0.00 where a dividend is nil.
      </p>
      <p
        className="text-sm text-ink-secondary"
        data-testid="directors-report-business-review"
      >
        This is a small-company directors&apos; report. It does not include a
        business review. Principal risks and future developments are optional
        and are not collected here.
      </p>
      {part === "records" ? (
      <>
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Accounting records location
        </span>
        <span className="text-ink-secondary">
          The exact location is required. Companies Act 2014, section 326.
        </span>
        <input
          value={location}
          disabled={locked}
          onChange={(event) => setLocation(event.target.value)}
          className={FIELD}
          data-testid="directors-report-location"
        />
      </label>
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Interim dividend
        </span>
        <span className="text-ink-secondary">
          Required. Enter 0.00 if none was paid. Companies Act 2014, section 326.
        </span>
        <input
          value={interim}
          disabled={locked}
          inputMode="decimal"
          onChange={(event) => setInterim(event.target.value)}
          className={FIELD}
          data-testid="directors-report-interim"
        />
      </label>
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Recommended dividend
        </span>
        <span className="text-ink-secondary">
          Required. Enter 0.00 if none is recommended. Companies Act 2014,
          section 326.
        </span>
        <input
          value={recommended}
          disabled={locked}
          inputMode="decimal"
          onChange={(event) => setRecommended(event.target.value)}
          className={FIELD}
          data-testid="directors-report-recommended"
        />
      </label>
      </>
      ) : null}
      {part === "interests" ? (
      <fieldset className="space-y-3">
        <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Interests in shares
        </legend>
        <p className="text-sm text-ink-secondary">
          Record every director who served, and the secretary if one is
          recorded. Companies Act 2014, section 329.
        </p>
        {people.length === 0 ? (
          <p className="text-sm text-ink-secondary" data-testid="directors-report-interests-empty">
            No interests have been recorded.
          </p>
        ) : null}
        {people.map((person, index) => (
          <div
            key={index}
            className="space-y-3 rounded-md border border-line p-3"
          >
            <label className="flex max-w-xl flex-col gap-1 text-sm">
              <span>Name</span>
              <input
                value={person.name}
                disabled={locked}
                onChange={(event) =>
                  updatePerson(index, { ...person, name: event.target.value })
                }
                className={FIELD}
                data-testid={`directors-report-interest-name-${index}`}
              />
            </label>
            <label className="flex max-w-xl flex-col gap-1 text-sm">
              <span>Role</span>
              <select
                value={person.role}
                disabled={locked}
                onChange={(event) =>
                  updatePerson(index, {
                    ...person,
                    role:
                      event.target.value === "secretary" ? "secretary" : "director",
                  })
                }
                className={FIELD}
                data-testid={`directors-report-interest-role-${index}`}
              >
                <option value="director">Director</option>
                <option value="secretary">Secretary</option>
              </select>
            </label>
            <InterestEndFields
              label="At the beginning of the year"
              end={person.at_start}
              disabled={locked}
              testId={`directors-report-interest-start-${index}`}
              onChange={(next) => updateEnd(index, "at_start", next)}
            />
            <InterestEndFields
              label="At the end of the year"
              end={person.at_end}
              disabled={locked}
              testId={`directors-report-interest-end-${index}`}
              onChange={(next) => updateEnd(index, "at_end", next)}
            />
            <button
              type="button"
              disabled={locked}
              onClick={() =>
                setPeople((current) => current.filter((_, item) => item !== index))
              }
              className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          disabled={locked}
          onClick={() => setPeople((current) => [...current, emptyPerson()])}
          className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
          data-testid="directors-report-add-person"
        >
          Add a person
        </button>
      </fieldset>
      ) : null}
      {part === "other" ? (
      <>
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Own shares
        </span>
        <span className="text-ink-secondary">
          Particulars are required only when the company holds its own shares.
          Companies Act 2014, section 328.
        </span>
        <textarea
          value={ownShares}
          disabled={locked}
          onChange={(event) => setOwnShares(event.target.value)}
          className={FIELD}
          data-testid="directors-report-own-shares"
        />
      </label>
      <label className="flex max-w-xl flex-col gap-1.5 text-sm">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
          Events since the balance sheet date
        </span>
        <span className="text-ink-secondary">
          Particulars are required only when those events are answered yes.
          Companies Act 2014, section 326.
        </span>
        <textarea
          value={events}
          disabled={locked}
          onChange={(event) => setEvents(event.target.value)}
          className={FIELD}
          data-testid="directors-report-subsequent-events"
        />
      </label>
      <TriState
        label="Research and development"
        help="Not recorded does not block a final draft. Yes needs the particulars. Companies Act 2014, section 326."
        value={research}
        disabled={locked}
        testId="directors-report-research"
        onChange={setResearch}
      />
      {research === "yes" ? (
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Research and development particulars
          </span>
          <textarea
            value={researchDetail}
            disabled={locked}
            onChange={(event) => setResearchDetail(event.target.value)}
            className={FIELD}
            data-testid="directors-report-research-detail"
          />
        </label>
      ) : null}
      <TriState
        label="Political donations"
        help="Not recorded does not block a final draft. Yes needs the particulars. Companies Act 2014, section 326, and the Electoral Act 1997."
        value={political}
        disabled={locked}
        testId="directors-report-political"
        onChange={setPolitical}
      />
      {political === "yes" ? (
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Political donation particulars
          </span>
          <textarea
            value={politicalDetail}
            disabled={locked}
            onChange={(event) => setPoliticalDetail(event.target.value)}
            className={FIELD}
            data-testid="directors-report-political-detail"
          />
        </label>
      ) : null}
      <TriState
        label="Year-end change filed"
        help="Record this when a year that is not 12 months was notified to the Registrar. It does not block a final draft. Companies Act 2014, section 288."
        value={periodChange}
        disabled={locked}
        testId="directors-report-period-change"
        onChange={setPeriodChange}
      />
      </>
      ) : null}
      {formError !== null ? (
        <StatutoryLoadError
          testId="statutory-directors-report-form-error"
          message={formError}
          onReview={() => undefined}
        />
      ) : null}
      {error !== null ? (
        <StatutoryLoadError
          testId="statutory-directors-report-error"
          message={error}
          onReview={() => undefined}
        />
      ) : null}
      {saved !== null ? (
        <p
          className="text-sm text-emerald-800"
          data-testid="statutory-directors-report-saved"
        >
          {saved}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={locked}
        className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="directors-report-save"
      >
        Save directors&apos; report
      </button>
    </form>
  );
}

export function PrincipalActivityPanel({
  activity,
  yearEndId,
}: {
  activity: string | null;
  yearEndId: string;
}) {
  const recorded = activity?.trim() ?? "";
  return (
    <section className="space-y-3" data-testid="directors-report-principal-activity">
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
        Principal activities
      </h2>
      <p className="text-sm text-ink">
        {recorded === ""
          ? "Principal activities have not been recorded."
          : recorded}
      </p>
      <p className="text-sm">
        <Link
          href={`/year-ends/${yearEndId}/draft?section=company-details#company-principal-activity`}
          className="font-semibold text-ink underline"
          data-testid="directors-report-principal-activity-link"
        >
          Edit principal activity in Company details
        </Link>
      </p>
    </section>
  );
}

function TriState({
  label,
  help,
  value,
  disabled,
  testId,
  onChange,
}: {
  label: string;
  help: string;
  value: string;
  disabled: boolean;
  testId: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="flex max-w-xl flex-col gap-1.5 text-sm">
      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
        {label}
      </span>
      <span className="text-ink-secondary">{help}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={FIELD}
        data-testid={testId}
      >
        <option value="">Not recorded</option>
        <option value="no">No</option>
        <option value="yes">Yes</option>
      </select>
    </label>
  );
}

function InterestEndFields({
  label,
  end,
  disabled,
  testId,
  onChange,
}: {
  label: string;
  end: EndDraft;
  disabled: boolean;
  testId: string;
  onChange: (next: EndDraft) => void;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm text-ink">{label}</legend>
      <label className="flex items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={end.interested}
          disabled={disabled}
          data-testid={testId}
          onChange={(event) => {
            const interested = event.target.checked;
            let holdings = end.holdings;
            if (interested && holdings.length === 0) {
              holdings = [{ undertaking: "", shares: "", amount: "" }];
            }
            if (!interested) {
              holdings = [];
            }
            onChange({ interested, holdings });
          }}
        />
        Interested in shares
      </label>
      {end.interested
        ? end.holdings.map((holding, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-3">
              <input
                value={holding.undertaking}
                disabled={disabled}
                placeholder="Undertaking"
                onChange={(event) =>
                  onChange({
                    ...end,
                    holdings: end.holdings.map((row, item) =>
                      item === index
                        ? { ...row, undertaking: event.target.value }
                        : row,
                    ),
                  })
                }
                className={FIELD}
                data-testid={`${testId}-undertaking-${index}`}
              />
              <input
                value={holding.shares}
                disabled={disabled}
                inputMode="numeric"
                placeholder="Shares"
                onChange={(event) =>
                  onChange({
                    ...end,
                    holdings: end.holdings.map((row, item) =>
                      item === index ? { ...row, shares: event.target.value } : row,
                    ),
                  })
                }
                className={FIELD}
                data-testid={`${testId}-shares-${index}`}
              />
              <input
                value={holding.amount}
                disabled={disabled}
                inputMode="decimal"
                placeholder="Amount"
                onChange={(event) =>
                  onChange({
                    ...end,
                    holdings: end.holdings.map((row, item) =>
                      item === index ? { ...row, amount: event.target.value } : row,
                    ),
                  })
                }
                className={FIELD}
                data-testid={`${testId}-amount-${index}`}
              />
            </div>
          ))
        : null}
    </fieldset>
  );
}
