"use client";

import { useState } from "react";
import type { ExtractedTbRow } from "@/types";

export type EditableExtractedRow = {
  key: string;
  account_code: string;
  account_name: string;
  debit: string;
  credit: string;
};

type PdfExtractReviewProps = {
  rows: ExtractedTbRow[];
  method: string;
  warnings: string[];
  busy?: boolean;
  confirmLabel?: string;
  busyLabel?: string;
  onConfirm: (rows: EditableExtractedRow[]) => void;
  onCancel: () => void;
};

function toEditable(rows: ExtractedTbRow[]): EditableExtractedRow[] {
  return rows.map((row, index) => ({
    key: `${row.row_index}-${index}`,
    account_code: row.account_code,
    account_name: row.account_name,
    debit: String(row.debit),
    credit: String(row.credit),
  }));
}

/** Build a four-column CSV the existing parser accepts unchanged. */
export function extractedRowsToCsvFile(
  rows: EditableExtractedRow[],
  filename = "extracted-trial-balance.csv",
): File {
  const escape = (value: string) => {
    if (/[",\n]/.test(value)) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };
  const lines = [
    "Account Code,Account Name,Debit,Credit",
    ...rows.map(
      (row) =>
        [
          escape(row.account_code.trim()),
          escape(row.account_name.trim()),
          escape(row.debit.trim() || "0"),
          escape(row.credit.trim() || "0"),
        ].join(","),
    ),
  ];
  const blob = new Blob([lines.join("\n") + "\n"], {
    type: "text/csv;charset=utf-8",
  });
  return new File([blob], filename, { type: "text/csv" });
}

/**
 * SpreadsheetML .xls that Excel opens natively — standalone copy of the
 * review table without a round-trip or extra npm dependency.
 */
export function extractedRowsToExcelFile(
  rows: EditableExtractedRow[],
  filename = "extracted-trial-balance.xls",
): File {
  const escapeXml = (value: string) =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const cell = (value: string, type: "String" | "Number") =>
    `<Cell><Data ss:Type="${type}">${escapeXml(value)}</Data></Cell>`;

  const bodyRows = rows
    .map((row) => {
      const debit = row.debit.trim() || "0";
      const credit = row.credit.trim() || "0";
      return `<Row>${cell(row.account_code.trim(), "String")}${cell(
        row.account_name.trim(),
        "String",
      )}${cell(debit, "Number")}${cell(credit, "Number")}</Row>`;
    })
    .join("");

  const xml = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Trial Balance">
  <Table>
   <Row>${cell("Account Code", "String")}${cell("Account Name", "String")}${cell(
     "Debit",
     "String",
   )}${cell("Credit", "String")}</Row>
   ${bodyRows}
  </Table>
 </Worksheet>
</Workbook>`;

  const blob = new Blob([xml], {
    type: "application/vnd.ms-excel;charset=utf-8",
  });
  return new File([blob], filename, {
    type: "application/vnd.ms-excel",
  });
}

function triggerBrowserDownload(file: File) {
  const url = URL.createObjectURL(file);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.name;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function PdfExtractReview({
  rows,
  method,
  warnings,
  busy = false,
  confirmLabel = "Confirm and continue",
  busyLabel = "Uploading…",
  onConfirm,
  onCancel,
}: PdfExtractReviewProps) {
  const [draft, setDraft] = useState(() => toEditable(rows));

  const update = (key: string, field: keyof EditableExtractedRow, value: string) => {
    setDraft((prev) =>
      prev.map((row) => (row.key === key ? { ...row, [field]: value } : row)),
    );
  };

  const removeRow = (key: string) => {
    setDraft((prev) => prev.filter((row) => row.key !== key));
  };

  const addRow = () => {
    setDraft((prev) => [
      ...prev,
      {
        key: `new-${prev.length}-${Date.now()}`,
        account_code: "",
        account_name: "",
        debit: "0",
        credit: "0",
      },
    ]);
  };

  const downloadExcel = () => {
    const file = extractedRowsToExcelFile(draft);
    triggerBrowserDownload(file);
  };

  return (
    <div
      className="space-y-4 rounded border border-stone-200 bg-white p-4"
      data-testid="pdf-extract-review"
    >
      <div>
        <h2 className="text-base font-semibold text-stone-900">
          Review extracted data
        </h2>
        <p className="mt-1 text-sm text-stone-600">
          Correct any cells before continuing. You can download a standalone
          Excel copy for your records, or confirm to build a CSV and run the
          normal upload → mapping pipeline — extraction does not invent
          statement figures.
        </p>
        <p className="mt-1 text-xs text-stone-500">
          Extracted via {method.replaceAll("_", " ")}
        </p>
      </div>

      {warnings.length > 0 ? (
        <ul className="list-disc space-y-1 rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-stone-200 text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-2 py-2 font-semibold">Code</th>
              <th className="px-2 py-2 font-semibold">Name</th>
              <th className="px-2 py-2 font-semibold text-right">Debit</th>
              <th className="px-2 py-2 font-semibold text-right">Credit</th>
              <th className="px-2 py-2 font-semibold"> </th>
            </tr>
          </thead>
          <tbody>
            {draft.map((row) => (
              <tr key={row.key} className="border-b border-stone-100">
                <td className="px-2 py-1.5">
                  <input
                    className="w-full min-w-[5rem] rounded border border-stone-300 px-2 py-1"
                    value={row.account_code}
                    onChange={(e) => update(row.key, "account_code", e.target.value)}
                    aria-label="Account code"
                  />
                </td>
                <td className="px-2 py-1.5">
                  <input
                    className="w-full min-w-[10rem] rounded border border-stone-300 px-2 py-1"
                    value={row.account_name}
                    onChange={(e) => update(row.key, "account_name", e.target.value)}
                    aria-label="Account name"
                  />
                </td>
                <td className="px-2 py-1.5">
                  <input
                    className="w-full min-w-[6rem] rounded border border-stone-300 px-2 py-1 text-right tabular-nums"
                    value={row.debit}
                    onChange={(e) => update(row.key, "debit", e.target.value)}
                    aria-label="Debit"
                  />
                </td>
                <td className="px-2 py-1.5">
                  <input
                    className="w-full min-w-[6rem] rounded border border-stone-300 px-2 py-1 text-right tabular-nums"
                    value={row.credit}
                    onChange={(e) => update(row.key, "credit", e.target.value)}
                    aria-label="Credit"
                  />
                </td>
                <td className="px-2 py-1.5">
                  <button
                    type="button"
                    className="text-xs font-medium text-stone-500 hover:text-red-700"
                    onClick={() => removeRow(row.key)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="rounded border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-800"
          onClick={addRow}
          disabled={busy}
        >
          Add row
        </button>
        <button
          type="button"
          className="rounded border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-800 disabled:opacity-50"
          onClick={downloadExcel}
          disabled={busy || draft.length === 0}
          data-testid="pdf-extract-download-excel"
        >
          Download as Excel
        </button>
        <button
          type="button"
          className="rounded border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-800"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
        <button
          type="button"
          className="rounded bg-stone-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={busy || draft.length === 0}
          onClick={() => onConfirm(draft)}
          data-testid="pdf-extract-confirm"
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </div>
  );
}
