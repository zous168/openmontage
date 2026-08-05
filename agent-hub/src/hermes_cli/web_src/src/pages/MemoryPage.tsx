import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bot,
  Brain,
  Layers,
  MessageSquare,
  RefreshCw,
  Settings2,
  User,
  Wrench,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Label } from "@nous-research/ui/ui/components/label";
import { Segmented } from "@nous-research/ui/ui/components/segmented";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { MemorySettingsDialog } from "@/components/MemorySettingsDialog";
import { usePageHeader } from "@/contexts/usePageHeader";
import { useProfileScope } from "@/contexts/useProfileScope";
import { useI18n } from "@/i18n";
import type { Translations } from "@/i18n/types";
import { api } from "@/lib/api";
import type {
  MemoryCompressionChainResponse,
  MemoryProfileEntity,
  MemoryProfileFact,
  MemoryProfileOverview,
  MemoryProfileSessionMessage,
  MemoryProfileSessionSummary,
  MemoryProfileSettings,
  MemoryRetrieveFactHit,
  MemoryRetrieveTestResponse,
} from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

const ALL_CATEGORIES = "__all__";

const SESSIONS_PAGE_SIZE = 15;

const MEMORY_TEXT: NonNullable<Translations["memoryPage"]> = {
  title: "Memory",
  subtitle: "Profile-scoped agent memory · Markdown + holographic facts",
  readOnlyHint: "Read-only · follows Profile switcher above (Profile data)",
    tabFacts: "Holographic facts",
    tabFactsScope: "Profile-wide fact store (memory_store.db), shared by all sessions",
  tabMarkdown: "Markdown",
    tabSessions: "Sessions",
    sessionsSplitOverview:
      "Session history (state.db) is per conversation. Holographic prefetch runs on each user turn inside a session; the fact store (memory_store.db) is shared across all sessions in this Profile.",
    sessionHistoryTitle: "Session history",
    sessionHistoryHint:
      "Read-only chat transcripts for this Profile. Sent to the LLM as conversation history — not searched as a memory store.",
    sessionHistorySource: "Source: {Profile}/state.db",
    sessionTranscriptTitle: "Conversation history",
    sessionTranscriptHint: "Read-only · sent to the LLM as messages[]",
    sessionHistoryPickMessage: "Transcript above is read-only for reference.",
    holographicMemoryTitle: "This session · turn prefetch",
    holographicMemoryHint:
      "Simulates memory load for a new user turn in the selected session. Facts come from the Profile-wide store.",
    holographicMemorySource: "Prefetch sources: memories/MEMORY.md · USER.md · memory_store.db (Profile-wide)",
    holographicMemoryEmpty: "Select a session, then enter a new user message below.",
    holographicMemoryScopeNote:
      "Fact library is Profile-wide; prefetch is triggered per user message within a session.",
    retrieveSessionContext: "Session",
    clickUserForRetrieve: "Simulate this turn",
    sessionsHint: "Agent session transcripts for the active profile (read-only)",
  sessionsEmpty: "No sessions yet.",
  sessionsSelect: "Select a session on the left",
  sessionsLoadMore: "Load more",
  paginationPrev: "Prev",
  paginationNext: "Next",
  paginationStatus: "{total} total · page {page} / {pages}",
  sessionActive: "Active",
  sessionCompressedBadge: "Compacted #{n}",
  compressionChainTitle: "Compaction lineage · {n} generations",
  compressionChainHint:
    "This conversation was context-compacted. Each generation is a forked snapshot; the summary is handed to the model as background reference.",
  compressionChainGen: "Gen #{n}",
  compressionChainRoot: "Original",
  compressionChainTip: "Live",
  compressionChainCurrent: "Viewing",
  compressionChainOpen: "Open",
  compressionChainShowSummary: "Show summary",
  compressionChainHideSummary: "Hide summary",
  roleUser: "User",
  roleAssistant: "Assistant",
  roleSystem: "System",
  roleTool: "Tool",
  provider: "Engine",
  statFacts: "Facts",
  statEntities: "Entities",
  statMemoryMd: "MEMORY.md entries",
  statUserMd: "USER.md entries",
  noStore: "No memory_store.db yet — enable holographic and write via fact_store.",
  noFacts: "No facts in this category.",
  colId: "#",
  colContent: "Content",
  colCategory: "Category",
  colTrust: "Trust",
  colUpdated: "Updated",
  filterAll: "All categories",
  totalFacts: "{total} facts",
  memoryMdTitle: "MEMORY.md (agent notes)",
  userMdTitle: "USER.md (user profile)",
  routingHint:
    "System rules: USER = language/name/tone; business, rules, projects → MEMORY.",
  noEntries: "No entries",
  loadFailed: "Failed to load memory",
  refresh: "Refresh",
  tabRetrieve: "Retrieval test",
  retrieveTitle: "Simulate agent memory retrieval",
  retrieveHint:
    "Select a session and enter a new user message to simulate prefetch using current profile config.",
  retrieveQueryLabel: "New user message (this turn)",
  retrieveQueryPlaceholder: "e.g. What are the Douyin comment rules?",
  retrieveClickUserMessage: "Enter a new user message below to run retrieval test",
  retrieveNoUserMessages: "No user messages in this session.",
  retrieveSelectedSession: "Session",
  retrieveEntityLabel: "Entity probe (optional)",
  retrieveEntityPlaceholder: "e.g. Douyin",
  retrieveEntitiesLabel: "Multi-entity reason (optional)",
  retrieveEntitiesPlaceholder: "e.g. Douyin, comment",
  entityPickerLabel: "Known entities",
  entityPickerHint: "Click entity → open session tab and prefill retrieval test message",
  entityFactCount: "{count} linked facts",
  noEntities: "No entities in the store yet.",
  entityNoiseTag: "noise",
  entityNoiseHint: "Auto-extracted but unsuitable for probe/reason.",
  statEntitiesBreakdown: "({usable} usable · {noise} noise)",
  purgeNoiseEntities: "Purge noise entities",
  purgeNoiseRunning: "Purging…",
  purgeNoiseDone: "Removed {count} noise entities",
  markdownTransientTag: "transient",
  markdownTransientHint: "Tool/shell debug — pollutes every session prompt",
  purgeTransientMarkdown: "Purge transient MEMORY entries",
  purgeTransientRunning: "Purging…",
  statMemoryMdTransient: "{count} transient",
  retrieveRun: "Run retrieval",
  retrieveRunning: "Retrieving…",
  retrievePresets: "Scenario presets",
  presetLanguage: "Language / tone",
  presetBusiness: "Business rules",
  presetProject: "Project info",
  presetEnv: "Environment / tools",
  sectionSessionStart: "Session start · system prompt",
  simulateSystemPromptTitle: "System prompt",
  simulateSystemPromptHint:
    "Sent as role=system: MEMORY.md, USER.md, and holographic meta block (no specific facts).",
  simulateUserMessagesTitle: "User messages (messages[])",
  simulateUserMessagesHint:
    "Prior turns from state.db plus this turn's user message (prefetch appended via memory-context).",
  sectionConversationHistory: "Prior turns",
  sectionSimulatedTurn: "This turn · API user message",
  sectionTurnPrefetch: "Prefetch detail",
  holographicSystemLabel: "Holographic · system meta block",
  noConversationHistory: "No prior messages in this session.",
  messagesMarkdownLabel: "messages[] · Markdown",
  prefetchInjectionLabel: "prefetch injection",
  sectionFactSearch: "fact_store · search",
  sectionFactProbe: "fact_store · probe",
  sectionFactReason: "fact_store · reason",
  sectionMarkdownHints: "Markdown relevance (diagnostic)",
  colScore: "Score",
  colTarget: "Target",
  noPrefetch: "No prefetch hits.",
  noSearchHits: "No search hits.",
  noProbeHits: "No probe hits.",
  noReasonHits: "No reason hits.",
  noMarkdownHints: "No related Markdown entries.",
  scenarioNoteLabel: "Note",
  injectContentLabel: "Injected content",
  retrieveResultLabel: "Retrieval result",
  matchedFactsLabel: "Matched facts",
  sectionMarkdownHintsNote: "Diagnostic only — not injected into the agent prompt.",
  blockPreview: "Injected block",
  configTitle: "Active memory config",
  configHint: "From config.yaml for this Profile. Retrieval tests use the same settings.",
  configEditLink: "Settings",
  configMemoryEnabled: "Inject MEMORY.md",
  configUserEnabled: "Inject USER.md",
  configMemoryLimit: "MEMORY budget",
  configUserLimit: "USER budget",
  configPrefetchLimit: "Prefetch facts / turn",
  configProvider: "Provider",
  configChars: "{n} chars",
  configEnabled: "On",
  configDisabled: "Off",
  configAppliedHint: "Simulated with current profile config",
  retrieveSectionTitle: "Retrieval test",
  retrieveSectionHint:
    "Results split into system prompt vs user messages — same layout as the LLM API request.",
};

