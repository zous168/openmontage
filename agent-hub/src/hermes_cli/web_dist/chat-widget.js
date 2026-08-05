/*
 * Hermes 客服浮窗 (chat-widget.js)
 * ================================
 * 自包含、零依赖的可嵌入客服聊天浮窗。任意页面只要
 *
 *   <script src="/chat-widget.js" defer></script>
 *
 * 装载后即在右下角浮出一个气泡图标，点击展开聊天面板。面板是**客户模拟客户端**，
 * 走 dashboard 的 `/api/customer-sim/*`：建客户 / 切换 / 删除 + 两模式聊天（流式 SSE / 同步）。
 * 「发消息」由 dashboard 代理到网关 api_server（客服 Agent 实际运行处）。整段用原生
 * DOM + Shadow DOM 实现，
 * 不依赖 React，样式与宿主页面完全隔离。
 *
 * 鉴权：同源（dashboard）下读取 `window.__HERMES_SESSION_TOKEN__` 与
 * `window.__HERMES_BASE_PATH__`；跨站嵌入可用 `data-token` / `data-api-base`
 * 显式指定。所有请求带 `credentials: include` 以兼容 cookie 门禁。
 *
 * 注意：本文件是**预构建的静态产物**（嵌入方不应被迫跑打包），随
 * `web_src/public/` 一并被 `npm run build` 拷入 `web_dist/`。
 */
