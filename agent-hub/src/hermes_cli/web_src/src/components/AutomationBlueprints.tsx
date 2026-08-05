import { useCallback, useEffect, useState } from "react";
import { Clock, Wand2 } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { api } from "@/lib/api";
import type { AutomationBlueprint, AutomationBlueprintField } from "@/lib/api";
import { useI18n } from "@/i18n";
import type { Translations } from "@/i18n";
import { cn, themedBody } from "@/lib/utils";

interface AutomationBlueprintsProps {
  profile: string;
  /** Called after a blueprint is instantiated so the parent can refresh its job list. */
  onCreated?: () => void;
}

const DEFAULT_BLUEPRINT_UI = {
  setUp: "Set up",
  cancel: "Cancel",
  scheduleIt: "Schedule it",
  scheduled: "scheduled",
  loadError: "Couldn't load blueprints",
  loading: "Loading blueprints…",
  empty: "No automation blueprints available.",
};

function blueprintOptionLabel(opt: string, field: AutomationBlueprintField, t: Translations): string {
  const byField = t.cron.blueprintOptions?.[`${field.name}:${opt}`];
  if (byField) return byField;
  const mapped = t.cron.blueprintOptions?.[opt];
  if (mapped) return mapped;
  const delivery = t.cron.delivery as Record<string, string | undefined>;
  if (delivery[opt]) return delivery[opt]!;
  return opt;
}

/** Initial form values for a blueprint = each field's default (or ""). */
function initialValues(blueprint: AutomationBlueprint): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of blueprint.fields) out[f.name] = f.default ?? "";
  return out;
}

function FieldInput({
  field,
  value,
  onChange,
  t,
}: {
  field: AutomationBlueprintField;
  value: string;
  onChange: (v: string) => void;
  t: Translations;
}) {
  if (field.type === "enum" || field.type === "weekdays") {
    return (
      <Select value={value} onValueChange={(v) => onChange(v)}>
        {field.options.map((opt) => (
          <SelectOption key={opt} value={opt}>
            {blueprintOptionLabel(opt, field, t)}
          </SelectOption>
        ))}
      </Select>
    );
  }
  if (field.type === "time") {
    return (
      <Input
        type="time"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  // text
  return (
    <Input
      type="text"
      value={value}
      placeholder={field.help || field.label}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function BlueprintCard({
  blueprint,
  profile,
  showToast,
  onCreated,
  ui,
  t,
}: {
  blueprint: AutomationBlueprint;
  profile: string;
  showToast: (message: string, type: "error" | "success") => void;
  onCreated?: () => void;
  ui: typeof DEFAULT_BLUEPRINT_UI;
  t: Translations;
}) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() => initialValues(blueprint));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.instantiateAutomationBlueprint({ blueprint: blueprint.key, values }, profile);
      const when = job.schedule_display ? ` — ${job.schedule_display}` : "";
      showToast(`${blueprint.title} ${ui.scheduled}${when}`, "success");
      setOpen(false);
      setValues(initialValues(blueprint));
      onCreated?.();
    } catch (e) {
      // 422 from the API carries the slot-level validation message.
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg.replace(/^\d+:\s*/, ""));
    } finally {
      setSubmitting(false);
    }
  }, [blueprint, values, profile, showToast, onCreated, ui.scheduled]);

  return (
    <Card className={cn("overflow-hidden", themedBody)}>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Wand2 className="h-4 w-4 shrink-0 opacity-70" />
              <span className="font-medium">{blueprint.title}</span>
            </div>
            <p className="mt-1 text-sm opacity-70">{blueprint.description}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {blueprint.tags.map((tag) => (
                <Badge key={tag} tone="secondary">
                  {tag}
                </Badge>
              ))}
            </div>
          </div>
          <Button
            ghost={open}
            size="sm"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? ui.cancel : ui.setUp}
          </Button>
        </div>

        {open && (
          <div className="space-y-3 border-t pt-3">
            {blueprint.fields.map((f) => (
              <div key={f.name} className="space-y-1">
                <Label htmlFor={`${blueprint.key}-${f.name}`}>{f.label}</Label>
                <FieldInput
                  field={f}
                  value={values[f.name] ?? ""}
                  onChange={(v) => setValues((prev) => ({ ...prev, [f.name]: v }))}
                  t={t}
                />
                {f.help && f.type !== "text" ? (
                  <p className="text-xs opacity-60">{f.help}</p>
                ) : null}
              </div>
            ))}
            {error ? (
              <p className="text-sm text-red-500" role="alert">
                {error}
              </p>
            ) : null}
            <div className="flex items-center gap-2">
              <Button onClick={() => void submit()} disabled={submitting}>
                {submitting ? <Spinner className="h-4 w-4" /> : <Clock className="h-4 w-4" />}
                {ui.scheduleIt}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Automation Blueprints gallery — the form-where-there's-a-screen surface. Each blueprint
 * card expands into an inline form (one field per typed slot); submitting POSTs
 * to /api/cron/blueprints/instantiate which fills the blueprint and creates the job
 * via the same create_job path as everything else.
 */
export function AutomationBlueprints({ profile, onCreated }: AutomationBlueprintsProps) {
  const { toast, showToast } = useToast();
  const { t } = useI18n();
  const ui = { ...DEFAULT_BLUEPRINT_UI, ...t.cron.blueprintUi };
  const [blueprints, setBlueprints] = useState<AutomationBlueprint[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getAutomationBlueprints()
      .then((r) => {
        if (!cancelled) setBlueprints(r.blueprints);
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return <p className="text-sm text-red-500">{ui.loadError}: {loadError}</p>;
  }
  if (blueprints === null) {
    return (
      <div className="flex items-center gap-2 opacity-70">
        <Spinner className="h-4 w-4" /> {ui.loading}
      </div>
    );
  }
  if (blueprints.length === 0) {
    return <p className="opacity-70">{ui.empty}</p>;
  }

  return (
    <>
      <Toast toast={toast} />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {blueprints.map((r) => (
          <BlueprintCard
            key={r.key}
            blueprint={r}
            profile={profile}
            showToast={showToast}
            onCreated={onCreated}
            ui={ui}
            t={t}
          />
        ))}
      </div>
    </>
  );
}

export default AutomationBlueprints;
