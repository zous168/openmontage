import { useCallback, useEffect, useRef, useState } from "react";
import { Headset, User } from "lucide-react";
import { api, buildWsUrl } from "@/lib/api";
import type { SimHistoryMessage, SimPeer } from "@/lib/api";
import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";

/** 渠道值 → UI 文案（与浮窗一致）。 */
const CHANNELS: Record<string, string> = {
  wechat: "微信",
  wecom: "企业微信",
  wechat_channels: "视频号",
  douyin: "抖音",
  xhs: "小红书",
  web: "官网",
};
function channelLabel(v: string): string {
  return CHANNELS[v] ?? v;
}

interface Sel {
  channel: string;
  uid: string;
}

/** 历史签名：轮询时判断是否有变化，避免无谓重渲染/滚动跳动。 */
function sig(msgs: SimHistoryMessage[]): string {
  const last = msgs[msgs.length - 1];
  return `${msgs.length}|${last ? last.role + ":" + last.content.length : ""}`;
}

/**
 * 坐席接待 · 只读监控（本期纯 AI；人工接管为 P2，见 docs §七）。
 *
 * 客服 Agent 的实际运行已收敛到网关（api_server）；本页只读地列出进行中会话、查看
 * 对话历史（共享 `state.db`，3s 轮询刷新）。转人工/坐席人工回复延后至 P2。
 */
