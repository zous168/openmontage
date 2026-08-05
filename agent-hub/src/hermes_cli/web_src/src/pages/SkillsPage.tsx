import { useEffect, useLayoutEffect, useState, useMemo, useCallback } from "react";
import {
  Package,
  Search,
  Wrench,
  X,
  Cpu,
  Globe,
  Shield,
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  Eye,
  Paintbrush,
  Brain,
  Blocks,
  Code,
  Zap,
  Filter,
  Download,
  RefreshCw,
  FileText,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Loader2,
  Pencil,
  Plus,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  SkillInfo,
  ToolsetInfo,
  SkillHubResult,
  SkillHubSource,
  SkillHubInstalledEntry,
  SkillHubPreview,
  SkillHubScan,
  PluginsHubResponse,
} from "@/lib/api";
import { ToolsetConfigDrawer } from "@/components/ToolsetConfigDrawer";
import { SkillEditorDialog } from "@/components/SkillEditorDialog";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { ListItem } from "@nous-research/ui/ui/components/list-item";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Switch } from "@nous-research/ui/ui/components/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@nous-research/ui/ui/components/dialog";
import { cn } from "@/lib/utils";
import { Input } from "@nous-research/ui/ui/components/input";
import { useI18n } from "@/i18n";
import type { Translations } from "@/i18n/types";
import { usePageHeader } from "@/contexts/usePageHeader";
import { useProfileScope } from "@/contexts/useProfileScope";
import { PluginSlot } from "@/plugins";

/* ------------------------------------------------------------------ */
/*  Types & helpers                                                    */
/* ------------------------------------------------------------------ */

const CATEGORY_LABELS: Record<string, string> = {
  mlops: "MLOps",
  "mlops/cloud": "MLOps / Cloud",
  "mlops/evaluation": "MLOps / Evaluation",
  "mlops/inference": "MLOps / Inference",
  "mlops/models": "MLOps / Models",
  "mlops/training": "MLOps / Training",
  "mlops/vector-databases": "MLOps / Vector DBs",
  mcp: "MCP",
  "red-teaming": "Red Teaming",
  ocr: "OCR",
  p5js: "p5.js",
  ai: "AI",
  ux: "UX",
  ui: "UI",
};

