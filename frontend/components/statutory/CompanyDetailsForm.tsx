"use client";

import { useState } from "react";
import { StatutoryLoadError } from "@/components/statutory/StatutoryLoadError";

export type DirectorInput = {
  name: string;
  appointed_on: string | null;
  resigned_on: string | null;
};

export type AdviserInput = {
  role: string;
  name: string;
};

export type ShareClassInput = {
  class_name: string;
  authorised_number: string;
  issued_number: string;
  nominal_value: string;
};

export type ShareClassDetails = {
  class_name: string;
  authorised_number: number | null;
  issued_number: number;
  nominal_value: string;
  issued_amount: string;
};

export const DIRECTORS_RESPONSIBILITIES_WORDING =
  "The directors are responsible for preparing the company's financial statements and for being satisfied that they give a true and fair view. The directors are responsible for keeping adequate accounting records and for safeguarding the assets of the company and for taking reasonable steps for the prevention and detection of fraud and other irregularities.";

export type CompanyDetails = {
  registered_office: string | null;
  business_address: string | null;
  company_number: string | null;
  incorporated_on: string | null;
  principal_activity: string | null;
  secretary: string | null;
  average_employees: number | null;
  directors: DirectorInput[];
  advisers: AdviserInput[];
  share_classes: ShareClassDetails[];
  approval_date: string | null;
  signing_directors: string[];
};

export type CompanyDetailsWrite = {
  registered_office: string | null;
  business_address: string | null;
  company_number: string | null;
  incorporated_on: string | null;
  principal_activity: string | null;
  secretary: string | null;
  average_employees: number | null;
  directors: DirectorInput[];
  advisers: AdviserInput[];
  share_classes: {
    class_name: string;
    authorised_number: number | null;
    issued_number: number;
    nominal_value: string;
  }[];
};

export type ApprovalWrite = {
  approval_date: string | null;
  signing_directors: string[];
};

function textValue(value: string | null): string {
  return value ?? "";
}

function dateOrNull(value: string): string | null {
  return value === "" ? null : value;
}

const FIELD =
  "rounded-md border border-line bg-surface-elevated px-3 py-2 text-sm text-ink disabled:opacity-50";