function configEnabledLabel(on: boolean, mT: NonNullable<Translations["memoryPage"]>): string {
  return on ? (mT.configEnabled ?? "On") : (mT.configDisabled ?? "Off");
}

function MemoryConfigStatusCard({
  settings,
  providerLabel,
  mT,
  onEdit,
}: {
  settings: MemoryProfileSettings;
  providerLabel: string;
  mT: NonNullable<Translations["memoryPage"]>;
  onEdit?: () => void;
}) {
  const holo = settings.provider === "holographic";
  const items: { label: string; value: string }[] = [
    { label: mT.configProvider, value: providerLabel },
    { label: mT.configMemoryEnabled, value: configEnabledLabel(settings.memory_enabled, mT) },
    { label: mT.configUserEnabled, value: configEnabledLabel(settings.user_profile_enabled, mT) },
    {
      label: mT.configMemoryLimit,
      value: (mT.configChars ?? "{n} chars").replace("{n}", String(settings.memory_char_limit)),
    },
    {
      label: mT.configUserLimit,
      value: (mT.configChars ?? "{n} chars").replace("{n}", String(settings.user_char_limit)),
    },
  ];
  if (holo) {
    items.push({
      label: mT.configPrefetchLimit,
      value: String(settings.prefetch_limit),
    });
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            {mT.configTitle}
          </CardTitle>
          {onEdit ? (
            <Button outlined size="sm" type="button" onClick={onEdit}>
              {mT.configEditLink}
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-muted-foreground text-xs">{mT.configHint}</p>
        <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          {items.map((item) => (
            <div key={item.label} className="rounded-md border bg-muted/10 px-3 py-2">
              <dt className="text-muted-foreground text-xs">{item.label}</dt>
              <dd className="mt-0.5 font-medium">{item.value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function memoryText(t: Translations): NonNullable<Translations["memoryPage"]> {
  return { ...MEMORY_TEXT, ...t.memoryPage };
}

const PROVIDER_LABELS: Record<string, string> = {
  holographic: "Holographic",
  builtin: "Built-in Markdown",
  honcho: "Honcho",
  hindsight: "Hindsight",
  mem0: "Mem0",
  supermemory: "Supermemory",
  retaindb: "RetainDB",
  openviking: "OpenViking",
  byterover: "ByteRover",
};

function formatTrust(score: number | null | undefined): string {
  if (score == null || Number.isNaN(Number(score))) return "—";
  return Number(score).toFixed(2);
}

function formatScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(Number(score))) return "—";
  return Number(score).toFixed(3);
}

function sessionMessageBody(msg: MemoryProfileSessionMessage): string {
  return (
    msg.content?.trim() ||
    (msg.tool_name ? `[${msg.tool_name}]` : "") ||
    (msg.tool_calls?.length ? `[tool_calls ×${msg.tool_calls.length}]` : "")
  );
}

function messageRoleLabel(
  role: string,
  mT: NonNullable<Translations["memoryPage"]>,
): string {
  if (role === "user") return mT.roleUser;
  if (role === "assistant") return mT.roleAssistant;
  if (role === "system") return mT.roleSystem;
  if (role === "tool") return mT.roleTool;
  return role;
}

function formatMessagesMarkdown(
  messages: MemoryProfileSessionMessage[],
  mT: NonNullable<Translations["memoryPage"]>,
): string {
  const parts: string[] = [];
  messages.forEach((msg, idx) => {
    const body = sessionMessageBody(msg);
    if (!body) return;
    const roleLabel = messageRoleLabel(msg.role, mT);
    const toolTag = msg.tool_name ? ` · \`${msg.tool_name}\`` : "";
    const heading = `### messages[${idx}] · ${roleLabel}${toolTag}`;
    const fenced =
      msg.role === "tool" && (body.startsWith("{") || body.startsWith("["))
        ? "```json\n" + body + "\n```"
        : body;
    parts.push(`${heading}\n\n${fenced}`);
  });
  return parts.join("\n\n---\n\n");
}

function formatSimulatedTurnMarkdown(
  history: MemoryRetrieveTestResponse["scenario"]["conversation_history"],
  mT: NonNullable<Translations["memoryPage"]>,
): string {
  const idx = history.message_count;
  const userContent = history.simulated_turn.user_content.trim();
  const injection = history.simulated_turn.prefetch_injection?.trim();
  const parts: string[] = [`### messages[${idx}] · ${mT.roleUser}`, "", userContent];
  if (injection) {
    parts.push(
      "",
      "---",
      "",
      `### memory-context · ${mT.prefetchInjectionLabel}`,
      "",
      "```",
      injection,
      "```",
    );
  }
  return parts.join("\n");
}

function SessionHistoryBubble({
  msg,
  mT,
}: {
  msg: MemoryProfileSessionMessage;
  mT: NonNullable<Translations["memoryPage"]>;
}) {
  const body = sessionMessageBody(msg);
  if (!body) return null;

  const role = msg.role;
  const isUser = role === "user";
  const isAssistant = role === "assistant";
  const isSystem = role === "system";
  const isTool = role === "tool";

  const roleLabel = isUser
    ? mT.roleUser
    : isAssistant
      ? mT.roleAssistant
      : isSystem
        ? mT.roleSystem
        : isTool
          ? mT.roleTool
          : role;

  if (isSystem) {
    return (
      <div className="flex justify-center px-2">
        <div className="max-w-[92%] rounded-md border border-dashed bg-muted/20 px-3 py-2 text-center">
          <p className="text-muted-foreground text-[11px] font-medium">{roleLabel}</p>
          <p className="text-muted-foreground mt-1 text-xs whitespace-pre-wrap">{body}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex items-start gap-2", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary/15 text-primary"
            : isTool
              ? "bg-muted text-muted-foreground"
              : "bg-secondary/70 text-foreground",
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5" />
        ) : isTool ? (
          <Wrench className="h-3.5 w-3.5" />
        ) : (
          <Bot className="h-3.5 w-3.5" />
        )}
      </div>
      <div
        className={cn(
          "min-w-0 max-w-[min(85%,520px)] rounded-2xl border px-3 py-2 text-sm shadow-sm",
          isUser
            ? "rounded-tr-sm border-primary/25 bg-primary/10"
            : isTool
              ? "rounded-tl-sm border-dashed bg-muted/30 font-mono text-xs"
              : "rounded-tl-sm border-border bg-secondary/40",
        )}
      >
        <div
          className={cn(
            "mb-1 flex flex-wrap items-center gap-2 text-[11px] font-medium",
            isUser ? "justify-end text-primary/80" : "text-muted-foreground",
          )}
        >
          <span>{roleLabel}</span>
          {msg.tool_name ? <span className="font-mono font-normal">{msg.tool_name}</span> : null}
          {msg.timestamp ? (
            <span className="font-normal tabular-nums opacity-70">
              {new Date(msg.timestamp * 1000).toLocaleString([], {
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          ) : null}
        </div>
        <pre
          className={cn(
            "whitespace-pre-wrap",
            isTool ? "font-mono text-xs leading-relaxed" : "font-sans text-sm",
          )}
        >
          {body}
        </pre>
      </div>
    </div>
  );
}

function BlockPreview({
  text,
  label,
  className,
}: {
  text: string | null | undefined;
  label: string;
  className?: string;
}) {
  if (!text) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold text-foreground">{label}</p>
      <pre
        className={cn(
          "bg-primary/5 border-primary/20 overflow-auto rounded-md border p-3 font-mono text-xs whitespace-pre-wrap",
          className ?? "max-h-64",
        )}
      >
        {text}
      </pre>
    </div>
  );
}

function ResultSection({
  label,
  children,
  empty,
}: {
  label: string;
  children?: ReactNode;
  empty?: string;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold text-foreground">{label}</p>
      {children ?? (
        <p className="text-muted-foreground rounded-md border border-dashed bg-muted/10 px-3 py-2 text-sm italic">
          {empty}
        </p>
      )}
    </div>
  );
}

function FactHitsTable({
  facts,
  categoryLabels,
  mT,
  showScore = false,
}: {
  facts: MemoryRetrieveFactHit[];
  categoryLabels: Record<string, string>;
  mT: NonNullable<Translations["memoryPage"]>;
  showScore?: boolean;
}) {
  if (facts.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left">
          <tr>
            <th className="px-3 py-2 font-medium w-12">{mT.colId}</th>
            <th className="px-3 py-2 font-medium">{mT.colContent}</th>
            <th className="px-3 py-2 font-medium w-28">{mT.colCategory}</th>
            {showScore ? (
              <th className="px-3 py-2 font-medium w-20">{mT.colScore}</th>
            ) : (
              <th className="px-3 py-2 font-medium w-16">{mT.colTrust}</th>
            )}
          </tr>
        </thead>
        <tbody>
          {facts.map((f) => (
            <tr key={`${f.fact_id}-${f.content.slice(0, 24)}`} className="border-t align-top">
              <td className="text-muted-foreground px-3 py-2">{f.fact_id}</td>
              <td className="px-3 py-2 whitespace-pre-wrap">{f.content}</td>
              <td className="text-muted-foreground px-3 py-2">
                {categoryLabels[f.category] ?? f.category}
              </td>
              <td className="text-muted-foreground px-3 py-2">
                {showScore ? formatScore(f.score) : formatTrust(f.trust_score)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SimulatePartShell({
  title,
  hint,
  children,
  variant,
}: {
  title: string;
  hint: string;
  children: ReactNode;
  variant: "system" | "user";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border-2 p-4 space-y-4",
        variant === "system"
          ? "border-violet-500/25 bg-violet-500/5"
          : "border-primary/25 bg-primary/5",
      )}
    >
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{hint}</p>
      </div>
      {children}
    </div>
  );
}

function RetrieveResultsPanel({
  retrieveResult,
  categoryLabels,
  mT,
}: {
  retrieveResult: MemoryRetrieveTestResponse;
  categoryLabels: Record<string, string>;
  mT: NonNullable<Translations["memoryPage"]>;
}) {
  const sessionStart = retrieveResult.scenario.session_start;
  const history = retrieveResult.scenario.conversation_history;
  const prefetch = retrieveResult.scenario.turn_prefetch;
  const historyMarkdown = formatMessagesMarkdown(history.messages, mT);
  const simulatedTurnMarkdown = formatSimulatedTurnMarkdown(history, mT);
  const hasSystemContent = Boolean(
    sessionStart.memory_block || sessionStart.user_block || sessionStart.holographic_system_block,
  );

  return (
    <div className="space-y-5">
      <SimulatePartShell
        title={mT.simulateSystemPromptTitle}
        hint={mT.simulateSystemPromptHint}
        variant="system"
      >
        <BlockPreview
          label={`MEMORY · ${mT.injectContentLabel}`}
          text={sessionStart.memory_block}
        />
        <BlockPreview label={`USER · ${mT.injectContentLabel}`} text={sessionStart.user_block} />
        <BlockPreview label={mT.holographicSystemLabel} text={sessionStart.holographic_system_block} />
        {!hasSystemContent ? (
          <ResultSection label={mT.retrieveResultLabel} empty={mT.noEntries} />
        ) : null}
      </SimulatePartShell>

      <SimulatePartShell
        title={mT.simulateUserMessagesTitle}
        hint={mT.simulateUserMessagesHint}
        variant="user"
      >
        {history.message_count > 0 ? (
          <BlockPreview
            label={`${mT.sectionConversationHistory} (${history.message_count}) · ${mT.messagesMarkdownLabel}`}
            text={historyMarkdown}
            className="max-h-[min(50vh,420px)]"
          />
        ) : (
          <ResultSection label={mT.sectionConversationHistory} empty={mT.noConversationHistory} />
        )}

        <BlockPreview
          label={`${mT.sectionSimulatedTurn} · ${mT.messagesMarkdownLabel}`}
          text={simulatedTurnMarkdown}
          className="max-h-[min(40vh,360px)]"
        />
        {prefetch.facts.length > 0 ? (
          <ResultSection label={mT.sectionTurnPrefetch}>
            <FactHitsTable
              facts={prefetch.facts}
              categoryLabels={categoryLabels}
              mT={mT}
              showScore
            />
          </ResultSection>
        ) : (
          <ResultSection label={mT.sectionTurnPrefetch} empty={mT.noPrefetch} />
        )}
      </SimulatePartShell>
    </div>
  );
}

export default function MemoryPage() {
  const { t } = useI18n();
  const mT = memoryText(t);
  const { profile } = useProfileScope();
  const { setAfterTitle, setEnd } = usePageHeader();

  const [overview, setOverview] = useState<MemoryProfileOverview | null>(null);
  const [facts, setFacts] = useState<MemoryProfileFact[]>([]);
  const [factsTotal, setFactsTotal] = useState(0);
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [tab, setTab] = useState<"facts" | "markdown" | "sessions">("facts");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [retrieveQuery, setRetrieveQuery] = useState("");
  const [retrieveLoading, setRetrieveLoading] = useState(false);
  const [retrieveError, setRetrieveError] = useState<string | null>(null);
  const [retrieveResult, setRetrieveResult] = useState<MemoryRetrieveTestResponse | null>(null);
  const [entities, setEntities] = useState<MemoryProfileEntity[]>([]);
  const [entityNoiseCount, setEntityNoiseCount] = useState(0);
  const [purgeLoading, setPurgeLoading] = useState(false);
  const [purgeMarkdownLoading, setPurgeMarkdownLoading] = useState(false);
  const [sessions, setSessions] = useState<MemoryProfileSessionSummary[]>([]);
  const [sessionsTotal, setSessionsTotal] = useState(0);
  const [sessionsPage, setSessionsPage] = useState(0);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionMessages, setSessionMessages] = useState<MemoryProfileSessionMessage[]>([]);
  const [sessionMessagesLoading, setSessionMessagesLoading] = useState(false);
  const [compressionChain, setCompressionChain] =
    useState<MemoryCompressionChainResponse | null>(null);
  const [expandedChainNode, setExpandedChainNode] = useState<string | null>(null);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);

  const effectiveProfileId = profile || overview?.profile_id || "default";

  const categoryLabels = overview?.category_labels ?? retrieveResult?.category_labels ?? {};

  const loadFacts = useCallback(async (cat: string) => {
    const res = await api.getMemoryProfileFacts({
      category: cat === ALL_CATEGORIES ? undefined : cat,
      limit: 100,
      offset: 0,
    });
    setFacts(res.facts);
    setFactsTotal(res.total);
  }, []);

  const loadEntities = useCallback(async () => {
    try {
      const res = await api.getMemoryProfileEntities({ limit: 200 });
      setEntities(res.entities);
      setEntityNoiseCount(res.noise);
    } catch {
      setEntities([]);
      setEntityNoiseCount(0);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ov = await api.getMemoryProfile();
      setOverview(ov);
      await Promise.all([loadFacts(category), loadEntities()]);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [category, loadEntities, loadFacts]);

  const runRetrieveTest = useCallback(
    async () => {
      const query = retrieveQuery.trim();
      if (!query || !selectedSessionId) return;
      setRetrieveLoading(true);
      setRetrieveError(null);
      try {
        const result = await api.postMemoryRetrieveTest({
          query,
          session_id: selectedSessionId,
        });
        setRetrieveResult(result);
      } catch (err) {
        setRetrieveError(String(err));
      } finally {
        setRetrieveLoading(false);
      }
    },
    [retrieveQuery, selectedSessionId],
  );

  const onEntityChipClick = useCallback((name: string) => {
    setTab("sessions");
    setRetrieveQuery((prev) => prev.trim() || name);
  }, []);

  const purgeNoiseEntities = useCallback(async () => {
    setPurgeLoading(true);
    setError(null);
    try {
      await api.purgeMemoryNoiseEntities();
      await loadAll();
    } catch (err) {
      setError(String(err));
    } finally {
      setPurgeLoading(false);
    }
  }, [loadAll]);

  const loadSessions = useCallback(async (page = 0) => {
    setSessionsLoading(true);
    setError(null);
    try {
      const res = await api.getMemoryProfileSessions({
        limit: SESSIONS_PAGE_SIZE,
        offset: page * SESSIONS_PAGE_SIZE,
        order: "recent",
      });
      setSessionsTotal(res.total);
      setSessions(res.sessions);
      setSessionsPage(page);
      if (res.sessions.length > 0) {
        setSelectedSessionId(res.sessions[0].id);
      } else {
        setSelectedSessionId(null);
        setSessionMessages([]);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const loadSessionMessages = useCallback(async (sessionId: string) => {
    setSessionMessagesLoading(true);
    setError(null);
    setCompressionChain(null);
    setExpandedChainNode(null);
    try {
      const res = await api.getMemoryProfileSessionMessages(sessionId);
      setSessionMessages(res.messages);
      // Best-effort: surface the compaction lineage (root + continuations) so
      // the otherwise-invisible time-stamp-id forks are navigable. Only keep it
      // when the family actually has >1 node; a failure here must not block the
      // transcript view.
      try {
        const chain = await api.getMemoryProfileSessionCompressionChain(sessionId);
        setCompressionChain(chain.compressed ? chain : null);
      } catch {
        setCompressionChain(null);
      }
    } catch (err) {
      setSessionMessages([]);
      setError(String(err));
    } finally {
      setSessionMessagesLoading(false);
    }
  }, []);

  const purgeTransientMarkdown = useCallback(async () => {
    setPurgeMarkdownLoading(true);
    setError(null);
    try {
      await api.purgeMemoryTransientMarkdown("memory");
      await loadAll();
    } catch (err) {
      setError(String(err));
    } finally {
      setPurgeMarkdownLoading(false);
    }
  }, [loadAll]);

  useEffect(() => {
    setCategory(ALL_CATEGORIES);
    setRetrieveResult(null);
    setRetrieveError(null);
    setRetrieveQuery("");
    setSelectedSessionId(null);
    setSessionMessages([]);
    setCompressionChain(null);
    setExpandedChainNode(null);
    setSessions([]);
  }, [profile]);

  useEffect(() => {
    if (tab !== "sessions") return;
    setRetrieveResult(null);
    setRetrieveQuery("");
  }, [selectedSessionId, tab]);

  useEffect(() => {
    if (tab !== "sessions") return;
    void loadSessions(0);
  }, [tab, profile, loadSessions]);

  useEffect(() => {
    if (!selectedSessionId || tab !== "sessions") return;
    void loadSessionMessages(selectedSessionId);
  }, [loadSessionMessages, selectedSessionId, tab]);

  useEffect(() => {
    void loadAll();
  }, [loadAll, profile]);

  useEffect(() => {
    setAfterTitle(null);
    setEnd(
      <Button outlined size="sm" onClick={() => void loadAll()} disabled={loading}>
        {loading ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />}
        <span className="ml-2 hidden sm:inline">{mT.refresh}</span>
      </Button>,
    );
    return () => {
      setAfterTitle(null);
      setEnd(null);
    };
  }, [loadAll, loading, mT.refresh, setAfterTitle, setEnd]);

  const providerLabel =
    PROVIDER_LABELS[overview?.provider ?? retrieveResult?.provider ?? ""] ??
    overview?.provider ??
    retrieveResult?.provider ??
    "—";

  const tabOptions = useMemo(
    () => [
      { value: "facts", label: mT.tabFacts },
      { value: "markdown", label: mT.tabMarkdown },
      { value: "sessions", label: mT.tabSessions },
    ],
    [mT.tabFacts, mT.tabMarkdown, mT.tabSessions],
  );

  const selectedSession = useMemo(
    () => sessions.find((s) => s.id === selectedSessionId) ?? null,
    [sessions, selectedSessionId],
  );

  const selectedSessionLabel = selectedSession
    ? selectedSession.title?.trim() ||
      selectedSession.preview?.trim()?.slice(0, 48) ||
      selectedSession.id.slice(0, 12)
    : null;

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{mT.title}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{mT.subtitle}</p>
        <p className="text-muted-foreground mt-1 text-xs">{mT.readOnlyHint}</p>
        {mT.routingHint ? (
          <p className="text-muted-foreground mt-2 text-xs border-l-2 border-muted-foreground/30 pl-3">
            {mT.routingHint}
          </p>
        ) : null}
      </div>

      {error ? (
        <Card>
          <CardContent className="pt-6 text-destructive text-sm">
            {mT.loadFailed}: {error}
          </CardContent>
        </Card>
      ) : null}

      {loading && !overview ? (
        <div className="flex justify-center py-12">
          <Spinner className="h-8 w-8" />
        </div>
      ) : overview ? (
        <>
          {overview.settings ? (
            <MemoryConfigStatusCard
              settings={overview.settings}
              providerLabel={providerLabel}
              mT={mT}
              onEdit={() => setConfigDialogOpen(true)}
            />
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Badge tone="secondary">
              {mT.provider}: {providerLabel}
            </Badge>
            <Badge tone="outline">
              {mT.statFacts}: {overview.stats.holographic_facts}
            </Badge>
            <Badge tone="outline">
              {mT.statEntities}: {overview.stats.holographic_entities}
              {(overview.stats.holographic_entities_noise ?? 0) > 0 ||
              (overview.stats.holographic_entities_usable ?? 0) > 0
                ? ` ${mT.statEntitiesBreakdown
                    .replace("{usable}", String(overview.stats.holographic_entities_usable ?? 0))
                    .replace("{noise}", String(overview.stats.holographic_entities_noise ?? 0))}`
                : ""}
            </Badge>
            <Badge tone="outline">
              {mT.statMemoryMd}: {overview.stats.memory_md_entries}
              {(overview.stats.memory_md_transient ?? 0) > 0
                ? ` · ${mT.statMemoryMdTransient.replace(
                    "{count}",
                    String(overview.stats.memory_md_transient),
                  )}`
                : ""}
            </Badge>
            <Badge tone="outline">
              {mT.statUserMd}: {overview.stats.user_md_entries}
            </Badge>
          </div>

          {overview.stats.memory_store_exists ? (
            <div className="space-y-2 rounded-lg border border-border/60 bg-muted/20 px-3 py-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label className="text-xs">{mT.entityPickerLabel}</Label>
                {entityNoiseCount > 0 ? (
                  <Button
                    outlined
                    size="sm"
                    disabled={purgeLoading}
                    onClick={() => void purgeNoiseEntities()}
                  >
                    {purgeLoading ? (
                      <>
                        <Spinner className="h-3 w-3" />
                        <span className="ml-2">{mT.purgeNoiseRunning}</span>
                      </>
                    ) : (
                      mT.purgeNoiseEntities
                    )}
                  </Button>
                ) : null}
              </div>
              <p className="text-muted-foreground text-xs">{mT.entityPickerHint}</p>
              {entities.length === 0 ? (
                <p className="text-muted-foreground text-xs">{mT.noEntities}</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {entities.map((entity) => (
                    <Badge
                      key={entity.id}
                      tone={entity.plausible ? "secondary" : "outline"}
                      className={
                        entity.plausible
                          ? "cursor-pointer hover:opacity-80"
                          : "border-destructive/40 text-destructive/90 opacity-90"
                      }
                      title={[
                        entity.plausible ? null : mT.entityNoiseHint,
                        mT.entityFactCount.replace("{count}", String(entity.fact_count)),
                        entity.sample_fact,
                      ]
                        .filter(Boolean)
                        .join("\n")}
                      onClick={
                        entity.plausible
                          ? () => onEntityChipClick(entity.name)
                          : undefined
                      }
                    >
                      {!entity.plausible ? (
                        <span className="mr-1 font-medium">{mT.entityNoiseTag}·</span>
                      ) : null}
                      {entity.name}
                      {entity.fact_count > 0 ? (
                        <span className="ml-1 opacity-60">({entity.fact_count})</span>
                      ) : null}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          <Segmented
            value={tab}
            onChange={(v) => setTab(v as "facts" | "markdown" | "sessions")}
            options={tabOptions}
          />

          {tab === "facts" && mT.tabFactsScope ? (
            <p className="text-muted-foreground text-xs">{mT.tabFactsScope}</p>
          ) : null}

          {tab === "facts" ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Brain className="h-4 w-4" />
                  memory_store.db
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {!overview.stats.memory_store_exists ? (
                  <p className="text-muted-foreground text-sm">{mT.noStore}</p>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-3">
                      <Label className="text-xs">{mT.colCategory}</Label>
                      <Select
                        value={category}
                        onValueChange={(v) => {
                          setCategory(v);
                          void loadFacts(v);
                        }}
                        className="w-[220px]"
                      >
                        <SelectOption value={ALL_CATEGORIES}>{mT.filterAll}</SelectOption>
                        {(overview.categories ?? []).map((c) => (
                          <SelectOption key={c.name} value={c.name}>
                            {categoryLabels[c.name]
                              ? `${categoryLabels[c.name]} (${c.count})`
                              : `${c.name} (${c.count})`}
                          </SelectOption>
                        ))}
                      </Select>
                      <span className="text-muted-foreground text-sm">
                        {mT.totalFacts.replace("{total}", String(factsTotal))}
                      </span>
                    </div>
                    {facts.length === 0 ? (
                      <p className="text-muted-foreground text-sm">{mT.noFacts}</p>
                    ) : (
                      <div className="overflow-x-auto rounded-md border">
                        <table className="w-full text-sm">
                          <thead className="bg-muted/50 text-left">
                            <tr>
                              <th className="px-3 py-2 font-medium w-12">{mT.colId}</th>
                              <th className="px-3 py-2 font-medium">{mT.colContent}</th>
                              <th className="px-3 py-2 font-medium w-28">{mT.colCategory}</th>
                              <th className="px-3 py-2 font-medium w-16">{mT.colTrust}</th>
                              <th className="px-3 py-2 font-medium w-36">{mT.colUpdated}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {facts.map((f) => (
                              <tr key={f.fact_id} className="border-t align-top">
                                <td className="text-muted-foreground px-3 py-2">{f.fact_id}</td>
                                <td className="px-3 py-2 whitespace-pre-wrap">{f.content}</td>
                                <td className="text-muted-foreground px-3 py-2">
                                  {categoryLabels[f.category] ?? f.category}
                                </td>
                                <td className="text-muted-foreground px-3 py-2">
                                  {formatTrust(f.trust_score)}
                                </td>
                                <td className="text-muted-foreground px-3 py-2 text-xs">
                                  {f.updated_at ?? "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          ) : tab === "markdown" ? (
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-base">{mT.memoryMdTitle}</CardTitle>
                    {(overview.stats.memory_md_transient ?? 0) > 0 ? (
                      <Button
                        outlined
                        size="sm"
                        disabled={purgeMarkdownLoading}
                        onClick={() => void purgeTransientMarkdown()}
                      >
                        {purgeMarkdownLoading ? (
                          <>
                            <Spinner className="h-3 w-3" />
                            <span className="ml-2">{mT.purgeTransientRunning}</span>
                          </>
                        ) : (
                          mT.purgeTransientMarkdown
                        )}
                      </Button>
                    ) : null}
                  </div>
                </CardHeader>
                <CardContent>
                  {overview.markdown.memory.length === 0 ? (
                    <p className="text-muted-foreground text-sm">{mT.noEntries}</p>
                  ) : (
                    <ul className="space-y-3 text-sm">
                      {overview.markdown.memory.map((e) => (
                        <li
                          key={e.index}
                          className={
                            e.transient
                              ? "rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2"
                              : "rounded-md border px-3 py-2"
                          }
                        >
                          <div className="mb-1 flex flex-wrap items-center gap-2">
                            <span className="text-muted-foreground">#{e.index + 1}</span>
                            {e.transient ? (
                              <Badge tone="outline" className="text-destructive/90 text-[10px]">
                                {mT.markdownTransientTag}
                              </Badge>
                            ) : null}
                          </div>
                          <span className="whitespace-pre-wrap">{e.text}</span>
                          {e.transient ? (
                            <p className="text-muted-foreground mt-2 text-xs">{mT.markdownTransientHint}</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{mT.userMdTitle}</CardTitle>
                </CardHeader>
                <CardContent>
                  {overview.markdown.user.length === 0 ? (
                    <p className="text-muted-foreground text-sm">{mT.noEntries}</p>
                  ) : (
                    <ul className="space-y-3 text-sm">
                      {overview.markdown.user.map((e) => (
                        <li key={e.index} className="rounded-md border px-3 py-2">
                          <span className="text-muted-foreground mr-2">#{e.index + 1}</span>
                          <span className="whitespace-pre-wrap">{e.text}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : tab === "sessions" ? (
            <div className="space-y-6">
              <p className="text-muted-foreground rounded-lg border border-border/60 bg-muted/10 px-4 py-3 text-sm">
                {mT.sessionsSplitOverview}
              </p>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <MessageSquare className="h-4 w-4" />
                    {mT.sessionHistoryTitle}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-1">
                    <p className="text-muted-foreground text-sm">{mT.sessionHistoryHint}</p>
                    <p className="text-muted-foreground font-mono text-xs">{mT.sessionHistorySource}</p>
                  </div>
                  <div className="grid gap-4 lg:grid-cols-[minmax(220px,280px)_1fr] lg:items-start">
                    <div className="space-y-2">
                      <div className="border rounded-md max-h-[min(50vh,420px)] overflow-y-auto">
                        {sessionsLoading && sessions.length === 0 ? (
                          <div className="flex justify-center py-8">
                            <Spinner className="h-6 w-6" />
                          </div>
                        ) : sessions.length === 0 ? (
                          <p className="text-muted-foreground p-3 text-sm">{mT.sessionsEmpty}</p>
                        ) : (
                          <ul className="divide-y">
                            {sessions.map((s) => (
                              <li key={s.id}>
                                <button
                                  type="button"
                                  className={
                                    selectedSessionId === s.id
                                      ? "bg-muted/60 w-full px-3 py-2.5 text-left text-sm"
                                      : "hover:bg-muted/30 w-full px-3 py-2.5 text-left text-sm"
                                  }
                                  onClick={() => setSelectedSessionId(s.id)}
                                >
                                  <div className="flex flex-wrap items-center gap-1.5">
                                    <span className="font-medium line-clamp-1">
                                      {s.title?.trim() || s.preview?.trim() || s.id.slice(0, 12)}
                                    </span>
                                    {s.is_active ? (
                                      <Badge tone="secondary" className="text-[10px]">
                                        {mT.sessionActive}
                                      </Badge>
                                    ) : null}
                                    {s.compressed ? (
                                      <Badge
                                        tone="secondary"
                                        className="border-primary/30 text-primary text-[10px]"
                                      >
                                        {mT.sessionCompressedBadge.replace(
                                          "{n}",
                                          String(s.generation ?? 1),
                                        )}
                                      </Badge>
                                    ) : null}
                                  </div>
                                  <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
                                    {s.preview || "—"}
                                  </p>
                                  <p className="text-muted-foreground mt-1 text-[10px]">
                                    {s.message_count} msgs · {timeAgo(s.last_active || s.started_at)}
                                    {s.source ? ` · ${s.source}` : ""}
                                  </p>
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                      {sessionsTotal > 0 ? (
                        <div className="space-y-1.5">
                          {sessionsTotal > SESSIONS_PAGE_SIZE ? (
                            <div className="flex flex-wrap items-center gap-1">
                              <Button
                                outlined
                                size="sm"
                                disabled={sessionsLoading || sessionsPage === 0}
                                onClick={() => void loadSessions(sessionsPage - 1)}
                              >
                                {mT.paginationPrev}
                              </Button>
                              {Math.ceil(sessionsTotal / SESSIONS_PAGE_SIZE) <= 10
                                ? Array.from(
                                    { length: Math.ceil(sessionsTotal / SESSIONS_PAGE_SIZE) },
                                    (_, i) => i,
                                  ).map((p) => (
                                    <Button
                                      key={p}
                                      outlined={p !== sessionsPage}
                                      size="sm"
                                      disabled={sessionsLoading}
                                      onClick={() => void loadSessions(p)}
                                    >
                                      {p + 1}
                                    </Button>
                                  ))
                                : null}
                              <Button
                                outlined
                                size="sm"
                                disabled={
                                  sessionsLoading ||
                                  (sessionsPage + 1) * SESSIONS_PAGE_SIZE >= sessionsTotal
                                }
                                onClick={() => void loadSessions(sessionsPage + 1)}
                              >
                                {mT.paginationNext}
                              </Button>
                            </div>
                          ) : null}
                          <p className="text-muted-foreground text-xs">
                            {mT.paginationStatus
                              .replace("{total}", String(sessionsTotal))
                              .replace("{page}", String(sessionsPage + 1))
                              .replace(
                                "{pages}",
                                String(Math.ceil(sessionsTotal / SESSIONS_PAGE_SIZE)),
                              )}
                          </p>
                        </div>
                      ) : null}
                    </div>
                    <div className="flex min-h-[240px] flex-col gap-4">
                      {compressionChain && compressionChain.nodes.length > 1 ? (
                        <div className="rounded-lg border border-primary/20 bg-muted/10 p-4 space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Layers className="text-primary h-4 w-4 shrink-0" />
                            <p className="text-sm font-medium">
                              {mT.compressionChainTitle.replace(
                                "{n}",
                                String(compressionChain.nodes.length),
                              )}
                            </p>
                          </div>
                          <p className="text-muted-foreground text-xs">
                            {mT.compressionChainHint}
                          </p>
                          <ul className="space-y-2">
                            {compressionChain.nodes.map((node) => (
                              <li
                                key={node.session_id}
                                className="bg-background/40 rounded-md border"
                              >
                                <div className="flex flex-wrap items-center gap-2 px-3 py-2">
                                  <Badge tone="secondary" className="text-[10px]">
                                    {mT.compressionChainGen.replace(
                                      "{n}",
                                      String(node.generation),
                                    )}
                                  </Badge>
                                  {node.is_root ? (
                                    <Badge tone="secondary" className="text-[10px]">
                                      {mT.compressionChainRoot}
                                    </Badge>
                                  ) : null}
                                  {node.is_tip ? (
                                    <Badge
                                      tone="secondary"
                                      className="border-primary/30 text-primary text-[10px]"
                                    >
                                      {mT.compressionChainTip}
                                    </Badge>
                                  ) : null}
                                  <span className="text-muted-foreground text-xs">
                                    {node.message_count} msgs
                                  </span>
                                  <span className="ml-auto flex items-center gap-2">
                                    {node.session_id === selectedSessionId ? (
                                      <span className="text-muted-foreground text-xs">
                                        {mT.compressionChainCurrent}
                                      </span>
                                    ) : (
                                      <button
                                        type="button"
                                        className="text-primary text-xs hover:underline"
                                        onClick={() => setSelectedSessionId(node.session_id)}
                                      >
                                        {mT.compressionChainOpen}
                                      </button>
                                    )}
                                    {node.has_summary ? (
                                      <button
                                        type="button"
                                        className="text-xs hover:underline"
                                        onClick={() =>
                                          setExpandedChainNode(
                                            expandedChainNode === node.session_id
                                              ? null
                                              : node.session_id,
                                          )
                                        }
                                      >
                                        {expandedChainNode === node.session_id
                                          ? mT.compressionChainHideSummary
                                          : mT.compressionChainShowSummary}
                                      </button>
                                    ) : null}
                                  </span>
                                </div>
                                {node.has_summary && expandedChainNode === node.session_id ? (
                                  <pre className="text-muted-foreground max-h-40 overflow-y-auto whitespace-pre-wrap border-t px-3 py-2 text-xs">
                                    {node.summary_preview}
                                  </pre>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : null}

                      <div className="flex min-h-[160px] flex-1 flex-col overflow-hidden rounded-md border">
                        <div className="border-b bg-muted/20 px-3 py-2">
                          <p className="text-sm font-medium">{mT.sessionTranscriptTitle}</p>
                          <p className="text-muted-foreground text-xs">{mT.sessionTranscriptHint}</p>
                        </div>
                        {!selectedSessionId ? (
                          <p className="text-muted-foreground flex flex-1 items-center justify-center p-4 text-sm">
                            {mT.sessionsSelect}
                          </p>
                        ) : sessionMessagesLoading ? (
                          <div className="flex flex-1 justify-center py-12">
                            <Spinner className="h-6 w-6" />
                          </div>
                        ) : sessionMessages.length === 0 ? (
                          <p className="text-muted-foreground flex flex-1 items-center justify-center p-4 text-sm">
                            {mT.sessionsEmpty}
                          </p>
                        ) : (
                          <div className="max-h-[min(40vh,360px)] flex-1 space-y-3 overflow-y-auto p-3">
                            {sessionMessages.map((msg, idx) => (
                              <SessionHistoryBubble
                                key={`${idx}-${msg.role}-${msg.tool_name ?? ""}`}
                                msg={msg}
                                mT={mT}
                              />
                            ))}
                          </div>
                        )}
                      </div>

                      {selectedSessionId ? (
                        <div className="rounded-lg border border-primary/20 bg-muted/10 p-4 space-y-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <Brain className="text-primary h-4 w-4 shrink-0" />
                            <p className="text-sm font-medium">{mT.retrieveSectionTitle}</p>
                            {selectedSessionLabel ? (
                              <Badge tone="secondary" className="font-normal text-xs">
                                {mT.retrieveSessionContext}: {selectedSessionLabel}
                              </Badge>
                            ) : null}
                          </div>
                          <p className="text-muted-foreground text-xs">{mT.retrieveSectionHint}</p>

                          <div className="space-y-3 rounded-lg border border-border/60 bg-background/80 p-3">
                            <div className="space-y-2">
                              <Label htmlFor="retrieve-query">{mT.retrieveQueryLabel}</Label>
                              <textarea
                                id="retrieve-query"
                                className="border-input bg-background min-h-[88px] w-full rounded-md border px-3 py-2 text-sm"
                                placeholder={mT.retrieveQueryPlaceholder}
                                value={retrieveQuery}
                                onChange={(e) => setRetrieveQuery(e.target.value)}
                              />
                            </div>
                            <Button
                              size="sm"
                              onClick={() => void runRetrieveTest()}
                              disabled={retrieveLoading || !retrieveQuery.trim()}
                            >
                              {retrieveLoading ? (
                                <>
                                  <Spinner className="h-4 w-4" />
                                  <span className="ml-2">{mT.retrieveRunning}</span>
                                </>
                              ) : (
                                mT.retrieveRun
                              )}
                            </Button>
                            {retrieveError ? (
                              <p className="text-destructive text-sm">
                                {mT.loadFailed}: {retrieveError}
                              </p>
                            ) : null}
                          </div>

                          {retrieveResult ? (
                            <RetrieveResultsPanel
                              retrieveResult={retrieveResult}
                              categoryLabels={categoryLabels}
                              mT={mT}
                            />
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          ) : null}
        </>
      ) : null}

      <MemorySettingsDialog
        open={configDialogOpen}
        profileId={effectiveProfileId}
        provider={overview?.settings?.provider ?? overview?.provider ?? "builtin"}
        onClose={() => setConfigDialogOpen(false)}
        onSaved={() => {
          void loadAll();
          setRetrieveResult(null);
        }}
      />
    </div>
  );
}
