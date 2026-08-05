import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Database,
  Play,
  RefreshCw,
  Table2,
  Trash2,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Checkbox } from "@nous-research/ui/ui/components/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@nous-research/ui/ui/components/dialog";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Segmented } from "@nous-research/ui/ui/components/segmented";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { usePageHeader } from "@/contexts/usePageHeader";
import { useI18n } from "@/i18n";
import type { Translations } from "@/i18n/types";
import { api } from "@/lib/api";
import type {
  MxaiColumnMeta,
  MxaiDatabaseRowsResponse,
  MxaiDatabaseSummary,
  MxaiDatabaseTableSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import {
  JsonCodeEditor,
  coerceJsonDraftValue,
  formatJsonDraftValue,
  normalizeJsonForCompare,
} from "@/components/JsonCodeEditor";
import { PluginSlot } from "@/plugins";

const PAGE_SIZES = [20, 50, 100, 200] as const;

const DATABASE_TEXT: NonNullable<Translations["database"]> = {
  title: "Database",
  subtitle: "Browse project SQLite stores",
  selectDatabase: "Select database",
  tables: "Tables",
  modeBrowse: "Browse",
  modeSql: "SQL query",
  noTables: "No tables",
  sqlQuery: "SQL query",
  sqlPlaceholder: "SELECT * FROM work_logs",
  runQuery: "Run query",
  readOnlyHint: "SELECT only — simple `SELECT * FROM table` supports edit; JOIN/aggregate read-only",
  tableData: "Table data · {table}",
  pickTable: "Pick a table",
  queryResult: "Query result",
  enterSql: "Enter SQL and run query",
  paginationSummary: "{total} rows · page {page}/{pages}",
  pageSize: "Page size",
  prevPage: "Previous page",
  nextPage: "Next page",
  presetAllRows: "All rows",
  presetCount: "Count",
  presetRecent: "Recent rowid",
  sqlRequired: "Enter SQL",
  queryFailed: "Query failed",
  filePath: "File path",
  doubleClickHint: "Double-click a row to view and edit",
  rowDetailTitle: "Row detail",
  rowDetailReadOnly: "This table is read-only",
  saveRow: "Save",
  saveRowSuccess: "Row saved",
  saveRowFailed: "Save failed",
  cancel: "Cancel",
  categoryMxai: "MxAI",
  categoryHermes: "Hermes",
  schemaVersion: "Schema version",
  schemaVersionUnknown: "Unknown",
  tabMxai: "MxAI",
  tabHermesGlobal: "Hermes global",
  tabHermesProfile: "Hermes profile",
  readOnlyField: "Read-only",
  tableTagView: "VIEW",
  tableTagSystem: "System",
  tableTagReadonly: "Read-only",
  tableTagViewTitle: "SQL view (read-only)",
  tableTagSystemTitle: "Internal system table (e.g. FTS segments)",
  tableTagReadonlyTitle: "Read-only table",
  deleteRow: "Delete row",
  deleteSelected: "Delete selected ({count})",
  deleteConfirmTitle: "Delete {count} row(s)?",
  deleteConfirmDescription: "This cannot be undone.",
  deleteRowSuccess: "Deleted {count} row(s)",
  deleteRowFailed: "Delete failed",
  selectAllRows: "Select all on page",
  invalidJson: "Invalid JSON in {field}",
};

type DbCategoryTab = "mxai" | "hermes_global" | "hermes_profile";

function dbCategoryTab(db: MxaiDatabaseSummary): DbCategoryTab {
  if (db.category === "mxai") return "mxai";
  return db.profile_id ? "hermes_profile" : "hermes_global";
}

function databaseText(t: Translations): NonNullable<Translations["database"]> {
  return { ...DATABASE_TEXT, ...t.database };
}

function formatSchemaVersion(
  version: number | null | undefined,
  dbT: NonNullable<Translations["database"]>,
): string {
  if (version == null) return dbT.schemaVersionUnknown ?? "Unknown";
  return `v${version}`;
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

type TableReadonlyTag = "view" | "system" | "readonly";

function isFtsShadowTable(name: string): boolean {
  const lower = name.toLowerCase();
  if (!lower.includes("_fts")) return false;
  return (
    lower.endsWith("_data")
    || lower.endsWith("_idx")
    || lower.endsWith("_config")
    || lower.endsWith("_content")
    || lower.endsWith("_docsize")
  );
}

function inferTableReadonlyTag(table: MxaiDatabaseTableSummary): TableReadonlyTag | null {
  if (table.editable !== false) return null;
  const lower = table.name.toLowerCase();
  if (table.type === "view") return "view";
  if (lower.startsWith("sqlite_") || isFtsShadowTable(table.name)) return "system";
  return "readonly";
}

function resolveTableReadonlyTag(
  table: Pick<MxaiDatabaseTableSummary, "name" | "type" | "editable" | "readonly_tag">,
): TableReadonlyTag | null {
  const raw = table.readonly_tag;
  if (raw === "fts") {
    return inferTableReadonlyTag(table as MxaiDatabaseTableSummary);
  }
  if (raw === "view" || raw === "system" || raw === "readonly") {
    return raw;
  }
  return inferTableReadonlyTag(table as MxaiDatabaseTableSummary);
}

function tableHasDistinctLabel(table: MxaiDatabaseTableSummary): boolean {
  const label = (table.label || "").trim();
  return Boolean(label && label !== table.name);
}

function tableReadonlyBadgeText(
  tag: string | null | undefined,
  dbT: NonNullable<Translations["database"]>,
): { label: string; title: string } | null {
  if (!tag) return null;
  switch (tag as TableReadonlyTag) {
    case "view":
      return {
        label: dbT.tableTagView ?? "视图",
        title: dbT.tableTagViewTitle ?? "SQL view",
      };
    case "system":
      return {
        label: dbT.tableTagSystem ?? "系统",
        title: dbT.tableTagSystemTitle ?? "SQLite internal",
      };
    default:
      return {
        label: dbT.tableTagReadonly ?? "只读",
        title: dbT.tableTagReadonlyTitle ?? "Read-only",
      };
  }
}

function TableReadonlyBadge({
  tag,
  dbT,
  className,
}: {
  tag: string | null | undefined;
  dbT: NonNullable<Translations["database"]>;
  className?: string;
}) {
  const meta = tableReadonlyBadgeText(tag, dbT);
  if (!meta) return null;
  return (
    <Badge
      tone="secondary"
      className={cn(
        "h-4 shrink-0 px-1.5 py-0 text-[10px] font-medium tracking-wide",
        className,
      )}
      title={meta.title}
    >
      {meta.label}
    </Badge>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  return text.length > 120 ? `${text.slice(0, 117)}…` : text;
}

function columnMetaByName(
  meta: MxaiColumnMeta[] | undefined,
  name: string,
): MxaiColumnMeta | undefined {
  return meta?.find((c) => c.name === name);
}

function inferColumnMeta(name: string, value: unknown): MxaiColumnMeta | undefined {
  const lower = name.toLowerCase();
  if (
    lower !== "timestamp" &&
    !lower.endsWith("_at") &&
    !lower.endsWith("_time") &&
    !lower.endsWith("_timestamp")
  ) {
    return undefined;
  }
  const asNumber = typeof value === "number" ? value : Number(String(value).trim());
  const isUnix =
    !Number.isNaN(asNumber) && Math.abs(asNumber) >= 1e8 && Math.abs(asNumber) < 1e11;
  return {
    cid: 0,
    name,
    label: name,
    type: isUnix ? "REAL" : "TEXT",
    notnull: false,
    default_value: null,
    pk: false,
    input_type: "datetime",
    value_format: isUnix ? "unix" : "iso",
  };
}

function resolveColumnMeta(
  meta: MxaiColumnMeta[] | undefined,
  name: string,
  value: unknown,
): MxaiColumnMeta | undefined {
  return columnMetaByName(meta, name) ?? inferColumnMeta(name, value);
}

function parseTimestampToDate(
  value: unknown,
  col?: MxaiColumnMeta,
): Date | null {
  if (value === null || value === undefined || value === "") return null;

  const asNumber = typeof value === "number" ? value : Number(String(value).trim());
  const useUnix =
    col?.value_format === "unix" ||
    (col?.value_format !== "iso" &&
      !Number.isNaN(asNumber) &&
      Math.abs(asNumber) >= 1e8 &&
      Math.abs(asNumber) < 1e11);

  if (useUnix && !Number.isNaN(asNumber)) {
    return new Date(asNumber * 1000);
  }
  if (
    col?.value_format !== "iso" &&
    !Number.isNaN(asNumber) &&
    Math.abs(asNumber) >= 1e12
  ) {
    return new Date(asNumber);
  }

  const text = String(value).trim();
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDateTime(d: Date): string {
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatDisplayValue(value: unknown, col?: MxaiColumnMeta): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);

  if (col && (col.input_type === "datetime" || col.value_format)) {
    const parsed = parseTimestampToDate(value, col);
    if (parsed) return formatDateTime(parsed);
  }

  return formatCell(value);
}

function columnTitle(meta: MxaiColumnMeta[] | undefined, name: string): string {
  const hit = meta?.find((c) => c.name === name);
  if (!hit) return name;
  return hit.label !== hit.name ? `${hit.label} (${hit.name})` : hit.name;
}

function isColumnReadOnly(col: MxaiColumnMeta, tableEditable: boolean): boolean {
  if (!tableEditable) return true;
  if (col.editable === false) return true;
  if (col.editable === true) return false;
  return col.pk === true;
}

function isColumnEditable(col: MxaiColumnMeta): boolean {
  return !isColumnReadOnly(col, true);
}

function toDatetimeLocalValue(raw: string, col?: MxaiColumnMeta): string {
  const parsed = parseTimestampToDate(raw, col);
  if (!parsed) {
    if (!raw) return "";
    const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
    return normalized.length >= 16 ? normalized.slice(0, 16) : normalized;
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

function fromDatetimeLocalValue(raw: string, col?: MxaiColumnMeta): unknown {
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  if (col?.value_format === "unix") {
    return d.getTime() / 1000;
  }
  return d.toISOString().slice(0, 19);
}

function coerceDraftValue(col: MxaiColumnMeta, raw: string): unknown {
  if (raw === "") return null;
  const inputType = col.input_type ?? "text";
  if (inputType === "number") {
    if (col.type.toUpperCase().includes("INT")) {
      const n = Number.parseInt(raw, 10);
      return Number.isNaN(n) ? raw : n;
    }
    const n = Number.parseFloat(raw);
    return Number.isNaN(n) ? raw : n;
  }
  if (inputType === "boolean") {
    if (raw === "1" || raw.toLowerCase() === "true") return 1;
    if (raw === "0" || raw.toLowerCase() === "false") return 0;
    return null;
  }
  if (inputType === "datetime") {
    return fromDatetimeLocalValue(raw, col) ?? raw;
  }
  return raw;
}

function ColumnFieldEditor({
  col,
  value,
  readOnly,
  onChange,
  fieldControlClass,
}: {
  col: MxaiColumnMeta;
  value: string;
  readOnly: boolean;
  onChange: (value: string) => void;
  fieldControlClass: string;
}) {
  const inputType = col.input_type ?? "text";

  if (inputType === "boolean" && !readOnly) {
    return (
      <Segmented
        value={value === "" ? "null" : value === "1" || value.toLowerCase() === "true" ? "1" : "0"}
        onChange={(v) => onChange(v === "null" ? "" : v)}
        options={[
          { value: "1", label: "是" },
          { value: "0", label: "否" },
          { value: "null", label: "NULL" },
        ]}
      />
    );
  }

  if (inputType === "boolean") {
    const label =
      value === "1" || value.toLowerCase() === "true"
        ? "是"
        : value === "0" || value.toLowerCase() === "false"
          ? "否"
          : "NULL";
    return (
      <Input value={label} readOnly className={cn(fieldControlClass, "h-9 cursor-default opacity-90")} />
    );
  }

  if (inputType === "json") {
    return (
      <JsonCodeEditor
        value={value}
        readOnly={readOnly}
        onChange={readOnly ? undefined : onChange}
      />
    );
  }

  if (inputType === "textarea") {
    return (
      <textarea
        value={value}
        readOnly={readOnly}
        rows={4}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          fieldControlClass,
          "min-h-[5rem] resize-y",
          readOnly && "cursor-default opacity-90",
        )}
      />
    );
  }

  if (inputType === "datetime") {
    const displayValue = readOnly
      ? formatDisplayValue(value, col)
      : toDatetimeLocalValue(value, col) || value;
    return (
      <Input
        type={readOnly ? "text" : "datetime-local"}
        value={displayValue}
        readOnly={readOnly}
        onChange={(e) => onChange(e.target.value)}
        className={cn(fieldControlClass, "h-9", readOnly && "cursor-default opacity-90")}
      />
    );
  }

  if (inputType === "number" && !readOnly) {
    const isInt = col.type.toUpperCase().includes("INT");
    return (
      <Input
        type="number"
        step={isInt ? 1 : "any"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(fieldControlClass, "h-9")}
      />
    );
  }

  return (
    <Input
      value={value}
      readOnly={readOnly}
      onChange={(e) => onChange(e.target.value)}
      className={cn(fieldControlClass, "h-9", readOnly && "cursor-default opacity-90")}
    />
  );
}

function formatOrderBy(column: string | null, direction: "asc" | "desc"): string | undefined {
  if (!column) return undefined;
  return `${column} ${direction.toUpperCase()}`;
}

function rowKey(row: Record<string, unknown>, pkColumns: string[]): string {
  return pkColumns.map((col) => JSON.stringify(row[col] ?? null)).join("\0");
}

function pickRowIdentity(
  row: Record<string, unknown>,
  pkColumns: string[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const col of pkColumns) {
    out[col] = row[col];
  }
  return out;
}

function SortableColumnHeader({
  label,
  column,
  sortColumn,
  sortDir,
  onSort,
}: {
  label: string;
  column: string;
  sortColumn: string | null;
  sortDir: "asc" | "desc";
  onSort: (column: string) => void;
}) {
  const active = sortColumn === column;
  return (
    <th
      className="whitespace-nowrap px-3 py-2 text-left font-medium"
      title={label}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={cn(
          "inline-flex items-center gap-1 rounded px-1 py-0.5 text-left transition-colors",
          "hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30",
          active && "text-foreground",
        )}
      >
        <span>{label}</span>
        {active ? (
          sortDir === "asc" ? (
            <ArrowUp className="h-3 w-3 shrink-0" />
          ) : (
            <ArrowDown className="h-3 w-3 shrink-0" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 shrink-0 opacity-40" />
        )}
      </button>
    </th>
  );
}

function DataTable({
  columns,
  columnMeta,
  rows,
  editable,
  onRowDoubleClick,
  doubleClickHint,
  sortColumn,
  sortDir,
  onSort,
  pkColumns,
  selectedKeys,
  onSelectClick,
  onSelectAll,
  allPageSelected,
  somePageSelected,
  selectAllLabel,
}: {
  columns: string[];
  columnMeta?: MxaiColumnMeta[];
  rows: Record<string, unknown>[];
  editable?: boolean;
  onRowDoubleClick?: (row: Record<string, unknown>) => void;
  doubleClickHint?: string;
  sortColumn?: string | null;
  sortDir?: "asc" | "desc";
  onSort?: (column: string) => void;
  pkColumns?: string[];
  selectedKeys?: Set<string>;
  onSelectClick?: (
    event: MouseEvent,
    index: number,
    visibleRows: Record<string, unknown>[],
  ) => void;
  onSelectAll?: (visibleRows: Record<string, unknown>[]) => void;
  allPageSelected?: boolean;
  somePageSelected?: boolean;
  selectAllLabel?: string;
}) {
  const selectable = Boolean(editable && pkColumns?.length && selectedKeys && onSelectClick);
  if (columns.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">—</p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {editable && doubleClickHint && (
        <p className="text-xs text-muted-foreground">{doubleClickHint}</p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full font-mondwest normal-case text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-xs">
              {selectable && (
                <th className="w-10 px-2 py-2">
                  <Checkbox
                    checked={allPageSelected ? true : somePageSelected ? "indeterminate" : false}
                    onCheckedChange={() => onSelectAll?.(rows)}
                    aria-label={selectAllLabel ?? "Select all on page"}
                  />
                </th>
              )}
              {columns.map((col) => {
                const label = columnMeta ? columnTitle(columnMeta, col) : col;
                if (onSort) {
                  return (
                    <SortableColumnHeader
                      key={col}
                      label={label}
                      column={col}
                      sortColumn={sortColumn ?? null}
                      sortDir={sortDir ?? "desc"}
                      onSort={onSort}
                    />
                  );
                }
                return (
                  <th
                    key={col}
                    className="whitespace-nowrap px-3 py-2 text-left font-medium"
                    title={label}
                  >
                    {label}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const key = pkColumns?.length ? rowKey(row, pkColumns) : String(idx);
              const checked = selectedKeys?.has(key) ?? false;
              return (
              <tr
                key={key}
                className={cn(
                  "border-b border-border/50 transition-colors",
                  editable && onRowDoubleClick
                    ? "cursor-pointer hover:bg-secondary/30"
                    : "hover:bg-secondary/20",
                  checked && "bg-secondary/20",
                )}
                onDoubleClick={() => onRowDoubleClick?.(row)}
              >
                {selectable && pkColumns && (
                  <td className="w-10 px-2 py-2 align-top">
                    <Checkbox
                      checked={checked}
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelectClick?.(event, idx, rows);
                      }}
                      aria-label={`Select row ${idx + 1}`}
                    />
                  </td>
                )}
                {columns.map((col) => {
                  const meta = resolveColumnMeta(columnMeta, col, row[col]);
                  const display = formatDisplayValue(row[col], meta);
                  return (
                  <td
                    key={col}
                    className={cn(
                      "max-w-[280px] truncate px-3 py-2 align-top text-xs",
                      meta?.input_type === "datetime" ? "font-sans" : "font-mono",
                    )}
                    title={display}
                  >
                    {display}
                  </td>
                  );
                })}
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RowEditDialog({
  open,
  onOpenChange,
  columnMeta,
  originalRow,
  editable,
  dbT,
  saving,
  deleting,
  onSave,
  onDelete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  columnMeta: MxaiColumnMeta[];
  originalRow: Record<string, unknown> | null;
  editable: boolean;
  dbT: NonNullable<Translations["database"]>;
  saving: boolean;
  deleting?: boolean;
  onSave: (values: Record<string, unknown>) => void;
  onDelete?: () => void;
}) {
  const { showToast } = useToast();
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!originalRow) {
      setDraft({});
      return;
    }
    const next: Record<string, string> = {};
    for (const col of columnMeta) {
      const v = originalRow[col.name];
      if ((col.input_type ?? "text") === "json") {
        next[col.name] = formatJsonDraftValue(v);
      } else {
        next[col.name] = v === null || v === undefined ? "" : String(v);
      }
    }
    setDraft(next);
  }, [originalRow, columnMeta, open]);

  if (!originalRow) return null;

  const fieldControlClass = cn(
    "w-full rounded-md border border-border/70 bg-background px-3 py-2 font-mono text-xs shadow-sm",
    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30",
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 space-y-1 border-b border-border/50 px-6 py-4">
          <DialogTitle>{dbT.rowDetailTitle ?? "Row detail"}</DialogTitle>
          <DialogDescription>
            {editable ? (dbT.doubleClickHint ?? "") : (dbT.rowDetailReadOnly ?? "")}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <div className="grid gap-3">
            {columnMeta.map((col) => {
              const readOnly = isColumnReadOnly(col, editable);
              return (
                <div
                  key={col.name}
                  className={cn(
                    "rounded-lg border border-border/50 p-3",
                    readOnly ? "bg-muted/20" : "bg-secondary/10",
                  )}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <Label className="text-sm font-medium leading-none">
                      {col.label !== col.name ? col.label : col.name}
                    </Label>
                    {col.label !== col.name && (
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {col.name}
                      </span>
                    )}
                    {col.pk && (
                      <Badge tone="secondary" className="text-[10px]">
                        PK
                      </Badge>
                    )}
                    {col.unique && !col.pk && (
                      <Badge tone="secondary" className="text-[10px]">
                        UNIQUE
                      </Badge>
                    )}
                    {readOnly && editable && (
                      <span className="text-[11px] text-muted-foreground">
                        {dbT.readOnlyField ?? "Read-only"}
                      </span>
                    )}
                  </div>
                  <ColumnFieldEditor
                    col={col}
                    value={draft[col.name] ?? ""}
                    readOnly={readOnly}
                    onChange={(next) =>
                      setDraft((prev) => ({ ...prev, [col.name]: next }))
                    }
                    fieldControlClass={fieldControlClass}
                  />
                </div>
              );
            })}
          </div>
        </div>

        <DialogFooter className="shrink-0 gap-2 border-t border-border/50 bg-background px-6 py-3 sm:justify-between">
          <div>
            {editable && onDelete && (
              <Button
                ghost
                className="text-destructive hover:text-destructive"
                disabled={saving || deleting}
                onClick={onDelete}
              >
                {deleting ? <Spinner className="mr-2" /> : <Trash2 className="mr-2 h-4 w-4" />}
                {dbT.deleteRow ?? "Delete row"}
              </Button>
            )}
          </div>
          <div className="flex gap-2">
          <Button ghost onClick={() => onOpenChange(false)} disabled={saving || deleting}>
            {dbT.cancel ?? "Cancel"}
          </Button>
          {editable && (
            <Button
              disabled={saving || deleting}
              onClick={() => {
                const values: Record<string, unknown> = {};
                for (const col of columnMeta) {
                  if (!isColumnEditable(col)) continue;
                  const raw = draft[col.name] ?? "";
                  const orig = originalRow[col.name];
                  const inputType = col.input_type ?? "text";
                  let nextVal: unknown;
                  if (inputType === "json") {
                    if (!raw.trim()) {
                      nextVal = null;
                    } else {
                      try {
                        nextVal = coerceJsonDraftValue(raw);
                      } catch {
                        showToast(
                          (dbT.invalidJson ?? "Invalid JSON").replace("{field}", col.label || col.name),
                          "error",
                        );
                        return;
                      }
                    }
                    if (normalizeJsonForCompare(orig) === normalizeJsonForCompare(nextVal)) {
                      continue;
                    }
                  } else {
                    nextVal = coerceDraftValue(col, raw);
                    if (String(orig ?? "") !== String(nextVal ?? "")) {
                      values[col.name] = nextVal;
                    }
                    continue;
                  }
                  values[col.name] = nextVal;
                }
                onSave(values);
              }}
            >
              {saving ? <Spinner className="mr-2" /> : null}
              {dbT.saveRow ?? "Save"}
            </Button>
          )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PaginationBar({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  dbT,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  dbT: NonNullable<Translations["database"]>;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-3">
      <span className="text-xs text-muted-foreground">
        {dbT.paginationSummary
          .replace("{total}", String(total))
          .replace("{page}", String(page))
          .replace("{pages}", String(totalPages))}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <Label className="text-xs">{dbT.pageSize}</Label>
        <Segmented
          value={String(pageSize)}
          onChange={(v) => onPageSizeChange(Number(v))}
          options={PAGE_SIZES.map((n) => ({ value: String(n), label: String(n) }))}
          className="text-xs"
        />
        <Button
          ghost
          size="icon"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label={dbT.prevPage}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button
          ghost
          size="icon"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label={dbT.nextPage}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export default function DatabasePage() {
  const { t } = useI18n();
  const dbT = databaseText(t);
  const { showToast } = useToast();
  const { setAfterTitle, setEnd } = usePageHeader();

  const [databases, setDatabases] = useState<MxaiDatabaseSummary[]>([]);
  const [selectedDbId, setSelectedDbId] = useState("");
  const [tables, setTables] = useState<MxaiDatabaseTableSummary[]>([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [mode, setMode] = useState<"browse" | "sql">("browse");
  const [rowsData, setRowsData] = useState<MxaiDatabaseRowsResponse | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(50);
  const [sql, setSql] = useState("");
  const [loadingDbs, setLoadingDbs] = useState(false);
  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingRows, setLoadingRows] = useState(false);
  const [savingRow, setSavingRow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editRow, setEditRow] = useState<Record<string, unknown> | null>(null);
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletingRows, setDeletingRows] = useState(false);
  const [pendingDeleteRows, setPendingDeleteRows] = useState<Record<string, unknown>[]>([]);
  const [dbTab, setDbTab] = useState<DbCategoryTab>("mxai");
  const selectedDbIdRef = useRef(selectedDbId);
  const lastClickedIndexRef = useRef<number | null>(null);
  selectedDbIdRef.current = selectedDbId;

  const selectedDbMeta = useMemo(
    () => databases.find((d) => d.id === selectedDbId) ?? null,
    [databases, selectedDbId],
  );

  const selectedTableMeta = useMemo(
    () => tables.find((tbl) => tbl.name === selectedTable) ?? null,
    [tables, selectedTable],
  );

  const rowsEditable = Boolean(rowsData?.editable);
  const pkColumns = rowsData?.pk_columns ?? [];
  const activeTable = rowsData?.table || selectedTable;

  const clearSelection = useCallback(() => {
    setSelectedKeys(new Set());
    lastClickedIndexRef.current = null;
  }, []);

  const filteredDatabases = useMemo(
    () => databases.filter((db) => dbCategoryTab(db) === dbTab),
    [databases, dbTab],
  );

  const dbTabOptions = useMemo(
    () => [
      { id: "mxai" as const, label: dbT.tabMxai ?? "MxAI" },
      { id: "hermes_global" as const, label: dbT.tabHermesGlobal ?? "Hermes global" },
      { id: "hermes_profile" as const, label: dbT.tabHermesProfile ?? "Hermes profile" },
    ],
    [dbT.tabHermesGlobal, dbT.tabHermesProfile, dbT.tabMxai],
  );

  const loadDatabases = useCallback(() => {
    setLoadingDbs(true);
    setError(null);
    api
      .getMxaiDatabases()
      .then((resp) => {
        const items = resp.items.filter((d) => d.exists);
        setDatabases(items);
        setSelectedDbId((prev) => {
          const nextId =
            prev && items.some((d) => d.id === prev) ? prev : items[0]?.id ?? "";
          const nextMeta = items.find((d) => d.id === nextId);
          if (nextMeta) setDbTab(dbCategoryTab(nextMeta));
          return nextId;
        });
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoadingDbs(false));
  }, []);

  const selectDatabase = useCallback((dbId: string) => {
    setSelectedDbId(dbId);
    setSelectedTable("");
    setRowsData(null);
    setSql("");
    setPage(1);
    setSortColumn(null);
    setSortDir("desc");
    setError(null);
    setEditOpen(false);
    setEditRow(null);
    clearSelection();
  }, [clearSelection]);

  const handleDbTabChange = useCallback(
    (tab: DbCategoryTab) => {
      setDbTab(tab);
      const items = databases.filter((db) => dbCategoryTab(db) === tab);
      if (!items.some((db) => db.id === selectedDbId)) {
        selectDatabase(items[0]?.id ?? "");
      }
    },
    [databases, selectedDbId, selectDatabase],
  );

  const loadTables = useCallback((dbId: string) => {
    if (!dbId) {
      setTables([]);
      return;
    }
    setLoadingTables(true);
    setError(null);
    api
      .getMxaiDatabaseTables(dbId)
      .then((resp) => {
        if (dbId !== selectedDbIdRef.current) return;
        setTables(resp.items);
        setSelectedTable((prev) =>
          prev && resp.items.some((t) => t.name === prev) ? prev : "",
        );
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoadingTables(false));
  }, []);

  const loadBrowseRows = useCallback(
    (
      dbId: string,
      table: string,
      nextPage: number,
      nextSize: number,
      orderBy?: string,
    ) => {
      if (!dbId || !table) return;
      setLoadingRows(true);
      setError(null);
      api
        .getMxaiTableRows(dbId, table, {
          page: nextPage,
          pageSize: nextSize,
          orderBy,
        })
        .then((data) => {
          if (dbId !== selectedDbIdRef.current) return;
          setRowsData(data);
        })
        .catch((err) => setError(String(err)))
        .finally(() => setLoadingRows(false));
    },
    [],
  );

  const runSqlQuery = useCallback(
    (nextPage = page, nextSize = pageSize, orderBy = formatOrderBy(sortColumn, sortDir)) => {
      if (!selectedDbId || !sql.trim()) {
        showToast(dbT.sqlRequired, "error");
        return;
      }
      setLoadingRows(true);
      setError(null);
      api
        .runMxaiDatabaseQuery(selectedDbId, {
          sql,
          page: nextPage,
          page_size: nextSize,
          order_by: orderBy,
        })
        .then(setRowsData)
        .catch((err) => {
          setError(String(err));
          showToast(`${dbT.queryFailed}: ${String(err)}`, "error");
        })
        .finally(() => setLoadingRows(false));
    },
    [page, pageSize, selectedDbId, sortColumn, sortDir, sql, dbT.queryFailed, dbT.sqlRequired, showToast],
  );

  const handleSort = useCallback(
    (column: string) => {
      const nextDir =
        sortColumn === column ? (sortDir === "asc" ? "desc" : "asc") : "desc";
      setSortColumn(column);
      setSortDir(nextDir);
      setPage(1);
      if (mode === "sql" && selectedDbId && sql.trim() && rowsData) {
        runSqlQuery(1, pageSize, formatOrderBy(column, nextDir));
      }
    },
    [mode, pageSize, rowsData, runSqlQuery, selectedDbId, sortColumn, sortDir, sql],
  );

  const reloadRows = useCallback(() => {
    if (mode === "browse" && selectedDbId && activeTable) {
      loadBrowseRows(
        selectedDbId,
        activeTable,
        page,
        pageSize,
        formatOrderBy(sortColumn, sortDir),
      );
    } else if (mode === "sql" && selectedDbId && sql.trim()) {
      runSqlQuery(page, pageSize);
    }
  }, [
    activeTable,
    loadBrowseRows,
    mode,
    page,
    pageSize,
    runSqlQuery,
    selectedDbId,
    sortColumn,
    sortDir,
    sql,
  ]);

  const performDelete = useCallback(
    async (rowsToDelete: Record<string, unknown>[]) => {
      if (!selectedDbId || !activeTable || rowsToDelete.length === 0) return;
      setDeletingRows(true);
      try {
        const resp = await api.deleteMxaiTableRows(
          selectedDbId,
          activeTable,
          rowsToDelete.map((row) => pickRowIdentity(row, pkColumns)),
        );
        showToast(
          (dbT.deleteRowSuccess ?? "Deleted {count} row(s)").replace(
            "{count}",
            String(resp.deleted),
          ),
          "success",
        );
        setDeleteOpen(false);
        setEditOpen(false);
        setEditRow(null);
        clearSelection();
        reloadRows();
      } catch (err) {
        showToast(`${dbT.deleteRowFailed ?? "Delete failed"}: ${String(err)}`, "error");
      } finally {
        setDeletingRows(false);
        setPendingDeleteRows([]);
      }
    },
    [
      activeTable,
      clearSelection,
      dbT.deleteRowFailed,
      dbT.deleteRowSuccess,
      pkColumns,
      reloadRows,
      selectedDbId,
      showToast,
    ],
  );

  const handleDeleteSelected = useCallback(() => {
    if (!rowsData?.rows.length || selectedKeys.size === 0 || !pkColumns.length) return;
    const toDelete = rowsData.rows.filter((row) =>
      selectedKeys.has(rowKey(row, pkColumns)),
    );
    setPendingDeleteRows(toDelete);
    setDeleteOpen(true);
  }, [pkColumns, rowsData?.rows, selectedKeys]);

  const handleDeleteSingle = useCallback(() => {
    if (!editRow) return;
    setPendingDeleteRows([editRow]);
    setDeleteOpen(true);
  }, [editRow]);

  const handleSelectClick = useCallback(
    (event: MouseEvent, index: number, visibleRows: Record<string, unknown>[]) => {
      if (!pkColumns.length) return;
      const row = visibleRows[index];
      if (!row) return;
      const key = rowKey(row, pkColumns);
      setSelectedKeys((prev) => {
        const next = new Set(prev);
        const wasSelected = next.has(key);
        const willSelect = !wasSelected;
        const anchor = lastClickedIndexRef.current;
        if (event.shiftKey && anchor !== null && anchor < visibleRows.length) {
          const [lo, hi] = anchor <= index ? [anchor, index] : [index, anchor];
          for (let i = lo; i <= hi; i++) {
            const visibleRow = visibleRows[i];
            if (!visibleRow) continue;
            const rowId = rowKey(visibleRow, pkColumns);
            if (willSelect) next.add(rowId);
            else next.delete(rowId);
          }
        } else if (willSelect) {
          next.add(key);
        } else {
          next.delete(key);
        }
        return next;
      });
      lastClickedIndexRef.current = index;
    },
    [pkColumns],
  );

  const toggleSelectAllOnPage = useCallback(
    (visibleRows: Record<string, unknown>[]) => {
      if (!pkColumns.length) return;
      setSelectedKeys((prev) => {
        const pageKeys = visibleRows.map((row) => rowKey(row, pkColumns));
        const allSelected =
          pageKeys.length > 0 && pageKeys.every((pageKey) => prev.has(pageKey));
        const next = new Set(prev);
        if (allSelected) {
          for (const pageKey of pageKeys) next.delete(pageKey);
        } else {
          for (const pageKey of pageKeys) next.add(pageKey);
        }
        return next;
      });
    },
    [pkColumns],
  );

  const pageRowKeys = useMemo(
    () => (rowsData?.rows ?? []).map((row) => rowKey(row, pkColumns)),
    [pkColumns, rowsData?.rows],
  );
  const allPageSelected =
    pageRowKeys.length > 0 && pageRowKeys.every((key) => selectedKeys.has(key));
  const somePageSelected =
    !allPageSelected && pageRowKeys.some((key) => selectedKeys.has(key));
  const selectedCount = selectedKeys.size;

  const saveRow = useCallback(
    async (values: Record<string, unknown>) => {
      const targetTable = rowsData?.table || selectedTable;
      if (!selectedDbId || !targetTable || !editRow) return;
      setSavingRow(true);
      try {
        await api.updateMxaiTableRow(selectedDbId, targetTable, {
          original: editRow,
          values,
        });
        showToast(dbT.saveRowSuccess ?? "Saved", "success");
        setEditOpen(false);
        reloadRows();
      } catch (err) {
        showToast(`${dbT.saveRowFailed ?? "Save failed"}: ${String(err)}`, "error");
      } finally {
        setSavingRow(false);
      }
    },
    [
      selectedDbId,
      selectedTable,
      rowsData?.table,
      editRow,
      reloadRows,
      showToast,
      dbT.saveRowFailed,
      dbT.saveRowSuccess,
    ],
  );

  useEffect(() => {
    clearSelection();
  }, [selectedDbId, selectedTable, mode, page, clearSelection]);

  useEffect(() => {
    loadDatabases();
  }, [loadDatabases]);

  useEffect(() => {
    if (!selectedDbId) return;
    loadTables(selectedDbId);
  }, [selectedDbId, loadTables]);

  useEffect(() => {
    if (mode !== "browse" || !selectedDbId || !selectedTable || loadingTables) return;
    if (!tables.some((t) => t.name === selectedTable)) return;
    loadBrowseRows(
      selectedDbId,
      selectedTable,
      page,
      pageSize,
      formatOrderBy(sortColumn, sortDir),
    );
  }, [
    mode,
    selectedDbId,
    selectedTable,
    page,
    pageSize,
    sortColumn,
    sortDir,
    loadBrowseRows,
    tables,
    loadingTables,
  ]);

  useEffect(() => {
    if (!selectedTable) return;
    if (!tables.some((t) => t.name === selectedTable)) return;
    setSql(`SELECT * FROM ${selectedTable}`);
  }, [selectedTable, tables]);

  useLayoutEffect(() => {
    setAfterTitle(
      selectedDbMeta ? (
        <Badge tone="secondary" className="text-xs">
          {selectedDbMeta.label}
        </Badge>
      ) : null,
    );
    setEnd(
      <Button
        ghost
        size="icon"
        onClick={() => {
          loadDatabases();
          if (selectedDbId) loadTables(selectedDbId);
          if (mode === "browse" && selectedDbId && selectedTable) {
            loadBrowseRows(
              selectedDbId,
              selectedTable,
              page,
              pageSize,
              formatOrderBy(sortColumn, sortDir),
            );
          } else if (mode === "sql" && selectedDbId && sql.trim()) {
            runSqlQuery(page, pageSize);
          }
        }}
        disabled={loadingDbs || loadingTables || loadingRows}
        aria-label={t.common.refresh}
      >
        {loadingDbs || loadingTables || loadingRows ? <Spinner /> : <RefreshCw />}
      </Button>,
    );
    return () => {
      setAfterTitle(null);
      setEnd(null);
    };
  }, [
    loadBrowseRows,
    loadDatabases,
    loadTables,
    loadingDbs,
    loadingRows,
    loadingTables,
    mode,
    page,
    pageSize,
    runSqlQuery,
    selectedDbId,
    selectedDbMeta,
    selectedTable,
    sortColumn,
    sortDir,
    setAfterTitle,
    setEnd,
    sql,
    t.common.refresh,
  ]);

  const sqlPresets = useMemo(() => {
    const table = selectedTable || "your_table";
    return [
      { label: dbT.presetAllRows, sql: `SELECT * FROM ${table}` },
      { label: dbT.presetCount, sql: `SELECT COUNT(*) AS row_count FROM ${table}` },
      { label: dbT.presetRecent, sql: `SELECT * FROM ${table} ORDER BY rowid DESC` },
    ];
  }, [selectedTable, dbT.presetAllRows, dbT.presetCount, dbT.presetRecent]);

  const tableTitle =
    mode === "browse" && selectedTable
      ? (rowsData?.table_label || selectedTableMeta?.label || selectedTable)
      : null;

  return (
    <div className="flex min-h-0 flex-col gap-4">
      <PluginSlot name="database-pre" />

      <div className="grid min-h-0 gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Card className="min-h-0">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-base">{dbT.selectDatabase}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="flex max-h-[70vh] flex-col gap-3 overflow-hidden">
            <div
              className="grid shrink-0 gap-1 border-b border-border/50 pb-3"
              role="tablist"
              aria-label={dbT.selectDatabase}
            >
              {dbTabOptions.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={dbTab === tab.id}
                  title={tab.label}
                  onClick={() => handleDbTabChange(tab.id)}
                  className={cn(
                    "rounded-md px-3 py-2 text-left text-xs transition-colors",
                    dbTab === tab.id
                      ? "bg-midground/10 font-medium text-foreground"
                      : "text-muted-foreground hover:bg-secondary/20 hover:text-foreground",
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
            {loadingDbs && databases.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner />
                {t.common.loading}
              </div>
            ) : filteredDatabases.length === 0 ? (
              <p className="text-sm text-muted-foreground">{dbT.noTables}</p>
            ) : (
              filteredDatabases.map((db) => (
                <button
                  key={db.id}
                  type="button"
                  onClick={() => {
                    selectDatabase(db.id);
                    setDbTab(dbCategoryTab(db));
                  }}
                  className={cn(
                    "rounded-md border px-3 py-2 text-left transition-colors",
                    selectedDbId === db.id
                      ? "border-midground/40 bg-midground/10"
                      : "border-border/60 hover:bg-secondary/20",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{db.label}</span>
                    <Badge tone="secondary" className="text-[10px]">
                      {db.category === "hermes" ? (dbT.categoryHermes ?? "Hermes") : (dbT.categoryMxai ?? "MxAI")}
                    </Badge>
                    <Badge tone="secondary" className="text-[10px] font-mono">
                      {formatSchemaVersion(db.schema_version, dbT)}
                    </Badge>
                  </div>
                  {db.description && (
                    <div className="mt-1 text-xs text-muted-foreground">{db.description}</div>
                  )}
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {formatBytes(db.size_bytes)}
                  </div>
                </button>
              ))
            )}
            </div>
          </CardContent>
        </Card>

        <div className="flex min-h-0 flex-col gap-4">
          {selectedDbMeta && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <p className="break-all">
                <span className="font-medium text-foreground">{dbT.filePath}: </span>
                {selectedDbMeta.path}
              </p>
              <p>
                <span className="font-medium text-foreground">{dbT.schemaVersion ?? "Schema version"}: </span>
                <span className="font-mono">
                  {formatSchemaVersion(selectedDbMeta.schema_version, dbT)}
                </span>
              </p>
            </div>
          )}

          <Card>
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Table2 className="h-4 w-4 text-muted-foreground" />
                  <CardTitle className="text-base">{dbT.tables}</CardTitle>
                </div>
                <Segmented
                  value={mode}
                  onChange={(v) => setMode(v as "browse" | "sql")}
                  options={[
                    { value: "browse", label: dbT.modeBrowse },
                    { value: "sql", label: dbT.modeSql },
                  ]}
                />
              </div>
            </CardHeader>
            <CardContent>
              {loadingTables ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Spinner />
                  {t.common.loading}
                </div>
              ) : tables.length === 0 ? (
                <p className="text-sm text-muted-foreground">{dbT.noTables}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {tables.map((table) => (
                    <Button
                      key={table.name}
                      ghost={selectedTable !== table.name}
                      size="sm"
                      onClick={() => {
                        setSelectedTable(table.name);
                        setMode("browse");
                        setPage(1);
                        setSortColumn(null);
                        setSortDir("desc");
                        clearSelection();
                      }}
                      className={cn(
                        "text-xs",
                        selectedTable === table.name && "bg-midground/10",
                      )}
                      title={[
                        table.name,
                        tableReadonlyBadgeText(resolveTableReadonlyTag(table), dbT)?.title,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    >
                      {tableHasDistinctLabel(table) && <span>{table.label}</span>}
                      <span
                        className={cn(
                          tableHasDistinctLabel(table) ? "font-mono text-muted-foreground" : "",
                        )}
                      >
                        {table.name}
                      </span>
                      <TableReadonlyBadge
                        tag={resolveTableReadonlyTag(table)}
                        dbT={dbT}
                        className="ml-1"
                      />
                      {table.row_count !== null && (
                        <span className="ml-1 text-muted-foreground">({table.row_count})</span>
                      )}
                    </Button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {mode === "sql" && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{dbT.sqlQuery}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-2">
                  {sqlPresets.map((preset) => (
                    <Button key={preset.label} ghost size="sm" onClick={() => setSql(preset.sql)}>
                      {preset.label}
                    </Button>
                  ))}
                </div>
                <textarea
                  value={sql}
                  onChange={(e) => setSql(e.target.value)}
                  rows={5}
                  className="flex min-h-[120px] w-full border border-border bg-background/40 px-3 py-2 font-mono text-xs shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
                  placeholder={dbT.sqlPlaceholder}
                />
                <div className="flex items-center gap-2">
                  <Button
                    onClick={() => {
                      setPage(1);
                      runSqlQuery(1, pageSize);
                    }}
                    disabled={loadingRows || !selectedDbId}
                  >
                    <Play className="mr-1 h-4 w-4" />
                    {dbT.runQuery}
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    {rowsEditable ? dbT.doubleClickHint : dbT.readOnlyHint}
                  </span>
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="min-h-[320px]">
            <CardHeader className="pb-2">
              <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                {mode === "browse" ? (
                  tableTitle ? (
                    <>
                      <span>{dbT.tableData.replace("{table}", tableTitle)}</span>
                      <TableReadonlyBadge
                        tag={
                          rowsData?.readonly_tag ??
                          (selectedTableMeta
                            ? resolveTableReadonlyTag(selectedTableMeta)
                            : null)
                        }
                        dbT={dbT}
                      />
                    </>
                  ) : (
                    dbT.pickTable
                  )
                ) : (
                  dbT.queryResult
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex min-h-0 flex-col gap-3">
              {error && (
                <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  {error}
                </p>
              )}
              {loadingRows ? (
                <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                  <Spinner />
                  {t.common.loading}
                </div>
              ) : rowsData ? (
                <>
                  {rowsEditable && selectedCount > 0 && (
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        ghost
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={handleDeleteSelected}
                      >
                        <Trash2 className="mr-1 h-4 w-4" />
                        {(dbT.deleteSelected ?? "Delete selected ({count})").replace(
                          "{count}",
                          String(selectedCount),
                        )}
                      </Button>
                    </div>
                  )}
                  <DataTable
                    columns={rowsData.columns}
                    columnMeta={rowsData.column_meta}
                    rows={rowsData.rows}
                    editable={rowsEditable}
                    doubleClickHint={dbT.doubleClickHint}
                    sortColumn={sortColumn}
                    sortDir={sortDir}
                    onSort={handleSort}
                    pkColumns={pkColumns}
                    selectedKeys={selectedKeys}
                    onSelectClick={handleSelectClick}
                    onSelectAll={toggleSelectAllOnPage}
                    allPageSelected={allPageSelected}
                    somePageSelected={somePageSelected}
                    selectAllLabel={dbT.selectAllRows}
                    onRowDoubleClick={
                      rowsEditable
                        ? (row) => {
                            setEditRow(row);
                            setEditOpen(true);
                          }
                        : undefined
                    }
                  />
                  <PaginationBar
                    page={rowsData.page}
                    pageSize={rowsData.page_size}
                    total={rowsData.total}
                    onPageChange={(next) => {
                      setPage(next);
                      if (mode === "sql") runSqlQuery(next, pageSize);
                    }}
                    onPageSizeChange={(next) => {
                      setPageSize(next);
                      setPage(1);
                      if (mode === "browse" && selectedDbId && selectedTable) {
                        loadBrowseRows(
                          selectedDbId,
                          selectedTable,
                          1,
                          next,
                          formatOrderBy(sortColumn, sortDir),
                        );
                      } else if (mode === "sql") {
                        runSqlQuery(1, next);
                      }
                    }}
                    dbT={dbT}
                  />
                </>
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {mode === "browse" ? dbT.pickTable : dbT.enterSql}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <RowEditDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        columnMeta={rowsData?.column_meta ?? []}
        originalRow={editRow}
        editable={rowsEditable}
        dbT={dbT}
        saving={savingRow}
        deleting={deletingRows}
        onSave={saveRow}
        onDelete={rowsEditable ? handleDeleteSingle : undefined}
      />

      <DeleteConfirmDialog
        open={deleteOpen}
        loading={deletingRows}
        title={(dbT.deleteConfirmTitle ?? "Delete {count} row(s)?").replace(
          "{count}",
          String(pendingDeleteRows.length),
        )}
        description={dbT.deleteConfirmDescription}
        onCancel={() => {
          setDeleteOpen(false);
          setPendingDeleteRows([]);
        }}
        onConfirm={() => performDelete(pendingDeleteRows)}
      />

      <PluginSlot name="database-post" />
    </div>
  );
}
