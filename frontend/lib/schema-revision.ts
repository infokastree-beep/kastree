/** Admin copy for the database revision reported by GET /health. */

export type SchemaRevisionStatus = {
  database_revision: string | null;
  code_revision: string | null;
  revision_matches: boolean;
};

export function revisionBanner(status: SchemaRevisionStatus): {
  tone: "ok" | "mismatch" | "unknown";
  text: string;
} {
  if (
    status.revision_matches &&
    status.code_revision != null &&
    status.code_revision.length > 0
  ) {
    return {
      tone: "ok",
      text: `Database revision matches the code (${status.code_revision}).`,
    };
  }
  if (
    status.database_revision != null &&
    status.database_revision.length > 0 &&
    status.code_revision != null &&
    status.code_revision.length > 0
  ) {
    return {
      tone: "mismatch",
      text: `Database revision ${status.database_revision} does not match the code revision ${status.code_revision}.`,
    };
  }
  return {
    tone: "unknown",
    text: "Database revision could not be compared with the code.",
  };
}