function prettyCategory(
  raw: string | null | undefined,
  generalLabel: string,
): string {
  if (!raw) return generalLabel;
  if (CATEGORY_LABELS[raw]) return CATEGORY_LABELS[raw];
  return raw
    .split(/[-_/]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const TOOLSET_ICONS: Record<
  string,
  React.ComponentType<{ className?: string }>
> = {
  computer: Cpu,
  web: Globe,
  security: Shield,
  vision: Eye,
  design: Paintbrush,
  ai: Brain,
  integration: Blocks,
  code: Code,
  automation: Zap,
};

function toolsetIcon(
  name: string,
): React.ComponentType<{ className?: string }> {
  const lower = name.toLowerCase();
  for (const [key, icon] of Object.entries(TOOLSET_ICONS)) {
    if (lower.includes(key)) return icon;
  }
  return Wrench;
}

type CatalogHitKind = "skill" | "toolset" | "tool" | "plugin_tool";

interface CatalogHit {
  kind: CatalogHitKind;
  id: string;
  name: string;
  subtitle?: string;
  enabled?: boolean;
  skill?: SkillInfo;
  toolset?: ToolsetInfo;
  pluginName?: string;
  /** 工具 / 插件工具行：所属工具集展示名（非配置入口）。 */
  associatedToolsetLabel?: string;
  associatedToolsetKey?: string;
}

function catalogHitKindLabel(
  kind: CatalogHitKind,
  skills: Translations["skills"],
): string {
  switch (kind) {
    case "skill":
      return skills.searchKindSkill ?? "Skill";
    case "toolset":
      return skills.searchKindToolset ?? "Toolset";
    case "tool":
      return skills.searchKindTool ?? "Tool";
    case "plugin_tool":
      return skills.searchKindPluginTool ?? "Plugin tool";
    default:
      return kind;
  }
}

function buildCatalogHits(
  skills: SkillInfo[],
  toolsets: ToolsetInfo[],
  pluginsHub: PluginsHubResponse | null,
  query?: string,
): CatalogHit[] {
  const q = (query ?? "").trim().toLowerCase();
  const filter = q.length > 0;
  const hits: CatalogHit[] = [];
  const seenToolNames = new Set<string>();

  for (const s of skills) {
    if (
      filter &&
      !s.name.toLowerCase().includes(q) &&
      !s.description.toLowerCase().includes(q) &&
      !(s.category ?? "").toLowerCase().includes(q)
    ) {
      continue;
    }
    hits.push({
      kind: "skill",
      id: `skill:${s.name}`,
      name: s.name,
      subtitle: s.category || undefined,
      enabled: s.enabled,
      skill: s,
    });
  }

  for (const ts of toolsets) {
    const label = (ts.label || ts.name).toLowerCase();
    const desc = (ts.description || "").toLowerCase();
    const tsMatch =
      !filter ||
      ts.name.toLowerCase().includes(q) ||
      label.includes(q) ||
      desc.includes(q);
    if (tsMatch) {
      hits.push({
        kind: "toolset",
        id: `toolset:${ts.name}`,
        name: ts.label?.trim() || ts.name,
        subtitle: ts.name,
        enabled: ts.enabled,
        toolset: ts,
      });
    }
    for (const tool of ts.tools) {
      const tl = tool.toLowerCase();
      if (filter && !tl.includes(q) && !tsMatch) continue;
      if (seenToolNames.has(tool)) continue;
      seenToolNames.add(tool);
      hits.push({
        kind: "tool",
        id: `tool:${ts.name}:${tool}`,
        name: tool,
        enabled:
          ts.name === "mxai" && ts.tool_enabled && tool in ts.tool_enabled
            ? ts.tool_enabled[tool]
            : ts.enabled,
        associatedToolsetLabel: ts.label?.trim() || ts.name,
        associatedToolsetKey: ts.name,
        toolset: ts,
      });
    }
  }

  if (pluginsHub) {
    for (const plugin of pluginsHub.plugins) {
      if (plugin.runtime_status !== "enabled") continue;
      const pluginMatch = plugin.name.toLowerCase().includes(q);
      for (const tool of plugin.provides_tools ?? []) {
        const tl = tool.toLowerCase();
        if (filter && !tl.includes(q) && !pluginMatch) continue;
        if (seenToolNames.has(tool)) continue;
        seenToolNames.add(tool);
        const linked =
          toolsets.find(
            (ts) =>
              ts.name === tool ||
              ts.tools.includes(tool) ||
              (plugin.toolset && ts.name === plugin.toolset) ||
              ts.name === plugin.name,
          ) ?? undefined;
        hits.push({
          kind: "plugin_tool",
          id: `plugin:${plugin.name}:${tool}`,
          name: tool,
          subtitle: plugin.name,
          pluginName: plugin.name,
          enabled:
            linked && linked.name === tool && linked.tool_enabled?.[tool] !== undefined
              ? linked.tool_enabled[tool]
              : linked?.enabled,
          associatedToolsetLabel: linked
            ? linked.label?.trim() || linked.name
            : plugin.toolset || plugin.name,
          associatedToolsetKey:
            linked?.name ?? plugin.toolset ?? plugin.name,
          toolset: linked,
        });
      }
    }
  }

  return hits;
}

/** Catalog 工具行开关写入的 toolset key（mxai / 单工具 toolset 用工具名）。 */
function catalogHitToggleKey(hit: CatalogHit): string {
  const bundleKey = hit.associatedToolsetKey ?? hit.name;
  if (bundleKey === "mxai" || bundleKey === hit.name) return hit.name;
  return bundleKey;
}

function catalogHitToggleToolset(hit: CatalogHit): ToolsetInfo {
  const bundleKey = hit.associatedToolsetKey ?? hit.name;
  const base = hit.toolset;
  return {
    name: bundleKey,
    label: hit.associatedToolsetLabel ?? bundleKey,
    description: base?.description ?? "",
    enabled: hit.enabled ?? base?.enabled ?? false,
    configured: base?.configured ?? false,
    tools: base?.tools ?? [hit.name],
    tool_enabled: base?.tool_enabled,
  };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [toolsets, setToolsets] = useState<ToolsetInfo[]>([]);
  const [pluginsHub, setPluginsHub] = useState<PluginsHubResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"skills" | "toolsets" | "hub">("skills");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [togglingSkills, setTogglingSkills] = useState<Set<string>>(new Set());
  const [togglingToolsets, setTogglingToolsets] = useState<Set<string>>(new Set());
  const [configToolset, setConfigToolset] = useState<ToolsetInfo | null>(null);
  // Skill editor dialog: open + which skill is being edited (null = create).
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorSkill, setEditorSkill] = useState<string | null>(null);
  const { toast, showToast } = useToast();
  const { t } = useI18n();
  const { setAfterTitle } = usePageHeader();
  /** 与侧栏 Profile 切换器 / ``?profile=`` 一致；"" = HUB_DATA_DIR 根。 */
  const { profile: writeProfile } = useProfileScope();

  useEffect(() => {
    // Promise-chain shape: setState fires only inside async callbacks so the
    // effect body stays lint-clean (react-hooks/set-state-in-effect). On a
    // profile switch the old list stays visible until the new one arrives.
    let cancelled = false;
    Promise.all([
      api.getSkills(writeProfile),
      api.getToolsets(writeProfile),
      api.getPluginsHub(),
    ])
      .then(([s, tsets, hub]) => {
        if (cancelled) return;
        setSkills(s);
        setToolsets(tsets);
        setPluginsHub(hub);
      })
      .catch(() => !cancelled && showToast(t.common.loading, "error"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [writeProfile, showToast, t]);

  /* ---- Toggle skill ---- */
  const handleToggleSkill = async (skill: SkillInfo) => {
    setTogglingSkills((prev) => new Set(prev).add(skill.name));
    try {
      await api.toggleSkill(skill.name, !skill.enabled, writeProfile);
      setSkills((prev) =>
        prev.map((s) =>
          s.name === skill.name ? { ...s, enabled: !s.enabled } : s,
        ),
      );
      showToast(
        `${skill.name} ${skill.enabled ? t.common.disabled : t.common.enabled}`,
        "success",
      );
    } catch {
      showToast(`${t.common.failedToToggle} ${skill.name}`, "error");
    } finally {
      setTogglingSkills((prev) => {
        const next = new Set(prev);
        next.delete(skill.name);
        return next;
      });
    }
  };

  /* ---- Refresh toolsets after a config change ---- */
  const refreshToolsets = async () => {
    try {
      const tsets = await api.getToolsets(writeProfile);
      setToolsets(tsets);
    } catch {
      /* non-fatal: the drawer already toasted on the failing write */
    }
  };

  const handleToggleToolset = async (
    toolset: ToolsetInfo,
    next: boolean,
    toolsetKey?: string,
  ) => {
    const key = toolsetKey ?? toolset.name;
    setTogglingToolsets((prev) => new Set(prev).add(key));
    try {
      await api.toggleToolset(key, next, writeProfile);
      await refreshToolsets();
      const label =
        toolsetKey && toolsetKey !== toolset.name
          ? toolsetKey
          : toolset.label || toolset.name;
      showToast(
        `${label} ${next ? t.common.enabled : t.common.disabled}`,
        "success",
      );
    } catch {
      showToast(`${t.common.failedToToggle} ${key}`, "error");
    } finally {
      setTogglingToolsets((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
    }
  };

  /* ---- Skill editor (create / edit SKILL.md) ---- */
  const openCreateEditor = useCallback(() => {
    setEditorSkill(null);
    setEditorOpen(true);
  }, []);
  const openEditEditor = useCallback((skillName: string) => {
    setEditorSkill(skillName);
    setEditorOpen(true);
  }, []);
  const handleEditorSaved = useCallback(
    (skillName: string) => {
      showToast(
        (t.skills?.savedSkill ?? "{name} saved").replace("{name}", skillName),
        "success",
      );
      // Reload the list so a newly created skill (or an edited description)
      // shows up immediately.
      api
        .getSkills(writeProfile)
        .then(setSkills)
        .catch(() => {});
    },
    [writeProfile, showToast, t],
  );

  /* ---- Derived data ---- */
  const lowerSearch = search.toLowerCase();
  const isSearching = search.trim().length > 0;

  const catalogAllHits = useMemo(
    () => buildCatalogHits(skills, toolsets, pluginsHub),
    [skills, toolsets, pluginsHub],
  );

  const catalogSearchHits = useMemo(
    () => (isSearching ? buildCatalogHits(skills, toolsets, pluginsHub, lowerSearch) : []),
    [isSearching, lowerSearch, skills, toolsets, pluginsHub],
  );

  const showUnifiedAll =
    view === "skills" && !activeCategory && !isSearching;

  const activeSkills = useMemo(() => {
    if (isSearching) return [];
    if (!activeCategory)
      return [...skills].sort((a, b) => a.name.localeCompare(b.name));
    return skills
      .filter((s) =>
        activeCategory === "__none__"
          ? !s.category
          : s.category === activeCategory,
      )
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [skills, activeCategory, isSearching]);

  const allCategories = useMemo(() => {
    const cats = new Map<string, number>();
    for (const s of skills) {
      const key = s.category || "__none__";
      cats.set(key, (cats.get(key) || 0) + 1);
    }
    return [...cats.entries()]
      .sort((a, b) => {
        if (a[0] === "__none__") return -1;
        if (b[0] === "__none__") return 1;
        return a[0].localeCompare(b[0]);
      })
      .map(([key, count]) => ({
        key,
        name: prettyCategory(key === "__none__" ? null : key, t.common.general),
        count,
      }));
  }, [skills, t]);

  const enabledCount = skills.filter((s) => s.enabled).length;

  useLayoutEffect(() => {
    if (loading) {
      setAfterTitle(null);
      return;
    }
    setAfterTitle(
      <span className="flex items-center gap-2 whitespace-nowrap text-xs text-muted-foreground">
        {t.skills.enabledOf
          .replace("{enabled}", String(enabledCount))
          .replace("{total}", String(skills.length))}
      </span>,
    );
    return () => {
      setAfterTitle(null);
    };
  }, [enabledCount, loading, setAfterTitle, skills.length, t]);

  const filteredToolsets = useMemo(() => {
    return toolsets.filter(
      (ts) =>
        !search ||
        ts.name.toLowerCase().includes(lowerSearch) ||
        ts.label.toLowerCase().includes(lowerSearch) ||
        ts.description.toLowerCase().includes(lowerSearch),
    );
  }, [toolsets, search, lowerSearch]);

  /* ---- Loading ---- */
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="text-2xl text-primary" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <PluginSlot name="skills:top" />
      <Toast toast={toast} />

      <div className="relative w-full min-w-0">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none"
          aria-hidden
        />
        <Input
          className="h-10 w-full rounded-none pl-10 pr-10 text-sm"
          placeholder={t.skills.searchPlaceholder ?? t.common.search}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={t.skills.searchPlaceholder ?? t.common.search}
        />
        {search && (
          <Button
            ghost
            size="xs"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            onClick={() => setSearch("")}
            aria-label={t.common.clear}
          >
            <X />
          </Button>
        )}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
        <aside aria-label={t.skills.title} className="sm:w-56 sm:shrink-0">
          <div className="sm:sticky sm:top-0">
            <div className="flex flex-col rounded-none border border-border bg-muted/20">
              <div className="hidden sm:flex items-center gap-2 px-3 py-2 border-b border-border">
                <Filter className="h-3 w-3 text-text-tertiary" />
                <span className="font-mondwest text-display text-xs tracking-[0.12em] text-text-secondary">
                  {t.skills.filters}
                </span>
              </div>

              <div className="flex sm:flex-col gap-1 overflow-x-auto sm:overflow-x-visible scrollbar-none p-2">
                <PanelItem
                  icon={Package}
                  label={`${t.skills.all} (${catalogAllHits.length})`}
                  active={showUnifiedAll}
                  onClick={() => {
                    setView("skills");
                    setActiveCategory(null);
                    setSearch("");
                  }}
                />
                <PanelItem
                  icon={Wrench}
                  label={`${t.skills.toolsets} (${toolsets.length})`}
                  active={view === "toolsets"}
                  onClick={() => {
                    setView("toolsets");
                    setSearch("");
                  }}
                />
                <PanelItem
                  icon={Search}
                  label={t.skills?.browseHub ?? "Browse hub"}
                  active={view === "hub"}
                  onClick={() => {
                    setView("hub");
                    setSearch("");
                  }}
                />
              </div>

              {view === "skills" &&
                !isSearching &&
                allCategories.length > 0 && (
                  <div className="hidden sm:flex flex-col border-t border-border">
                    <div className="px-3 pt-2 pb-1 font-mondwest text-display text-xs tracking-[0.12em] text-text-tertiary">
                      {t.skills.categories}
                    </div>
                    <div className="flex flex-col p-2 pt-1 gap-px max-h-[calc(100vh-340px)] overflow-y-auto">
                      {allCategories.map(({ key, name, count }) => {
                        const isActive = activeCategory === key;

                        return (
                          <ListItem
                            key={key}
                            active={isActive}
                            onClick={() =>
                              setActiveCategory(isActive ? null : key)
                            }
                            className="rounded-none px-2 py-1 text-xs"
                          >
                            <span className="flex-1 truncate">{name}</span>
                            <span
                              className={`text-xs tabular-nums ${
                                isActive
                                  ? "text-text-secondary"
                                  : "text-text-tertiary"
                              }`}
                            >
                              {count}
                            </span>
                          </ListItem>
                        );
                      })}
                    </div>
                  </div>
                )}
            </div>
          </div>
        </aside>

        <div className="flex-1 min-w-0">
          {isSearching ? (
            <Card className="rounded-none">
              <CardHeader className="py-3 px-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Search className="h-4 w-4" />
                    {t.skills.title}
                  </CardTitle>
                  <Badge tone="secondary" className="text-xs">
                    {t.skills.resultCount
                      .replace("{count}", String(catalogSearchHits.length))
                      .replace(
                        "{s}",
                        catalogSearchHits.length !== 1 ? "s" : "",
                      )}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {catalogSearchHits.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    {t.skills.noCatalogMatch ??
                      t.skills.noSkillsMatch ??
                      "No matches."}
                  </p>
                ) : (
                  <CatalogHitSections
                    hits={catalogSearchHits}
                    defaultCollapsed={{}}
                    skillsI18n={t.skills}
                    common={t.common}
                    togglingSkills={togglingSkills}
                    onToggleSkill={handleToggleSkill}
                    onEditSkill={openEditEditor}
                    onConfigureToolset={setConfigToolset}
                    onToggleToolset={handleToggleToolset}
                    togglingToolsets={togglingToolsets}
                    noDescriptionLabel={t.skills.noDescription}
                    editSkillLabel={t.skills?.editSkillMd ?? "Edit SKILL.md"}
                    editAriaPrefix={t.skills?.editAria ?? "Edit"}
                    belongsToToolsetLabel={
                      t.skills.belongsToToolset ?? "Toolset"
                    }
                  />
                )}
              </CardContent>
            </Card>
          ) : view === "skills" ? (
            <Card className="rounded-none">
              <CardHeader className="py-3 px-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Package className="h-4 w-4" />
                    {activeCategory
                      ? prettyCategory(
                          activeCategory === "__none__" ? null : activeCategory,
                          t.common.general,
                        )
                      : t.skills.all}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge tone="secondary" className="text-xs">
                      {showUnifiedAll
                        ? t.skills.resultCount
                            .replace("{count}", String(catalogAllHits.length))
                            .replace(
                              "{s}",
                              catalogAllHits.length !== 1 ? "s" : "",
                            )
                        : t.skills.skillCount
                            .replace("{count}", String(activeSkills.length))
                            .replace(
                              "{s}",
                              activeSkills.length !== 1 ? "s" : "",
                            )}
                    </Badge>
                    <Button
                      size="xs"
                      outlined
                      className="uppercase"
                      onClick={openCreateEditor}
                      prefix={<Plus />}
                    >
                      {t.skills?.newSkill ?? "New skill"}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {showUnifiedAll ? (
                  catalogAllHits.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">
                      {t.skills.noCatalogMatch ?? t.skills.noSkills}
                    </p>
                  ) : (
                    <CatalogHitSections
                      hits={catalogAllHits}
                      hiddenSections={["toolset"]}
                      defaultCollapsed={{}}
                      skillsI18n={t.skills}
                      common={t.common}
                      togglingSkills={togglingSkills}
                      onToggleSkill={handleToggleSkill}
                      onEditSkill={openEditEditor}
                      onConfigureToolset={setConfigToolset}
                      onToggleToolset={handleToggleToolset}
                      togglingToolsets={togglingToolsets}
                      noDescriptionLabel={t.skills.noDescription}
                      editSkillLabel={t.skills?.editSkillMd ?? "Edit SKILL.md"}
                      editAriaPrefix={t.skills?.editAria ?? "Edit"}
                      belongsToToolsetLabel={
                        t.skills.belongsToToolset ?? "Toolset"
                      }
                    />
                  )
                ) : activeSkills.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    {skills.length === 0
                      ? t.skills.noSkills
                      : t.skills.noSkillsMatch}
                  </p>
                ) : (
                  <div className="grid gap-1">
                    {activeSkills.map((skill) => (
                      <SkillRow
                        key={skill.name}
                        skill={skill}
                        toggling={togglingSkills.has(skill.name)}
                        onToggle={() => handleToggleSkill(skill)}
                        onEdit={() => openEditEditor(skill.name)}
                        noDescriptionLabel={t.skills.noDescription}
                        editSkillLabel={t.skills?.editSkillMd ?? "Edit SKILL.md"}
                        editAriaPrefix={t.skills?.editAria ?? "Edit"}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : view === "toolsets" ? (
            /* Toolsets grid */
            <>
              {filteredToolsets.length === 0 ? (
                <Card className="rounded-none">
                  <CardContent className="py-8 text-center text-sm text-muted-foreground">
                    {t.skills.noToolsetsMatch}
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {filteredToolsets.map((ts) => {
                    const labelText = ts.label.trim() || ts.name;

                    return (
                      <Card key={ts.name} className="relative rounded-none">
                        <CardContent className="py-4">
                          <div className="flex items-start gap-3">
                            <div className="pt-0.5 shrink-0">
                              <Switch
                                checked={ts.enabled}
                                onCheckedChange={(v) =>
                                  handleToggleToolset(ts, v)
                                }
                                disabled={togglingToolsets.has(ts.name)}
                                aria-label={labelText}
                              />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="font-medium text-sm">
                                  {labelText}
                                </span>
                                <Badge
                                  tone={ts.enabled ? "success" : "outline"}
                                  className="text-xs"
                                >
                                  {ts.enabled
                                    ? t.common.active
                                    : t.common.inactive}
                                </Badge>
                              </div>
                              <p className="text-xs text-text-secondary mb-2">
                                {ts.description}
                              </p>
                              {ts.enabled && !ts.configured && (
                                <p className="text-xs text-amber-300 mb-2">
                                  {t.skills.setupNeeded}
                                </p>
                              )}
                              {ts.tools.length > 0 && (
                                <div className="flex flex-wrap gap-1">
                                  {ts.tools.map((tool) => (
                                    <Badge
                                      key={tool}
                                      tone="secondary"
                                      className="text-xs font-mono"
                                    >
                                      {tool}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                              {ts.tools.length === 0 && (
                                <span className="text-xs text-text-tertiary">
                                  {ts.enabled
                                    ? t.skills.toolsetLabel.replace(
                                        "{name}",
                                        ts.name,
                                      )
                                    : t.skills.disabledForCli}
                                </span>
                              )}
                              <div className="mt-3">
                                <Button
                                  size="xs"
                                  outlined
                                  onClick={() => setConfigToolset(ts)}
                                >
                                  <Wrench className="h-3 w-3 mr-1" />
                                  {t.skills?.configure ?? "Configure"}
                                </Button>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </>
          ) : (
            <HubBrowser showToast={showToast} profile={writeProfile} t={t} />
          )}
        </div>
      </div>
      {configToolset && (
        <ToolsetConfigDrawer
          toolset={configToolset}
          profile={writeProfile}
          onClose={() => setConfigToolset(null)}
          onChanged={() => void refreshToolsets()}
        />
      )}
      <SkillEditorDialog
        open={editorOpen}
        editName={editorSkill}
        profile={writeProfile}
        onClose={() => setEditorOpen(false)}
        onSaved={handleEditorSaved}
      />
      <PluginSlot name="skills:bottom" />
    </div>
  );
}

interface CatalogHitSectionsProps {
  hits: CatalogHit[];
  skillsI18n: Translations["skills"];
  common: Translations["common"];
  togglingSkills: Set<string>;
  onToggleSkill: (skill: SkillInfo) => void;
  onEditSkill: (name: string) => void;
  onConfigureToolset: (ts: ToolsetInfo) => void;
  onToggleToolset: (ts: ToolsetInfo, enabled: boolean, toolsetKey?: string) => void;
  togglingToolsets: Set<string>;
  noDescriptionLabel: string;
  editSkillLabel: string;
  editAriaPrefix: string;
  belongsToToolsetLabel: string;
  /** 初始折叠状态；搜索页应传空对象以全部展开。 */
  defaultCollapsed?: Partial<Record<CatalogHitKind, boolean>>;
  /** 不展示的分组（如「全部」页隐藏工具集，改在工具集 Tab 管理）。 */
  hiddenSections?: CatalogHitKind[];
}

function CatalogHitSections({
  hits,
  skillsI18n,
  common,
  togglingSkills,
  onToggleSkill,
  onEditSkill,
  onConfigureToolset,
  onToggleToolset,
  togglingToolsets,
  noDescriptionLabel,
  editSkillLabel,
  editAriaPrefix,
  belongsToToolsetLabel,
  defaultCollapsed = { tool: true },
  hiddenSections = [],
}: CatalogHitSectionsProps) {
  const hidden = new Set(hiddenSections);
  const [collapsed, setCollapsed] = useState<Partial<Record<CatalogHitKind, boolean>>>(
    () => ({ ...defaultCollapsed }),
  );

  const sections: { kind: CatalogHitKind; title: string; items: CatalogHit[] }[] = [
    {
      kind: "skill",
      title: skillsI18n.catalogSectionSkills ?? skillsI18n.searchKindSkill ?? "Skills",
      items: hits.filter((h) => h.kind === "skill"),
    },
    {
      kind: "toolset",
      title: skillsI18n.catalogSectionToolsets ?? skillsI18n.searchKindToolset ?? "Toolsets",
      items: hits.filter((h) => h.kind === "toolset"),
    },
    {
      kind: "tool",
      title: skillsI18n.catalogSectionTools ?? skillsI18n.searchKindTool ?? "Tools",
      items: hits.filter((h) => h.kind === "tool"),
    },
    {
      kind: "plugin_tool",
      title:
        skillsI18n.catalogSectionPluginTools ??
        skillsI18n.searchKindPluginTool ??
        "Plugin tools",
      items: hits.filter((h) => h.kind === "plugin_tool"),
    },
  ];

  const toggleSection = (kind: CatalogHitKind) => {
    setCollapsed((prev) => ({ ...prev, [kind]: !prev[kind] }));
  };

  const isSectionCollapsed = (kind: CatalogHitKind) => collapsed[kind] ?? false;

  return (
    <div className="flex flex-col gap-4">
      {sections.map((section) =>
        section.items.length === 0 || hidden.has(section.kind) ? null : (
          <div
            key={section.kind}
            className="border border-border rounded-none bg-muted/10"
          >
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-muted/40 transition-colors"
              aria-expanded={!isSectionCollapsed(section.kind)}
              onClick={() => toggleSection(section.kind)}
            >
              {isSectionCollapsed(section.kind) ? (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <span className="text-xs font-medium text-text-secondary uppercase tracking-wide">
                {section.title}
              </span>
              <Badge tone="secondary" className="text-xs">
                {section.items.length}
              </Badge>
            </button>
            {!isSectionCollapsed(section.kind) && (
              <div className="grid gap-1 px-1 pb-2">
                {section.items.map((hit) =>
                  hit.kind === "skill" && hit.skill ? (
                    <SkillRow
                      key={hit.id}
                      skill={hit.skill}
                      toggling={togglingSkills.has(hit.skill.name)}
                      onToggle={() => onToggleSkill(hit.skill!)}
                      onEdit={() => onEditSkill(hit.skill!.name)}
                      noDescriptionLabel={noDescriptionLabel}
                      editSkillLabel={editSkillLabel}
                      editAriaPrefix={editAriaPrefix}
                    />
                  ) : (
                    <CatalogSearchRow
                      key={hit.id}
                      hit={hit}
                      kindLabel={catalogHitKindLabel(hit.kind, skillsI18n)}
                      activeLabel={common.active}
                      inactiveLabel={common.inactive}
                      configureLabel={skillsI18n.configure ?? "Configure"}
                      belongsToToolsetLabel={belongsToToolsetLabel}
                      onConfigure={onConfigureToolset}
                      onToggleToolset={onToggleToolset}
                      toggling={togglingToolsets.has(catalogHitToggleKey(hit))}
                    />
                  ),
                )}
              </div>
            )}
          </div>
        ),
      )}
    </div>
  );
}

interface CatalogSearchRowProps {
  hit: CatalogHit;
  kindLabel: string;
  activeLabel: string;
  inactiveLabel: string;
  configureLabel: string;
  belongsToToolsetLabel: string;
  onConfigure: (ts: ToolsetInfo) => void;
  onToggleToolset: (ts: ToolsetInfo, enabled: boolean, toolsetKey?: string) => void;
  toggling: boolean;
}

function CatalogSearchRow({
  hit,
  kindLabel,
  activeLabel,
  inactiveLabel,
  configureLabel,
  belongsToToolsetLabel,
  onConfigure,
  onToggleToolset,
  toggling,
}: CatalogSearchRowProps) {
  const isCatalogTool = hit.kind === "tool" || hit.kind === "plugin_tool";
  const toggleToolset = hit.kind === "toolset" ? hit.toolset : undefined;
  const catalogToggleKey = isCatalogTool ? catalogHitToggleKey(hit) : undefined;
  const catalogToggleTs = isCatalogTool ? catalogHitToggleToolset(hit) : undefined;
  const TsIcon =
    toggleToolset || catalogToggleTs
      ? toolsetIcon((toggleToolset ?? catalogToggleTs)!.name)
      : Wrench;
  const canToggle = Boolean(toggleToolset) || isCatalogTool;
  const switchChecked = isCatalogTool
    ? hit.enabled ?? false
    : toggleToolset!.enabled;
  return (
    <div className="flex items-start gap-3 px-3 py-2.5 transition-colors hover:bg-muted/40">
      {canToggle ? (
        <div className="pt-0.5 shrink-0">
          <Switch
            checked={switchChecked}
            onCheckedChange={(v) => {
              if (hit.kind === "toolset" && toggleToolset) {
                onToggleToolset(toggleToolset, v);
              } else if (isCatalogTool && catalogToggleTs && catalogToggleKey) {
                onToggleToolset(
                  catalogToggleTs,
                  v,
                  catalogToggleKey !== catalogToggleTs.name
                    ? catalogToggleKey
                    : undefined,
                );
              }
            }}
            disabled={toggling}
            aria-label={hit.name}
          />
        </div>
      ) : (
        <TsIcon className="h-4 w-4 text-muted-foreground shrink-0 mt-1" />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-0.5">
          <span className="font-mono-ui text-sm text-foreground">{hit.name}</span>
          <Badge tone="secondary" className="text-xs">{kindLabel}</Badge>
          {switchChecked !== undefined && (
            <Badge
              tone={switchChecked ? "success" : "outline"}
              className="text-xs"
            >
              {switchChecked ? activeLabel : inactiveLabel}
            </Badge>
          )}
        </div>
        {isCatalogTool && (hit.associatedToolsetLabel || hit.associatedToolsetKey) ? (
          <p className="text-xs text-muted-foreground truncate">
            {belongsToToolsetLabel}:{" "}
            <span>{hit.associatedToolsetLabel ?? hit.associatedToolsetKey}</span>
            {hit.associatedToolsetKey &&
              hit.associatedToolsetLabel &&
              hit.associatedToolsetKey !== hit.associatedToolsetLabel && (
                <span className="font-mono-ui text-text-tertiary">
                  {" "}
                  ({hit.associatedToolsetKey})
                </span>
              )}
          </p>
        ) : hit.subtitle ? (
          <p className="text-xs text-muted-foreground truncate">{hit.subtitle}</p>
        ) : null}
        {isCatalogTool && hit.kind === "plugin_tool" && hit.subtitle && (
          <p className="text-xs text-text-tertiary truncate mt-0.5">
            {hit.subtitle}
          </p>
        )}
      </div>
      {hit.kind === "toolset" && hit.toolset && (
        <Button
          size="xs"
          outlined
          className="shrink-0"
          onClick={() => onConfigure(hit.toolset!)}
        >
          <Wrench className="h-3 w-3 mr-1" />
          {configureLabel}
        </Button>
      )}
    </div>
  );
}

function SkillRow({
  skill,
  toggling,
  onToggle,
  onEdit,
  noDescriptionLabel,
  editSkillLabel,
  editAriaPrefix,
}: SkillRowProps) {
  return (
    <div className="group flex items-start gap-3 px-3 py-2.5 transition-colors hover:bg-muted/40">
      <div className="pt-0.5 shrink-0">
        <Switch
          checked={skill.enabled}
          onCheckedChange={onToggle}
          disabled={toggling}
        />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span
            className={`font-mono-ui text-sm ${
              skill.enabled ? "text-foreground" : "text-muted-foreground"
            }`}
          >
            {skill.name}
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
          {skill.description || noDescriptionLabel}
        </p>
      </div>
      <Button
        ghost
        size="icon"
        className="shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:text-foreground"
        title={editSkillLabel}
        aria-label={`${editAriaPrefix} ${skill.name}`}
        onClick={onEdit}
      >
        <Pencil />
      </Button>
    </div>
  );
}

function PanelItem({ active, icon: Icon, label, onClick }: PanelItemProps) {
  return (
    <ListItem
      active={active}
      onClick={onClick}
      className={cn(
        "rounded-none whitespace-nowrap px-2.5 py-1.5",
        "font-mondwest text-[0.7rem] tracking-[0.08em] uppercase",
        active && "bg-foreground/90 text-background hover:text-background",
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span className="flex-1 truncate">{label}</span>
    </ListItem>
  );
}

interface PanelItemProps {
  active: boolean;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
}

interface SkillRowProps {
  noDescriptionLabel: string;
  editSkillLabel: string;
  editAriaPrefix: string;
  onToggle: () => void;
  onEdit: () => void;
  skill: SkillInfo;
  toggling: boolean;
}

/* ------------------------------------------------------------------ */
/*  Hub browser -- search the skill hub, preview, scan, install        */
/* ------------------------------------------------------------------ */

/** Map a trust level to a Badge tone + label. */
function trustVisual(
  level: string,
  labels: { trusted: string; builtin: string; community: string; unknown: string },
): {
  tone: "success" | "secondary" | "warning" | "outline";
  label: string;
} {
  switch (level) {
    case "trusted":
      return { tone: "success", label: labels.trusted };
    case "builtin":
      return { tone: "secondary", label: labels.builtin };
    case "community":
      return { tone: "warning", label: labels.community };
    default:
      return { tone: "outline", label: level || labels.unknown };
  }
}

/** Map a scan verdict to tone + icon + label. */
function verdictVisual(
  verdict: string,
  labels: { safe: string; caution: string; dangerous: string },
): {
  tone: "success" | "warning" | "destructive";
  Icon: React.ComponentType<{ className?: string }>;
  label: string;
} {
  switch (verdict) {
    case "safe":
      return { tone: "success", Icon: ShieldCheck, label: labels.safe };
    case "caution":
      return { tone: "warning", Icon: ShieldAlert, label: labels.caution };
    case "dangerous":
      return { tone: "destructive", Icon: ShieldAlert, label: labels.dangerous };
    default:
      return { tone: "warning", Icon: ShieldQuestion, label: verdict };
  }
}

const SEVERITY_TONE: Record<string, "destructive" | "warning" | "secondary" | "outline"> = {
  critical: "destructive",
  high: "destructive",
  medium: "warning",
  low: "secondary",
};

function HubBrowser({
  showToast,
  profile,
  t,
}: {
  showToast: (msg: string, kind: "success" | "error") => void;
  /** Optional profile scoping installs + installed-state badges. */
  profile?: string;
  t: ReturnType<typeof useI18n>["t"];
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SkillHubResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({});
  const [timedOut, setTimedOut] = useState<string[]>([]);
  const [searchMs, setSearchMs] = useState<number | null>(null);

  // Landing state: which hubs are wired up + featured skills.
  const [sources, setSources] = useState<SkillHubSource[]>([]);
  const [featured, setFeatured] = useState<SkillHubResult[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);

  // identifier -> installed entry (drives "Installed" badges).
  const [installed, setInstalled] = useState<Record<string, SkillHubInstalledEntry>>({});

  // Live action log for the most recent install/update.
  const [action, setAction] = useState<string | null>(null);
  const [actionLog, setActionLog] = useState<string[]>([]);
  const [actionRunning, setActionRunning] = useState(false);

  // Detail dialog (preview + scan for a single skill).
  const [detail, setDetail] = useState<SkillHubResult | null>(null);

  /* ---- Load connected hubs + featured skills on mount ---- */
  useEffect(() => {
    let cancelled = false;
    api
      .getSkillHubSources(profile)
      .then((r) => {
        if (cancelled) return;
        setSources(r.sources);
        setFeatured(r.featured);
        setInstalled(r.installed);
      })
      .catch(() => {
        /* leave landing minimal on failure */
      })
      .finally(() => {
        if (!cancelled) setSourcesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [profile]);

  /* ---- Search ---- */
  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setSearched(true);
    const t0 = performance.now();
    try {
      const r = await api.searchSkillsHub(q, "all", 20, profile);
      setResults(r.results);
      setSourceCounts(r.source_counts || {});
      setTimedOut(r.timed_out || []);
      setInstalled((prev) => ({ ...prev, ...(r.installed || {}) }));
    } catch (e) {
      showToast(
        (t.skills?.hubSearchFailed ?? "Hub search failed: {error}").replace("{error}", String(e)),
        "error",
      );
      setResults([]);
      setSourceCounts({});
      setTimedOut([]);
    } finally {
      setSearchMs(Math.round(performance.now() - t0));
      setSearching(false);
    }
  }, [query, showToast, profile, t]);

  /* ---- Poll a spawned action's log until it exits ---- */
  useEffect(() => {
    if (!action) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      try {
        const st = await api.getActionStatus(action, 200);
        if (cancelled) return;
        setActionLog(st.lines);
        setActionRunning(st.running);
        if (st.running) {
          timer = setTimeout(poll, 1200);
        } else {
          // Install finished -- refresh installed-state so badges update.
          api
            .getSkillHubSources(profile)
            .then((r) => !cancelled && setInstalled(r.installed))
            .catch(() => {});
        }
      } catch {
        if (!cancelled) setActionRunning(false);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [action, profile]);

  const install = useCallback(
    async (identifier: string) => {
      try {
        const res = await api.installSkillFromHub(identifier, profile);
        showToast(
          (t.skills?.installingSkill ?? "Installing {identifier}...").replace("{identifier}", identifier),
          "success",
        );
        setActionLog([]);
        setActionRunning(true);
        setAction(res.name);
        setDetail(null);
      } catch (e) {
        showToast(
          (t.skills?.installFailed ?? "Install failed: {error}").replace("{error}", String(e)),
          "error",
        );
      }
    },
    [showToast, profile, t],
  );

  const updateAll = useCallback(async () => {
    try {
      const res = await api.updateSkillsFromHub(profile);
      showToast(t.skills?.updatingSkills ?? "Updating installed skills...", "success");
      setActionLog([]);
      setActionRunning(true);
      setAction(res.name);
    } catch (e) {
      showToast(
        (t.skills?.updateFailed ?? "Update failed: {error}").replace("{error}", String(e)),
        "error",
      );
    }
  }, [showToast, profile, t]);

  const isInstalled = useCallback(
    (identifier: string) => Boolean(installed[identifier]),
    [installed],
  );

  const showLanding = !searched && !searching;

  return (
    <div className="flex flex-col gap-3">
      {/* -- Search bar -- */}
      <Card className="rounded-none">
        <CardContent className="py-4 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                className="h-8 pl-8 text-sm"
                placeholder={t.skills?.hubSearchPlaceholder ?? "Search the skill hub (GitHub, official, community)..."}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runSearch();
                }}
              />
            </div>
            <Button
              size="sm"
              onClick={() => void runSearch()}
              disabled={searching || !query.trim()}
              prefix={searching ? <Spinner /> : <Search className="h-3.5 w-3.5" />}
            >
              {t.skills?.search ?? t.common.search.replace("...", "")}
            </Button>
            <Button
              size="sm"
              outlined
              onClick={() => void updateAll()}
              prefix={<RefreshCw className="h-3.5 w-3.5" />}
            >
              {t.skills?.updateAll ?? "Update all"}
            </Button>
          </div>

          {/* Connected hubs strip -- proves the tab is wired up. */}
          <ConnectedHubs sources={sources} loading={sourcesLoading} t={t} />
        </CardContent>
      </Card>

      {/* -- Install/update action log -- */}
      {action && (
        <Card className="rounded-none">
          <CardContent className="py-3">
            <div className="flex items-center gap-2 mb-2">
              <Download className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="font-mono text-xs">{action}</span>
              {actionRunning ? (
                <Badge tone="warning">{t.skills?.actionRunning ?? "running"}</Badge>
              ) : (
                <Badge tone="success">{t.skills?.actionDone ?? "done"}</Badge>
              )}
              {!actionRunning && (
                <Button
                  ghost
                  size="xs"
                  className="ml-auto text-muted-foreground"
                  onClick={() => setAction(null)}
                  aria-label={t.skills?.dismiss ?? "Dismiss"}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words bg-background/50 border border-border p-2 text-xs font-mono text-muted-foreground">
              {actionLog.length ? actionLog.join("\n") : (t.skills?.actionStarting ?? "Starting...")}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* -- Landing: featured skills (before any search) -- */}
      {showLanding && (
        <>
          {sourcesLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spinner className="text-xl text-primary" />
            </div>
          ) : featured.length > 0 ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 px-1">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                <span className="font-mondwest text-display text-xs tracking-[0.12em] text-text-secondary uppercase">
                  {t.skills?.featuredSkills ?? "Featured skills"}
                </span>
                <span className="text-xs text-text-tertiary">
                  {t.skills?.featuredSubtitle ?? "from the Hermes index - search above for thousands more"}
                </span>
              </div>
              {featured.map((r) => (
                <HubResultCard
                  key={r.identifier}
                  result={r}
                  installed={isInstalled(r.identifier)}
                  onOpen={() => setDetail(r)}
                  onInstall={() => void install(r.identifier)}
                  t={t}
                />
              ))}
            </div>
          ) : (
            <Card className="rounded-none">
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                {t.skills?.hubEmptyLanding ?? "Search the hub above to browse installable skills from the connected sources."}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* -- Searching spinner -- */}
      {searching && (
        <div className="flex items-center justify-center py-8">
          <Spinner className="text-xl text-primary" />
        </div>
      )}

      {/* -- Search results -- */}
      {!searching && searched && (
        <>
          <SearchMeta
            count={results.length}
            sourceCounts={sourceCounts}
            timedOut={timedOut}
            ms={searchMs}
            t={t}
          />
          {results.length === 0 ? (
            <Card className="rounded-none">
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                {t.skills?.noHubResults ?? "No matching skills found in the hub."}
              </CardContent>
            </Card>
          ) : (
            results.map((r) => (
              <HubResultCard
                key={r.identifier}
                result={r}
                installed={isInstalled(r.identifier)}
                onOpen={() => setDetail(r)}
                onInstall={() => void install(r.identifier)}
                t={t}
              />
            ))
          )}
        </>
      )}

      {/* -- Detail dialog: preview + scan -- */}
      {detail && (
        <SkillDetailDialog
          result={detail}
          installed={isInstalled(detail.identifier)}
          onClose={() => setDetail(null)}
          onInstall={() => void install(detail.identifier)}
          showToast={showToast}
          t={t}
        />
      )}
    </div>
  );
}

/* ---- Connected hubs strip ---- */
function ConnectedHubs({
  sources,
  loading,
  t,
}: {
  sources: SkillHubSource[];
  loading: boolean;
  t: ReturnType<typeof useI18n>["t"];
}) {
  if (loading) {
    return (
      <p className="text-xs text-muted-foreground">
        {t.skills?.connectingHubs ?? "Connecting to skill hubs..."}
      </p>
    );
  }
  if (sources.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        {t.skills?.hubSourcesFallback ?? "Results come from the same sources as"}{" "}
        <span className="font-mono">hermes skills search</span>.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="flex items-center gap-1 text-xs text-text-tertiary">
        <Globe className="h-3 w-3" />
        {t.skills?.connectedHubs ?? "Connected hubs:"}
      </span>
      {sources.map((s) => {
        const down =
          (s.id === "hermes-index" && s.available === false) ||
          (s.id === "github" && s.rate_limited === true);
        return (
          <Badge
            key={s.id}
            tone={down ? "outline" : "secondary"}
            className={cn("text-xs", down && "opacity-60")}
            title={
              s.id === "github" && s.rate_limited
                ? (t.skills?.githubRateLimitedTitle ?? "GitHub API rate-limited - set GITHUB_TOKEN to raise the limit")
                : s.id === "hermes-index" && s.available === false
                  ? (t.skills?.hermesIndexUnavailableTitle ?? "Centralized index unavailable - falling back to live sources")
                  : undefined
            }
          >
            {s.label}
            {s.id === "github" && s.rate_limited
              ? ` (${t.skills?.rateLimited ?? "rate-limited"})`
              : ""}
          </Badge>
        );
      })}
    </div>
  );
}

/* ---- Search result-count + per-source breakdown ---- */
function SearchMeta({
  count,
  sourceCounts,
  timedOut,
  ms,
  t,
}: {
  count: number;
  sourceCounts: Record<string, number>;
  timedOut: string[];
  ms: number | null;
  t: ReturnType<typeof useI18n>["t"];
}) {
  const entries = Object.entries(sourceCounts).filter(([, n]) => n > 0);
  return (
    <div className="flex flex-wrap items-center gap-2 px-1 text-xs text-text-tertiary">
      <Badge tone="secondary" className="text-xs">
        {(t.skills?.hubResultCount ?? "{count} result{s}")
          .replace("{count}", String(count))
          .replace("{s}", count !== 1 ? "s" : "")}
      </Badge>
      {ms != null && <span>{(ms / 1000).toFixed(1)}s</span>}
      {entries.length > 0 && (
        <span className="flex flex-wrap items-center gap-1.5">
          {entries.map(([sid, n]) => (
            <span key={sid} className="font-mono">
              {sid}:{n}
            </span>
          ))}
        </span>
      )}
      {timedOut.length > 0 && (
        <span className="flex items-center gap-1 text-amber-400">
          <AlertTriangle className="h-3 w-3" />
          {timedOut.join(", ")}{" "}
          {t.skills?.timedOut ?? "timed out"}
        </span>
      )}
    </div>
  );
}

/* ---- One result card ---- */
function HubResultCard({
  result,
  installed,
  onOpen,
  onInstall,
  t,
}: {
  result: SkillHubResult;
  installed: boolean;
  onOpen: () => void;
  onInstall: () => void;
  t: ReturnType<typeof useI18n>["t"];
}) {
  const trust = trustVisual(result.trust_level, {
    trusted: t.skills?.trustTrusted ?? "trusted",
    builtin: t.skills?.trustBuiltin ?? "builtin",
    community: t.skills?.trustCommunity ?? "community",
    unknown: t.common.unknown,
  });
  return (
    <Card className="rounded-none transition-colors hover:bg-muted/30">
      <CardContent className="py-3 flex items-start gap-3">
        <button
          type="button"
          className="flex-1 min-w-0 text-left"
          onClick={onOpen}
          aria-label={`${t.skills?.openSkill ?? "Open"} ${result.name}`}
        >
          <div className="flex flex-wrap items-center gap-2 mb-0.5">
            <span className="font-mono-ui text-sm hover:underline">
              {result.name}
            </span>
            <Badge tone={trust.tone} className="text-xs">
              {trust.label}
            </Badge>
            <Badge tone="secondary" className="text-xs">
              {result.source}
            </Badge>
            {installed && (
              <Badge tone="success" className="text-xs">
                {t.skills?.installedBadge ?? "installed"}
              </Badge>
            )}
          </div>
          <p className="text-xs text-text-secondary line-clamp-2">
            {result.description}
          </p>
          <div className="flex flex-wrap items-center gap-1 mt-1">
            {result.tags.slice(0, 5).map((tag) => (
              <span
                key={tag}
                className="text-[0.65rem] font-mono text-text-tertiary border border-border px-1 py-px"
              >
                {tag}
              </span>
            ))}
          </div>
          <p className="text-xs font-mono text-text-tertiary truncate mt-1">
            {result.identifier}
          </p>
        </button>
        <div className="flex shrink-0 flex-col gap-1.5">
          <Button
            size="sm"
            outlined
            onClick={onOpen}
            prefix={<FileText className="h-3.5 w-3.5" />}
          >
            {t.skills?.details ?? "Details"}
          </Button>
          {installed ? (
            <Button size="sm" ghost disabled prefix={<CheckCircle2 className="h-3.5 w-3.5" />}>
              {t.skills?.installedButton ?? "Installed"}
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={onInstall}
              prefix={<Download className="h-3.5 w-3.5" />}
            >
              {t.skills?.installButton ?? "Install"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/* ---- Detail dialog: SKILL.md preview + on-demand security scan ---- */
function SkillDetailDialog({
  result,
  installed,
  onClose,
  onInstall,
  showToast,
  t,
}: {
  result: SkillHubResult;
  installed: boolean;
  onClose: () => void;
  onInstall: () => void;
  showToast: (msg: string, kind: "success" | "error") => void;
  t: ReturnType<typeof useI18n>["t"];
}) {
  const [tab, setTab] = useState<"readme" | "scan">("readme");
  const [preview, setPreview] = useState<SkillHubPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [scan, setScan] = useState<SkillHubScan | null>(null);
  const [scanning, setScanning] = useState(false);
  const trust = trustVisual(result.trust_level, {
    trusted: t.skills?.trustTrusted ?? "trusted",
    builtin: t.skills?.trustBuiltin ?? "builtin",
    community: t.skills?.trustCommunity ?? "community",
    unknown: t.common.unknown,
  });

  useEffect(() => {
    let cancelled = false;
    setPreviewLoading(true);
    api
      .previewSkillFromHub(result.identifier)
      .then((p) => !cancelled && setPreview(p))
      .catch((e) => {
        if (!cancelled)
          showToast(
            (t.skills?.previewFailed ?? "Preview failed: {error}").replace("{error}", String(e)),
            "error",
          );
      })
      .finally(() => !cancelled && setPreviewLoading(false));
    return () => {
      cancelled = true;
    };
  }, [result.identifier, showToast, t]);

  const runScan = useCallback(async () => {
    setScanning(true);
    setTab("scan");
    try {
      const s = await api.scanSkillFromHub(result.identifier);
      setScan(s);
    } catch (e) {
      showToast(
        (t.skills?.scanFailed ?? "Scan failed: {error}").replace("{error}", String(e)),
        "error",
      );
    } finally {
      setScanning(false);
    }
  }, [result.identifier, showToast, t]);

  return (
    <Dialog open onOpenChange={(o: boolean) => !o && onClose()}>
      <DialogContent className="max-w-3xl rounded-none">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2 text-sm">
            <Package className="h-4 w-4" />
            {result.name}
            <Badge tone={trust.tone} className="text-xs">
              {trust.label}
            </Badge>
            <Badge tone="secondary" className="text-xs">
              {result.source}
            </Badge>
            {installed && (
              <Badge tone="success" className="text-xs">
                {t.skills?.installedBadge ?? "installed"}
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {(t.skills?.detailDialogDescription ?? "Preview the SKILL.md source and run a security scan for {name} before installing.")
              .replace("{name}", result.name)}
          </DialogDescription>
        </DialogHeader>

        <div className="mt-1 flex flex-col gap-1">
          <p className="text-xs text-text-secondary">{result.description}</p>
          <p className="text-xs font-mono text-text-tertiary truncate">
            {result.identifier}
          </p>
        </div>

        {/* Action row */}
        <div className="mt-3 flex flex-wrap items-center gap-2 border-y border-border py-2.5">
          <Button
            size="sm"
            outlined={tab !== "readme"}
            onClick={() => setTab("readme")}
            prefix={<FileText className="h-3.5 w-3.5" />}
          >
            {t.skills?.readSkillMd ?? "Read SKILL.md"}
          </Button>
          <Button
            size="sm"
            outlined={tab !== "scan"}
            onClick={() => void runScan()}
            disabled={scanning}
            prefix={
              scanning ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Shield className="h-3.5 w-3.5" />
              )
            }
          >
            {scan
              ? (t.skills?.rescan ?? "Re-scan")
              : (t.skills?.securityScan ?? "Security scan")}
          </Button>
          <div className="ml-auto flex items-center gap-3">
            {result.repo && (
              <a
                href={`https://github.com/${result.repo}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                {result.repo}
              </a>
            )}
            {installed ? (
              <Button size="sm" ghost disabled prefix={<CheckCircle2 className="h-3.5 w-3.5" />}>
                {t.skills?.installedButton ?? "Installed"}
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={onInstall}
                prefix={<Download className="h-3.5 w-3.5" />}
              >
                {t.skills?.installButton ?? "Install"}
              </Button>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="mt-3 max-h-[55vh] overflow-auto">
          {tab === "readme" ? (
            previewLoading ? (
              <div className="flex items-center justify-center py-12">
                <Spinner className="text-xl text-primary" />
              </div>
            ) : preview ? (
              <div className="flex flex-col gap-2.5">
                {preview.tags.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1">
                    {preview.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-[0.65rem] font-mono text-text-tertiary border border-border px-1 py-px"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                {preview.files.length > 0 && (
                  <div className="text-xs text-text-tertiary">
                    <span className="font-mondwest tracking-[0.1em] uppercase">
                      {t.skills?.filesLabel ?? "Files:"}{" "}
                    </span>
                    <span className="font-mono">{preview.files.join("  ")}</span>
                  </div>
                )}
                <pre className="whitespace-pre-wrap break-words bg-background/50 border border-border p-3 text-xs font-mono text-text-secondary leading-relaxed">
                  {(preview.skill_md || "").trim() || (t.skills?.skillMdEmpty ?? "(SKILL.md is empty)")}
                </pre>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-10">
                {t.skills?.previewLoadFailed ?? "Couldn't load the skill source."}
              </p>
            )
          ) : (
            <ScanPanel scan={scan} scanning={scanning} t={t} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ---- Visual security-scan result ---- */
function ScanPanel({
  scan,
  scanning,
  t,
}: {
  scan: SkillHubScan | null;
  scanning: boolean;
  t: ReturnType<typeof useI18n>["t"];
}) {
  if (scanning && !scan) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-12">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <span className="text-xs text-muted-foreground">
          {t.skills?.scanningMessage ?? "Fetching, quarantining, and scanning..."}
        </span>
      </div>
    );
  }
  if (!scan) {
    return (
      <p className="text-sm text-muted-foreground text-center py-10">
        {t.skills?.scanPrompt ?? "Run a security scan to inspect this skill for risky patterns before installing."}
      </p>
    );
  }

  const verdictLabels = {
    safe: t.skills?.verdictSafe ?? "Safe",
    caution: t.skills?.verdictCaution ?? "Caution",
    dangerous: t.skills?.verdictDangerous ?? "Dangerous",
  };
  const v = verdictVisual(scan.verdict, verdictLabels);

  const policyTone =
    scan.policy === "allow"
      ? "success"
      : scan.policy === "ask"
        ? "warning"
        : "destructive";
  const policyLabel =
    scan.policy === "allow"
      ? (t.skills?.policyAllow ?? "Install allowed")
      : scan.policy === "ask"
        ? (t.skills?.policyAsk ?? "Needs confirmation")
        : (t.skills?.policyBlock ?? "Install blocked");

  return (
    <div className="flex flex-col gap-3">
      {/* Verdict header */}
      <div className="flex flex-wrap items-center gap-2 border border-border p-3">
        <v.Icon
          className={cn(
            "h-6 w-6",
            scan.verdict === "safe"
              ? "text-emerald-400"
              : scan.verdict === "dangerous"
                ? "text-red-400"
                : "text-amber-400",
          )}
        />
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">
              {(t.skills?.verdictLabel ?? "Verdict: {label}").replace("{label}", v.label)}
            </span>
            <Badge tone={v.tone} className="text-xs">
              {scan.verdict}
            </Badge>
          </div>
          <span className="text-xs text-text-tertiary">
            {(t.skills?.scanSummary ?? "{trust_level} source · {count} finding{s}")
              .replace("{trust_level}", scan.trust_level)
              .replace("{count}", String(scan.findings.length))
              .replace("{s}", scan.findings.length !== 1 ? "s" : "")}
          </span>
        </div>
        <Badge tone={policyTone} className="ml-auto text-xs">
          {policyLabel}
        </Badge>
      </div>

      {/* Severity tally */}
      <div className="flex flex-wrap items-center gap-1.5">
        {(["critical", "high", "medium", "low"] as const).map((sev) => {
          const n = scan.severity_counts[sev] || 0;
          if (n === 0) return null;
          return (
            <Badge key={sev} tone={SEVERITY_TONE[sev]} className="text-xs">
              {n} {sev}
            </Badge>
          );
        })}
        {scan.findings.length === 0 && (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <CheckCircle2 className="h-3.5 w-3.5" />
            {t.skills?.noRiskyPatterns ?? "No risky patterns detected"}
          </span>
        )}
      </div>

      <p className="text-xs text-text-tertiary">{scan.policy_reason}</p>

      {/* Findings */}
      {scan.findings.length > 0 && (
        <div className="flex flex-col border border-border divide-y divide-border">
          {scan.findings.map((f, i) => (
            <div key={i} className="flex items-start gap-2 p-2">
              <Badge tone={SEVERITY_TONE[f.severity] || "outline"} className="text-xs shrink-0">
                {f.severity}
              </Badge>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium">{f.category}</span>
                  <span className="text-xs font-mono text-text-tertiary truncate">
                    {f.file}:{f.line}
                  </span>
                </div>
                <p className="text-xs text-text-secondary">{f.description}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
