/**
 * Node proof harness for frontend/lib/buildXlsx.ts
 * Run: node --experimental-strip-types scripts/prove-xlsx-download.mts
 */
import { writeFileSync } from "node:fs";
import { buildXlsxBytes } from "../lib/buildXlsx.ts";

const tbRows = [
  ["Account Code", "Account Name", "Debit", "Credit"],
  ["1000", "Cash", 1500.5, 0],
  ["2000", "Sales", 0, 1500.5],
];
const glRows = [
  ["Account Code", "Account Name", "Debit", "Credit"],
  ["4000", "Revenue", 0, 2500],
  ["5000", "COS", 900, 0],
  ["1000", "Bank", 1600, 0],
];

const tbBytes = buildXlsxBytes(tbRows);
const glBytes = buildXlsxBytes(glRows);

writeFileSync("/tmp/extracted-trial-balance.xlsx", tbBytes);
writeFileSync("/tmp/extracted-general-ledger.xlsx", glBytes);

function assertPk(label: string, bytes: Uint8Array) {
  if (bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
    throw new Error(`${label}: not a ZIP/xlsx (magic ${bytes[0]},${bytes[1]})`);
  }
  const head = Buffer.from(bytes.slice(0, 20)).toString("utf8");
  if (head.includes("<?xml") || head.includes("Workbook")) {
    throw new Error(`${label}: still SpreadsheetML XML, not OOXML zip`);
  }
  console.log(`${label}: OK PK zip, ${bytes.length} bytes`);
}

assertPk("TB path extracted-trial-balance.xlsx", tbBytes);
assertPk("GL path extracted-general-ledger.xlsx", glBytes);
console.log("Wrote /tmp/extracted-trial-balance.xlsx and /tmp/extracted-general-ledger.xlsx");
