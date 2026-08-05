import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { json, jsonParseLinter } from "@codemirror/lang-json";
import { oneDark } from "@codemirror/theme-one-dark";
import { linter } from "@codemirror/lint";
import { cn } from "@/lib/utils";

export function formatJsonDraftValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  const raw = String(value);
  if (!raw.trim()) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

export function normalizeJsonForCompare(value: unknown): string {
  if (value === null || value === undefined) return "";
  const raw = typeof value === "object" ? JSON.stringify(value) : String(value);
  if (!raw.trim()) return "";
  try {
    return JSON.stringify(JSON.parse(raw));
  } catch {
    return raw;
  }
}

export function coerceJsonDraftValue(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  return JSON.stringify(JSON.parse(trimmed));
}

interface JsonCodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  className?: string;
  minHeight?: string;
}

export function JsonCodeEditor({
  value,
  onChange,
  readOnly = false,
  className,
  minHeight = "10rem",
}: JsonCodeEditorProps) {
  const extensions = useMemo(
    () => [json(), linter(jsonParseLinter())],
    [],
  );

  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-border/70 bg-background shadow-sm",
        readOnly && "opacity-90",
        className,
      )}
    >
      <CodeMirror
        value={value}
        height={minHeight}
        theme={oneDark}
        extensions={extensions}
        editable={!readOnly}
        readOnly={readOnly}
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: !readOnly,
          autocompletion: false,
        }}
        onChange={(next) => onChange?.(next)}
        className="text-xs [&_.cm-editor]:outline-none [&_.cm-scroller]:font-mono"
      />
    </div>
  );
}
