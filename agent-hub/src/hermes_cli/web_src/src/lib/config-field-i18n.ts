import type { Locale } from "@/i18n/types";
import {
  CONFIG_FIELD_DESCRIPTIONS_ZH,
  CONFIG_FIELD_LABELS_ZH,
} from "@/i18n/config-fields-zh.generated";

function englishLabelFromKey(schemaKey: string): string {
  const leaf = schemaKey.split(".").pop() ?? schemaKey;
  return leaf.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function isAutoEnglishDescription(schemaKey: string, description: string): boolean {
  const normalized = description.trim().toLowerCase();
  const leaf = schemaKey.split(".").pop() ?? schemaKey;
  const auto = leaf.replace(/_/g, " ").toLowerCase();
  const path = schemaKey.replace(/\./g, " → ").replace(/_/g, " ").toLowerCase();
  return normalized === auto || normalized === path;
}

export function resolveConfigFieldLabel(
  schemaKey: string,
  locale: Locale,
): string {
  if (locale === "zh") {
    return CONFIG_FIELD_LABELS_ZH[schemaKey] ?? englishLabelFromKey(schemaKey);
  }
  return englishLabelFromKey(schemaKey);
}

export function resolveConfigFieldDescription(
  schemaKey: string,
  schema: Record<string, unknown>,
  locale: Locale,
): string | undefined {
  const raw = schema.description ? String(schema.description) : "";
  if (locale === "zh") {
    const zh = CONFIG_FIELD_DESCRIPTIONS_ZH[schemaKey];
    if (zh) return zh;
    if (raw && !isAutoEnglishDescription(schemaKey, raw)) {
      return raw;
    }
    return CONFIG_FIELD_LABELS_ZH[schemaKey];
  }
  return raw || undefined;
}
