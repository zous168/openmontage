import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { useI18n } from "@/i18n";
import { api } from "@/lib/api";
import type { SessionLlmRequestSummary } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

function formatJson(raw: string | null | undefined): string {
  if (!raw) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function statusTone(status: string): "success" | "destructive" | "secondary" {
  if (status === "success") return "success";
  if (status === "error" || status === "invalid_response") return "destructive";
  return "secondary";
}

function JsonBlock({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="min-w-0">
      <div className="mb-1 text-xs font-medium text-muted-foreground">{label}</div>
      <pre className="max-h-80 overflow-auto rounded-md border border-border/60 bg-background/80 p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all">
        {value}
      </pre>
    </div>
  );
}

export function LlmRequestLogPanel({
  sessionId,
  profile,
}: {
  sessionId: string;
  profile?: string;
}) {
  const { t } = useI18n();
  const copy = t.sessions2;
  const [items, setItems] = useState<SessionLlmRequestSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SessionLlmRequestSummary | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadList = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getSessionLlmRequests(sessionId, { limit: 100, offset: 0, profile })
      .then((resp) => {
        setItems(resp.items);
        setTotal(resp.total);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [sessionId, profile]);

  useEffect(() => {
    loadList();
    setExpandedId(null);
    setDetail(null);
  }, [loadList, sessionId]);

  const loadDetail = useCallback(
    async (requestId: number) => {
      if (expandedId === requestId && detail) {
        setExpandedId(null);
        setDetail(null);
        return;
      }
      setExpandedId(requestId);
      setDetailLoading(true);
      try {
        const resp = await api.getSessionLlmRequest(sessionId, requestId, profile);
        setDetail(resp.item);
      } catch (err) {
        setError(String(err));
        setExpandedId(null);
        setDetail(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [detail, expandedId, profile, sessionId],
  );

  const emptyLabel = copy?.llmRequestsEmpty ?? "No LLM request logs yet";

  const rows = useMemo(() => items, [items]);

  if (loading && rows.length === 0) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner className="text-xl text-primary" />
      </div>
    );
  }

  if (error && rows.length === 0) {
    return <p className="py-4 text-center text-sm text-destructive">{error}</p>;
  }

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
        <Button ghost size="sm" onClick={loadList}>
          {t.common.refresh}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {(copy?.llmRequestsSummary ?? "{total} request(s)").replace(
            "{total}",
            String(total),
          )}
        </span>
        <Button ghost size="sm" onClick={loadList} disabled={loading}>
          {loading ? <Spinner className="mr-2" /> : null}
          {t.common.refresh}
        </Button>
      </div>

      <div className="max-h-[600px] overflow-y-auto pr-1">
        <div className="flex flex-col gap-2">
          {rows.map((row) => {
            const open = expandedId === row.id;
            return (
              <div
                key={row.id}
                className="rounded-md border border-border/60 bg-background/40"
              >
                <button
                  type="button"
                  className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left hover:bg-secondary/20"
                  onClick={() => void loadDetail(row.id)}
                >
                  <Badge tone={statusTone(row.status)} className="text-[10px] uppercase">
                    {row.status}
                  </Badge>
                  <span className="font-mono text-xs">
                    {(row.model ?? "unknown").split("/").pop()}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    #{row.api_call_number ?? "?"} · attempt {row.attempt}
                  </span>
                  {row.latency_ms != null && (
                    <span className="text-xs text-muted-foreground">
                      {(row.latency_ms / 1000).toFixed(2)}s
                    </span>
                  )}
                  {(row.input_tokens != null || row.output_tokens != null) && (
                    <span className="text-xs text-muted-foreground">
                      in {row.input_tokens ?? 0} / out {row.output_tokens ?? 0}
                    </span>
                  )}
                  <span className="ml-auto text-xs text-muted-foreground">
                    {timeAgo(row.created_at)}
                  </span>
                </button>

                {open && (
                  <div className="space-y-3 border-t border-border/60 px-3 py-3">
                    {detailLoading ? (
                      <div className="flex justify-center py-4">
                        <Spinner />
                      </div>
                    ) : detail && detail.id === row.id ? (
                      <>
                        <div className="grid gap-1 text-xs text-muted-foreground">
                          <div>
                            <span className="font-medium text-foreground">ID: </span>
                            <span className="font-mono">{detail.api_request_id}</span>
                          </div>
                          <div>
                            <span className="font-medium text-foreground">Provider: </span>
                            {detail.provider ?? "—"} · {detail.api_mode ?? "—"}
                          </div>
                          <div className="break-all">
                            <span className="font-medium text-foreground">Endpoint: </span>
                            {detail.base_url ?? "—"}
                          </div>
                        </div>
                        <JsonBlock
                          label={copy?.llmRequestRequest ?? "Request"}
                          value={formatJson(detail.request_json)}
                        />
                        <JsonBlock
                          label={copy?.llmRequestResponse ?? "Response"}
                          value={formatJson(detail.response_json)}
                        />
                        <JsonBlock
                          label={copy?.llmRequestError ?? "Error"}
                          value={formatJson(detail.error_json)}
                        />
                      </>
                    ) : null}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