export default function SeatPage() {
  const [peers, setPeers] = useState<SimPeer[]>([]);
  const [selected, setSelected] = useState<Sel | null>(null);
  const [messages, setMessages] = useState<SimHistoryMessage[]>([]);
  // 当前会话进行中一轮的实时态（逐 token）：{客户问, 正在生成的 AI 回复}。done 后并入 messages。
  const [live, setLive] = useState<{ user: string; reply: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const selRef = useRef<Sel | null>(null);
  const sigRef = useRef("");
  const peersRef = useRef<SimPeer[]>([]);
  useEffect(() => {
    selRef.current = selected;
    peersRef.current = peers;
  });

  const selectedPeer = peers.find(
    (p) => selected && p.channel === selected.channel && p.user_unique_id === selected.uid,
  );

  const loadMessages = useCallback(async (channel: string, uid: string) => {
    const res = await api.seatMessages(channel, uid);
    sigRef.current = sig(res.messages);
    setMessages(res.messages);
  }, []);

  const selectPeer = useCallback(
    async (channel: string, uid: string) => {
      setSelected({ channel, uid });
      setError(null);
      setMessages([]);
      setLive(null);
      sigRef.current = "";
      try {
        await loadMessages(channel, uid);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [loadMessages],
  );

  // 首次载入主体列表，默认选第一个。
  useEffect(() => {
    api
      .seatList()
      .then((res) => {
        setPeers(res.peers);
        const first = res.peers[0];
        if (!first) return undefined;
        setSelected({ channel: first.channel, uid: first.user_unique_id });
        return api.seatMessages(first.channel, first.user_unique_id).then((h) => {
          sigRef.current = sig(h.messages);
          setMessages(h.messages);
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  // 实时（逐 token）：订阅 dashboard 事件广播（复用嵌入式 Chat 的 /api/events WS，
  // channel=cs-seat）。客户模拟每轮：sim_api 推 turn.started → delta… → turn.done。
  // 命中当前会话 → **直接渲染 delta**（不再每轮拉 messages）；非当前会话仅刷新左侧列表。
  // 连上/重连即拉一次当前会话对齐 DB，补偿断连期间漏掉的轮次。
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const refreshList = async () => {
      try {
        setPeers((await api.seatList()).peers);
      } catch {
        /* 忽略 */
      }
    };
    const reloadCurrent = async () => {
      const sel = selRef.current;
      if (!sel) return;
      try {
        const res = await api.seatMessages(sel.channel, sel.uid);
        if (
          selRef.current &&
          selRef.current.channel === sel.channel &&
          selRef.current.uid === sel.uid
        ) {
          sigRef.current = sig(res.messages);
          setMessages(res.messages);
          setLive(null);
        }
      } catch {
        /* 忽略 */
      }
    };

    const connect = async () => {
      if (closed) return;
      try {
        const url = await buildWsUrl("/api/events", { channel: "cs-seat" });
        if (closed) return;
        ws = new WebSocket(url);
        ws.onopen = () => {
          void refreshList();
          void reloadCurrent();
        };
        ws.onmessage = (ev) => {
          let evt: {
            type?: string;
            channel?: string;
            user_unique_id?: string;
            user_message?: string;
            reply?: string;
            delta?: string;
          } = {};
          try {
            evt = JSON.parse(ev.data);
          } catch {
            return;
          }
          const sel = selRef.current;
          const cur = !!sel && evt.channel === sel.channel && evt.user_unique_id === sel.uid;
          const ch = evt.channel ?? "";
          const id = evt.user_unique_id ?? "";
          // 该主体是否已在本地列表里：已知 → 本地增量更新；未知（新客户首条）→ 才拉一次去发现。
          const known = peersRef.current.some(
            (p) => p.channel === ch && p.user_unique_id === id,
          );
          if (evt.type === "turn.started") {
            if (!known) void refreshList();
            if (cur) setLive({ user: evt.user_message ?? "", reply: "" });
          } else if (evt.type === "delta") {
            if (cur)
              setLive((l) =>
                l
                  ? { ...l, reply: l.reply + (evt.delta ?? "") }
                  : { user: "", reply: evt.delta ?? "" },
              );
          } else if (evt.type === "turn.done") {
            // 列表更新走本地增量（轮次 +1 / 活跃时间），不再每轮拉整张 peers 列表。
            if (known) {
              setPeers((ps) =>
                ps.map((p) =>
                  p.channel === ch && p.user_unique_id === id
                    ? { ...p, rounds: (p.rounds ?? 0) + 1, last_active_at: Date.now() / 1000 }
                    : p,
                ),
              );
            } else {
              void refreshList();
            }
            if (cur) {
              const u = evt.user_message ?? "";
              const r = evt.reply ?? "";
              setMessages((m) => {
                const next = [...m];
                if (u) next.push({ role: "user", content: u });
                if (r) next.push({ role: "assistant", content: r });
                return next;
              });
              setLive(null);
            }
          }
        };
        ws.onclose = () => {
          if (!closed) retry = setTimeout(() => void connect(), 2000);
        };
        ws.onerror = () => {
          try {
            ws?.close();
          } catch {
            /* noop */
          }
        };
      } catch {
        if (!closed) retry = setTimeout(() => void connect(), 2000);
      }
    };
    void connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      try {
        ws?.close();
      } catch {
        /* noop */
      }
    };
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, live]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-bold text-foreground">坐席接待</h2>
        <span className="text-xs text-muted-foreground">
          只读监控：客服 Agent 由网关自动应答；此处查看进行中会话与对话历史。人工接管为后续能力。
        </span>
      </div>

      <div className="flex h-[70vh] gap-3">
        {/* 左：会话（主体）列表 */}
        <div className="flex w-72 shrink-0 flex-col border border-border bg-background-base/40">
          <div className="border-b border-border px-3 py-2 text-xs text-muted-foreground">
            进行中会话（{peers.length}）
          </div>
          <div className="flex-1 overflow-y-auto">
            {peers.length === 0 && (
              <div className="p-3 text-xs text-muted-foreground">
                暂无会话。客户从浮窗发起咨询后会出现在这里。
              </div>
            )}
            {peers.map((p) => {
              const active =
                selected?.channel === p.channel && selected?.uid === p.user_unique_id;
              return (
                <div
                  key={`${p.channel}|${p.user_unique_id}`}
                  onClick={() => void selectPeer(p.channel, p.user_unique_id)}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 border-b border-border/50 px-2.5 py-2",
                    active ? "bg-primary/10" : "hover:bg-secondary/30",
                  )}
                >
                  <User className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-foreground">
                      {p.user_display_name}
                    </div>
                    <div className="truncate text-[0.7rem] text-muted-foreground">
                      {channelLabel(p.channel)} · {fmtTime(p.last_active_at ?? p.created_at)} ·{" "}
                      {p.rounds ?? 0} 轮
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 右：会话详情（只读） */}
        <div className="flex min-w-0 flex-1 flex-col border border-border bg-background-base/40">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2">
            {selected ? (
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-foreground">
                  {selectedPeer?.user_display_name ?? selected.uid}
                </div>
                <div className="truncate text-[0.7rem] text-muted-foreground">
                  {channelLabel(selected.channel)} · AI 自动应答
                </div>
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">选择左侧会话查看对话</span>
            )}
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {!selected ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                左侧选择一个会话查看对话。
              </div>
            ) : messages.length === 0 && !live ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                暂无消息。
              </div>
            ) : (
              <>
                {messages.map((m, i) => (
                  <MessageBubble key={i} message={m} />
                ))}
                {live && (
                  <>
                    {live.user ? (
                      <MessageBubble
                        key="live-user"
                        message={{ role: "user", content: live.user }}
                      />
                    ) : null}
                    <MessageBubble
                      key="live-agent"
                      message={{ role: "assistant", content: live.reply }}
                      streaming
                    />
                  </>
                )}
              </>
            )}
          </div>

          {error && (
            <div className="border-t border-destructive/40 bg-destructive/10 px-4 py-2 text-xs text-destructive">
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function fmtTime(ts?: number | null): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString([], { month: "2-digit", day: "2-digit" });
}

/** 监控视角：`user` = 客户（左），`assistant` = 客服 AI（右）。 */
function MessageBubble({
  message,
  streaming,
}: {
  message: SimHistoryMessage;
  streaming?: boolean;
}) {
  const isCustomer = message.role === "user";
  return (
    <div
      className={cn(
        "flex items-start gap-2",
        isCustomer ? "flex-row" : "flex-row-reverse",
      )}
    >
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isCustomer ? "bg-secondary/60 text-foreground" : "bg-primary/20 text-primary",
        )}
      >
        {isCustomer ? <User className="h-3.5 w-3.5" /> : <Headset className="h-3.5 w-3.5" />}
      </div>
      <div
        className={cn(
          "max-w-[80%] border px-3 py-2 text-sm",
          isCustomer
            ? "border-border bg-secondary/40 text-foreground"
            : "border-primary/30 bg-primary/10 text-foreground",
        )}
      >
        {isCustomer ? (
          <span className="whitespace-pre-wrap">{message.content}</span>
        ) : streaming ? (
          // 流式中：纯文本逐 token（避免每帧重解析 Markdown），尾随光标。
          <span className="whitespace-pre-wrap">
            {message.content}
            <span className="ml-0.5 animate-pulse">▍</span>
          </span>
        ) : (
          <Markdown content={message.content} />
        )}
      </div>
    </div>
  );
}