(function () {
  "use strict";

  if (window.__HERMES_CHAT_WIDGET_LOADED__) return;
  window.__HERMES_CHAT_WIDGET_LOADED__ = true;

  // ── 配置（window 注入优先，其次脚本 data-* 属性）─────────────────────
  var SCRIPT =
    document.currentScript ||
    document.querySelector('script[src*="chat-widget.js"]');

  function attr(name, fallback) {
    var v = SCRIPT && SCRIPT.getAttribute(name);
    return v != null && v !== "" ? v : fallback;
  }

  var BASE = (function () {
    var b = window.__HERMES_BASE_PATH__ || attr("data-api-base", "") || "";
    if (!b) return "";
    if (!/^https?:/i.test(b) && b.charAt(0) !== "/") b = "/" + b;
    return b.replace(/\/+$/, "");
  })();
  var TOKEN = window.__HERMES_SESSION_TOKEN__ || attr("data-token", "") || "";
  var TITLE = attr("data-title", "在线客服");
  var SUBTITLE = attr("data-subtitle", "客服 Agent 实时应答");
  var ACCENT = attr("data-accent", "#2563eb");
  var DEFAULT_CHANNEL = attr("data-channel", "web");

  /** 预设全渠道（值=协议 channel，标签=UI 文案）。 */
  var CHANNELS = [
    { value: "wechat", label: "微信" },
    { value: "wecom", label: "企业微信" },
    { value: "wechat_channels", label: "视频号" },
    { value: "douyin", label: "抖音" },
    { value: "xhs", label: "小红书" },
    { value: "web", label: "官网" },
  ];
  function channelLabel(value) {
    for (var i = 0; i < CHANNELS.length; i++) {
      if (CHANNELS[i].value === value) return CHANNELS[i].label;
    }
    return value;
  }

  // ── 运行态 ──────────────────────────────────────────────────────────
  var state = {
    open: false,
    loaded: false,
    peers: [],
    selected: null, // {channel, uid, name}
    messages: [], // {role:'customer'|'agent', content}
    mode: "stream",
    sending: false,
    sendingPeer: null, // 正在回复的主体 {channel, uid}（用于跨主体切换时正确显示状态）
    queue: [], // 待发送队列 [{text, channel, uid}]：回复期间可继续发，按序投递
    error: null,
    showNewForm: false,
    newChannel: DEFAULT_CHANNEL,
  };

  // ── HTTP ────────────────────────────────────────────────────────────
  function apiFetch(path, init) {
    init = init || {};
    var headers = new Headers(init.headers || {});
    if (TOKEN && !headers.has("X-Hermes-Session-Token")) {
      headers.set("X-Hermes-Session-Token", TOKEN);
    }
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return fetch(BASE + path, {
      method: init.method || "GET",
      headers: headers,
      body: init.body,
      credentials: init.credentials || "include",
    });
  }
  async function apiJson(path, init) {
    var res = await apiFetch(path, init);
    if (!res.ok) {
      var t = await res.text().catch(function () {
        return res.statusText;
      });
      throw new Error(res.status + ": " + t);
    }
    return res.json();
  }

  var qs = function (o) {
    return Object.keys(o)
      .map(function (k) {
        return encodeURIComponent(k) + "=" + encodeURIComponent(o[k]);
      })
      .join("&");
  };

  var apiPeers = {
    list: function () {
      return apiJson("/api/customer-sim/peers");
    },
    create: function (channel, name) {
      return apiJson("/api/customer-sim/peers", {
        method: "POST",
        body: JSON.stringify({
          channel: channel,
          user_unique_id: null,
          user_display_name: name || null,
        }),
      });
    },
    messages: function (channel, uid) {
      return apiJson(
        "/api/customer-sim/peers/messages?" +
          qs({ channel: channel, user_unique_id: uid }),
      );
    },
    del: function (channel, uid) {
      return apiJson(
        "/api/customer-sim/peers?" + qs({ channel: channel, user_unique_id: uid }),
        { method: "DELETE" },
      );
    },
  };

  function chatOnce(endpoint, channel, uid, message) {
    return apiJson("/api/customer-sim/" + endpoint, {
      method: "POST",
      body: JSON.stringify({
        channel: channel,
        user_unique_id: uid,
        message: message,
      }),
    });
  }

  /**
   * SSE 流式：POST `/api/customer-sim/stream`，逐 token `data:{delta}`，末
   * `event:done {reply}`。POST 不能用 EventSource，故 fetch 流式读取并解析。
   */
  async function chatStream(channel, uid, message, handlers) {
    var res = await apiFetch("/api/customer-sim/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({
        channel: channel,
        user_unique_id: uid,
        message: message,
      }),
    });
    if (!res.ok || !res.body) {
      var text = await res.text().catch(function () {
        return res.statusText;
      });
      handlers.onError({ status: res.status, error: text || "请求失败" });
      return;
    }
    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buf = "";
    for (;;) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, { stream: true });
      var idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        var frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        var event = "message";
        var data = "";
        var lines = frame.split("\n");
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (line.indexOf("event:") === 0) event = line.slice(6).trim();
          else if (line.indexOf("data:") === 0) data += line.slice(5).trim();
        }
        if (!data) continue;
        var parsed;
        try {
          parsed = JSON.parse(data);
        } catch (e) {
          continue;
        }
        if (event === "done") handlers.onDone(parsed);
        else if (event === "error") handlers.onError(parsed);
        else handlers.onDelta((parsed && parsed.delta) || "");
      }
    }
  }

  // ── 工具 ────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
  function fmtTime(ts) {
    if (!ts) return "—";
    var d = new Date(ts * 1000);
    var now = new Date();
    var sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString([], { month: "2-digit", day: "2-digit" });
  }
  function toBubble(m) {
    return {
      role: m.role === "assistant" ? "agent" : "customer",
      content: m.content,
    };
  }

  // ── 样式（注入 Shadow DOM，与宿主页面隔离）──────────────────────────
  var CSS =
    ":host{all:initial}" +
    "*{box-sizing:border-box;font-family:system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif}" +
    ".launcher{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;z-index:2147483000;" +
    "background:var(--accent);color:#fff;box-shadow:0 6px 20px rgba(0,0,0,.28);display:flex;align-items:center;justify-content:center;transition:transform .15s ease,box-shadow .15s ease}" +
    ".launcher:hover{transform:translateY(-2px) scale(1.03);box-shadow:0 10px 26px rgba(0,0,0,.34)}" +
    ".launcher svg{width:26px;height:26px}" +
    ".panel{position:fixed;right:20px;bottom:88px;width:380px;max-width:calc(100vw - 32px);height:560px;max-height:calc(100vh - 120px);" +
    "z-index:2147483000;background:#fff;color:#1f2330;border-radius:16px;overflow:hidden;display:none;flex-direction:column;" +
    "box-shadow:0 18px 50px rgba(0,0,0,.30);opacity:0;transform:translateY(12px);transition:opacity .18s ease,transform .18s ease}" +
    ".panel.show{display:flex;opacity:1;transform:translateY(0)}" +
    ".hd{background:var(--accent);color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0}" +
    ".hd .avatar{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.22);display:flex;align-items:center;justify-content:center;flex-shrink:0}" +
    ".hd .avatar svg{width:18px;height:18px}" +
    ".hd .meta{min-width:0;flex:1}" +
    ".hd .title{font-size:14px;font-weight:600;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
    ".hd .sub{font-size:11px;opacity:.85;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
    ".hd button{background:transparent;border:none;color:#fff;cursor:pointer;opacity:.85;padding:4px;display:flex;border-radius:6px}" +
    ".hd button:hover{opacity:1;background:rgba(255,255,255,.16)}" +
    ".peerbar{display:flex;align-items:center;gap:6px;padding:8px 10px;border-bottom:1px solid #eceef2;background:#f7f8fa;flex-shrink:0}" +
    ".peerbar select{flex:1;min-width:0;font-size:12px;padding:5px 6px;border:1px solid #d7dbe2;border-radius:7px;background:#fff;color:#1f2330;outline:none}" +
    ".peerbar select:focus{border-color:var(--accent)}" +
    ".iconbtn{flex-shrink:0;width:28px;height:28px;border:1px solid #d7dbe2;border-radius:7px;background:#fff;color:#5a6172;cursor:pointer;display:flex;align-items:center;justify-content:center}" +
    ".iconbtn:hover{border-color:var(--accent);color:var(--accent)}" +
    ".iconbtn:disabled{opacity:.4;cursor:not-allowed}" +
    ".iconbtn svg{width:15px;height:15px}" +
    ".newform{display:none;flex-direction:column;gap:6px;padding:10px;border-bottom:1px solid #eceef2;background:#fbfcfd;flex-shrink:0}" +
    ".newform.show{display:flex}" +
    ".newform .row{display:flex;gap:6px}" +
    ".newform select,.newform input{font-size:12px;padding:6px;border:1px solid #d7dbe2;border-radius:7px;background:#fff;color:#1f2330;outline:none}" +
    ".newform select{flex-shrink:0}.newform input{flex:1;min-width:0}" +
    ".newform select:focus,.newform input:focus{border-color:var(--accent)}" +
    ".newform .create{border:none;border-radius:7px;background:var(--accent);color:#fff;font-size:12px;padding:6px 12px;cursor:pointer}" +
    ".body{flex:1;overflow-y:auto;padding:14px;background:#f2f4f7;display:flex;flex-direction:column;gap:10px}" +
    ".empty{margin:auto;text-align:center;color:#9aa1ad;font-size:12.5px;line-height:1.6;padding:0 20px}" +
    ".msg{display:flex;align-items:flex-start;gap:8px;max-width:100%}" +
    ".msg.customer{flex-direction:row-reverse}" +
    ".msg .ava{width:28px;height:28px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center}" +
    ".msg .ava svg{width:15px;height:15px}" +
    ".msg.agent .ava{background:#e4e7ec;color:#5a6172}" +
    ".msg.customer .ava{background:var(--accent);color:#fff}" +
    ".bubble{max-width:78%;padding:8px 11px;border-radius:12px;font-size:13px;line-height:1.55;white-space:pre-wrap;word-break:break-word}" +
    ".msg.agent .bubble{background:#fff;color:#1f2330;border-bottom-left-radius:4px;box-shadow:0 1px 2px rgba(0,0,0,.06)}" +
    ".msg.customer .bubble{background:var(--accent);color:#fff;border-bottom-right-radius:4px}" +
    ".bubble.placeholder{color:#9aa1ad}" +
    ".msg .col{display:flex;flex-direction:column;gap:2px;max-width:78%;align-items:flex-end}" +
    ".msg.pending .bubble{opacity:.6;font-style:italic;max-width:100%;border:1px dashed rgba(0,0,0,.18)}" +
    ".qtag{font-size:10px;color:#8a909c}" +
    ".qcount{justify-content:flex-end;color:#8a909c;font-style:italic}" +
    ".status{font-size:11.5px;color:#8a909c;padding:2px 4px;display:flex;align-items:center;gap:6px}" +
    ".dot{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:blink 1s infinite}" +
    "@keyframes blink{0%,100%{opacity:.3}50%{opacity:1}}" +
    ".err{font-size:11.5px;color:#b42318;background:#fef3f2;border-top:1px solid #fda29b;padding:7px 12px;flex-shrink:0}" +
    ".composer{display:flex;align-items:flex-end;gap:6px;padding:10px;border-top:1px solid #eceef2;background:#fff;flex-shrink:0}" +
    ".composer textarea{flex:1;min-width:0;resize:none;border:1px solid #d7dbe2;border-radius:9px;padding:8px 10px;font-size:13px;line-height:1.4;outline:none;max-height:96px;color:#1f2330;background:#fff}" +
    ".composer textarea:focus{border-color:var(--accent)}" +
    ".composer textarea:disabled{opacity:.5}" +
    ".composer select{flex-shrink:0;align-self:stretch;border:1px solid #d7dbe2;border-radius:9px;background:#fff;color:#5a6172;font-size:11px;padding:0 4px;outline:none}" +
    ".composer select:focus{border-color:var(--accent)}" +
    ".send{flex-shrink:0;width:38px;height:38px;border:none;border-radius:9px;background:var(--accent);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}" +
    ".send:disabled{opacity:.4;cursor:not-allowed}" +
    ".send svg{width:18px;height:18px}";

  // ── SVG 图标 ────────────────────────────────────────────────────────
  var ICON = {
    chat:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>',
    close:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    plus:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    trash:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    send:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
    user:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    agent:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11h2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H3zm16 0h2v6h-2a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2z"/><path d="M5 11a7 7 0 0 1 14 0"/><line x1="12" y1="18" x2="12" y2="21"/></svg>',
  };

  // ── DOM 构建 ────────────────────────────────────────────────────────
  var host = document.createElement("div");
  host.id = "hermes-chat-widget";
  var root = host.attachShadow({ mode: "open" });
  var style = document.createElement("style");
  style.textContent = CSS.replace(/var\(--accent\)/g, ACCENT);
  root.appendChild(style);

  function h(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  // 浮动气泡
  var launcher = h("button", "launcher", ICON.chat);
  launcher.setAttribute("aria-label", "打开在线客服");
  root.appendChild(launcher);

  // 面板骨架
  var panel = h("div", "panel");
  panel.innerHTML =
    '<div class="hd">' +
    '<div class="avatar">' +
    ICON.agent +
    "</div>" +
    '<div class="meta"><div class="title"></div><div class="sub"></div></div>' +
    '<button class="close" aria-label="关闭">' +
    ICON.close +
    "</button>" +
    "</div>" +
    '<div class="peerbar">' +
    "<select class=\"peersel\"></select>" +
    '<button class="iconbtn newbtn" title="新建客户">' +
    ICON.plus +
    "</button>" +
    '<button class="iconbtn delbtn" title="删除当前客户">' +
    ICON.trash +
    "</button>" +
    "</div>" +
    '<div class="newform">' +
    '<div class="row"><select class="nchan"></select>' +
    '<input class="nname" placeholder="客户名（可选）" /></div>' +
    '<button class="create">新建客户</button>' +
    "</div>" +
    '<div class="body"></div>' +
    '<div class="err" style="display:none"></div>' +
    '<div class="composer">' +
    '<textarea rows="1" placeholder="输入消息，Enter 发送"></textarea>' +
    '<select class="modesel" title="发送接口（对应网关 api_server 两形态）：&#10;流式=逐字 SSE 实时显示&#10;同步=一次性返回完整回复&#10;两者均可连发，前端自动排队按序投递">' +
    '<option value="stream">流式</option><option value="send">同步</option>' +
    "</select>" +
    '<button class="send" aria-label="发送">' +
    ICON.send +
    "</button>" +
    "</div>";
  root.appendChild(panel);

  // 引用
  var $ = function (sel) {
    return panel.querySelector(sel);
  };
  $(".title").textContent = TITLE;
  $(".sub").textContent = SUBTITLE;
  var peerSel = $(".peersel");
  var newBtn = $(".newbtn");
  var delBtn = $(".delbtn");
  var newForm = $(".newform");
  var nchan = $(".nchan");
  var nname = $(".nname");
  var createBtn = $(".create");
  var bodyEl = $(".body");
  var errEl = $(".err");
  var textarea = $(".composer textarea");
  var modeSel = $(".modesel");
  var sendBtn = $(".send");

  // 渠道下拉填充
  CHANNELS.forEach(function (c) {
    var o = document.createElement("option");
    o.value = c.value;
    o.textContent = c.label;
    nchan.appendChild(o);
  });
  nchan.value = state.newChannel;

  var streamingContentEl = null; // 流式时直接追加的气泡内容节点

  // ── 渲染 ────────────────────────────────────────────────────────────
  function renderPeers() {
    peerSel.innerHTML = "";
    if (state.peers.length === 0) {
      var o = document.createElement("option");
      o.textContent = "暂无客户 — 点 + 新建";
      o.value = "";
      peerSel.appendChild(o);
      peerSel.disabled = true;
      delBtn.disabled = true;
      return;
    }
    peerSel.disabled = false;
    delBtn.disabled = !state.selected;
    state.peers.forEach(function (p) {
      var o = document.createElement("option");
      o.value = p.channel + "|" + p.user_unique_id;
      o.textContent =
        channelLabel(p.channel) +
        " · " +
        p.user_display_name +
        " · " +
        fmtTime(p.last_active_at || p.created_at);
      peerSel.appendChild(o);
    });
    if (state.selected) {
      peerSel.value = state.selected.channel + "|" + state.selected.uid;
    }
  }

  function queuedHere() {
    if (!state.selected) return [];
    return state.queue.filter(function (item) {
      return (
        item.channel === state.selected.channel &&
        item.uid === state.selected.uid
      );
    });
  }

  function renderMessages() {
    bodyEl.innerHTML = "";
    streamingContentEl = null;
    if (!state.selected) {
      bodyEl.appendChild(
        h("div", "empty", "点上方 + 新建一位客户，或从下拉选择，开始对话。"),
      );
      return;
    }
    var busyHere =
      state.sending &&
      state.sendingPeer &&
      state.selected.channel === state.sendingPeer.channel &&
      state.selected.uid === state.sendingPeer.uid;
    var qhere = queuedHere();
    if (state.messages.length === 0 && !busyHere && qhere.length === 0) {
      bodyEl.appendChild(
        h("div", "empty", "以客户身份输入消息，开始与客服 Agent 对话。"),
      );
      return;
    }
    state.messages.forEach(function (m) {
      var row = h("div", "msg " + m.role);
      var ava = h("div", "ava", m.role === "customer" ? ICON.user : ICON.agent);
      var bubble = h("div", "bubble");
      if (m.role === "agent" && !m.content) {
        bubble.className = "bubble placeholder";
        bubble.textContent = "▍";
      } else {
        bubble.textContent = m.content;
      }
      row.appendChild(ava);
      row.appendChild(bubble);
      bodyEl.appendChild(row);
    });
    // 末条若是空 agent 气泡，记录其节点供流式追加
    var last = state.messages[state.messages.length - 1];
    if (last && last.role === "agent") {
      var rows = bodyEl.querySelectorAll(".msg.agent .bubble");
      streamingContentEl = rows[rows.length - 1] || null;
    }
    if (busyHere) {
      var st = h("div", "status");
      st.appendChild(h("span", "dot"));
      st.appendChild(document.createTextNode("客服 Agent 正在回复…"));
      bodyEl.appendChild(st);
    }
    // 排队中（仅当前主体）：尾部显示淡色「排队中」客户气泡 + 计数。
    qhere.forEach(function (item) {
      var row = h("div", "msg customer pending");
      var ava = h("div", "ava", ICON.user);
      var col = h("div", "col");
      var bubble = h("div", "bubble");
      bubble.textContent = item.text;
      col.appendChild(bubble);
      col.appendChild(h("div", "qtag", "⏳ 排队中"));
      row.appendChild(ava);
      row.appendChild(col);
      bodyEl.appendChild(row);
    });
    if (qhere.length > 1) {
      bodyEl.appendChild(
        h("div", "status qcount", "队列：" + qhere.length + " 条待发送，将按序自动发送"),
      );
    }
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  function setError(msg) {
    state.error = msg || null;
    if (msg) {
      errEl.textContent = msg;
      errEl.style.display = "";
    } else {
      errEl.style.display = "none";
    }
  }

  function updateSendBtn() {
    // 发送按钮只看「有主体 + 有文字」——回复期间也允许继续入队发送。
    sendBtn.disabled = !state.selected || !textarea.value.trim();
  }
  function setComposerEnabled() {
    // 输入框只在「未选主体」时禁用；回复期间保持可输入。
    textarea.disabled = !state.selected;
    updateSendBtn();
  }
  function setSending(v) {
    state.sending = v;
    setComposerEnabled();
  }

  // ── 行为 ────────────────────────────────────────────────────────────
  async function loadPeers() {
    try {
      var res = await apiPeers.list();
      state.peers = res.peers || [];
      renderPeers();
      return state.peers;
    } catch (e) {
      setError(e.message || String(e));
      return [];
    }
  }

  // 每轮发完只需把当前客户的「活跃时间」刷成现在并重渲染下拉，无需重拉整张 peers 列表。
  function bumpPeerActive(channel, uid) {
    for (var i = 0; i < state.peers.length; i++) {
      if (
        state.peers[i].channel === channel &&
        state.peers[i].user_unique_id === uid
      ) {
        state.peers[i].last_active_at = Date.now() / 1000;
        renderPeers();
        return;
      }
    }
    void loadPeers(); // 本地列表没有该客户（异常）→ 兜底拉一次
  }

  async function selectPeer(channel, uid) {
    var p = null;
    for (var i = 0; i < state.peers.length; i++) {
      if (
        state.peers[i].channel === channel &&
        state.peers[i].user_unique_id === uid
      ) {
        p = state.peers[i];
        break;
      }
    }
    state.selected = {
      channel: channel,
      uid: uid,
      name: p ? p.user_display_name : uid,
    };
    setError(null);
    state.messages = [];
    renderPeers();
    renderMessages();
    // 切换主体只刷新输入区可用态；不动全局 sending（别的主体可能仍在回复）。
    setComposerEnabled();
    try {
      var res = await apiPeers.messages(channel, uid);
      state.messages = (res.messages || []).map(toBubble);
      renderMessages();
    } catch (e) {
      setError(e.message || String(e));
    }
  }

  async function createPeer() {
    try {
      var name = nname.value.trim();
      var peer = await apiPeers.create(state.newChannel, name || undefined);
      nname.value = "";
      newForm.classList.remove("show");
      state.showNewForm = false;
      await loadPeers();
      await selectPeer(peer.channel, peer.user_unique_id);
      textarea.focus();
    } catch (e) {
      setError(e.message || String(e));
    }
  }

  async function deleteCurrent() {
    if (!state.selected) return;
    var sel = state.selected;
    try {
      await apiPeers.del(sel.channel, sel.uid);
      var list = await loadPeers();
      state.messages = [];
      if (list.length > 0) {
        await selectPeer(list[0].channel, list[0].user_unique_id);
      } else {
        state.selected = null;
        renderPeers();
        renderMessages();
      }
    } catch (e) {
      setError(e.message || String(e));
    }
  }

  function submitText() {
    var text = textarea.value.trim();
    if (!text || !state.selected) return;
    // 客户端串行队列：回复期间也能继续发，消息按序投递；同一主体不并发轮次
    // （后端每主体单 agent 实例，并发会话会相互踩踏）。
    state.queue.push({
      text: text,
      channel: state.selected.channel,
      uid: state.selected.uid,
    });
    textarea.value = "";
    autoGrow();
    renderMessages(); // 立刻把这条显示为「排队中」气泡（若当前空闲会被 drainQueue 即时转为发送中）
    drainQueue();
  }

  async function drainQueue() {
    if (state.sending) return; // 正在回复 → 此条已入队，待当前轮结束后自动续发
    var item = state.queue.shift();
    if (!item) return;
    var channel = item.channel;
    var uid = item.uid;
    var text = item.text;

    function isCurrent() {
      return (
        !!state.selected &&
        state.selected.channel === channel &&
        state.selected.uid === uid
      );
    }
    // 仅当该轮主体仍是当前视图时才改动气泡；切走了则后台静默跑完并入库，
    // 切回该主体重新拉历史即可看到。
    function applyAgent(fn) {
      if (!isCurrent()) return;
      var last = state.messages[state.messages.length - 1];
      if (last && last.role === "agent") fn(last);
    }

    if (isCurrent()) {
      state.messages.push({ role: "customer", content: text });
      state.messages.push({ role: "agent", content: "" });
    }
    setError(null);
    state.sendingPeer = { channel: channel, uid: uid };
    setSending(true);
    renderMessages();

    var failed = false;
    try {
      if (state.mode === "stream") {
        await chatStream(channel, uid, text, {
          onDelta: function (d) {
            applyAgent(function (last) {
              last.content += d;
              if (streamingContentEl) {
                if (streamingContentEl.classList.contains("placeholder")) {
                  streamingContentEl.classList.remove("placeholder");
                  streamingContentEl.textContent = "";
                }
                streamingContentEl.textContent = last.content;
                bodyEl.scrollTop = bodyEl.scrollHeight;
              }
            });
          },
          onDone: function (p) {
            applyAgent(function (last) {
              last.content = (p && p.reply) || last.content || "（无回复）";
            });
          },
          onError: function (p) {
            failed = true;
            setError((p && p.error) || "请求失败");
          },
        });
      } else {
        var res = await chatOnce(state.mode, channel, uid, text);
        applyAgent(function (last) {
          last.content = (res && res.reply) || "（无回复）";
        });
      }
    } catch (e) {
      failed = true;
      setError(e.message || String(e));
    }

    state.sendingPeer = null;
    setSending(false);
    if (failed) {
      if (isCurrent()) state.messages = state.messages.slice(0, -2);
      state.queue = []; // 失败则清空后续排队，避免连环失败
      if (!textarea.value.trim()) {
        textarea.value = text; // 把这条放回输入框（仅当你没在打新的字）
        autoGrow();
      }
    } else {
      bumpPeerActive(channel, uid); // 本地刷新活跃时间，不每轮拉 peers
    }
    renderMessages();
    if (!failed) drainQueue(); // 接着发队列里的下一条
  }

  function autoGrow() {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 96) + "px";
    updateSendBtn();
  }

  function togglePanel(open) {
    state.open = open == null ? !state.open : open;
    panel.classList.toggle("show", state.open);
    if (state.open) {
      if (!state.loaded) {
        state.loaded = true;
        loadPeers().then(function (list) {
          if (list.length > 0 && !state.selected) {
            selectPeer(list[0].channel, list[0].user_unique_id);
          } else {
            renderMessages();
          }
        });
      }
      setTimeout(function () {
        textarea.focus();
      }, 60);
    }
  }

  // ── 事件 ────────────────────────────────────────────────────────────
  launcher.addEventListener("click", function () {
    togglePanel();
  });
  $(".close").addEventListener("click", function () {
    togglePanel(false);
  });
  peerSel.addEventListener("change", function () {
    var v = peerSel.value;
    if (!v) return;
    var sep = v.indexOf("|");
    selectPeer(v.slice(0, sep), v.slice(sep + 1));
  });
  newBtn.addEventListener("click", function () {
    state.showNewForm = !state.showNewForm;
    newForm.classList.toggle("show", state.showNewForm);
    if (state.showNewForm) nname.focus();
  });
  delBtn.addEventListener("click", function () {
    deleteCurrent();
  });
  nchan.addEventListener("change", function () {
    state.newChannel = nchan.value;
  });
  nname.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      createPeer();
    }
  });
  createBtn.addEventListener("click", function () {
    createPeer();
  });
  modeSel.addEventListener("change", function () {
    state.mode = modeSel.value;
  });
  textarea.addEventListener("input", autoGrow);
  textarea.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitText();
    }
  });
  sendBtn.addEventListener("click", function () {
    submitText();
  });

  // 初始渲染
  renderPeers();
  renderMessages();

  function mount() {
    if (!document.body) {
      setTimeout(mount, 30);
      return;
    }
    document.body.appendChild(host);
  }
  mount();
})();