export function CompanyDetailsForm({
  details,
  canEdit,
  busy,
  companyError,
  companySaved,
  approvalError,
  approvalSaved,
  onSaveCompany,
  onSaveApproval,
}: {
  details: CompanyDetails;
  canEdit: boolean;
  busy: boolean;
  companyError: string | null;
  companySaved: string | null;
  approvalError: string | null;
  approvalSaved: string | null;
  onSaveCompany: (next: CompanyDetailsWrite) => void;
  onSaveApproval: (next: ApprovalWrite) => void;
}) {
  const [office, setOffice] = useState(textValue(details.registered_office));
  const [business, setBusiness] = useState(textValue(details.business_address));
  const [number, setNumber] = useState(textValue(details.company_number));
  const [incorporated, setIncorporated] = useState(
    textValue(details.incorporated_on),
  );
  const [activity, setActivity] = useState(textValue(details.principal_activity));
  const [secretary, setSecretary] = useState(textValue(details.secretary));
  const [employees, setEmployees] = useState(
    details.average_employees === null ? "" : String(details.average_employees),
  );
  const [directors, setDirectors] = useState<DirectorInput[]>(
    details.directors.length > 0
      ? details.directors
      : [{ name: "", appointed_on: null, resigned_on: null }],
  );
  const [advisers, setAdvisers] = useState<AdviserInput[]>(
    details.advisers.length > 0 ? details.advisers : [{ role: "", name: "" }],
  );
  const [shareClasses, setShareClasses] = useState<ShareClassInput[]>(
    details.share_classes.length > 0
      ? details.share_classes.map((row) => ({
          class_name: row.class_name,
          authorised_number:
            row.authorised_number === null ? "" : String(row.authorised_number),
          issued_number: String(row.issued_number),
          nominal_value: row.nominal_value,
        }))
      : [
          {
            class_name: "",
            authorised_number: "",
            issued_number: "",
            nominal_value: "",
          },
        ],
  );
  const [approvalDate, setApprovalDate] = useState(
    textValue(details.approval_date),
  );
  const [signing, setSigning] = useState<string[]>(details.signing_directors);
  const locked = !canEdit || busy;
  const savedNames = details.directors
    .map((director) => director.name.trim())
    .filter((name) => name.length > 0);

  function updateDirector(index: number, patch: Partial<DirectorInput>): void {
    setDirectors((current) =>
      current.map((row, rowIndex) =>
        rowIndex === index ? { ...row, ...patch } : row,
      ),
    );
  }

  function updateAdviser(index: number, patch: Partial<AdviserInput>): void {
    setAdvisers((current) =>
      current.map((row, rowIndex) =>
        rowIndex === index ? { ...row, ...patch } : row,
      ),
    );
  }

  function updateShareClass(
    index: number,
    patch: Partial<ShareClassInput>,
  ): void {
    setShareClasses((current) =>
      current.map((row, rowIndex) =>
        rowIndex === index ? { ...row, ...patch } : row,
      ),
    );
  }

  function issuedAmount(row: ShareClassInput): string {
    const saved = details.share_classes.find(
      (item) => item.class_name === row.class_name.trim(),
    );
    if (
      saved === undefined ||
      String(saved.issued_number) !== row.issued_number.trim() ||
      saved.nominal_value !== row.nominal_value.trim()
    ) {
      return "Issued amount is calculated on save.";
    }
    return `Issued amount ${saved.issued_amount}`;
  }

  function toggleSigning(name: string): void {
    setSigning((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name],
    );
  }

  return (
    <div className="space-y-8" data-testid="statutory-company-details">
      <section
        className="max-w-3xl space-y-2 rounded-md border border-line bg-surface-elevated p-4"
        data-testid="directors-responsibilities-source"
      >
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
          Directors&apos; responsibilities statement
        </h2>
        <p className="text-sm font-semibold text-ink">source not confirmed</p>
        <p className="text-sm text-ink-secondary">
          {DIRECTORS_RESPONSIBILITIES_WORDING}
        </p>
      </section>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSaveCompany({
            registered_office: office.trim() === "" ? null : office,
            business_address: business.trim() === "" ? null : business,
            company_number: number.trim() === "" ? null : number,
            incorporated_on: dateOrNull(incorporated),
            principal_activity: activity.trim() === "" ? null : activity,
            secretary: secretary.trim() === "" ? null : secretary,
            average_employees: employees.trim() === "" ? null : Number(employees),
            directors: directors
              .filter(
                (row) =>
                  row.name.trim() !== "" ||
                  row.appointed_on !== null ||
                  row.resigned_on !== null,
              )
              .map((row) => ({
                name: row.name.trim(),
                appointed_on: row.appointed_on,
                resigned_on: row.resigned_on,
              })),
            advisers: advisers
              .filter((row) => row.role.trim() !== "" || row.name.trim() !== "")
              .map((row) => ({
                role: row.role.trim(),
                name: row.name.trim(),
              })),
            share_classes: shareClasses
              .filter(
                (row) =>
                  row.class_name.trim() !== "" ||
                  row.authorised_number.trim() !== "" ||
                  row.issued_number.trim() !== "" ||
                  row.nominal_value.trim() !== "",
              )
              .map((row) => ({
                class_name: row.class_name.trim(),
                authorised_number:
                  row.authorised_number.trim() === ""
                    ? null
                    : Number(row.authorised_number),
                issued_number: Number(row.issued_number),
                nominal_value: row.nominal_value.trim(),
              })),
          });
        }}
      >
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
          Company
        </h2>
        <p className="max-w-3xl text-sm text-ink-secondary">
          These facts are stored as entered. A blank field stays blank.
        </p>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Registered office
          </span>
          <input
            value={office}
            disabled={locked}
            onChange={(event) => setOffice(event.target.value)}
            className={FIELD}
            data-testid="company-registered-office"
          />
        </label>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Business address
          </span>
          <textarea
            value={business}
            disabled={locked}
            rows={3}
            onChange={(event) => setBusiness(event.target.value)}
            className={FIELD}
            data-testid="company-business-address"
          />
        </label>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Company number
          </span>
          <input
            value={number}
            disabled={locked}
            onChange={(event) => setNumber(event.target.value)}
            className={FIELD}
            data-testid="company-number"
          />
        </label>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Date of incorporation
          </span>
          <input
            type="date"
            value={incorporated}
            disabled={locked}
            onChange={(event) => setIncorporated(event.target.value)}
            className={FIELD}
            data-testid="company-incorporated-on"
          />
        </label>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Principal activity
          </span>
          <input
            value={activity}
            disabled={locked}
            onChange={(event) => setActivity(event.target.value)}
            className={FIELD}
            data-testid="company-principal-activity"
          />
        </label>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Secretary
          </span>
          <input
            value={secretary}
            disabled={locked}
            onChange={(event) => setSecretary(event.target.value)}
            className={FIELD}
            data-testid="company-secretary"
          />
        </label>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Average number of employees
          </span>
          <input
            type="number"
            min={0}
            step={1}
            value={employees}
            disabled={locked}
            onChange={(event) => setEmployees(event.target.value)}
            className={FIELD}
            data-testid="company-average-employees"
          />
        </label>
        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Directors
          </legend>
          {directors.map((row, index) => (
            <div
              key={index}
              className="grid gap-2 rounded-md border border-line bg-surface-elevated p-3 sm:grid-cols-3"
            >
              <label className="flex flex-col gap-1 text-sm">
                <span>Name</span>
                <input
                  value={row.name}
                  disabled={locked}
                  onChange={(event) =>
                    updateDirector(index, { name: event.target.value })
                  }
                  className={FIELD}
                  data-testid={`company-director-name-${index}`}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Appointed</span>
                <input
                  type="date"
                  value={textValue(row.appointed_on)}
                  disabled={locked}
                  onChange={(event) =>
                    updateDirector(index, {
                      appointed_on: dateOrNull(event.target.value),
                    })
                  }
                  className={FIELD}
                  data-testid={`company-director-appointed-${index}`}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Resigned</span>
                <input
                  type="date"
                  value={textValue(row.resigned_on)}
                  disabled={locked}
                  onChange={(event) =>
                    updateDirector(index, {
                      resigned_on: dateOrNull(event.target.value),
                    })
                  }
                  className={FIELD}
                  data-testid={`company-director-resigned-${index}`}
                />
              </label>
            </div>
          ))}
          <button
            type="button"
            disabled={locked}
            onClick={() =>
              setDirectors((current) => [
                ...current,
                { name: "", appointed_on: null, resigned_on: null },
              ])
            }
            className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
          >
            Add director
          </button>
        </fieldset>
        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Advisers
          </legend>
          {advisers.map((row, index) => (
            <div
              key={index}
              className="grid gap-2 rounded-md border border-line bg-surface-elevated p-3 sm:grid-cols-2"
            >
              <label className="flex flex-col gap-1 text-sm">
                <span>Role</span>
                <input
                  value={row.role}
                  disabled={locked}
                  onChange={(event) =>
                    updateAdviser(index, { role: event.target.value })
                  }
                  className={FIELD}
                  data-testid={`company-adviser-role-${index}`}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Name</span>
                <input
                  value={row.name}
                  disabled={locked}
                  onChange={(event) =>
                    updateAdviser(index, { name: event.target.value })
                  }
                  className={FIELD}
                  data-testid={`company-adviser-name-${index}`}
                />
              </label>
            </div>
          ))}
          <button
            type="button"
            disabled={locked}
            onClick={() =>
              setAdvisers((current) => [...current, { role: "", name: "" }])
            }
            className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
          >
            Add adviser
          </button>
        </fieldset>
        <fieldset className="space-y-3">
          <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Share classes
          </legend>
          <p className="max-w-3xl text-sm text-ink-secondary">
            Leave authorised blank when no maximum is recorded. The issued
            amount is the issued number times the nominal value.
          </p>
          {shareClasses.map((row, index) => (
            <div
              key={index}
              className="grid gap-2 rounded-md border border-line bg-surface-elevated p-3 sm:grid-cols-2"
            >
              <label className="flex flex-col gap-1 text-sm">
                <span>Class</span>
                <input
                  value={row.class_name}
                  disabled={locked}
                  onChange={(event) =>
                    updateShareClass(index, { class_name: event.target.value })
                  }
                  className={FIELD}
                  data-testid={`company-share-class-${index}`}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Authorised shares</span>
                <input
                  value={row.authorised_number}
                  disabled={locked}
                  inputMode="numeric"
                  onChange={(event) =>
                    updateShareClass(index, {
                      authorised_number: event.target.value,
                    })
                  }
                  className={FIELD}
                  data-testid={`company-share-authorised-${index}`}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Issued shares</span>
                <input
                  value={row.issued_number}
                  disabled={locked}
                  inputMode="numeric"
                  onChange={(event) =>
                    updateShareClass(index, {
                      issued_number: event.target.value,
                    })
                  }
                  className={FIELD}
                  data-testid={`company-share-issued-${index}`}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Nominal value</span>
                <input
                  value={row.nominal_value}
                  disabled={locked}
                  onChange={(event) =>
                    updateShareClass(index, {
                      nominal_value: event.target.value,
                    })
                  }
                  className={FIELD}
                  data-testid={`company-share-nominal-${index}`}
                />
              </label>
              <p
                className="text-sm text-ink-secondary sm:col-span-2"
                data-testid={`company-share-issued-amount-${index}`}
              >
                {issuedAmount(row)}
              </p>
            </div>
          ))}
          <button
            type="button"
            disabled={locked}
            onClick={() =>
              setShareClasses((current) => [
                ...current,
                {
                  class_name: "",
                  authorised_number: "",
                  issued_number: "",
                  nominal_value: "",
                },
              ])
            }
            className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-50"
          >
            Add share class
          </button>
        </fieldset>
        {companyError !== null ? (
          <StatutoryLoadError
            testId="statutory-company-error"
            message={companyError}
            onReview={() => undefined}
          />
        ) : null}
        {companySaved !== null ? (
          <p className="text-sm text-emerald-800" data-testid="statutory-company-saved">
            {companySaved}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={locked}
          className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="company-save"
        >
          Save company details
        </button>
      </form>

      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSaveApproval({
            approval_date: dateOrNull(approvalDate),
            signing_directors: signing,
          });
        }}
      >
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-soft">
          This year
        </h2>
        <label className="flex max-w-xl flex-col gap-1.5 text-sm">
          <span className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Approval date
          </span>
          <input
            type="date"
            value={approvalDate}
            disabled={locked}
            onChange={(event) => setApprovalDate(event.target.value)}
            className={FIELD}
            data-testid="company-approval-date"
          />
        </label>
        <fieldset className="space-y-2">
          <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-soft">
            Signing directors
          </legend>
          {savedNames.length === 0 ? (
            <p className="text-sm text-ink-secondary">
              Save the directors first. A signing director has to be one of them.
            </p>
          ) : (
            savedNames.map((name) => (
              <label key={name} className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={signing.includes(name)}
                  disabled={locked}
                  onChange={() => toggleSigning(name)}
                  data-testid={`company-signing-${name}`}
                />
                {name}
              </label>
            ))
          )}
        </fieldset>
        {approvalError !== null ? (
          <StatutoryLoadError
            testId="statutory-approval-error"
            message={approvalError}
            onReview={() => undefined}
          />
        ) : null}
        {approvalSaved !== null ? (
          <p
            className="text-sm text-emerald-800"
            data-testid="statutory-approval-saved"
          >
            {approvalSaved}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={locked}
          className="rounded-md border border-line bg-surface-elevated px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="approval-save"
        >
          Save approval details
        </button>
      </form>
    </div>
  );
}
