// Backlot project board — renders BoardState and stays live via SSE.

import {
  STAGE_ICONS, brandMark, el, fmtAgo, fmtClock, fmtDuration, fmtMoney,
  getJSON, mediaURL, pageURL, pinMediaElements, postJSON, releaseUnusedPinnedMedia,
  subscribe, takePinnedMedia, thumbURL, waveBars,
} from "/ui/lib.js";
import {
  artifactLabel, decisionCategoryLabel, decisionSubjectLabel, stageLabel, statusLabel, t, toolLabel,
} from "/ui/i18n.js";
import { openProjectSettings } from "/ui/project-settings.js";
import { renderSourceMediaSection } from "/ui/source-media-preview.js";
import { applyPreferences, readLocalPreferences, renderThemeToggle } from "/ui/preferences.js";

const rawProjectPath = location.pathname.split("/p/")[1] || "";
const projectId = decodeURIComponent(rawProjectPath);
const encodedProjectId = encodeURIComponent(projectId);
const app = document.getElementById("app");
const modal = document.getElementById("modal");
const player = document.getElementById("player");

readLocalPreferences();
getJSON("/api/settings").then(applyPreferences).catch(() => {});

let state = null;
let selectedStage = null;   // stage drawer — separate from project summary
let activeRender = 0;
let replay = null;          // {t0, t1, t, playing} — replay mode when non-null
let firstPaint = true;
let summaryOpenItem = null;
let selectedEditCutIndex = 0;
let selectedEditNode = { track: "cut", index: 0 };
let editPlayheadSeconds = 0;
let editPreviewPlaying = false;
let editNarrationPlaying = false;
let editPreviewRafId = null;
let editNleRuntime = null;
let editPreviewLastCutKey = null;
let nleDraft = null;       // {cuts, overlays} — in-memory timeline edit (not yet applied)
let nleDirty = false;      // true when nleDraft differs from canonical edit_decisions
let nleDraftRestored = false; // one-shot guard for restoring drafts after reload
let editPreviewAudio = null;

function renderThemeToggleInBoard() {
  return renderThemeToggle(() => render());
}

function renderSlate(s) {
  const board = s.storyboard;
  const chips = [
    el("span", { class: "chip" }, s.pipeline.label_zh || s.pipeline.pipeline_type || t("unknown")),
    board && board.total_duration_seconds
      ? el("span", { class: "chip" }, t("scenesDuration", {
        n: board.scenes.length,
        dur: fmtDuration(board.total_duration_seconds),
      }))
      : null,
    s.style_playbook
      ? el("span", { class: "chip" }, s.style_playbook_label_zh || s.style_playbook)
      : null,
    s.deliverable?.resolution
      ? el("span", { class: "chip" }, `${s.deliverable.resolution} · ${s.deliverable.aspect_ratio || ""}`)
      : null,
  ];

  const awaiting = s.stages.find((x) => x.status === "awaiting_human");
  const inProgress = s.stages.find((x) => x.status === "in_progress");
  const stalled = s.stages.find((x) => x.stalled);
  const pipelineIdle = s.stages.some((x) => x.name === "compose" && x.status === "completed")
    && !s.stages.some((x) => !x.undeclared && (x.status === "in_progress" || x.status === "awaiting_human"));
  const productionActive = typeof s.production_active === "boolean"
    ? (s.production_active || Boolean(inProgress || awaiting))
    : (Boolean(inProgress || awaiting) || (Boolean(s.live) && !pipelineIdle));
  let liveEl;
  if (awaiting) {
    liveEl = el("span", { class: "live" }, el("span", { class: "dot" }), t("awaitingYou"));
  } else if (stalled) {
    liveEl = el("span", { class: "live", style: "color:var(--red)" },
      el("span", { class: "dot", style: "background:var(--red);animation:none" }), t("stalled"));
  } else if (productionActive) {
    liveEl = el("span", { class: "live" }, el("span", { class: "dot" }), t("live"));
  } else {
    liveEl = el("span", { class: "live idle" }, el("span", { class: "dot" }),
      `${t("idle")}${s.last_activity ? " · " + fmtAgo(s.last_activity) : ""}`);
  }

  const cost = el("div", { class: "cost" });
  if (s.cost) {
    const spent = s.cost.total_spent_usd ?? 0;
    const budget = spent + (s.cost.budget_remaining_usd ?? 0);
    const hasBudget = s.cost.budget_remaining_usd != null;
    const pct = hasBudget && budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
    cost.append(el("div", { class: "nums" }, el("b", {}, fmtMoney(spent)),
      hasBudget ? el("span", {}, ` / ${fmtMoney(budget)}`) : ""));
    if (hasBudget) {
      cost.append(el("div", { class: "bar" }, el("i", {
        class: pct > 90 ? "crit" : pct > 75 ? "warn" : "", style: `width:${pct}%`,
      })));
    }
    cost.append(el("div", { class: "label" }, t("generationSpend")));
  }

  return el("header", { class: "slate slate-board" },
    el("div", { class: "slate-brand" },
      brandMark(),
      el("div", { class: "board-intro" },
        el("a", { class: "wordmark backlink", href: pageURL("/") }, t("backlot")),
        el("h1", {}, s.title),
        chips.length ? el("div", { class: "slate-chips" }, ...chips) : null,
      ),
    ),
    el("div", { class: "slate-actions" },
      el("a", {
        class: "board-settings-btn",
        href: pageURL(`/flow/${encodeURIComponent(projectId)}`),
        title: t("flowViewTitle"),
      }, t("flowView")),
      el("button", {
        class: "board-settings-btn board-summary-btn",
        type: "button",
        onclick: openProjectSummaryModal,
        title: t("projectSummaryLead"),
      }, t("projectSummaryTitle")),
      el("button", {
        class: "board-settings-btn",
        type: "button",
        onclick: openBoardSettings,
      }, t("projectSettings")),
      renderThemeToggleInBoard(),
      liveEl,
      s.cost ? cost : null,
    ),
  );
}

// ---------------------------------------------------------------------------
// stage rail
// ---------------------------------------------------------------------------

function stageOutputLine(st) {
  const names = artifactNamesForStage(st).filter((n) => n !== "decision_log");
  if (!names.length) return "";
  return names.map((n) => artifactLabel(n)).join(" · ");
}

function stageSub(st) {
  const outputs = stageOutputLine(st);
  // Completed stages: show outputs only — timestamp adds noise on the rail.
  if (st.status === "completed" && outputs) return outputs;

  let hint = "";
  if (st.status === "awaiting_human") hint = t("awaitingApprovalHint");
  else if (st.status === "in_progress" && st.stalled) {
    hint = t("stalledDetail", { n: st.stalled_minutes });
  } else if (st.status === "in_progress" && st.partial_progress) {
    const done = st.partial_progress.completed_scene_ids;
    hint = Array.isArray(done) ? t("scenesDone", { n: done.length }) : t("inProgress");
  } else if (st.status === "in_progress") hint = t("inProgress");
  else if (st.status === "failed") {
    hint = st.error ? String(st.error).slice(0, 60) : t("failed");
  } else if (st.blocked_by_upstream) {
    hint = t("blockedByUpstreamHint");
  } else if (st.timestamp) {
    const approved = st.gated && st.human_approved ? t("approvedSuffix") : "";
    hint = fmtClock(st.timestamp) + approved;
  }
  if (hint && outputs) return `${hint}\n${outputs}`;
  if (outputs) return outputs;
  return hint;
}

function railStatusLabel(st) {
  if (st.stalled) return t("stalledRail");
  if (st.is_next && (st.status === "pending" || !st.status)) return statusLabel("pendingNext");
  return statusLabel(st.status || "pending");
}

function renderRail(s) {
  const rail = el("nav", { class: "rail" });
  let pendingIndex = 1;
  for (const st of s.stages) {
    const cls = st.status === "completed" ? "done"
      : st.status === "in_progress" ? (st.stalled ? "active stalled" : "active")
      : st.status === "awaiting_human" ? "await"
      : st.status === "failed" ? "failed"
      : st.is_next ? "next"
      : "pending";
    const icon = STAGE_ICONS[st.status] || String(pendingIndex);
    if (!STAGE_ICONS[st.status]) pendingIndex += 1;
    const statusCls = st.stalled ? "stalled"
      : st.status === "completed" ? "done"
      : st.status === "in_progress" ? "active"
      : st.status === "awaiting_human" ? "await"
      : st.status === "failed" ? "failed"
      : st.is_next ? "next"
      : "pending";
    const node = el("div", {
      class: `stage ${cls}${selectedStage === st.name ? " selected" : ""}${st.undeclared ? " undeclared" : ""}`,
      title: st.undeclared ? t("undeclaredStage", { name: st.name }) : null,
      onclick: () => toggleDrawer(st.name),
    },
      el("span", { class: "line" }),
      el("div", { class: "stage-marker" },
        el("span", { class: `stage-status stage-status--${statusCls}` }, railStatusLabel(st)),
        el("span", { class: "node" }, icon),
      ),
      el("span", { class: "name" }, stageLabel(st.name)),
      el("span", { class: "sub", style: "white-space:pre-line" },
        st.undeclared ? `${stageSub(st)}\n${t("unlisted")}`.trim() : stageSub(st)),
    );
    rail.append(node);
  }
  return el("div", { class: "rail-shell" }, rail);
}

function toggleDrawer(stageName) {
  if (stageName !== selectedStage && stageName === "edit") {
    selectedEditCutIndex = 0;
    selectedEditNode = { track: "cut", index: 0 };
    editPlayheadSeconds = 0;
    editPreviewPlaying = false;
    editNarrationPlaying = false;
    stopEditPreviewClock();
  }
  selectedStage = selectedStage === stageName ? null : stageName;
  render();
}

function selectEditNode(track, index, startAt, { keepPlaying = false } = {}) {
  selectedEditNode = { track, index };
  if (track === "cut") selectedEditCutIndex = index;
  if (startAt != null) editPlayheadSeconds = startAt;
  if (!keepPlaying) {
    editPreviewPlaying = false;
    editNarrationPlaying = false;
    stopEditPreviewClock();
    ensureEditPreviewAudio().pause();
  }
  editPreviewLastCutKey = null;
  render();
}

function selectEditCut(index) {
  const artifact = state?.artifacts?.edit_decisions;
  const cuts = artifact?.cuts || [];
  const clipMeta = buildEditClipMeta(cuts, artifact || {});
  const start = clipMeta[index]?.start ?? 0;
  selectEditNode("cut", index, start);
}

function setEditNleRuntime(ctx) {
  editNleRuntime = ctx;
  editPreviewLastCutKey = null;
}

function ensureEditPreviewAudio() {
  if (!editPreviewAudio) {
    editPreviewAudio = document.createElement("audio");
    editPreviewAudio.className = "edit-nle-preview-audio";
    editPreviewAudio.preload = "metadata";
    document.body.append(editPreviewAudio);
    editPreviewAudio.addEventListener("ended", () => {
      if (editNarrationPlaying) {
        editNarrationPlaying = false;
      } else if (editPreviewPlaying) {
        editPreviewPlaying = false;
        stopEditPreviewClock();
      }
      syncEditPlayheadUI(true);
    });
  }
  return editPreviewAudio;
}

/** Match remotion-composer CaptionOverlay: show the full caption page, not active words only. */
function remotionCaptionPageAtPlayhead(artifact, seconds) {
  const props = resolveCompositionProps(artifact);
  const captions = props.captions || [];
  if (!captions.length || captions[0]?.startMs == null) return null;
  const ms = seconds * 1000;
  const pages = buildCaptionPages(captions, 6);
  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    const pageStart = Number(page.words[0]?.startMs) || 0;
    const pageEnd = Number(page.words[page.words.length - 1]?.endMs) || pageStart;
    const visibleEnd = i + 1 < pages.length
      ? Number(pages[i + 1].words[0]?.startMs) || pageEnd
      : pageEnd + 500;
    if (ms >= pageStart && ms < visibleEnd) {
      return page;
    }
  }
  return null;
}

function remotionCaptionAtPlayhead(artifact, seconds) {
  const page = remotionCaptionPageAtPlayhead(artifact, seconds);
  if (!page) return "";
  return page.words.map((w) => w.word || "").join("");
}

function scriptCaptionAtPlayhead(captionTracks, seconds) {
  for (const item of captionTracks.detail.length ? captionTracks.detail : captionTracks.summary) {
    const start = Number(item.start) || 0;
    const end = start + (Number(item.duration) || 0);
    if (seconds >= start && seconds < end) {
      return item.text || item.label || "";
    }
  }
  return "";
}

function resolveEditPreviewCaption(artifact, seconds, captionTracks) {
  const overlay = overlayAtPlayhead(artifact, seconds);
  const scriptCaption = scriptCaptionAtPlayhead(captionTracks, seconds);
  const remotionCaption = remotionCaptionAtPlayhead(artifact, seconds);
  if (scriptCaption) {
    return { captionText: scriptCaption, overlayLabel: overlay?.text || "" };
  }
  if (remotionCaption) {
    return { captionText: remotionCaption, overlayLabel: overlay?.text || "" };
  }
  return {
    captionText: overlay?.text || "",
    overlayLabel: "",
  };
}

function updateEditPreviewCaption(artifact, captionTracks) {
  let { captionText, overlayLabel } = resolveEditPreviewCaption(
    artifact,
    editPlayheadSeconds,
    captionTracks,
  );
  if (!captionText && selectedEditNode.track === "overlay") {
    const layer = editNleRuntime?.composition?.layers?.find((item) => item.id === "overlays");
    const node = layer?.nodes?.[selectedEditNode.index];
    captionText = node?.data?.text || node?.label || "";
  }
  if (!captionText && selectedEditNode.track.startsWith("caption")) {
    const list = selectedEditNode.track === "caption-detail"
      ? captionTracks.detail
      : captionTracks.summary;
    captionText = list[selectedEditNode.index]?.text || list[selectedEditNode.index]?.label || "";
  }
  const stage = document.querySelector(".edit-nle-preview-stage");
  if (!stage) return;
  let capEl = stage.querySelector(".edit-nle-preview-caption");
  let overlayEl = stage.querySelector(".edit-nle-preview-overlay");
  if (captionText) {
    if (!capEl) {
      capEl = el("div", { class: "edit-nle-preview-caption" });
      stage.append(capEl);
    }
    capEl.textContent = captionText;
  } else if (capEl) {
    capEl.remove();
  }
  if (overlayLabel) {
    if (!overlayEl) {
      overlayEl = el("div", { class: "edit-nle-preview-overlay" });
      stage.append(overlayEl);
    }
    overlayEl.textContent = overlayLabel;
  } else if (overlayEl) {
    overlayEl.remove();
  }
}

function updateEditPreviewStage(s, artifact, clipMeta, captionTracks, active) {
  const stage = document.querySelector(".edit-nle-preview-stage");
  if (!stage || !active) return;
  const asset = findManifestAsset(s, active.cut.source);
  let mediaWrap = stage.querySelector(".edit-nle-preview-media");
  stage.querySelector(".edit-nle-preview-empty")?.remove();
  if (!mediaWrap) {
    mediaWrap = el("div", { class: "edit-nle-preview-media" });
    stage.prepend(mediaWrap);
  }
  mediaWrap.replaceChildren();
  if (asset && (isImageMedia(asset) || isVideoMedia(asset))) {
    mediaWrap.append(buildMediaPreview(s, asset, { variant: "full", chromeless: true }));
  }
  const metaEl = document.querySelector(".edit-nle-transport-meta");
  if (metaEl) {
    metaEl.textContent = [
      active.cut.reason || active.cut.id || t("item", { n: active.index + 1 }),
      `${fmtTimelineClock(active.start)} – ${fmtTimelineClock(active.start + active.duration)}`,
    ].join(" · ");
  }
  updateEditPreviewCaption(artifact, captionTracks);
}

function syncEditPlayheadUI(refreshTransport = false) {
  const ctx = editNleRuntime;
  if (!ctx) return;
  const { totalSeconds, clipMeta, artifact, captionTracks, s } = ctx;
  const pct = Math.min(100, (editPlayheadSeconds / Math.max(totalSeconds, 0.001)) * 100);
  const playhead = document.querySelector(".edit-nle-editor .nle-playhead");
  if (playhead) playhead.style.left = `${pct}%`;
  const timeText = `${fmtTimelineClock(editPlayheadSeconds)} / ${fmtTimelineClock(totalSeconds)}`;
  document.querySelectorAll(".edit-decisions-inline .edit-nle-transport-time").forEach((timeEl) => {
    timeEl.textContent = timeText;
  });
  if (refreshTransport) {
    const playTitle = editPreviewPlaying ? t("editPreviewPause") : t("editPreviewPlayTimeline");
    document.querySelectorAll(".edit-decisions-inline .nle-play-btn").forEach((btn) => {
      btn.classList.toggle("is-playing", editPreviewPlaying);
      btn.innerHTML = editPreviewPlaying ? NLE_TRANSPORT_SVG.pause : NLE_TRANSPORT_SVG.play;
      btn.title = playTitle;
      btn.setAttribute("aria-label", playTitle);
    });
    const narrTitle = editNarrationPlaying ? t("editNarrationPause") : t("editNarrationPlay");
    document.querySelectorAll(".edit-decisions-inline .nle-block-play-btn--narr").forEach((btn) => {
      btn.classList.toggle("is-playing", editNarrationPlaying);
      btn.innerHTML = editNarrationPlaying ? NLE_TRANSPORT_SVG.pause : NLE_TRANSPORT_SVG.play;
      btn.title = narrTitle;
      btn.setAttribute("aria-label", narrTitle);
    });
  }
  const active = cutAtPlayhead(clipMeta, editPlayheadSeconds)
    || clipMeta[selectedEditCutIndex]
    || null;
  const cutKey = active ? `${active.index}:${active.cut.source}` : "";
  if (cutKey !== editPreviewLastCutKey) {
    editPreviewLastCutKey = cutKey;
    if (active) updateEditPreviewStage(s, artifact, clipMeta, captionTracks, active);
  } else {
    updateEditPreviewCaption(artifact, captionTracks);
  }
}

function stopEditPreviewClock() {
  if (editPreviewRafId != null) {
    cancelAnimationFrame(editPreviewRafId);
    editPreviewRafId = null;
  }
}

function startEditPreviewClock(totalSeconds) {
  stopEditPreviewClock();
  const t0 = performance.now();
  const start = editPlayheadSeconds;
  const tick = () => {
    if (!editPreviewPlaying) return;
    const elapsed = (performance.now() - t0) / 1000;
    editPlayheadSeconds = Math.min(totalSeconds, start + elapsed);
    if (editPlayheadSeconds >= totalSeconds) {
      editPreviewPlaying = false;
      syncEditPlayheadUI(true);
      return;
    }
    syncEditPlayheadUI();
    editPreviewRafId = requestAnimationFrame(tick);
  };
  editPreviewRafId = requestAnimationFrame(tick);
}

function resetEditNarrationPlaybackState() {
  editNarrationPlaying = false;
}

function pauseEditNarrationPlayback() {
  resetEditNarrationPlaybackState();
  if (!editPreviewPlaying) ensureEditPreviewAudio().pause();
  syncEditPlayheadUI(true);
}

function pauseEditPreviewPlayback() {
  editPreviewPlaying = false;
  resetEditNarrationPlaybackState();
  stopEditPreviewClock();
  ensureEditPreviewAudio().pause();
  syncEditPlayheadUI(true);
}

/** Play narration audio only — does not drive timeline playhead or video preview. */
function startEditNarrationPlayback() {
  pauseEditPreviewPlayback();
  editNarrationPlaying = true;
  const audioEl = ensureEditPreviewAudio();
  const narrSrc = resolveNarrationSrc(editNleRuntime?.s, editNleRuntime?.artifact);
  if (narrSrc && editNleRuntime?.s) {
    audioEl.src = mediaURL(editNleRuntime.s.project_id, narrSrc);
    audioEl.currentTime = editPlayheadSeconds;
    audioEl.play().catch(() => {
      editNarrationPlaying = false;
      syncEditPlayheadUI(true);
    });
  } else {
    editNarrationPlaying = false;
  }
  syncEditPlayheadUI(true);
}

function toggleEditNarrationPlayback() {
  if (editNarrationPlaying) pauseEditNarrationPlayback();
  else startEditNarrationPlayback();
}

/** Drive playhead + preview from narration while timeline transport is playing. */
function startEditPreviewAudioSyncLoop(totalSeconds, audioEl) {
  stopEditPreviewClock();
  const tick = () => {
    if (!editPreviewPlaying) return;
    if (audioEl && !audioEl.paused && !audioEl.ended) {
      editPlayheadSeconds = Math.min(audioEl.currentTime, totalSeconds);
      if (editPlayheadSeconds >= totalSeconds - 0.02) {
        pauseEditPreviewPlayback();
        return;
      }
      syncEditPlayheadUI();
    }
    editPreviewRafId = requestAnimationFrame(tick);
  };
  editPreviewRafId = requestAnimationFrame(tick);
}

function startEditPreviewPlayback(totalSeconds) {
  resetEditNarrationPlaybackState();
  editPreviewPlaying = true;
  const audioEl = ensureEditPreviewAudio();
  const narrSrc = resolveNarrationSrc(editNleRuntime?.s, editNleRuntime?.artifact);
  if (narrSrc && editNleRuntime?.s) {
    audioEl.src = mediaURL(editNleRuntime.s.project_id, narrSrc);
    audioEl.currentTime = editPlayheadSeconds;
    audioEl.play()
      .then(() => startEditPreviewAudioSyncLoop(totalSeconds, audioEl))
      .catch(() => startEditPreviewClock(totalSeconds));
  } else {
    startEditPreviewClock(totalSeconds);
  }
  syncEditPlayheadUI(true);
}

function toggleEditPreviewPlay(totalSeconds) {
  if (editPreviewPlaying) pauseEditPreviewPlayback();
  else startEditPreviewPlayback(totalSeconds);
}

let editNlePlaybackKeysBound = false;
function ensureEditNlePlaybackKeys() {
  if (editNlePlaybackKeysBound) return;
  editNlePlaybackKeysBound = true;
  document.addEventListener("keydown", (event) => {
    if (event.code !== "Space" && event.key !== " ") return;
    if (!document.querySelector(".edit-nle-editor") || !editNleRuntime) return;
    if (event.target.closest("input, textarea, select, [contenteditable=true], .modal.open")) return;
    event.preventDefault();
    toggleEditPreviewPlay(editNleRuntime.totalSeconds);
  });
}

const NLE_TRANSPORT_SVG = {
  play: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 5h4v14H6zm8 0h4v14h-4z" fill="currentColor"/></svg>',
  toStart: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" fill="currentColor"/></svg>',
  stepBack: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M11 7v10l-7-5 7-5zm2 0v10l7-5-7-5z" fill="currentColor"/></svg>',
  stepForward: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 7v10l7-5-7-5zm9 0v10l7-5-7-5z" fill="currentColor"/></svg>',
  toEnd: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M16 6h2v12h-2zm-3.5 6-8.5 6V6z" fill="currentColor"/></svg>',
};

function nleTransportButton(className, title, svg, onClick) {
  const btn = el("button", {
    type: "button",
    class: `nle-transport-btn ${className}`.trim(),
    title,
    onclick: (event) => {
      event.stopPropagation();
      onClick();
    },
  });
  btn.innerHTML = svg;
  return btn;
}

function isEditAudioSelected(layer) {
  if (layer?.kind !== "audio" || !layer.nodes?.length) return false;
  const node = layer.nodes[0];
  return selectedEditNode.track === node.track && selectedEditNode.index === node.index;
}

function renderNleMonitorPlayButton(totalSeconds) {
  const playing = editPreviewPlaying;
  const btn = el("button", {
    type: "button",
    class: `nle-transport-btn nle-transport-btn--play nle-play-btn${playing ? " is-playing" : ""}`,
    title: playing ? t("editPreviewPause") : t("editPreviewPlayTimeline"),
    "aria-label": playing ? t("editPreviewPause") : t("editPreviewPlayTimeline"),
    onclick: (event) => {
      event.stopPropagation();
      toggleEditPreviewPlay(totalSeconds);
    },
  });
  btn.innerHTML = playing ? NLE_TRANSPORT_SVG.pause : NLE_TRANSPORT_SVG.play;
  return btn;
}

function renderEditNleTransportBar(clipMeta, totalSeconds) {
  const step = 1;
  const controls = el("div", { class: "nle-transport-group", role: "group", "aria-label": t("editPreviewPlayTimeline") },
    nleTransportButton("nle-transport-btn--jump", t("editTransportStart"), NLE_TRANSPORT_SVG.toStart,
      () => seekEditPlayhead(0, totalSeconds)),
    nleTransportButton("nle-transport-btn--step", t("editTransportBack"), NLE_TRANSPORT_SVG.stepBack,
      () => seekEditPlayhead(Math.max(0, editPlayheadSeconds - step), totalSeconds)),
    renderNleMonitorPlayButton(totalSeconds),
    nleTransportButton("nle-transport-btn--step", t("editTransportForward"), NLE_TRANSPORT_SVG.stepForward,
      () => seekEditPlayhead(Math.min(totalSeconds, editPlayheadSeconds + step), totalSeconds)),
    nleTransportButton("nle-transport-btn--jump", t("editTransportEnd"), NLE_TRANSPORT_SVG.toEnd,
      () => seekEditPlayhead(totalSeconds, totalSeconds)),
  );
  const bar = el("div", { class: "nle-transport-bar" },
    controls,
    el("div", { class: "nle-transport-timecode" },
      el("span", { class: "edit-nle-transport-time" },
        `${fmtTimelineClock(editPlayheadSeconds)} / ${fmtTimelineClock(totalSeconds)}`),
    ),
  );
  const active = cutAtPlayhead(clipMeta, editPlayheadSeconds)
    || clipMeta[selectedEditCutIndex]
    || null;
  if (active?.cut) {
    bar.append(el("span", { class: "edit-nle-transport-meta" }, [
      active.cut.reason || active.cut.id || t("item", { n: active.index + 1 }),
      `${fmtTimelineClock(active.start)} – ${fmtTimelineClock(active.start + active.duration)}`,
    ].join(" · ")));
  }
  return bar;
}

function cutAtPlayhead(clipMeta, seconds) {
  for (let i = clipMeta.length - 1; i >= 0; i--) {
    const clip = clipMeta[i];
    if (seconds >= clip.start && seconds < clip.start + clip.duration) {
      return { ...clip, index: i };
    }
  }
  return clipMeta[0] || null;
}

function overlayAtPlayhead(artifact, seconds) {
  const overlays = resolveCompositionProps(artifact).overlays || [];
  for (const ov of overlays) {
    const { start, end } = overlayTiming(ov);
    if (seconds >= start && seconds < end) return ov;
  }
  return null;
}

function isEditNodeSelected(track, index) {
  return selectedEditNode.track === track && selectedEditNode.index === index;
}

function renderEditPreviewPanel(s, artifact, clipMeta, captionTracks, totalSeconds) {
  const active = cutAtPlayhead(clipMeta, editPlayheadSeconds)
    || clipMeta[selectedEditCutIndex]
    || null;
  let { captionText, overlayLabel } = resolveEditPreviewCaption(
    artifact,
    editPlayheadSeconds,
    captionTracks,
  );
  if (!captionText && selectedEditNode.track.startsWith("caption")) {
    const list = selectedEditNode.track === "caption-detail"
      ? captionTracks.detail
      : captionTracks.summary;
    captionText = list[selectedEditNode.index]?.text || list[selectedEditNode.index]?.label || "";
  }

  const asset = active ? findManifestAsset(s, active.cut.source) : null;
  const stageChildren = [];
  if (asset && (isImageMedia(asset) || isVideoMedia(asset))) {
    const mediaWrap = el("div", { class: "edit-nle-preview-media" });
    mediaWrap.append(buildMediaPreview(s, asset, { variant: "full", chromeless: true }));
    stageChildren.push(mediaWrap);
  } else {
    stageChildren.push(el("div", { class: "edit-nle-preview-empty" }, t("editPreviewNoMedia")));
  }
  if (captionText) {
    stageChildren.push(el("div", { class: "edit-nle-preview-caption" }, captionText));
  }
  if (overlayLabel) {
    stageChildren.push(el("div", { class: "edit-nle-preview-overlay" }, overlayLabel));
  }

  const narrSrc = resolveNarrationSrc(s, artifact);
  const audioEl = ensureEditPreviewAudio();
  if (narrSrc) {
    audioEl.src = mediaURL(s.project_id, narrSrc);
  }

  return el("div", { class: "edit-nle-preview" },
    el("div", {
      class: "edit-nle-preview-stage",
      style: `--edit-preview-aspect: ${deliverableAspect(s)}; aspect-ratio: ${deliverableAspect(s)};`,
    }, ...stageChildren),
    renderEditNleTransportBar(clipMeta, totalSeconds),
  );
}

async function openEditPreview(runtime, mode, { scaffold = false } = {}) {
  openEditPreviewModalLoading(runtime, mode);
  try {
    const result = await postJSON(`/api/project/${encodedProjectId}/edit-preview/start`, {
      runtime,
      mode,
      scaffold,
    });
    if (result.url) {
      openEditPreviewModal(result, runtime, mode);
    } else {
      closeModal();
    }
    if (result.hint) {
      console.info("[edit-preview]", result.hint);
    }
  } catch (err) {
    closeModal();
    window.alert(err.message || String(err));
  }
}

function editPreviewTitle(runtime, mode) {
  if (mode === "nle") return t("editNleLivePreview");
  if (runtime === "remotion") return t("editOpenRemotionStudio");
  if (mode === "play") return t("editOpenHyperFramesPlayer");
  return t("editOpenHyperFramesStudio");
}

function openEditPreviewModalLoading(runtime, mode) {
  modal.innerHTML = "";
  modal.classList.add("open", "modal-bg--fullscreen");
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: "modal-page modal-page-edit-preview" },
      el("div", { class: "edit-preview-toolbar" },
        el("span", { class: "edit-preview-title" }, editPreviewTitle(runtime, mode)),
        el("span", { class: "edit-preview-status" }, t("editPreviewLoading")),
      ),
      el("div", { class: "edit-preview-body edit-preview-body--loading" },
        el("div", { class: "bl-loading-block" }, t("editPreviewStarting")),
      ),
    ),
  );
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function openEditPreviewModal(result, runtime, mode) {
  const title = editPreviewTitle(runtime, mode);
  const subtitle = [
    result.composition_id,
    result.runtime,
    result.mode !== "studio" ? result.mode : null,
  ].filter(Boolean).join(" · ");

  modal.innerHTML = "";
  modal.classList.add("open", "modal-bg--fullscreen");
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: "modal-page modal-page-edit-preview" },
      el("div", { class: "edit-preview-toolbar" },
        el("div", { class: "edit-preview-toolbar-main" },
          el("span", { class: "edit-preview-title" }, title),
          subtitle ? el("span", { class: "edit-preview-subtitle" }, subtitle) : null,
        ),
        el("div", { class: "edit-preview-toolbar-actions" },
          el("a", {
            class: "edit-preview-external",
            href: result.url,
            target: "_blank",
            rel: "noopener noreferrer",
          }, t("editPreviewOpenExternal")),
        ),
      ),
      el("div", { class: "edit-preview-body" },
        el("iframe", {
          class: "edit-preview-frame",
          src: result.url,
          title: title,
          allow: "autoplay; fullscreen",
        }),
      ),
    ),
  );
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function renderStageArtifactBlock(name, artifact, s) {
  return el("article", { class: "drawer-artifact", "data-artifact": name },
    el("div", { class: "drawer-artifact-head" },
      el("div", {},
        el("div", { class: "drawer-section-label", style: "margin:0 0 4px" }, artifactLabel(name)),
        el("div", { class: "drawer-artifact-name" }, artifactReviewTitle(name, artifact, s)),
      ),
    ),
    el("div", { class: "drawer-artifact-summary" }, ...artifactReviewContent(name, artifact, s)),
  );
}

/** Stage drawer — per-stage review + artifacts only (not project summary). */
function renderDrawer(s) {
  if (!selectedStage) return null;
  const st = s.stages.find((x) => x.name === selectedStage);
  if (!st) return null;

  const body = el("div", { class: "drawer-body" });

  if (st.review) {
    const metrics = reviewMetrics(st.review);
    const summary = reviewSummaryText(st.review);
    body.append(el("div", { class: "findings", style: "margin-bottom:12px" },
      el("span", { class: `f ${metrics.critical ? "crit" : ""}` }, t("critical", { n: metrics.critical })),
      el("span", { class: `f ${metrics.suggestions ? "sugg" : ""}` }, t("suggestions", { n: metrics.suggestions })),
      el("span", { class: "f" }, t("nitpicks", { n: metrics.nitpicks })),
      summary ? el("span", { style: "font-size:calc(11.5px * var(--fs-scale));color:var(--text-2);margin-left:8px" }, summary) : null,
    ));
  }

  const names = artifactNamesForStage(st).filter((n) => n !== "decision_log");
  let shown = false;
  for (const name of names) {
    const artifact = s.artifacts[name];
    if (!artifact) continue;
    shown = true;
    body.append(renderStageArtifactBlock(name, artifact, s));
  }
  if (!shown) {
    body.append(el("div", { class: "hint" },
      st.status === "pending" ? t("stageNotRun") : t("noArtifactOnDisk")));
  }

  return el("div", { class: "drawer" },
    el("div", { class: "drawer-head" },
      el("h3", {}, `${stageLabel(st.name)} - ${statusLabel(st.status)}`),
      st.gate_skipped ? el("span", { class: "gate-chip" }, t("gateSkipped")) : null,
      st.versions > 1 ? el("span", { class: "ver-chip" }, `v${st.versions}`) : null,
      st.timestamp ? el("span", { class: "meta", style: "font-family:var(--mono);font-size:calc(10.5px * var(--fs-scale));color:var(--text-3)" }, st.timestamp) : null,
      el("span", { class: "close", onclick: () => toggleDrawer(st.name) }, t("close")),
    ),
    body,
  );
}

const STAGE_ARTIFACTS = {
  research: ["research_brief"],
  proposal: ["proposal_packet"],
  idea: ["brief"],
  script: ["script"],
  scene_plan: ["scene_plan"],
  assets: ["asset_manifest"],
  edit: ["edit_decisions"],
  compose: ["render_report", "final_review"],
  publish: ["publish_log"],
  reference_analysis: ["video_analysis_brief"],
};

function artifactNamesForStage(st) {
  if (Array.isArray(st.outputs) && st.outputs.length) {
    return st.outputs.filter(Boolean);
  }
  const declared = Array.isArray(st.produces) ? st.produces : [];
  const fallback = STAGE_ARTIFACTS[st.name] || [];
  return [...new Set([...declared, ...fallback].filter(Boolean))];
}

function mountSummaryModal(bodyContent, wide = false) {
  modal.innerHTML = "";
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: `modal-page modal-page-summary${wide ? " modal-page-viewer" : ""}` }, bodyContent),
  );
  modal.classList.add("open");
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function mediaTypeLabel(type, path = "") {
  if (type && type !== "file") {
    const map = {
      video: t("summaryDocTypeVideo"),
      image: t("summaryDocTypeImage"),
      audio: t("summaryDocTypeAudio"),
      url: t("summaryDocTypeUrl"),
    };
    if (map[type]) return map[type];
  }
  const p = String(path || "");
  if (/\.(mp4|webm|mov|mkv|m4v)$/i.test(p)) return t("summaryDocTypeVideo");
  if (/\.(mp3|wav|aac|m4a|ogg|flac)$/i.test(p)) return t("summaryDocTypeAudio");
  if (/\.(png|jpe?g|gif|webp|svg)$/i.test(p)) return t("summaryDocTypeImage");
  return t("summaryDocTypeFile");
}

function renderAssetTableHead(cols) {
  return el("div", { class: "asset-table-head", "aria-hidden": "true" },
    ...cols.map((col) => el("span", { class: "asset-table-col" }, col)),
  );
}

function isVideoMedia(item) {
  const path = String(item?.path || "");
  return item?.type === "video" || /\.(mp4|webm|mov|mkv|m4v)$/i.test(path);
}

function isAudioMedia(item) {
  const path = String(item?.path || "");
  return item?.type === "audio"
    || item?.type === "narration"
    || item?.type === "music"
    || item?.type === "sfx"
    || /\.(mp3|wav|aac|m4a|ogg|flac)$/i.test(path);
}

function isImageMedia(item) {
  const path = String(item?.path || "");
  return item?.type === "image"
    || item?.type === "diagram"
    || /\.(png|jpe?g|gif|webp|svg)$/i.test(path);
}

function inferMediaType(path) {
  const p = String(path || "");
  if (/\.(mp4|webm|mov|mkv|m4v)$/i.test(p)) return "video";
  if (/\.(mp3|wav|aac|m4a|ogg|flac)$/i.test(p)) return "audio";
  if (/\.(png|jpe?g|gif|webp|svg)$/i.test(p)) return "image";
  if (/\.(srt|vtt|ass)$/i.test(p)) return "subtitle";
  return "";
}

function normalizeProjectPath(path, projectId = "") {
  let p = String(path || "").trim().replaceAll("\\", "/");
  if (!p) return "";
  if (projectId) {
    for (const marker of [`/projects/${projectId}/`, `projects/${projectId}/`]) {
      const idx = p.toLowerCase().indexOf(marker.toLowerCase());
      if (idx >= 0) {
        p = p.slice(idx + marker.length);
        break;
      }
    }
  }
  return p.replace(/^\/+/, "");
}

function normalizeMediaItem(item, projectId = "") {
  const path = normalizeProjectPath(item?.path, projectId);
  const type = item?.type || inferMediaType(path);
  return {
    ...item,
    path,
    type,
    exists: item?.exists !== false && !!path,
    renderable: item?.renderable ?? (isImageMedia({ type, path }) || isVideoMedia({ type, path })),
  };
}

function resolveMediaRef(s, raw) {
  const projectId = s.project_id || "";
  const path = normalizeProjectPath(raw?.path || raw?.output_path || raw?.file || "", projectId);
  if (!path) return normalizeMediaItem({ exists: false }, projectId);

  const tail = path.split("/").pop() || path;
  const candidates = [
    ...(s.media?.renders || []),
    ...(s.project_summary?.media || []),
  ];
  for (const entry of candidates) {
    const entryPath = normalizeProjectPath(entry.path, projectId);
    if (!entryPath) continue;
    if (entryPath === path || entryPath.endsWith(`/${tail}`) || entryPath.split("/").pop() === tail) {
      return normalizeMediaItem({ ...entry, path: entryPath, exists: entry.exists !== false }, projectId);
    }
  }
  return normalizeMediaItem({
    ...raw,
    path,
    type: raw?.type || inferMediaType(path) || "video",
    exists: true,
  }, projectId);
}

function deliverableAspect(s) {
  const d = s.deliverable || {};
  const aspect = String(d.aspect_ratio || d.aspect || "");
  const m = aspect.match(/(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)/);
  if (m) return `${m[1]} / ${m[2]}`;
  const res = String(d.resolution || "");
  const rm = res.match(/(\d+)\s*[x×]\s*(\d+)/i);
  if (rm) return `${rm[1]} / ${rm[2]}`;
  if (d.width && d.height) return `${d.width} / ${d.height}`;
  return "9 / 16";
}

function buildArtifactPreview(s, entry) {
  const artifact = s.artifacts[entry.name];
  if (!artifact) return el("p", { class: "hint" }, t("artifactMissing"));
  return el("div", { class: "asset-preview-body" },
    el("pre", { class: "asset-preview-pre" }, JSON.stringify(artifact, null, 2)),
  );
}

function buildMediaPreview(s, item, { variant = "full", chromeless = false } = {}) {
  const media = normalizeMediaItem(item, s.project_id);
  if (media.type === "url" && media.path) {
    return el("div", { class: "asset-preview-body" },
      el("a", {
        class: "asset-preview-link",
        href: media.path,
        target: "_blank",
        rel: "noopener noreferrer",
      }, media.path));
  }
  if (!media.exists) return el("p", { class: "hint" }, t("assetMissing"));

  if (isVideoMedia(media)) {
    const frame = el("div", {
      class: `media-preview-frame media-preview-frame--video media-preview-frame--${variant}`,
      style: variant === "compact" ? `aspect-ratio:${deliverableAspect(s)}` : "",
    });
    frame.append(el("video", {
      class: "asset-preview-media asset-preview-video",
      src: mediaURL(s.project_id, media.path),
      ...(chromeless ? { preload: "metadata", playsinline: "" } : { controls: "", preload: "metadata", playsinline: "" }),
    }));
    return el("div", { class: "asset-preview-body" }, frame);
  }

  if (isAudioMedia(media)) {
    return el("div", { class: "asset-preview-body" },
      el("audio", {
        class: "asset-preview-media asset-preview-audio",
        src: mediaURL(s.project_id, media.path),
        controls: "",
        preload: "metadata",
      }));
  }

  if (isImageMedia(media)) {
    const frame = el("div", {
      class: `media-preview-frame media-preview-frame--image media-preview-frame--${variant}`,
      style: variant === "compact" ? `aspect-ratio:${deliverableAspect(s)}` : "",
    });
    const img = el("img", {
      class: "asset-preview-media asset-preview-image",
      src: variant === "compact"
        ? thumbURL(s.project_id, media.path, 960)
        : mediaURL(s.project_id, media.path),
      alt: "",
      loading: "lazy",
    });
    img.onerror = () => {
      if (variant === "compact" && img.src.includes("/thumb/")) {
        img.src = mediaURL(s.project_id, media.path);
        return;
      }
      frame.classList.add("media-preview-frame--missing");
      frame.replaceChildren(el("span", { class: "hint" }, t("assetMissing")));
    };
    frame.append(img);
    return el("div", { class: "asset-preview-body" }, frame);
  }

  return el("p", { class: "hint" }, t("summaryMediaFileHint"));
}

function resolveManifestAssets(s, artifact) {
  const raw = artifact.assets || [];
  const projectId = s.project_id || "";
  const byPath = new Map();
  for (const item of (s.project_summary?.media || [])) {
    if (item.source_artifact === "asset_manifest" && item.path) {
      byPath.set(normalizeProjectPath(item.path, projectId), item);
    }
  }
  return raw.map((asset) => {
    const enriched = byPath.get(normalizeProjectPath(asset.path, projectId));
    if (enriched) return { ...asset, ...enriched, path: normalizeProjectPath(enriched.path, projectId) };
    const path = normalizeProjectPath(asset.path, projectId);
    return {
      ...asset,
      label: asset.id,
      exists: !!path,
      renderable: /\.(png|jpe?g|gif|webp|svg)$/i.test(path) || /\.(mp4|webm|mov|mkv|m4v)$/i.test(path),
    };
  });
}

function buildAssetTilePreview(s, asset) {
  const path = asset.path || "";
  if (asset.type === "subtitle" || /\.(srt|vtt|ass|json)$/i.test(path)) {
    if (!path) return el("p", { class: "hint" }, t("assetMissing"));
    return el("div", { class: "asset-preview-body" },
      el("a", {
        class: "asset-preview-link",
        href: mediaURL(s.project_id, path),
        target: "_blank",
        rel: "noopener noreferrer",
      }, path.split("/").pop()));
  }
  if (asset.type === "animation" || asset.type === "code_snippet") {
    return el("div", { class: "asset-manifest-spec" },
      asset.generation_summary || asset.prompt || path || t("summaryMediaFileHint"));
  }
  const preview = buildMediaPreview(s, {
    path: asset.path,
    type: asset.type,
    exists: asset.exists !== false,
    renderable: asset.renderable ?? (isImageMedia(asset) || isVideoMedia(asset)),
  }, { variant: "compact" });
  const prompt = asset.prompt || asset.generation_summary;
  if (prompt) {
    return el("div", { class: "asset-manifest-preview-stack" },
      preview,
      el("div", {
        class: "asset-manifest-prompt",
        title: prompt,
      }, prompt));
  }
  return preview;
}

function assetManifestTile(s, asset) {
  const label = asset.id || asset.label || asset.scene_id || (asset.path || "").split("/").pop();
  const meta = [
    asset.scene_id ? sceneLabel(asset.scene_id) : null,
    asset.type,
    asset.duration_seconds != null ? fmtDuration(asset.duration_seconds) : null,
    asset.cost_usd != null ? fmtMoney(asset.cost_usd) : null,
  ].filter(Boolean).join(" · ");

  return el("article", { class: "asset-manifest-tile" },
    el("div", { class: "asset-manifest-tile-head" },
      el("div", { class: "asset-manifest-tile-id" }, label),
      meta ? el("div", { class: "asset-manifest-tile-meta" }, meta) : null),
    buildAssetTilePreview(s, asset),
  );
}

function renderAssetManifestBody(s, artifact) {
  const assets = resolveManifestAssets(s, artifact);
  const sceneOrder = (id) => {
    const m = String(id || "").match(/(\d+)\s*$/);
    return m ? Number(m[1]) : Number.MAX_SAFE_INTEGER;
  };
  assets.sort((a, b) => {
    const sa = sceneOrder(a.scene_id);
    const sb = sceneOrder(b.scene_id);
    if (sa !== sb) return sa - sb;
    return String(a.id || "").localeCompare(String(b.id || ""));
  });

  return el("div", { class: "asset-manifest-inline" },
    el("div", { class: "asset-manifest-grid" },
      ...assets.map((asset) => assetManifestTile(s, asset)),
    ),
  );
}

function findManifestAsset(s, source) {
  const key = String(source || "").trim();
  if (!key) return null;
  const manifest = s.artifacts?.asset_manifest;
  if (!manifest) {
    if (key.includes("/") || key.includes("\\")) {
      return resolveMediaRef(s, { path: key, type: inferMediaType(key) });
    }
    return null;
  }
  const assets = resolveManifestAssets(s, manifest);
  const matched = assets.find((asset) => asset.id === key
    || asset.path === key
    || (asset.path && (asset.path.endsWith(`/${key}`) || asset.path.endsWith(`\\${key}`))));
  if (matched) return matched;
  if (key.includes("/") || key.includes("\\")) {
    return resolveMediaRef(s, { path: key, type: inferMediaType(key) });
  }
  return null;
}

/** Resolve narration file path from edit_decisions (src or segment asset_id → manifest). */
function resolveNarrationSrc(s, artifact) {
  const narration = artifact?.audio?.narration;
  if (!narration) return null;
  if (narration.src) return narration.src;
  for (const seg of narration.segments || []) {
    if (seg.src) return seg.src;
    if (seg.asset_id) {
      const asset = findManifestAsset(s, seg.asset_id);
      if (asset?.path) return asset.path;
    }
  }
  return null;
}

function editUsesAbsoluteTimeline(artifact) {
  const rt = artifact?.render_runtime || "ffmpeg";
  return rt === "remotion" || rt === "hyperframes";
}

/** Same contract as lib/composition_timeline.normalize_composition_props */
function resolveCompositionProps(artifact) {
  if (!artifact) {
    return { cuts: [], overlays: [], captions: [], audio: {}, render_runtime: "ffmpeg" };
  }
  const overlays = (artifact.overlays && artifact.overlays.length)
    ? artifact.overlays
    : (artifact.metadata?.remotion_overlays || []);
  const captions = (artifact.captions && artifact.captions.length)
    ? artifact.captions
    : (artifact.metadata?.remotion_captions || []);
  return {
    cuts: artifact.cuts || [],
    overlays,
    captions,
    audio: artifact.audio || {},
    render_runtime: artifact.render_runtime || "ffmpeg",
    renderer_family: artifact.renderer_family,
  };
}

function overlayTiming(overlay) {
  const start = Number(overlay?.in_seconds ?? overlay?.start_seconds) || 0;
  const endRaw = overlay?.out_seconds ?? overlay?.end_seconds;
  const end = Number.isFinite(Number(endRaw)) ? Number(endRaw) : start;
  return { start, end, duration: Math.max(0, end - start) };
}

/** Match remotion-composer Explainer.tsx cutSequenceName(). */
function cutSequenceName(cut) {
  const file = String(cut?.source || "").split("/").pop() || cut?.source || "";
  if (cut?.id && cut?.reason) return `${cut.id} · ${cut.reason}`;
  if (cut?.id && file) return `${cut.id} · ${file}`;
  return cut?.id || file || "cut";
}

function cutDisplayReason(s, cut) {
  if (cut?.reason) return cut.reason;
  const source = String(cut?.source || "");
  const scenes = s?.artifacts?.scene_plan?.scenes || [];
  const scene = scenes.find(
    (sc) => source === sc.id || source === `img_${sc.id}` || source.includes(sc.id),
  );
  if (!scene) return "";
  const sections = s?.artifacts?.script?.sections || [];
  const sec = sections.find((item) => item.id === scene.script_section_id);
  if (sec?.label) return `${scene.id} · ${sec.label}`;
  return scene.id || "";
}

function cutMediaChild(cut, s = null) {
  let source = String(cut?.source || "");
  const asset = s ? findManifestAsset(s, source) : null;
  if (asset?.path) source = asset.path;
  const base = source.split("/").pop() || source.split("\\").pop() || source;
  if (!base) return null;
  const ext = base.includes(".") ? base.split(".").pop().toLowerCase() : "";
  const imageExt = ["jpg", "jpeg", "png", "webp", "gif"];
  const videoExt = ["mp4", "webm", "mov", "m4v"];
  if (asset?.type === "image" || imageExt.includes(ext)) {
    return { track: "media", kind: "image", label: `<Img> ${base}`, data: cut, asset };
  }
  if (asset?.type === "video" || videoExt.includes(ext)) {
    return { track: "media", kind: "video", label: `<Video> ${base}`, data: cut, asset };
  }
  return null;
}

/** Match remotion-composer CaptionOverlay page splitting. */
function buildCaptionPages(captions, wordsPerPage = 6) {
  const pages = [];
  for (let index = 0; index < captions.length; index += wordsPerPage) {
    const pageWords = captions.slice(index, index + wordsPerPage);
    if (!pageWords.length) continue;
    const startMs = Number(pageWords[0].startMs) || 0;
    const endMs = Number(pageWords[pageWords.length - 1].endMs) || startMs;
    const preview = pageWords.map((w) => w.word || "").join("").slice(0, 12);
    pages.push({ words: pageWords, startMs, endMs, preview });
  }
  return pages;
}

function captionPageTiming(page, pages, pageIndex, durationSeconds) {
  const start = Math.max(0, page.startMs / 1000);
  let end;
  if (pageIndex + 1 < pages.length) {
    end = Math.max(start, pages[pageIndex + 1].startMs / 1000);
  } else {
    end = Math.max(start, page.endMs / 1000 + 0.5);
  }
  end = Math.min(end, durationSeconds);
  return { start, end, duration: Math.max(0, end - start) };
}

function overlaySequenceName(overlay, index) {
  if (overlay?.text) return overlay.text;
  return overlay?.type || `overlay-${index + 1}`;
}

/** Match remotion-composer/src/Root.tsx calculateMetadata for Explainer. */
function compositionDurationSeconds(artifact, clipMeta) {
  const cuts = artifact?.cuts || [];
  if (editUsesAbsoluteTimeline(artifact)) {
    if (!cuts.length) return 0;
    const lastEnd = Math.max(...cuts.map((cut) => Number(cut.out_seconds) || 0));
    return lastEnd + 1;
  }
  return clipMeta.reduce((sum, clip) => sum + clip.duration, 0);
}

/** Same layer tree as lib/composition_timeline.build_composition_timeline */
function buildCompositionTimeline(artifact, s) {
  const props = resolveCompositionProps(artifact);
  const clipMeta = buildEditClipMeta(props.cuts, artifact);
  const durationSeconds = compositionDurationSeconds(artifact, clipMeta);
  const absolute = editUsesAbsoluteTimeline(artifact);
  const scriptSections = s?.artifacts?.script?.sections || [];

  const overlayNodes = (props.overlays || [])
    .map((overlay, index) => {
      const { start, end, duration } = overlayTiming(overlay);
      if (duration <= 0) return null;
      const fullText = overlaySequenceName(overlay, index);
      const shortLabel = overlayNodeLabel(overlay, clipMeta, scriptSections) || fullText;
      return {
        track: "overlay",
        index,
        id: overlay.id || `overlay-${index}`,
        start,
        end,
        duration,
        label: shortLabel,
        preview: fullText,
        data: overlay,
      };
    })
    .filter(Boolean);

  const layers = [];

  layers.push({
    id: "cuts",
    layer: 1,
    kind: "sequence",
    nodes: clipMeta.map(({ cut, index, start, duration }) => {
      const child = cutMediaChild(cut, s);
      const children = child
        ? [{ ...child, index: 0, start, end: start + duration, duration }]
        : [];
      const reason = cutDisplayReason(s, cut);
      const displayCut = reason && !cut.reason ? { ...cut, reason } : cut;
      return {
        track: "cut",
        index,
        id: cut.id || `cut-${index}`,
        start,
        end: start + duration,
        duration,
        label: cutSequenceName(displayCut),
        reason: reason || cut.reason,
        data: cut,
        children,
      };
    }),
  });

  if (overlayNodes.length) {
    layers.push({
      id: "overlays",
      layer: 2,
      kind: "overlay",
      nodes: overlayNodes,
    });
  }

  const remotionCaptions = props.captions || [];
  if (absolute && remotionCaptions.length && remotionCaptions[0]?.startMs != null && !overlayNodes.length) {
    const captionPages = buildCaptionPages(remotionCaptions, 1);
    const captionNodes = captionPages
      .map((page, pageIndex) => {
        const { start, end, duration } = captionPageTiming(
          page, captionPages, pageIndex, durationSeconds,
        );
        if (duration <= 0) return null;
        const preview = page.preview || page.words?.map((w) => w.word || "").join("") || "";
        return {
          track: "caption",
          index: pageIndex,
          id: `caption-${pageIndex}`,
          start,
          end,
          duration,
          label: shortText(preview, 16) || "caption",
          preview,
          data: page,
        };
      })
      .filter(Boolean);
    if (captionNodes.length) {
      layers.push({
        id: "captions",
        layer: 3,
        kind: "caption",
        nodes: captionNodes,
      });
    }
  } else if (!absolute) {
    const captionTracks = buildNleCaptionTracksFromScript(s, durationSeconds);
    if (captionTracks.summary.length) {
      const summaryLayer = {
        id: "script-captions-summary",
        layer: 2,
        kind: "script-caption",
        nodes: captionTracks.summary.map((item, index) => ({
          track: "caption-summary",
          index,
          id: `caption-summary-${index}`,
          start: item.start,
          end: item.start + item.duration,
          duration: item.duration,
          label: item.label,
          data: item,
        })),
      };
      const detailLayer = {
        id: "script-captions-detail",
        layer: 2,
        kind: "script-caption",
        nodes: captionTracks.detail.map((item, index) => ({
          track: "caption-detail",
          index,
          id: `caption-detail-${index}`,
          start: item.start,
          end: item.start + item.duration,
          duration: item.duration,
          label: shortText(item.text, 48),
          data: item,
        })),
      };
      const cutIdx = layers.findIndex((layer) => layer.id === "cuts");
      layers.splice(cutIdx, 0, summaryLayer, detailLayer);
    }
  } else if (
    remotionCaptions.length
    && !overlayNodes.length
    && remotionCaptions[0]?.startMs == null
  ) {
    const starts = remotionCaptions.map((cap) => Number(cap.start) || 0);
    const ends = remotionCaptions.map((cap) => Number(cap.end) || 0);
    const capStart = Math.min(...starts);
    const capEnd = Math.max(...ends);
    layers.push({
      id: "captions",
      layer: 3,
      kind: "caption",
      nodes: [{
        track: "caption",
        index: 0,
        id: "captions",
        start: capStart,
        end: capEnd,
        duration: Math.max(0, capEnd - capStart),
        label: t("editLayerCaptions"),
        data: { captions: remotionCaptions },
      }],
    });
  }

  const narration = props.audio?.narration || {};
  const narrSegments = narration.segments || [];
  const narrSrc = narration.src;
  if (narrSegments.length || narrSrc) {
    const nodes = narrSegments.length
      ? narrSegments.map((seg, index) => {
        const start = Number(seg.start_seconds) || 0;
        const end = seg.end_seconds != null ? Number(seg.end_seconds) : durationSeconds;
        return {
          track: "narr",
          index,
          id: seg.asset_id || `narr-${index}`,
          start,
          end,
          duration: Math.max(0.1, end - start),
          label: seg.asset_id || t("editTrackNarration"),
          data: seg,
        };
      })
      : [{
        track: "narr",
        index: 0,
        id: "narration",
        start: 0,
        end: durationSeconds,
        duration: durationSeconds,
        label: String(narrSrc).split("/").pop() || t("editTrackNarration"),
        data: { src: narrSrc, volume: narration.volume },
      }];
    layers.push({
      id: "audio-narration",
      layer: 4,
      kind: "audio",
      nodes,
    });
  }

  const music = props.audio?.music;
  if (music?.src || music?.asset_id) {
    layers.push({
      id: "audio-music",
      layer: 4,
      kind: "audio",
      nodes: [{
        track: "music",
        index: 0,
        id: music.asset_id || "music",
        start: 0,
        end: durationSeconds,
        duration: durationSeconds,
        label: music.asset_id || String(music.src || "").split("/").pop() || "music",
        data: music,
      }],
    });
  }

  if (!absolute) {
    const sfxList = props.audio?.sfx || [];
    if (sfxList.length) {
      layers.push({
        id: "audio-sfx",
        layer: 5,
        kind: "audio",
        nodes: sfxList.map((sfx, index) => ({
          track: "sfx",
          index,
          id: sfx.asset_id || `sfx-${index}`,
          start: Number(sfx.start_seconds) || 0,
          end: (Number(sfx.start_seconds) || 0) + (Number(sfx.duration_seconds) || 2),
          duration: Number(sfx.duration_seconds) || 2,
          label: sfx.asset_id || t("editTrackSfx"),
          data: sfx,
        })),
      });
    }
  }

  return { props, clipMeta, durationSeconds, layers, absolute };
}

function editCutTimelineDuration(cut, artifact) {
  const raw = Math.max(0, (Number(cut.out_seconds) || 0) - (Number(cut.in_seconds) || 0));
  if (editUsesAbsoluteTimeline(artifact)) {
    return raw;
  }
  const speed = Number(cut.speed) || 1;
  return raw / speed;
}

function buildEditClipMeta(cuts, artifact) {
  if (editUsesAbsoluteTimeline(artifact)) {
    return cuts.map((cut, index) => ({
      cut,
      index,
      start: Number(cut.in_seconds) || 0,
      duration: editCutTimelineDuration(cut, artifact),
    }));
  }
  let cursor = 0;
  return cuts.map((cut, index) => {
    const start = cursor;
    const duration = editCutTimelineDuration(cut, artifact);
    cursor += duration;
    return { cut, index, start, duration };
  });
}

function editTimelineTotalSeconds(artifact, clipMeta) {
  return compositionDurationSeconds(artifact, clipMeta);
}

function editCutDetailPanel(s, cut, index, timelineStart) {
  const asset = findManifestAsset(s, cut.source);
  const sourceLabel = asset?.id || cut.source || "—";
  const sourcePath = asset?.path || (String(cut.source || "").includes("/") ? cut.source : null);
  const timelineDur = editCutTimelineDuration(cut, state?.artifacts?.edit_decisions || {});
  const trimLabel = `${fmtDuration(cut.in_seconds)} → ${fmtDuration(cut.out_seconds)}`;
  const timelineLabel = `${fmtDuration(timelineStart)} → ${fmtDuration(timelineStart + timelineDur)}`;

  const chips = [
    cut.layer && cut.layer !== "primary" ? cut.layer : null,
    cut.transition_in ? `▶ ${cut.transition_in}` : null,
    cut.transition_out ? `${cut.transition_out} ▶` : null,
    cut.transform?.animation,
    cut.speed && cut.speed !== 1 ? `${cut.speed}×` : null,
  ].filter(Boolean);

  const panel = el("article", { class: "edit-cut-detail" },
    el("div", { class: "edit-cut-head" },
      el("span", { class: "edit-cut-id" }, cut.id || t("item", { n: index + 1 })),
      el("span", { class: "edit-cut-time" }, timelineLabel),
    ),
    el("div", { class: "edit-cut-meta" },
      el("span", {}, `${t("editOnTimeline")} · ${fmtDuration(timelineDur)}`),
      el("span", {}, `${t("editCutSource")} · ${trimLabel}`),
    ),
    el("div", { class: "edit-cut-source" },
      el("b", {}, sourceLabel),
      sourcePath && sourcePath !== sourceLabel
        ? el("span", { class: "edit-cut-path" }, sourcePath)
        : null,
    ),
    chips.length
      ? el("div", { class: "edit-cut-chips" }, ...chips.map((chip) => el("span", { class: "edit-cut-chip" }, chip)))
      : null,
    cut.reason ? el("p", { class: "edit-cut-reason" }, cut.reason) : null,
  );

  if (asset && (isImageMedia(asset) || isVideoMedia(asset) || isAudioMedia(asset))) {
    panel.append(el("div", { class: "edit-cut-preview" }, buildMediaPreview(s, asset, { variant: "full" })));
  }
  return panel;
}

function fmtTimelineClock(seconds) {
  const n = Math.max(0, Number(seconds) || 0);
  const m = Math.floor(n / 60);
  const s = Math.floor(n % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function nleClipStyle(start, duration, total) {
  const safeTotal = Math.max(total, 0.001);
  const left = (Math.max(0, start) / safeTotal) * 100;
  const width = (Math.max(duration, 0.05) / safeTotal) * 100;
  return `left:${left}%;width:${Math.min(100 - left, width)}%`;
}

function nleLayerTrackType(layer) {
  if (layer.kind === "audio") return "audio";
  if (layer.captionRow || layer.kind === "caption") return "caption";
  if (layer.overlayRow || layer.kind === "overlay") return "overlay";
  if (layer.nested && layer.kind === "media") return "image";
  return "video";
}

function nleTrackHeadMeta(layer) {
  const label = layer.trackLabel || "";
  if (layer.kind === "audio") {
    const name = layer.nodes[0]?.label || t("editTrackNarration");
    return { label: name, title: name };
  }
  if (layer.captionRow) {
    const preview = layer.nodes[0]?.preview || "caption";
    return { label: preview, title: preview };
  }
  if (layer.overlayRow) {
    return { label, title: label };
  }
  if (layer.nested && layer.kind === "media") {
    const match = label.match(/^<(Img|Video)>\s*(.+)$/i);
    return { label: match ? match[2] : label, title: label };
  }
  if (layer.staircase && layer.kind === "sequence") {
    return { label, title: label };
  }
  return { label, title: label };
}

const NLE_TRACK_TYPE_SVG = {
  video: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="5" width="15" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M9.5 8.5v3l3.5-1.5-3.5-1.5z" fill="currentColor"/></svg>',
  image: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4.5" width="14" height="11" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="7.5" cy="8.5" r="1.3" fill="currentColor"/><path d="M5.5 13.5l2.8-2.4 2.2 1.8 2.5-2.2 1.5 2.8H5.5z" fill="currentColor" opacity=".9"/></svg>',
  overlay: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3" width="14" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.3"/><text x="10" y="14" text-anchor="middle" font-size="10" font-weight="700" fill="currentColor" font-family="system-ui,sans-serif">T</text></svg>',
  caption: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3" width="14" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.3"/><text x="10" y="14" text-anchor="middle" font-size="10" font-weight="700" fill="currentColor" font-family="system-ui,sans-serif">T</text></svg>',
  audio: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M8 4.5v11c0 .8-.9 1.3-1.6.9L3.5 14H2.5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h1l2.9-2.4c.7-.4 1.6.1 1.6.9zm8.2 1.8a1 1 0 0 1 0 1.4A4.6 4.6 0 0 0 14 12a4.6 4.6 0 0 0 2.2 4.3 1 1 0 1 1-1 1.7A6.6 6.6 0 0 1 12 12a6.6 6.6 0 0 1 3.2-5.8 1 1 0 0 1 1 1.1z" fill="currentColor"/></svg>',
};

function nleTrackTypeIcon(type) {
  const node = el("span", { class: `nle-track-type nle-track-type--${type}` });
  node.innerHTML = NLE_TRACK_TYPE_SVG[type] || NLE_TRACK_TYPE_SVG.video;
  return node;
}

function nleNarrationBlockPlayButton() {
  const playing = editNarrationPlaying;
  const btn = el("button", {
    type: "button",
    class: `nle-block-play-btn nle-block-play-btn--narr${playing ? " is-playing" : ""}`,
    title: playing ? t("editNarrationPause") : t("editNarrationPlay"),
    "aria-label": playing ? t("editNarrationPause") : t("editNarrationPlay"),
    onclick: (event) => {
      event.stopPropagation();
      toggleEditNarrationPlayback();
    },
  });
  btn.innerHTML = playing ? NLE_TRANSPORT_SVG.pause : NLE_TRANSPORT_SVG.play;
  return btn;
}

function nleTrackControlsPro({
  trackType,
  label = "",
  title = "",
  nested = false,
  sequenceParent = false,
  layer = null,
  totalSeconds = 0,
} = {}) {
  const classes = ["nle-track-controls", "nle-track-controls--pro"];
  if (nested) classes.push("nle-track-controls--nested");
  if (sequenceParent) classes.push("nle-track-controls--sequence-parent");
  if (layer?.kind === "audio") classes.push("nle-track-controls--audio-row");
  if (layer && isEditAudioSelected(layer)) classes.push("is-selected");
  const row = el("div", { class: classes.join(" ") });
  if (nested) row.append(el("span", { class: "nle-track-tree", "aria-hidden": "true" }));
  const head = el("div", { class: "nle-track-head" });
  head.append(nleTrackTypeIcon(trackType));
  if (label) {
    head.append(el("span", { class: "nle-track-name", title: title || label }, label));
  }
  row.append(head);
  if (layer?.kind === "audio" && layer.nodes?.[0]) {
    const node = layer.nodes[0];
    row.addEventListener("click", (event) => {
      if (event.target.closest(".nle-block-play-btn, .nle-track-play-btn")) return;
      selectEditNode(node.track, node.index, editPlayheadSeconds);
    });
  }
  return row;
}

function nleTrackControls(kind, label = "", { nested = false, sequenceParent = false, title = "", pro = false, trackType = "video", layer = null, totalSeconds = 0 } = {}) {
  if (pro) {
    return nleTrackControlsPro({ trackType, label, title, nested, sequenceParent, layer, totalSeconds });
  }
  if (label && nested) {
    const match = label.match(/^<(Img|Video)>\s*(.+)$/i);
    const badge = match ? match[1] : null;
    const name = match ? match[2] : label;
    return el("div", { class: "nle-track-controls nle-track-controls--named nle-track-controls--nested" },
      el("span", { class: "nle-track-tree", "aria-hidden": "true" }),
      badge ? el("span", { class: "nle-node-badge" }, `<${badge}>`) : null,
      el("span", { class: "nle-track-name nle-track-name--child", title: label }, name),
    );
  }
  if (label) {
    const classes = ["nle-track-controls", "nle-track-controls--named"];
    if (sequenceParent) classes.push("nle-track-controls--sequence-parent");
    return el("div", { class: classes.join(" ") },
      el("span", { class: "nle-track-name", title: title || label }, label),
    );
  }
  if (kind === "audio") {
    return el("div", { class: "nle-track-controls nle-track-controls--audio" },
      el("span", { class: "nle-track-ctl", title: t("editTrackMute") }, "M"),
      el("span", { class: "nle-track-ctl", title: t("editTrackSolo") }, "S"),
      el("span", { class: "nle-track-ctl nle-track-ctl--icon", title: t("editTrackAudio") }, "♪"),
    );
  }
  return el("div", { class: "nle-track-controls" },
    el("span", { class: "nle-track-ctl nle-track-ctl--icon", title: t("editTrackVisible") }, "◉"),
    el("span", { class: "nle-track-ctl nle-track-ctl--icon", title: t("editTrackLock") }, "⌂"),
  );
}

function nleWaveformEl(seed, variant = "audio") {
  const wave = el("div", { class: `nle-waveform nle-waveform--${variant}` });
  const count = variant === "video" ? 18 : 28;
  const maxHeight = variant === "video" ? 10 : (variant === "composition-audio" ? 22 : 16);
  waveBars(wave, seed || "wave", count, maxHeight);
  return wave;
}

function nleFilmstrip(s, asset, duration, { cover = false } = {}) {
  if (!asset?.path || !(isImageMedia(asset) || isVideoMedia(asset))) {
    return el("div", { class: "nle-filmstrip nle-filmstrip--empty" });
  }
  if (cover) {
    return el("div", { class: "nle-filmstrip nle-filmstrip--cover" },
      el("img", {
        class: "nle-filmstrip-cover",
        src: thumbURL(s.project_id, asset.path, 480),
        loading: "lazy",
        alt: "",
      }),
    );
  }
  const frameCount = Math.max(2, Math.min(10, Math.ceil(duration / 1.5)));
  const frames = [];
  for (let i = 0; i < frameCount; i++) {
    frames.push(el("img", {
      class: "nle-filmstrip-frame",
      src: thumbURL(s.project_id, asset.path, 240),
      loading: "lazy",
      alt: "",
    }));
  }
  return el("div", { class: "nle-filmstrip" }, frames);
}

function nleTimelineBlock({
  className = "",
  start,
  duration,
  total,
  title,
  subtitle,
  compact = false,
  wrap = false,
  onClick,
  children,
}) {
  const block = el("div", {
    class: `nle-block ${className}`.trim(),
    style: nleClipStyle(start, duration, total),
    title: title || "",
  });
  if (!compact) {
    const labelClass = wrap ? "nle-block-label nle-block-label--wrap" : "nle-block-label";
    if (subtitle) {
      block.append(el("div", { class: "nle-block-head" },
        el("span", { class: "nle-block-title" }, title || ""),
        el("span", { class: "nle-block-meta" }, subtitle),
      ));
    } else if (title) {
      block.append(el("div", { class: labelClass }, title));
    }
  }
  if (children) block.append(...(Array.isArray(children) ? children : [children]));
  if (onClick) {
    block.classList.add("nle-block--clickable");
    block.addEventListener("click", onClick);
  }
  return block;
}

function findScriptSectionAtTime(sections, time) {
  return sections.find((sec) => {
    const start = Number(sec.start_seconds) || 0;
    const endRaw = Number(sec.end_seconds);
    const end = Number.isFinite(endRaw) && endRaw > start ? endRaw : start + 999;
    return time >= start && time < end;
  });
}

/** Short section label for overlay staircase rows (Hook, 双口味, …). */
function overlayNodeLabel(overlay, clipMeta, scriptSections) {
  const start = Number(overlay.in_seconds ?? overlay.start_seconds) || 0;
  const sec = findScriptSectionAtTime(scriptSections, start);
  if (sec?.label) return sec.label;
  const clip = clipMeta.find((item) => Math.abs(item.start - start) < 0.08);
  if (clip?.cut?.reason) return clip.cut.reason;
  const text = overlay.text || "";
  if (overlay.type === "section_title" && text.length <= 24) return text;
  if (text.length <= 18) return text;
  return overlay.type || shortText(text, 12) || `overlay-${Math.round(start)}s`;
}

function buildNleCaptionTracksFromScript(s, totalSeconds) {
  const empty = { summary: [], detail: [] };
  if (!totalSeconds) return empty;
  const script = s?.artifacts?.script;
  const sections = (script?.sections || []).filter((sec) => sec.text);
  if (!sections.length) return empty;

  const summary = [];
  const detail = [];
  for (const sec of sections) {
    const start = Math.max(0, Number(sec.start_seconds) || 0);
    const endRaw = Number(sec.end_seconds);
    const end = Number.isFinite(endRaw) && endRaw > start ? endRaw : start + 2;
    const duration = Math.min(end - start, totalSeconds - start);
    if (duration <= 0) continue;
    const label = sec.label || shortText(sec.text, 18);
    summary.push({ start, duration, label, text: sec.text });
    detail.push({ start, duration, text: sec.text });
  }
  return { summary, detail };
}

function buildNleCaptionTracks(s, artifact, totalSeconds) {
  if (editUsesAbsoluteTimeline(artifact)) {
    return buildNleCaptionTracksFromScript(s, totalSeconds);
  }
  const props = resolveCompositionProps(artifact);
  if (props.overlays?.length) {
    const summary = [];
    const detail = [];
    for (const ov of props.overlays) {
      const { start, duration } = overlayTiming(ov);
      if (duration <= 0) continue;
      const clipped = Math.min(duration, totalSeconds - start);
      if (clipped <= 0) continue;
      const text = ov.text || "";
      summary.push({ start, duration: clipped, label: shortText(text, 16), text });
      detail.push({ start, duration: clipped, text });
    }
    if (summary.length) return { summary, detail };
  }
  return buildNleCaptionTracksFromScript(s, totalSeconds);
}

function seekEditPlayhead(seconds, totalSeconds, { keepPlaying = false } = {}) {
  if (!totalSeconds) return;
  editPlayheadSeconds = Math.max(0, Math.min(totalSeconds, seconds));
  editPreviewLastCutKey = null;
  const audioEl = ensureEditPreviewAudio();
  if (keepPlaying && editPreviewPlaying) {
    if (audioEl.src) audioEl.currentTime = editPlayheadSeconds;
  } else {
    editPreviewPlaying = false;
    editNarrationPlaying = false;
    stopEditPreviewClock();
    audioEl.pause();
  }
  syncEditPlayheadUI(true);
}

function setEditPlayheadFromPointer(event, laneEl, totalSeconds, { keepPlaying = false } = {}) {
  if (!laneEl || !totalSeconds) return;
  const rect = laneEl.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
  seekEditPlayhead((x / rect.width) * totalSeconds, totalSeconds, { keepPlaying });
}

function seekAndPlayFromPointer(event, laneEl, totalSeconds) {
  setEditPlayheadFromPointer(event, laneEl, totalSeconds);
  startEditPreviewPlayback(totalSeconds);
}

function makeNleBlockClickHandler(node, totalSeconds, { playOnClick = false } = {}) {
  return (event) => {
    if (event.target.closest(".nle-block-play-btn")) return;
    event.stopPropagation();
    const lane = event.currentTarget.closest(".nle-lane");
    let startAt = node.start;
    if (lane) {
      const rect = lane.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
      startAt = (x / rect.width) * totalSeconds;
    }
    selectedEditNode = { track: node.track, index: node.index };
    if (node.track === "cut") selectedEditCutIndex = node.index;
    editPlayheadSeconds = startAt;
    editPreviewLastCutKey = null;
    if (playOnClick) {
      render();
      startEditPreviewPlayback(totalSeconds);
    } else {
      editPreviewPlaying = false;
      editNarrationPlaying = false;
      stopEditPreviewClock();
      ensureEditPreviewAudio().pause();
      render();
    }
  };
}

function bindNleBlockPlayback(block, totalSeconds) {
  block.addEventListener("dblclick", (event) => {
    event.stopPropagation();
    const lane = block.closest(".nle-lane");
    if (lane) seekAndPlayFromPointer(event, lane, totalSeconds);
  });
}

function expandLayersForStaircase(layers, absolute) {
  if (!absolute) return layers;
  const expanded = [];
  for (const layer of layers) {
    if (layer.kind === "sequence") {
      for (const node of layer.nodes) {
        expanded.push({
          ...layer,
          id: `${layer.id}-${node.index}`,
          nodes: [node],
          staircase: true,
          trackLabel: node.label,
        });
        for (const child of node.children || []) {
          expanded.push({
            id: `${layer.id}-${node.index}-media`,
            kind: "media",
            layer: layer.layer,
            nodes: [{ ...child, parentIndex: node.index }],
            nested: true,
            trackLabel: child.label,
          });
        }
      }
      continue;
    }
    if (layer.kind === "overlay" || layer.kind === "caption") {
      for (const node of layer.nodes) {
        expanded.push({
          ...layer,
          id: `${layer.id}-${node.index}`,
          nodes: [node],
          overlayRow: layer.kind === "overlay",
          captionRow: layer.kind === "caption",
          trackLabel: node.label,
        });
      }
      continue;
    }
    if (layer.kind === "script-caption") {
      for (const node of layer.nodes) {
        expanded.push({
          ...layer,
          id: `${layer.id}-${node.index}`,
          nodes: [node],
          trackLabel: node.label,
        });
      }
      continue;
    }
    expanded.push(layer);
  }
  return expanded;
}

function nleLayerTrackSize(layer) {
  if (layer.nested && layer.kind === "media") return "sm";
  if (layer.staircase && layer.kind === "sequence") return "sm";
  if (layer.kind === "sequence") return "lg";
  if (layer.kind === "overlay" || layer.kind === "caption" || layer.kind === "script-caption") {
    return "sm";
  }
  return "md";
}

function nleLayerTrackKind(layer) {
  return layer.kind === "audio" ? "audio" : "video";
}

function renderNleTimelineNode(s, composition, layer, node, totalSeconds) {
  const selected = isEditNodeSelected(node.track, node.index);
  const onClick = makeNleBlockClickHandler(node, totalSeconds);
  const attachPlayback = (block) => {
    if (block) bindNleBlockPlayback(block, totalSeconds);
    return block;
  };

  if (layer.kind === "sequence") {
    const cut = node.data;
    const asset = findManifestAsset(s, cut.source);
    const fileName = asset?.path?.split("/").pop()
      || cut.source
      || cut.id
      || node.label;
    const compact = Boolean(layer.staircase);
    const block = nleTimelineBlock({
      className: `nle-block--video${compact ? " nle-block--sequence-parent" : ""}${selected ? " is-selected" : ""}`,
      start: node.start,
      duration: node.duration,
      total: totalSeconds,
      title: compact ? (cut.reason || node.label) : fileName,
      subtitle: compact ? undefined : fmtTimelineClock(node.duration),
      compact,
      onClick,
    });
    if (compact) {
      const badge = cut.reason || cutDisplayReason(s, cut) || node.reason || node.label;
      if (badge) {
        block.append(el("span", { class: "nle-block-reason" }, badge));
      }
    } else if (!compact) {
      block.append(
        nleFilmstrip(s, asset, node.duration),
        nleWaveformEl(`${fileName}-${node.index}`, "video"),
      );
    }
    // Interactive NLE editing — absolute timelines (remotion/hyperframes)
    // map 1:1 to cut.in_seconds/out_seconds, so drag/resize edits them.
    // NOTE: on absolute timelines every sequence row is a compact staircase
    // row, so the binding must NOT be gated on !compact (that would make
    // drag editing dead code).
    if (composition.absolute && renderRuntimeIsEditable(s)) {
      bindNleDragEdit(block, cut, totalSeconds);
    }
    return attachPlayback(block);
  }

  if (layer.kind === "media") {
    const cut = node.data;
    const asset = findManifestAsset(s, cut.source);
    const block = nleTimelineBlock({
      className: `nle-block--video nle-block--media-child${selected ? " is-selected" : ""}`,
      start: node.start,
      duration: node.duration,
      total: totalSeconds,
      compact: true,
      onClick: makeNleBlockClickHandler({ ...node, track: "cut", index: node.parentIndex ?? node.index }, totalSeconds),
    });
    block.append(nleFilmstrip(s, asset, node.duration, { cover: true }));
    return attachPlayback(block);
  }

  if (layer.kind === "overlay") {
    return attachPlayback(nleTimelineBlock({
      className: `nle-block--overlay nle-block--overlay-stair${layer.overlayRow ? " nle-block--overlay-row" : ""}${selected ? " is-selected" : ""}`,
      start: node.start,
      duration: node.duration,
      total: totalSeconds,
      title: node.preview || node.label,
      wrap: true,
      onClick,
    }));
  }

  if (layer.kind === "caption") {
    const blockTitle = node.preview || node.data?.preview || node.label || "";
    return attachPlayback(nleTimelineBlock({
      className: `nle-block--caption-summary${layer.captionRow ? " nle-block--caption-row" : ""}${selected ? " is-selected" : ""}`,
      start: node.start,
      duration: node.duration,
      total: totalSeconds,
      title: blockTitle,
      wrap: true,
      onClick,
    }));
  }

  if (layer.kind === "script-caption") {
    const isDetail = node.track === "caption-detail";
    return attachPlayback(nleTimelineBlock({
      className: `${isDetail ? "nle-block--caption-detail" : "nle-block--caption-summary"}${selected ? " is-selected" : ""}`,
      start: node.start,
      duration: node.duration,
      total: totalSeconds,
      title: isDetail ? `A: ${node.label}` : node.label,
      wrap: isDetail,
      onClick,
    }));
  }

  if (layer.kind === "audio") {
    const isNarr = node.track === "narr";
    const onClick = makeNleBlockClickHandler(node, totalSeconds);
    const block = nleTimelineBlock({
      className: `nle-block--audio${node.track === "music" ? " nle-block--music" : ""}${node.track === "sfx" ? " nle-block--sfx" : ""}${selected ? " is-selected" : ""}`,
      start: node.start,
      duration: node.duration,
      total: totalSeconds,
      title: isNarr ? "" : node.label,
      compact: isNarr,
      onClick: isNarr ? undefined : onClick,
    });
    const wave = nleWaveformEl(`${node.id}-${node.start}`, "audio");
    if (isNarr) {
      block.classList.add("nle-block--audio-narr");
      const inner = el("div", { class: "nle-block-audio-inner nle-block--clickable" });
      inner.addEventListener("click", onClick);
      inner.append(wave);
      block.append(nleNarrationBlockPlayButton(), inner);
    } else {
      block.append(wave);
    }
    return block;
  }

  return null;
}

function renderNleTimeline(s, artifact, composition) {
  const { durationSeconds: totalSeconds, layers, absolute } = composition;
  const displayLayers = expandLayersForStaircase(layers, absolute);
  const playheadPct = Math.min(100, (editPlayheadSeconds / Math.max(totalSeconds, 0.001)) * 100);

  const rulerStep = totalSeconds <= 24 ? 3 : totalSeconds <= 90 ? 6 : 15;
  const ticks = [];
  for (let sec = 0; sec <= totalSeconds + 0.001; sec += rulerStep) {
    const pct = (sec / totalSeconds) * 100;
    ticks.push(el("span", { class: "nle-ruler-tick", style: `left:${pct}%` }, fmtTimelineClock(sec)));
  }

  const controlRows = [];
  const laneRows = [];
  const bindScrub = (laneEl) => {
    laneEl.addEventListener("click", (event) => {
      if (event.target.closest(".nle-block--clickable")) return;
      setEditPlayheadFromPointer(event, laneEl, totalSeconds);
    });
    laneEl.addEventListener("dblclick", (event) => {
      if (event.target.closest(".nle-block--clickable, .nle-block-play-btn")) return;
      seekAndPlayFromPointer(event, laneEl, totalSeconds);
    });
  };
  const pushTrack = (controls, lane, size = "md") => {
    controls.classList.add(`nle-track-controls--${size}`);
    lane.classList.add(`nle-lane--${size}`);
    controlRows.push(controls);
    laneRows.push(lane);
  };

  for (const layer of displayLayers) {
    const laneClass = layer.kind === "sequence"
      ? `nle-lane nle-lane--video${layer.staircase ? " nle-lane--sequence-row nle-lane--sequence-parent" : ""}`
      : layer.kind === "media"
        ? "nle-lane nle-lane--media-row nle-lane--nested"
        : layer.kind === "overlay"
          ? `nle-lane nle-lane--overlays${layer.overlayRow ? " nle-lane--overlay-row" : ""}`
          : layer.kind === "caption"
            ? `nle-lane nle-lane--captions${layer.captionRow ? " nle-lane--caption-row" : ""}`
            : layer.kind === "script-caption"
              ? (layer.nodes[0]?.track === "caption-detail"
                ? "nle-lane nle-lane--caption-detail"
                : "nle-lane nle-lane--caption-summary")
              : `nle-lane nle-lane--${layer.id}`;
    const lane = el("div", { class: laneClass });
    bindScrub(lane);
    for (const node of layer.nodes) {
      const block = renderNleTimelineNode(s, composition, layer, node, totalSeconds);
      if (block) lane.append(block);
    }
    const headMeta = nleTrackHeadMeta(layer);
    const controls = nleTrackControls(
      nleLayerTrackKind(layer),
      headMeta.label,
      {
        nested: Boolean(layer.nested),
        sequenceParent: Boolean(layer.staircase && layer.kind === "sequence"),
        title: headMeta.title,
        pro: absolute,
        trackType: nleLayerTrackType(layer),
        layer,
        totalSeconds,
      },
    );
    pushTrack(
      controls,
      lane,
      nleLayerTrackSize(layer),
    );
  }

  const rulerLane = el("div", {
    class: "nle-ruler",
    onclick: (event) => setEditPlayheadFromPointer(event, event.currentTarget, totalSeconds),
    ondblclick: (event) => seekAndPlayFromPointer(event, event.currentTarget, totalSeconds),
  }, ticks);

  const lanesCol = el("div", { class: "nle-lanes-col" },
    el("div", { class: "nle-playhead", style: `left:${playheadPct}%` }),
    ...laneRows,
  );

  return el("div", { class: `nle-timeline${absolute ? " nle-timeline--staircase nle-timeline--composition" : ""}` },
    el("div", { class: "nle-head" },
      el("div", { class: "nle-corner" }),
      rulerLane,
    ),
    el("div", { class: "nle-body" },
      el("div", { class: "nle-controls-col" }, ...controlRows),
      lanesCol,
    ),
  );
}

/* ------------------------------------------------------------------ *
 * Interactive NLE editing — drag/resize cut blocks on the timeline,   *
 * preview the draft live, then apply through the governed API.        *
 * ------------------------------------------------------------------ */

function renderRuntimeIsEditable(s) {
  const rt = (s.artifacts?.edit_decisions || {}).render_runtime;
  return rt === "remotion" || rt === "hyperframes";
}

function nleInitDraft() {
  if (nleDraft) return nleDraft;
  const canonical = state?.artifacts?.edit_decisions || {};
  nleDraft = {
    cuts: structuredClone(canonical.cuts || []),
    overlays: canonical.overlays != null ? structuredClone(canonical.overlays) : null,
  };
  return nleDraft;
}

function updateNleBlockVisual(block, cut, totalSeconds) {
  const inSec = Number(cut.in_seconds) || 0;
  const outSec = Number(cut.out_seconds) || inSec + 1;
  const dur = Math.max(outSec - inSec, 0.001);
  block.style.left = `${(inSec / totalSeconds) * 100}%`;
  block.style.width = `${(dur / totalSeconds) * 100}%`;
  const meta = block.querySelector(".nle-block-meta");
  if (meta) meta.textContent = fmtTimelineClock(dur);
}

function bindNleDragEdit(block, cut, totalSeconds) {
  const leftHandle = el("span", { class: "nle-block-handle nle-block-handle--left", title: t("editNleResize") });
  const rightHandle = el("span", { class: "nle-block-handle nle-block-handle--right", title: t("editNleResize") });
  block.append(leftHandle, rightHandle);
  block.classList.add("nle-block--editable");

  const startDrag = (mode, downEv) => {
    if (downEv.button !== 0) return;
    const isHandle = mode !== "move";
    if (isHandle) {
      // Handles have no click semantics of their own; suppress selection.
      downEv.preventDefault();
      downEv.stopPropagation();
    }
    // Body drags must NOT preventDefault — the block's click (selection)
    // must keep working for plain clicks. We gate the actual drag behind a
    // 3px movement threshold so clicks never mark the timeline dirty.
    const laneEl = block.closest(".nle-lane");
    const laneWidth = laneEl ? laneEl.offsetWidth : block.parentElement.offsetWidth;
    if (!laneWidth) return;

    const draft = nleInitDraft();
    const cutId = cut.id ?? cut.source;
    const draftCut = draft.cuts.find((c) => (c.id ?? c.source) === cutId) || draft.cuts[0];
    if (!draftCut) return;
    const startX = downEv.clientX;
    const startY = downEv.clientY;
    const startIn = Number(draftCut.in_seconds) || 0;
    const startOut = Number(draftCut.out_seconds) || startIn + 1;
    const MIN_DUR = 0.4;
    let moved = false;

    const onMove = (ev) => {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (!moved && Math.hypot(dx, dy) < 3) return; // below click threshold
      if (!moved) {
        moved = true;
        block.classList.add("nle-block--dragging");
      }
      const dxSec = (dx / laneWidth) * totalSeconds;
      if (mode === "resize-left") {
        const newIn = Math.min(Math.max(0, startIn + dxSec), startOut - MIN_DUR);
        draftCut.in_seconds = Math.round(newIn * 10) / 10;
      } else if (mode === "resize-right") {
        const newOut = Math.max(startOut + dxSec, startIn + MIN_DUR);
        draftCut.out_seconds = Math.round(newOut * 10) / 10;
      } else {
        const newIn = Math.max(0, startIn + dxSec);
        draftCut.in_seconds = Math.round(newIn * 10) / 10;
        draftCut.out_seconds = Math.round((newIn + (startOut - startIn)) * 10) / 10;
      }
      updateNleBlockVisual(block, draftCut, totalSeconds);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!moved) return; // plain click: selection handled by the click event
      block.classList.remove("nle-block--dragging");
      nleDirty = true;
      render();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  leftHandle.addEventListener("pointerdown", (e) => startDrag("resize-left", e));
  rightHandle.addEventListener("pointerdown", (e) => startDrag("resize-right", e));
  block.addEventListener("pointerdown", (e) => startDrag("move", e));
}

function renderEditNleToolbar(s, artifact) {
  if (!renderRuntimeIsEditable(s)) {
    return el("div", { class: "nle-edit-toolbar nle-edit-toolbar--locked" },
      el("span", { class: "edit-runtime-note" }, t("editNleFfmpegLocked")));
  }
  const dirty = Boolean(nleDraft) && nleDirty;
  return el("div", { class: "nle-edit-toolbar" },
    el("div", { class: "nle-edit-toolbar-status" },
      dirty ? el("span", { class: "nle-edit-dirty" }, t("editNleDirty")) : null),
    el("div", { class: "nle-edit-toolbar-actions" },
      el("button", { type: "button", class: "edit-advanced-btn",
        onclick: () => toggleNlePreview(s) }, t("editNleLivePreview")),
      el("button", { type: "button", class: "edit-advanced-btn",
        disabled: !dirty, onclick: () => previewNleDraft(s) }, t("editNlePreviewDraft")),
      el("button", { type: "button", class: "edit-advanced-btn edit-advanced-btn--primary",
        disabled: !dirty, onclick: () => applyNleDraft(s) }, t("editNleApply")),
      el("button", { type: "button", class: "edit-advanced-btn edit-advanced-btn--ghost",
        disabled: !dirty, onclick: discardNleDraft }, t("editNleDiscard")),
    ),
  );
}

async function toggleNlePreview(s) {
  try {
    const info = await getJSON(`/api/project/${encodedProjectId}/edit-preview`);
    const url = info.remotion?.nle_preview_url;
    if (url) {
      openEditPreviewModal({ url, runtime: "remotion", mode: "nle" }, "remotion", "nle");
      return;
    }
    const result = await postJSON(`/api/project/${encodedProjectId}/edit-preview/start`, {
      runtime: "remotion",
      mode: "nle",
    });
    if (result.url) {
      openEditPreviewModal(result, "remotion", "nle");
    } else {
      closeModal();
    }
  } catch (err) {
    closeModal();
    window.alert(err.message || String(err));
  }
}

async function previewNleDraft(s) {
  if (!nleDraft) return;
  try {
    await postJSON(`/api/project/${encodedProjectId}/nle-edit/preview`, {
      cuts: nleDraft.cuts,
      overlays: nleDraft.overlays,
    });
    await toggleNlePreview(s);
  } catch (err) {
    window.alert(err.message || String(err));
  }
}

async function applyNleDraft(s) {
  if (!nleDraft) return;
  const summary = nleDraft.cuts
    .map((c) => `${c.id || c.source}: ${fmtTimelineClock(Number(c.in_seconds) || 0)} – ${fmtTimelineClock(Number(c.out_seconds) || 0)}`)
    .join("\n");
  if (!window.confirm(`${t("editNleApplyConfirm")}\n\n${summary}`)) return;
  try {
    await postJSON(`/api/project/${encodedProjectId}/nle-edit/apply`, {
      cuts: nleDraft.cuts,
      overlays: nleDraft.overlays,
      decision_note: "用户在 Backlot NLE 时间线上确认的剪辑调整",
    });
    nleDraft = null;
    nleDirty = false;
    render(); // immediate refresh; SSE also fires (heartbeat up to 15s)
  } catch (err) {
    // 409 = draft stale: canonical edit_decisions changed underneath us.
    nleDraft = null;
    nleDirty = false;
    window.alert(err.message || String(err));
    render();
  }
}

function discardNleDraft() {
  nleDraft = null;
  nleDirty = false;
  render();
}

/**
 * After a page reload the in-memory draft is gone but the server-side draft
 * (renders/.nle_draft.json) may still exist — restore it so the timeline and
 * the preview iframe stay consistent. Runs at most once per session.
 */
async function restoreNleDraftFromServer() {
  try {
    const d = await getJSON(`/api/project/${encodedProjectId}/nle-edit/draft`);
    if (d.has_draft && !d.stale) {
      nleDraft = { cuts: d.cuts || [], overlays: d.overlays != null ? d.overlays : null };
      nleDirty = true;
      render();
    } else if (d.has_draft && d.stale) {
      // Canonical edit_decisions changed underneath the draft — drop it.
      nleDraft = null;
      nleDirty = false;
      render();
    }
  } catch {
    // Restoring the draft is best-effort; the board works without it.
  }
}

function renderEditRuntimeBar(s, artifact) {
  const runtime = artifact.render_runtime || "ffmpeg";
  const bar = el("div", { class: "edit-runtime-bar" },
    el("span", { class: `edit-runtime-chip edit-runtime-chip--${runtime}` }, runtime),
  );
  const actions = el("div", { class: "edit-advanced-actions" });

  if (runtime === "remotion") {
    actions.append(el("button", {
      type: "button",
      class: "edit-advanced-btn",
      onclick: () => openEditPreview("remotion", "studio"),
    }, t("editOpenRemotionStudio")));
  } else if (runtime === "hyperframes") {
    actions.append(el("button", {
      type: "button",
      class: "edit-advanced-btn",
      onclick: () => openEditPreview("hyperframes", "preview", { scaffold: true }),
    }, t("editOpenHyperFramesStudio")));
    actions.append(el("button", {
      type: "button",
      class: "edit-advanced-btn edit-advanced-btn--ghost",
      onclick: () => openEditPreview("hyperframes", "play", { scaffold: true }),
    }, t("editOpenHyperFramesPlayer")));
  } else {
    actions.append(el("span", { class: "edit-runtime-note" }, t("editFfmpegTimelineNote")));
  }

  bar.append(actions);
  return bar;
}

function renderEditDecisionsBody(s, artifact) {
  // NLE draft overlays the canonical edit_decisions while editing; canonical
  // data is only replaced through the governed apply flow (nle-edit/apply).
  const display = nleDraft
    ? { ...artifact, cuts: nleDraft.cuts, overlays: nleDraft.overlays ?? artifact.overlays }
    : artifact;
  const cuts = display.cuts || [];
  const summary = editAudioSummary(display);
  if (!cuts.length) {
    return el("div", { class: "edit-decisions-inline" }, summary);
  }

  const composition = buildCompositionTimeline(display, s);
  const { clipMeta, durationSeconds: totalSeconds } = composition;
  const captionTracks = buildNleCaptionTracks(s, display, totalSeconds);
  const safeIndex = Math.min(Math.max(0, selectedEditCutIndex), (display.cuts || []).length - 1);
  if (safeIndex !== selectedEditCutIndex) selectedEditCutIndex = safeIndex;

  setEditNleRuntime({ s, artifact: display, composition, clipMeta, captionTracks, totalSeconds });
  ensureEditNlePlaybackKeys();

  if (!nleDraftRestored) {
    nleDraftRestored = true;
    restoreNleDraftFromServer();
  }

  return el("div", { class: "edit-decisions-inline" },
    summary,
    renderEditRuntimeBar(s, display),
    renderEditNleToolbar(s, display),
    el("section", { class: "edit-timeline-section edit-nle-editor" },
      el("div", { class: "edit-timeline-head" },
        el("div", { class: "drawer-section-label" }, t("editTimelineTitle")),
      ),
      renderEditPreviewPanel(s, display, clipMeta, captionTracks, totalSeconds),
      el("div", { class: "edit-timeline-scroll" },
        renderNleTimeline(s, display, composition),
      ),
      el("p", { class: "edit-timeline-hint" }, t("editTimelineSelectHint")),
    ),
  );
}

function humanizeSubtitleStyle(subs) {
  if (subs.enabled === false) return t("editSubtitlesOff");
  const style = subs.style || "";
  const styleLabels = {
    "word-by-word": t("editSubtitleStyleWordByWord"),
    sentence: t("editSubtitleStyleSentence"),
    karaoke: t("editSubtitleStyleKaraoke"),
  };
  if (styleLabels[style]) return styleLabels[style];
  if (subs.source) {
    const base = String(subs.source).split("/").pop() || subs.source;
    return base;
  }
  return "";
}

function editAudioSummary(artifact) {
  const audio = artifact.audio || {};
  const facts = [];
  const narr = audio.narration?.segments || [];
  if (narr.length) facts.push(reviewFact(t("editNarrationSegments", { n: narr.length }), t("approved")));
  if (audio.music?.asset_id) facts.push(reviewFact(t("editMusicTrack", { id: audio.music.asset_id }), audio.music.volume ?? "—"));
  return reviewFacts(facts);
}


function renderOutputTile(s, output, index) {
  const media = resolveMediaRef(s, output);
  const label = media.path.split("/").pop() || t("item", { n: index + 1 });
  const meta = [
    output.format,
    output.resolution,
    output.duration_seconds != null ? fmtDuration(output.duration_seconds) : null,
    media.path !== label ? media.path : null,
  ].filter(Boolean).join(" · ");
  return el("article", { class: "render-output-tile" },
    el("div", { class: "render-output-head" },
      el("div", { class: "render-output-title" }, label),
      meta ? el("div", { class: "render-output-meta" }, meta) : null),
    buildMediaPreview(s, media, { variant: "full" }),
  );
}

function humanizeReviewStatus(status) {
  const map = {
    pass: t("finalReviewStatusPass"),
    revise: t("finalReviewStatusRevise"),
    fail: t("finalReviewStatusFail"),
  };
  return map[status] || status || "—";
}

function humanizeRecommendedAction(action) {
  const map = {
    present_to_user: t("finalReviewActionPresent"),
    re_render: t("finalReviewActionRerender"),
    revise_edit: t("finalReviewActionReviseEdit"),
    revise_assets: t("finalReviewActionReviseAssets"),
    block: t("finalReviewActionBlock"),
    re_author: t("finalReviewActionReAuthor"),
  };
  return map[action] || action || "—";
}

function finalReviewCheckFacts(checks) {
  if (!checks || typeof checks !== "object") return [];
  const facts = [];
  const tech = checks.technical_probe;
  if (tech?.resolution) facts.push(reviewFact(t("finalReviewCheckResolution"), tech.resolution));
  if (tech?.has_audio != null) {
    facts.push(reviewFact(
      t("finalReviewCheckAudio"),
      tech.has_audio ? t("finalReviewYes") : t("finalReviewNo"),
    ));
  }
  const visual = checks.visual_spotcheck;
  if (visual?.black_frames_detected) {
    facts.push(reviewFact(t("finalReviewCheckBlackFrames"), t("finalReviewDetected")));
  }
  const subtitle = checks.subtitle_check;
  if (subtitle?.subtitles_expected) {
    facts.push(reviewFact(
      t("finalReviewCheckSubtitles"),
      subtitle.subtitles_present ? t("finalReviewYes") : t("finalReviewNo"),
    ));
  }
  return facts.filter(Boolean);
}

function renderFinalReviewReport(finalReview) {
  if (!finalReview) return null;
  const issues = finalReview.issues_found || [];
  const statusClass = finalReview.status === "pass" ? "ok" : finalReview.status === "fail" ? "crit" : "";
  return el("section", { class: "compose-review-report" },
    el("div", { class: "drawer-section-label" }, t("finalReviewTitle")),
    reviewFacts([
      reviewFact(t("reviewStatus"), humanizeReviewStatus(finalReview.status)),
      reviewFact(t("recommendedAction"), humanizeRecommendedAction(finalReview.recommended_action)),
      reviewFact(t("reviewIssues"), issues.length ? `${issues.length} ${t("reviewIssueUnit")}` : t("none")),
      ...finalReviewCheckFacts(finalReview.checks),
    ]),
    issues.length
      ? el("ul", { class: "approval-items final-review-issues" },
        issues.map((issue) => el("li", { class: statusClass }, shortText(issue, 320))))
      : null,
  );
}

function renderComposeReviewBody(s, renderReport, finalReview) {
  const outputs = renderReport?.outputs || [];
  const warnings = [
    ...(renderReport?.warnings || []),
    ...(renderReport?.verification_notes || []),
  ];
  const nodes = [];
  if (outputs.length) {
    nodes.push(el("div", { class: "render-report-inline" },
      ...outputs.map((output, index) => renderOutputTile(s, output, index)),
    ));
  }
  const report = renderFinalReviewReport(finalReview);
  if (report) nodes.push(report);
  if (warnings.length) {
    nodes.push(
      el("section", { class: "compose-review-warnings" },
        el("div", { class: "drawer-section-label" }, t("finalReviewRenderWarnings")),
        el("ul", { class: "approval-items" },
          warnings.map((note) => el("li", {}, shortText(note, 320))),
        ),
      ),
    );
  }
  return el("div", { class: "compose-review-inline" }, ...nodes);
}

function renderFinalReviewBody(s, artifact) {
  return el("div", { class: "final-review-inline" },
    renderFinalReviewReport(artifact),
  );
}

function renderRenderReportBody(s, artifact) {
  const outputs = artifact.outputs || [];
  return el("div", { class: "render-report-inline" },
    ...outputs.map((output, index) => renderOutputTile(s, output, index)),
  );
}

function closeSummaryPreview() {
  if (!summaryOpenItem) return;
  const { li, viewBtn } = summaryOpenItem;
  li.classList.remove("asset-item--open");
  const panel = li.querySelector(".asset-preview");
  if (panel) panel.setAttribute("hidden", "");
  if (viewBtn) viewBtn.textContent = t("summaryViewDoc");
  summaryOpenItem = null;
}

function toggleSummaryPreview(li, viewBtn) {
  const panel = li.querySelector(".asset-preview");
  if (!panel) return;
  const isOpen = li.classList.contains("asset-item--open");
  closeSummaryPreview();
  if (!isOpen) {
    li.classList.add("asset-item--open");
    panel.removeAttribute("hidden");
    if (viewBtn) viewBtn.textContent = t("summaryHideDoc");
    summaryOpenItem = { li, viewBtn };
    panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function renderSummaryViewButton(li, present) {
  if (!present) return el("span", { class: "asset-row-action" }, "");
  const viewBtn = el("button", {
    type: "button",
    class: "asset-row-view",
  }, t("summaryViewDoc"));
  viewBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleSummaryPreview(li, viewBtn);
  });
  return viewBtn;
}

function renderArtifactItem(s, entry, { showStage = true } = {}) {
  const present = Boolean(entry.present);
  const stages = entry.stages?.length
    ? entry.stages.map((stageName) => stageLabel(stageName)).join(" · ")
    : "";
  const path = entry.path || `artifacts/${entry.name}.json`;
  const li = el("li", { class: "asset-item" });
  const rowChildren = [
    el("span", { class: "asset-row-name" }, artifactLabel(entry.name)),
    el("span", { class: "asset-row-path" }, path || "—"),
  ];
  if (showStage) {
    rowChildren.push(el("span", { class: "asset-row-stage" }, stages || "—"));
  }
  rowChildren.push(
    el("span", { class: `asset-row-status${present ? " ok" : ""}` },
      present ? t("summaryArtifactPresent") : t("summaryArtifactPending")),
    renderSummaryViewButton(li, present),
  );
  li.append(
    el("div", {
      class: `asset-row asset-row--artifact${present ? "" : " asset-row--pending"}${showStage ? "" : " asset-row--no-stage"}`,
    }, ...rowChildren),
    el("div", { class: "asset-preview", hidden: "" },
      present ? buildArtifactPreview(s, entry) : null,
    ),
  );
  return li;
}

function renderMediaItem(s, item, index) {
  const label = item.label || (item.path || "").split("/").pop() || t("item", { n: 1 });
  const present = item.type === "url" ? Boolean(item.path) : Boolean(item.exists);
  const li = el("li", { class: "asset-item" });
  li.append(
    el("div", {
      class: `asset-row asset-row--media${present ? "" : " asset-row--pending"}`,
    },
      el("span", { class: "asset-row-name" }, label),
      el("span", { class: "asset-row-type" }, mediaTypeLabel(item.type, item.path)),
      el("span", { class: "asset-row-path" }, item.path || "—"),
      el("span", { class: `asset-row-status${present ? " ok" : ""}` },
        present ? t("summaryMediaPresent") : t("summaryMediaMissing")),
      renderSummaryViewButton(li, present),
    ),
    el("div", { class: "asset-preview", hidden: "" },
      present ? buildMediaPreview(s, item) : null,
    ),
  );
  return li;
}

function renderAssetSection({ title, desc, countLabel, headCols, rows, emptyHint, tableKind, tableExtraClass = "" }) {
  const tableClass = `asset-table asset-table--${tableKind}${tableExtraClass ? ` ${tableExtraClass}` : ""}`;
  return el("section", { class: "asset-section" },
    el("header", { class: "asset-section-head" },
      el("div", { class: "asset-section-titles" },
        el("h3", { class: "asset-section-title" }, title),
        el("p", { class: "asset-section-desc" }, desc),
      ),
      countLabel ? el("span", { class: "asset-section-count" }, countLabel) : null,
    ),
    rows.length
      ? el("div", { class: tableClass },
        renderAssetTableHead(headCols),
        el("ul", { class: "asset-list" }, ...rows),
      )
      : el("p", { class: "hint asset-section-empty" }, emptyHint),
  );
}

function buildProjectSummaryContent(s) {
  const summary = s.project_summary || { artifacts: [], by_stage: [], media: [], counts: {} };
  const counts = summary.counts || {};
  const byStage = summary.by_stage || [];
  const media = summary.media || [];

  const artifactHeadWithStage = [
    t("summaryColName"), t("summaryColPath"), t("summaryColStage"),
    t("summaryColStatus"), t("summaryColAction"),
  ];
  const artifactHeadGrouped = [
    t("summaryColName"), t("summaryColPath"), t("summaryColStatus"), t("summaryColAction"),
  ];

  const artifactSections = byStage.length
    ? byStage.map((group) => {
      const entries = (group.artifacts || []).filter((entry) => entry.name !== "decision_log");
      const rows = entries.map((entry) => renderArtifactItem(s, entry, { showStage: false }));
      const title = group.stage === "_orphan"
        ? t("summaryOrphanSectionTitle")
        : stageLabel(group.stage);
      const desc = group.stage === "_orphan" ? t("summaryOrphanSectionDesc") : "";
      const present = entries.filter((e) => e.present).length;
      return renderAssetSection({
        title,
        desc,
        countLabel: entries.length ? t("summaryStageArtifacts", { present, total: entries.length }) : null,
        headCols: artifactHeadGrouped,
        rows,
        emptyHint: t("summaryNoArtifacts"),
        tableKind: "artifact",
        tableExtraClass: "asset-table--artifact-grouped",
      });
    })
    : [renderAssetSection({
      title: t("summaryArtifactSectionTitle"),
      desc: t("summaryArtifactSectionDesc"),
      countLabel: counts.artifacts_total != null
        ? t("summaryArtifacts", {
          present: counts.artifacts_present ?? 0,
          total: counts.artifacts_total ?? 0,
        })
        : null,
      headCols: artifactHeadWithStage,
      rows: (summary.artifacts || [])
        .filter((entry) => entry.name !== "decision_log")
        .map((entry) => renderArtifactItem(s, entry)),
      emptyHint: t("summaryNoArtifacts"),
      tableKind: "artifact",
    })];

  const mediaRows = media.map((item, index) => renderMediaItem(s, item, index));
  const mediaCount = counts.media != null
    ? t("summaryMedia", { n: counts.media ?? 0 })
    : null;

  return el("div", { class: "project-summary-body" },
    el("header", { class: "project-summary-head" },
      el("h2", { class: "project-summary-title" }, t("projectSummaryTitle")),
      el("p", { class: "hint project-summary-lead" }, t("projectSummaryLead")),
    ),
    ...artifactSections,
    renderAssetSection({
      title: t("summaryMediaSectionTitle"),
      desc: t("summaryMediaSectionDesc"),
      countLabel: mediaCount,
      headCols: [t("summaryColName"), t("summaryColType"), t("summaryColPath"), t("summaryColStatus"), t("summaryColAction")],
      rows: mediaRows,
      emptyHint: t("summaryNoMedia"),
      tableKind: "media",
    }),
  );
}

function openProjectSummaryModal() {
  if (!state) return;
  summaryOpenItem = null;
  mountSummaryModal(buildProjectSummaryContent(state));
}

function reviewMetrics(review) {
  const nested = review && review.summary && typeof review.summary === "object"
    ? review.summary : {};
  return {
    critical: Number((review && review.critical) ?? nested.critical ?? 0),
    suggestions: Number((review && review.suggestions) ?? nested.suggestions ?? 0),
    nitpicks: Number((review && review.nitpicks) ?? nested.nitpicks ?? 0),
  };
}

function reviewSummaryText(review) {
  if (!review) return "";
  if (typeof review.summary === "string") return review.summary;
  const nested = review.summary && typeof review.summary === "object" ? review.summary : {};
  const counts = reviewMetrics(review);
  return [
    review.decision,
    `${counts.critical} critical`,
    `${counts.suggestions} suggestion${counts.suggestions === 1 ? "" : "s"}`,
    nested.review_focus_met ? `review focus ${nested.review_focus_met}` : null,
    nested.schema_validation,
  ].filter(Boolean).join(" · ");
}

function stageForArtifact(s, artifactName, fallbackStage) {
  for (const st of s.stages) {
    if (artifactNamesForStage(st).includes(artifactName)) return st;
  }
  if (fallbackStage) {
    return s.stages.find((st) => st.name === fallbackStage) || { name: fallbackStage, status: "unknown" };
  }
  return null;
}

const ARTIFACT_PATHS = {
  script: "artifacts/script.json",
  scene_plan: "artifacts/scene_plan.json",
  asset_manifest: "artifacts/asset_manifest.json",
  render_report: "artifacts/render_report.json",
  source_media_review: "artifacts/source_media_review.json",
};

function artifactBlockStatus(st) {
  if (!st || !st.status) return null;
  if (st.status === "completed") {
    return el("span", { class: "artifact-block-status ok" }, t("approved"));
  }
  if (st.status === "awaiting_human") {
    return el("span", { class: "artifact-block-status pending" }, t("pendingApproval"));
  }
  if (st.status === "in_progress") {
    return el("span", { class: "artifact-block-status draft" }, t("drafting"));
  }
  if (st.status === "failed") {
    return el("span", { class: "artifact-block-status failed" }, t("failed"));
  }
  return null;
}

function renderArtifactBlockHeader(s, artifactName, fallbackStage, meta) {
  const st = stageForArtifact(s, artifactName, fallbackStage);
  const stageName = st?.name || fallbackStage || "";
  const path = ARTIFACT_PATHS[artifactName] || `artifacts/${artifactName}.json`;
  return el("div", { class: "artifact-block-head" },
    el("button", {
      type: "button",
      class: "artifact-block-kicker",
      title: t("openStageDrawer"),
      onclick: (e) => {
        e.stopPropagation();
        selectedStage = stageName;
        render();
      },
    },
      el("span", { class: "artifact-block-stage" }, stageLabel(stageName)),
      el("span", { class: "artifact-block-sep" }, t("stageArtifactSep")),
      el("span", { class: "artifact-block-artifact" }, artifactLabel(artifactName)),
    ),
    el("span", { class: "artifact-block-path" }, path),
    meta ? el("span", { class: "artifact-block-meta" }, meta) : null,
    artifactBlockStatus(st),
  );
}

function wrapArtifactBlock(s, artifactName, fallbackStage, content, meta) {
  return el("div", { class: `artifact-block artifact-block--${artifactName}` },
    renderArtifactBlockHeader(s, artifactName, fallbackStage, meta),
    content,
  );
}

// ---------------------------------------------------------------------------
// script card
// ---------------------------------------------------------------------------

function scriptSections(script, limit) {
  const sections = script.sections || [];
  const shown = limit ? sections.slice(0, limit) : sections;
  const nodes = [];
  for (const sec of shown) {
    nodes.push(el("div", { class: "sp-slug" },
      `${(sec.id || "").toUpperCase()} · ${sec.label || t("section")} `,
      el("span", { class: "tc" }, `${fmtDuration(sec.start_seconds)} - ${fmtDuration(sec.end_seconds)}`)));
    if (sec.text) nodes.push(el("div", { class: "sp-action" }, sec.text));
    if (sec.speaker_directions) nodes.push(el("div", { class: "sp-paren" }, `(${sec.speaker_directions})`));
    const cues = sec.enhancement_cues || [];
    if (cues.length) {
      nodes.push(el("div", { style: "margin-left:42px" },
        cues.map((c) => el("span", { class: "sp-cue" }, `▸ ${c.type} · ${String(c.description || "").slice(0, 60)}`))));
    }
  }
  if (limit && sections.length > limit) {
    nodes.push(el("div", { class: "sp-fade" }, t("moreSections", { n: sections.length - limit })));
  }
  return nodes;
}

function renderScriptBody(script, { includeHeader = false, title = "" } = {}) {
  const nodes = [];
  if (includeHeader) {
    nodes.push(
      el("div", { class: "sp-title" }, title || script.title || ""),
      el("div", { class: "sp-meta" },
        t("scriptMeta", {
          dur: fmtDuration(script.total_duration_seconds),
          n: (script.sections || []).length,
        })),
    );
  }
  nodes.push(...scriptSections(script, 0));
  return el("div", { class: "script-card script-card--inline" }, ...nodes);
}

function renderScriptCard(s) {
  const script = s.artifacts.script;
  if (!script) return null;

  const card = el("div", { class: "script-card script-preview", title: t("clickExpandScript"), onclick: openScriptModal },
    el("div", { class: "sp-title" }, script.title || s.title),
    el("div", { class: "sp-meta" },
      t("scriptMeta", {
        dur: fmtDuration(script.total_duration_seconds),
        n: (script.sections || []).length,
      })),
    ...scriptSections(script, 4),
    el("span", { class: "sp-expand" }, t("expandScript")),
  );
  return wrapArtifactBlock(s, "script", "script", card);
}

function humanize(value) {
  return artifactLabel(value);
}

function shortText(value, limit = 180) {
  const text = String(value || "").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function reviewFact(label, value) {
  if (value == null || value === "") return null;
  return el("div", { class: "approval-fact" },
    el("span", {}, label),
    el("b", {}, value),
  );
}

function reviewFacts(items) {
  const facts = items.filter(Boolean);
  return facts.length ? el("div", { class: "approval-facts" }, facts) : null;
}

function titledItems(items, selectedId = null) {
  const rows = (items || []).slice(0, 4).map((item, index) => {
    if (item == null) return null;
    if (typeof item !== "object") {
      return el("li", {}, shortText(item));
    }
    const id = item.id || item.concept_id || item.option_id;
    const title = item.title || item.name || item.display_name || item.label || id || item.path || item.platform || item.description || t("item", { n: index + 1 });
    const detail = item.hook || item.why_this_works || item.summary || item.description || item.silhouette_notes;
    return el("li", { class: id && id === selectedId ? "selected" : "" },
      el("div", { class: "approval-item-title" }, shortText(title, 100),
        id && id === selectedId ? el("span", { class: "approval-selected" }, t("selected")) : null),
      detail && detail !== title ? el("p", {}, shortText(detail)) : null,
    );
  }).filter(Boolean);
  return rows.length ? el("ul", { class: "approval-items" }, rows) : null;
}

function genericArtifactSummary(artifact) {
  const facts = [];
  const items = [];
  for (const [key, value] of Object.entries(artifact || {})) {
    if (["version", "decision_log_ref"].includes(key)) continue;
    if (["string", "number", "boolean"].includes(typeof value)) {
      facts.push(reviewFact(humanize(key), shortText(value, 90)));
    } else if (Array.isArray(value)) {
      facts.push(reviewFact(humanize(key), `${value.length} ${value.length === 1 ? "项" : "项"}`));
      if (!items.length && value.length) items.push(titledItems(value));
    }
    if (facts.length >= 6) break;
  }
  return [reviewFacts(facts), ...items].filter(Boolean);
}

function publishExportMedia(s) {
  const media = (s.project_summary && s.project_summary.media) || [];
  return media.filter((m) => {
    const p = m.path || "";
    return m.source_artifact === "publish_log" || p.startsWith("exports/");
  });
}

function publishCoverPreview(s) {
  const cover = publishExportMedia(s).find((m) => m.type === "image" && m.exists && m.renderable);
  if (!cover) return null;
  return el("div", { class: "approval-cover" },
    el("div", { class: "approval-cover-label" }, t("publishCover")),
    el("img", {
      class: "approval-cover-img",
      src: thumbURL(s.project_id, cover.path, 720),
      alt: "",
      loading: "lazy",
    }),
  );
}

function renderVideoAnalysisBriefBody(artifact) {
  if (!artifact || typeof artifact !== "object") return null;
  const custom = ((artifact.replication_guidance || {}).playbook_customizations) || {};
  const dna = custom.dna_lock || artifact.global_dna_lock || {};
  const scenes = (artifact.structure_analysis || {}).scenes || [];
  const replicate = (artifact.replication_guidance || {}).key_elements_to_replicate || [];
  const blocks = [];

  const dnaBits = [
    dna.subject ? el("p", { class: "ref-dna-line" }, el("b", {}, `${t("refDnaLock")} · `), dna.subject) : null,
    dna.scene ? el("p", { class: "ref-dna-line" }, dna.scene) : null,
    dna.lighting ? el("p", { class: "ref-dna-line ref-dna-line--muted" }, dna.lighting) : null,
    dna.control_tokens
      ? el("p", { class: "ref-dna-tokens" }, dna.control_tokens)
      : null,
  ].filter(Boolean);
  if (dnaBits.length) {
    blocks.push(el("div", { class: "ref-analysis-block" }, ...dnaBits));
  }

  if (replicate.length) {
    blocks.push(el("div", { class: "ref-analysis-block" },
      el("div", { class: "ref-analysis-kicker" }, t("refReplicateElements")),
      el("ul", { class: "ref-analysis-list" },
        ...replicate.slice(0, 8).map((item) => el("li", {}, shortText(item, 200)))),
    ));
  }

  if (scenes.length) {
    const rows = scenes.map((scene) => {
      const start = Number(scene.start_time) || 0;
      const end = Number(scene.end_time) || start;
      const timing = `${fmtDuration(start)} – ${fmtDuration(end)}`;
      const bits = [
        scene.description ? el("p", { class: "ref-scene-desc" }, scene.description) : null,
        scene.on_screen_text
          ? el("p", { class: "ref-scene-meta" }, el("b", {}, `${t("refOverlays")}: `), scene.on_screen_text)
          : null,
        scene.narration_text
          ? el("p", { class: "ref-scene-meta" }, el("b", {}, `${t("refSceneNarration")}: `), scene.narration_text)
          : null,
        scene.motion_type
          ? el("p", { class: "ref-scene-meta" }, el("b", {}, `${t("refMotionProfile")}: `), String(scene.motion_type).replaceAll("_", " "))
          : null,
      ].filter(Boolean);
      if (!bits.length) return null;
      return el("article", { class: "ref-scene-row" },
        el("div", { class: "ref-scene-head" },
          el("span", { class: "ref-scene-idx" }, `#${(scene.scene_index ?? 0) + 1}`),
          el("span", { class: "ref-scene-time" }, timing)),
        ...bits);
    }).filter(Boolean);
    blocks.push(el("div", { class: "ref-analysis-block" },
      el("div", { class: "ref-analysis-kicker" }, t("refSceneBreakdown")),
      rows.length
        ? el("div", { class: "ref-scene-list" }, ...rows)
        : el("p", { class: "hint" }, t("refNoSceneDetail"))));
  }

  return blocks.length ? el("div", { class: "ref-analysis-body" }, ...blocks) : null;
}

function renderReferenceAnalysisCard(s) {
  const brief = s.artifacts?.video_analysis_brief;
  if (!brief || typeof brief !== "object") return null;
  const source = brief.source || {};
  const scenes = (brief.structure_analysis || {}).scenes || [];
  const dur = source.duration_seconds != null ? fmtDuration(source.duration_seconds) : "—";
  const meta = t("refAnalysisMeta", { n: scenes.length || brief.structure_analysis?.total_scenes || 0, dur });
  const body = renderVideoAnalysisBriefBody(brief);
  if (!body) return null;
  return wrapArtifactBlock(s, "video_analysis_brief", "reference_analysis", body, meta);
}

function artifactReviewContent(name, artifact, s) {
  if (name === "brief") {
    return [
      artifact.hook ? el("p", { class: "approval-lead" }, artifact.hook) : null,
      reviewFacts([
        reviewFact(t("platform"), artifact.target_platform),
        reviewFact(t("duration"), artifact.target_duration_seconds != null ? fmtDuration(artifact.target_duration_seconds) : null),
        reviewFact(t("tone"), artifact.tone),
        reviewFact(t("style"), artifact.style),
      ]),
      titledItems(artifact.key_points),
    ].filter(Boolean);
  }
  if (name === "proposal_packet") {
    const selected = (artifact.selected_concept || {}).concept_id;
    const concept = (artifact.concept_options || []).find((item) => item.id === selected)
      || (artifact.concept_options || [])[0];
    const plan = artifact.production_plan || {};
    const cost = artifact.cost_estimate || {};
    return [
      concept?.core_message
        ? el("p", { class: "approval-lead" }, shortText(concept.core_message, 220))
        : concept?.hook
          ? el("p", { class: "approval-lead" }, shortText(concept.hook, 220))
          : null,
      reviewFacts([
        reviewFact(t("runtime"), plan.render_runtime),
        reviewFact(t("pipelineField"), plan.pipeline),
        reviewFact(t("estimatedCost"), cost.total_estimated_usd != null ? fmtMoney(cost.total_estimated_usd) : null),
        reviewFact(t("concepts"), Array.isArray(artifact.concept_options) ? artifact.concept_options.length : null),
      ]),
      titledItems(artifact.concept_options, selected),
      (artifact.selected_concept || {}).rationale
        ? el("p", { class: "approval-rationale" },
          el("b", {}, t("whyThisConcept")), shortText(artifact.selected_concept.rationale))
        : null,
    ].filter(Boolean);
  }
  if (name === "research_brief") {
    return [
      artifact.topic ? el("p", { class: "approval-lead" }, artifact.topic) : null,
      reviewFacts([
        reviewFact(t("sources"), Array.isArray(artifact.sources) ? artifact.sources.length : null),
        reviewFact(t("dataPoints"), Array.isArray(artifact.data_points) ? artifact.data_points.length : null),
        reviewFact(t("angles"), Array.isArray(artifact.angles_discovered) ? artifact.angles_discovered.length : null),
      ]),
      titledItems(artifact.angles_discovered),
    ].filter(Boolean);
  }
  if (name === "script") {
    return [
      reviewFacts([
        reviewFact(t("duration"), fmtDuration(artifact.total_duration_seconds)),
        reviewFact(t("sections"), (artifact.sections || []).length),
      ]),
      renderScriptBody(artifact),
    ].filter(Boolean);
  }
  if (name === "scene_plan") {
    const scenes = artifact.scenes || [];
    const end = scenes.reduce((max, scene) => Math.max(max, Number(scene.end_seconds) || 0), 0);
    return [
      reviewFacts([
        reviewFact(t("scenesField"), scenes.length),
        reviewFact(t("duration"), end ? fmtDuration(end) : null),
      ]),
      renderScenePlanBody(s, artifact),
    ].filter(Boolean);
  }
  if (name === "asset_manifest") {
    const assets = artifact.assets || [];
    const types = [...new Set(assets.map((asset) => asset.type).filter(Boolean))];
    return [
      reviewFacts([
        reviewFact(t("assets"), assets.length),
        reviewFact(t("types"), types.join(", ")),
        reviewFact(t("generationCost"), artifact.total_cost_usd != null ? fmtMoney(artifact.total_cost_usd) : null),
      ]),
      renderAssetManifestBody(s, artifact),
    ].filter(Boolean);
  }
  if (name === "edit_decisions") {
    const cuts = artifact.cuts || [];
    const composition = buildCompositionTimeline(artifact, s);
    const timelineEnd = composition.durationSeconds;
    const subtitleStyle = humanizeSubtitleStyle(artifact.subtitles || {});
    return [
      reviewFacts([
        reviewFact(t("cuts"), cuts.length),
        reviewFact(t("runtime"), artifact.render_runtime || (artifact.metadata || {}).render_runtime),
        reviewFact(t("duration"), timelineEnd ? fmtDuration(timelineEnd) : null),
        reviewFact(t("pipelineField"), artifact.renderer_family),
        reviewFact("合成", artifact.composition_mode),
        reviewFact(t("editSubtitleStyle"), subtitleStyle),
      ]),
      renderEditDecisionsBody(s, artifact),
    ].filter(Boolean);
  }
  if (name === "render_report") {
    const outputs = artifact.outputs || [];
    const duration = outputs[0]?.duration_seconds ?? artifact.duration_seconds;
    return [
      reviewFacts([
        reviewFact(t("outputs"), outputs.length),
        reviewFact(t("duration"), duration != null ? fmtDuration(duration) : null),
      ]),
      renderRenderReportBody(s, artifact),
    ].filter(Boolean);
  }
  if (name === "final_review") {
    return [renderFinalReviewBody(s, artifact)];
  }
  if (name === "publish_log") {
    return [
      publishCoverPreview(s),
      reviewFacts([reviewFact(t("destinations"), Array.isArray(artifact.entries) ? artifact.entries.length : null)]),
      titledItems((artifact.entries || []).map((entry) => ({
        title: entry.platform || entry.destination || t("publishDestination"),
        description: [entry.status, entry.export_path, entry.url].filter(Boolean).join(" · "),
      }))),
    ].filter(Boolean);
  }
  if (name === "video_analysis_brief") {
    const source = artifact.source || {};
    const content = artifact.content_analysis || {};
    const detail = renderVideoAnalysisBriefBody(artifact);
    return [
      content.summary ? el("p", { class: "approval-lead" }, shortText(content.summary, 220)) : null,
      reviewFacts([
        reviewFact(t("duration"), source.duration_seconds != null ? fmtDuration(source.duration_seconds) : null),
        reviewFact(t("scenesField"), (artifact.structure_analysis || {}).total_scenes),
        reviewFact("来源", source.title || source.url || source.local_path),
      ]),
      detail,
    ].filter(Boolean);
  }
  return genericArtifactSummary(artifact);
}

function artifactReviewTitle(name, artifact, s) {
  if (name === "proposal_packet") {
    const selected = (artifact.selected_concept || {}).concept_id;
    const concept = (artifact.concept_options || []).find((item) => item.id === selected);
    return (concept && concept.title) || t("productionProposal");
  }
  if (name === "research_brief") return artifact.topic || t("researchBrief");
  if (name === "scene_plan") return t("scenePlanTitle");
  if (name === "asset_manifest") return t("generatedAssets");
  if (name === "edit_decisions") return t("editDecisions");
  if (name === "render_report") return t("renderReport");
  if (name === "final_review") return artifact.metadata?.title || t("finalReviewTitle");
  if (name === "publish_log") return t("publishPlan");
  return artifact.title || artifact.name || s.title;
}

function renderApprovalReview(s) {
  const awaiting = s.stages.find((item) => item.status === "awaiting_human");
  if (!awaiting) return null;

  const names = artifactNamesForStage(awaiting);
  const entries = names
    .filter((name) => name !== "decision_log")
    .map((name) => [name, s.artifacts[name]])
    .filter(([, artifact]) => artifact && typeof artifact === "object");
  const stageIndex = s.stages.findIndex((item) => item.name === awaiting.name);
  const nextStage = stageIndex >= 0 ? s.stages[stageIndex + 1] : null;
  const review = awaiting.review || {};
  const reviewSummary = reviewSummaryText(review);

  let artifacts;
  if (awaiting.name === "compose") {
    const renderReport = s.artifacts.render_report;
    const finalReview = s.artifacts.final_review;
    if (renderReport || finalReview) {
      const outputs = renderReport?.outputs || [];
      const duration = outputs[0]?.duration_seconds;
      artifacts = [el("article", {
        class: "approval-artifact approval-artifact--compose",
        "data-artifact": "compose_result",
      },
        el("div", { class: "approval-artifact-kicker" }, t("composeResultKicker")),
        el("h2", {}, t("composeResultTitle")),
        reviewFacts([
          reviewFact(t("outputs"), outputs.length || null),
          reviewFact(t("duration"), duration != null ? fmtDuration(duration) : null),
        ]),
        renderComposeReviewBody(s, renderReport, finalReview),
      )];
    } else {
      artifacts = [];
    }
  } else {
    artifacts = entries.map(([name, artifact]) => el("article", {
      class: "approval-artifact",
      "data-artifact": name,
    },
      el("div", { class: "approval-artifact-kicker" }, humanize(name)),
      el("h2", {}, artifactReviewTitle(name, artifact, s)),
      ...artifactReviewContent(name, artifact, s),
    ));
  }

  if (!artifacts.length) {
    artifacts.push(el("div", { class: "approval-missing", role: "alert" },
      el("b", {}, t("nothingReviewable")),
      names.length
        ? t("checkpointDeclaresMissing", {
          stage: stageLabel(awaiting.name),
          artifacts: names.map(humanize).join("、"),
        })
        : t("checkpointNoArtifact", { stage: stageLabel(awaiting.name) }),
    ));
  }

  return el("section", { class: "approval-review", "data-stage": awaiting.name },
    el("div", { class: "approval-review-head" },
      el("div", {},
        el("div", { class: "approval-eyebrow" }, t("reviewGate")),
        el("h2", {}, t("stageReadyReview", { stage: stageLabel(awaiting.name) })),
        el("p", {}, t("reviewInChat")),
      ),
      el("span", { class: "approval-status" }, t("pendingApproval")),
    ),
    reviewSummary ? el("div", { class: "approval-review-note" },
      el("b", {}, t("selfReview")), shortText(reviewSummary, 260)) : null,
    el("div", { class: "approval-artifacts" }, artifacts),
    el("div", { class: "approval-review-foot" },
      el("span", {}, nextStage
        ? t("approvalUnlocks", { stage: stageLabel(nextStage.name) })
        : t("finalApprovalGate")),
      el("div", { class: "run-btn-group" },
        el("button", { type: "button", onclick: () => toggleDrawer(awaiting.name) }, t("openFullArtifact")),
        approvalButtons(awaiting.name)),
    ),
  );
}

function openScriptModal() {
  const script = state && state.artifacts.script;
  if (!script) return;
  modal.innerHTML = "";
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: "modal-page" },
      el("div", { class: "script-card", style: "cursor:default" },
        el("div", { class: "sp-title" }, script.title || state.title),
        el("div", { class: "sp-meta" },
          t("scriptMeta", {
            dur: fmtDuration(script.total_duration_seconds),
            n: (script.sections || []).length,
          })),
        ...scriptSections(script, 0),
        el("div", { class: "sp-fade" }, t("end")),
      )),
  );
  modal.classList.add("open");
}

function openNarrModal(card) {
  modal.innerHTML = "";
  const meta = [sceneLabel(card.id), card.section_label, fmtDuration(card.duration_seconds)]
    .filter(Boolean).join(" · ");
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: "modal-page" },
      el("div", { class: "script-card", style: "cursor:default" },
        el("div", { class: "sp-meta" }, meta),
        card.narration ? el("div", { class: "sp-action", style: "margin-left:0" }, card.narration) : null,
        card.shot_intent ? el("div", { class: "sp-paren", style: "margin-left:0" }, t("intent", { text: card.shot_intent })) : null,
        card.description ? el("div", { class: "sp-paren", style: "margin-left:0" }, card.description) : null,
      )),
  );
  modal.classList.add("open");
}

function sceneGenerationPrompt(card) {
  const primary = String(card.generation_prompt || card.planned_prompt || "").trim();
  if (primary) return primary;
  for (const asset of card.required_assets || []) {
    if (["video", "image"].includes(asset?.type) && asset?.source === "generate" && asset.description) {
      const d = String(asset.description).trim();
      if (asset.type === "image") return d;
      if (d.includes("Aspect ratio:") || d.startsWith("[INHERIT DNA LOCK]")) return d;
    }
  }
  const visual = card.visual;
  if (visual?.prompt && visual.source_tool !== "frame_sampler") {
    return String(visual.prompt).trim();
  }
  for (let i = (card.takes || []).length - 1; i >= 0; i--) {
    const take = card.takes[i];
    if (take?.prompt && take.source_tool !== "frame_sampler") {
      return String(take.prompt).trim();
    }
  }
  if (visual?.prompt) return String(visual.prompt).trim();
  for (let i = (card.takes || []).length - 1; i >= 0; i--) {
    const take = card.takes[i];
    if (take?.prompt) return String(take.prompt).trim();
  }
  if (visual?.generation_summary) return String(visual.generation_summary).trim();
  for (let i = (card.takes || []).length - 1; i >= 0; i--) {
    const take = card.takes[i];
    if (take?.generation_summary) return String(take.generation_summary).trim();
  }
  return "";
}

function openScenePromptModal(card, promptText) {
  const prompt = String(promptText || sceneGenerationPrompt(card)).trim();
  if (!prompt) return;
  modal.innerHTML = "";
  const meta = [sceneLabel(card.id), card.section_label, fmtDuration(card.duration_seconds)]
    .filter(Boolean).join(" · ");
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: "modal-page modal-page-summary modal-page-prompt" },
      el("div", { class: "script-card script-card--prompt", style: "cursor:default" },
        el("div", { class: "sp-meta" }, meta),
        el("div", { class: "sp-cue" }, "生成提示词 · " + (card.visual?.source_tool || "scene_plan")),
        el("div", { class: "scene-prompt-body scene-prompt-body--scroll" }, prompt),
      )),
  );
  modal.classList.add("open");
}

function openSceneVideoModal(s, card, visual) {
  modal.innerHTML = "";
  const meta = [sceneLabel(card.id), card.section_label, fmtDuration(card.duration_seconds)]
    .filter(Boolean).join(" · ");
  const prompt = sceneGenerationPrompt(card);
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: "modal-page modal-page-viewer" },
      el("div", { class: "scene-video-modal" },
        el("div", { class: "scene-video-meta" }, meta),
        el("video", {
          class: "scene-video-full",
          src: mediaURL(s.project_id, visual.path),
          controls: "",
          autoplay: "",
          preload: "auto",
          playsinline: "",
        }),
        prompt
          ? el("div", { class: "scene-prompt-body", style: "margin:12px 0 0;padding:0 4px" }, prompt)
          : null,
        visual.path ? el("code", { class: "doc-viewer-path doc-viewer-path--head" }, visual.path) : null,
      ),
    ),
  );
  modal.classList.add("open");
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function openSceneImageModal(s, card, visual) {
  modal.innerHTML = "";
  const meta = [sceneLabel(card.id), card.section_label, fmtDuration(card.duration_seconds)]
    .filter(Boolean).join(" · ");
  const prompt = sceneGenerationPrompt(card);
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    el("div", { class: "modal-page modal-page-viewer" },
      el("div", { class: "scene-video-modal" },
        el("div", { class: "scene-video-meta" }, meta),
        el("img", {
          class: "scene-video-full",
          src: mediaURL(s.project_id, visual.path),
          alt: "",
          style: "object-fit:contain;max-height:70vh;width:100%",
        }),
        prompt
          ? el("div", { class: "scene-prompt-body", style: "margin:12px 0 0;padding:0 4px" }, prompt)
          : null,
        visual.path ? el("code", { class: "doc-viewer-path doc-viewer-path--head" }, visual.path) : null,
      ),
    ),
  );
  modal.classList.add("open");
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  stopRunLogSession();
  modal.classList.remove("open", "modal-bg--fullscreen");
  modal.innerHTML = "";
  modal.removeAttribute("role");
  modal.removeAttribute("aria-modal");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  summaryOpenItem = null;
}
function openBoardSettings() {
  openProjectSettings(projectId, {
    modalHost: modal,
    onClose: closeModal,
    onSaved: refresh,
  }).catch(console.error);
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && modal.classList.contains("open")) closeModal();
});
modal.addEventListener("click", (e) => {
  if (e.target === modal && !modal.classList.contains("modal-bg--fullscreen")) closeModal();
});

// ---------------------------------------------------------------------------
// right rail: decisions, activity
// ---------------------------------------------------------------------------

function renderDecisions(s) {
  const log = s.artifacts.decision_log;
  const decisions = (log && log.decisions) || [];
  if (!decisions.length) return null;
  const body = el("div", { class: "panel-body" });
  // Collapse by category+subject: a decision that changed mid-run (e.g. voice
  // openai_onyx → chirp3) is superseded by the later entry — show the CURRENT
  // choice, not the first one recorded, and mark that it was revised.
  const current = new Map();
  decisions.forEach((d, i) => {
    const key = `${d.category || "decision"}::${d.subject || ""}`;
    const prev = current.get(key);
    current.set(key, { d, order: i, revised: prev ? prev.revised + 1 : 0 });
  });
  const shown = [...current.values()].sort((a, b) => b.order - a.order).slice(0, 8);
  for (const { d, revised } of shown) {
    const selLabel = (() => {
      // Prefer the human label of the selected option over its bare id.
      const opt = (d.options_considered || []).find((o) => (o.option_id ?? o.label) === d.selected);
      return (opt && opt.label) || d.selected || "";
    })();
    const alts = (d.options_considered || [])
      .filter((o) => (o.option_id ?? o.label) !== d.selected && (o.option_id || o.label));
    body.append(el("div", { class: "decision" },
      el("div", { class: "d-cat" },
        el("span", { class: "d-cat-label" }, decisionCategoryLabel(d.category)),
        d.stage ? el("span", { class: "d-stage" }, ` · ${stageLabel(d.stage)}`) : null,
        d.confidence != null
          ? el("span", { class: "d-confidence" }, ` · ${t("decisionConfidence", { n: Math.round(Number(d.confidence) * 100) })}`)
          : null,
        revised ? el("span", { class: "d-revised" }, t("revised")) : null,
      ),
      el("div", { class: "d-pick" },
        `${decisionSubjectLabel(d.subject)} `,
        el("span", { class: "arrow" }, "→"),
        ` ${selLabel}`),
      d.reason ? el("div", { class: "d-why" }, d.reason) : null,
      alts.length ? el("div", { class: "d-alt" }, t("alsoConsidered"),
        alts.slice(0, 3).map((o, i) => [i ? " · " : "", el("s", {}, o.label || o.option_id)]).flat()) : null,
    ));
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" },
      el("div", {},
        el("h2", {}, t("decisions")),
        el("p", { class: "panel-lead" }, t("decisionsLead")),
      ),
      el("span", { class: "meta" }, "decision_log.json")),
    body);
}

function dedupeErrorDisplay(text) {
  if (!text) return text;
  const tabRe = /^\[Tab \d+,[^\]]+\]\s*/;
  const lines = String(text).split(/\r?\n/).filter((l) => l.trim());
  const counts = new Map();
  const order = [];
  for (const line of lines) {
    const key = line.replace(tabRe, "").trim();
    if (!counts.has(key)) order.push(key);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return order.map((key) => {
    const n = counts.get(key);
    return n > 1 ? `${key} （重复 ${n} 次）` : key;
  }).join("\n");
}

async function copyActivityError(text, btn) {
  if (!text) return;
  const markCopied = () => {
    if (!btn) return;
    const prev = btn.textContent;
    btn.textContent = t("copiedError");
    setTimeout(() => { btn.textContent = prev; }, 1500);
  };
  try {
    await navigator.clipboard.writeText(text);
    markCopied();
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    markCopied();
  }
}

function toggleActivityError(item, row, toggleEl) {
  const open = item.classList.toggle("act-item--open");
  row.setAttribute("aria-expanded", open ? "true" : "false");
  if (toggleEl) toggleEl.textContent = open ? t("hideError") : t("viewError");
}

function renderActivity(s) {
  const events = s.events || [];
  if (!events.length) return null;
  const body = el("div", { class: "panel-body" });
  // A start is "running" only until a later finish/error for the same
  // tool+scene closes it — closed starts are dropped (the finish row tells
  // the story), unmatched starts render as live. Counted (not keyed-single)
  // so parallel runs of the same tool on the same scene stay visible.
  const open = new Map(); // key -> {count, ev}
  const rows = [];
  for (const ev of events) {
    const key = `${ev.tool}:${ev.scene_id || ""}`;
    if (ev.event === "start") {
      const slot = open.get(key) || { count: 0, ev };
      slot.count += 1;
      slot.ev = ev;
      open.set(key, slot);
    } else {
      const slot = open.get(key);
      if (slot) {
        slot.count -= 1;
        if (slot.count <= 0) open.delete(key);
      }
      rows.push(ev);
    }
  }
  for (const slot of open.values()) rows.push(slot.ev);
  rows.sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
  for (const ev of rows.slice(-10).reverse()) {
    const failed = ev.event === "error" || (ev.event === "finish" && ev.success === false);
    const errText = ev.error || "";
    const errDisplay = dedupeErrorDisplay(errText);
    let statusEl;
    if (ev.event === "finish") {
      const dur = ev.duration_s != null
        ? ` ${ev.duration_s.toFixed ? ev.duration_s.toFixed(1) : ev.duration_s}s`
        : "";
      const cost = ev.cost_usd ? ` ${fmtMoney(ev.cost_usd)}` : "";
      statusEl = el("span", { class: `status ${failed ? "err" : "ok"}` },
        `${failed ? "✕" : "✓"}${dur}${cost}`);
    } else if (ev.event === "error") {
      const dur = ev.duration_s != null
        ? ` ${ev.duration_s.toFixed ? ev.duration_s.toFixed(1) : ev.duration_s}s`
        : "";
      statusEl = el("span", { class: "status err" }, `✕${dur}`);
    } else {
      statusEl = el("span", { class: "status run" }, t("running"));
    }
    const rowKids = [
      el("span", { class: "t" }, fmtClock(ev.ts)),
      el("span", { class: "tool" }, toolLabel(ev.tool)),
      el("span", { class: "target" }, ev.scene_id ? t("activityScene", { id: ev.scene_id }) : ""),
    ];
    const item = el("div", { class: `act-item${failed && errText ? " act-item--failed" : ""}` });
    if (errText) {
      const toggleEl = el("span", { class: "act-err-toggle" }, t("viewError"));
      rowKids.push(toggleEl);
      rowKids.push(statusEl);
      const row = el("div", {
        class: "act-row act-row--toggle",
        role: "button",
        tabindex: "0",
        "aria-expanded": "false",
        onclick: () => toggleActivityError(item, row, toggleEl),
        onkeydown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleActivityError(item, row, toggleEl);
          }
        },
      }, ...rowKids);
      const copyBtn = el("button", {
        type: "button",
        class: "act-copy-btn",
        title: t("copyError"),
        onclick: (e) => {
          e.stopPropagation();
          copyActivityError(errText, copyBtn);
        },
      }, t("copyError"));
      const errKids = [el("pre", { class: "act-err" }, errDisplay)];
      if (ev.error_log) {
        errKids.push(el("span", { class: "act-err-log meta" }, `完整日志：${ev.error_log}`));
      }
      errKids.push(copyBtn);
      item.append(
        row,
        el("div", { class: "act-err-block" }, ...errKids),
      );
    } else {
      rowKids.push(statusEl);
      item.append(el("div", { class: "act-row" }, ...rowKids));
    }
    body.append(item);
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" },
      el("div", {},
        el("h2", {}, t("activity")),
        el("p", { class: "panel-lead" }, t("activityLead")),
      ),
      el("span", { class: "meta" }, t("activitySource"))),
    body);
}

// ---------------------------------------------------------------------------
// source / reference footage
// ---------------------------------------------------------------------------

function renderSourceMedia(s) {
  const src = s.source_media;
  if (!src || !src.path) return null;
  const metaParts = [
    src.duration_seconds != null ? fmtDuration(src.duration_seconds) : null,
    src.resolution || null,
    src.format ? src.format.toUpperCase() : null,
  ].filter(Boolean);
  const meta = metaParts.length
    ? t("sourceMediaMeta", {
      dur: metaParts[0],
      res: metaParts[1] || "—",
      fmt: metaParts[2] || "—",
    })
    : src.path.split("/").pop();
  const fallbackStage = src.kind === "reference" ? "reference_analysis" : "source_media_review";
  const inner = renderSourceMediaSection(s.project_id, src, { hideTitle: true });
  if (!inner) return null;
  return wrapArtifactBlock(s, "source_media_review", fallbackStage, inner, meta);
}

// ---------------------------------------------------------------------------
// storyboard filmstrip
// ---------------------------------------------------------------------------

function sceneLabel(id) {
  // "sc4" → "SC 04", "scene-11" → "SC 11", anything else → uppercased id
  const m = String(id).match(/(\d+)\s*$/);
  if (m) return `SC ${m[1].padStart(2, "0")}`;
  return String(id).toUpperCase().slice(0, 10);
}

function sceneCard(s, card) {
  const dur = card.duration_seconds;
  const width = Math.max(132, Math.min(300, 70 + (dur || 3) * 26));
  const wrap = el("div", {
    class: "scene-card",
    style: `width:${width}px;--scene-thumb-aspect:${deliverableAspect(s)}`,
  });
  const track = el("div", { class: "scene-card-track" });
  const details = el("div", { class: "scene-card-details" });

  const slate = el("div", { class: "sc-slate" },
    el("span", { class: "num" }, sceneLabel(card.id)),
    card.takes.length > 1 ? el("span", { class: "take" }, `T${card.takes.length}`) : null,
    card.hero_moment ? el("span", { class: "hero" }, t("hero")) : null,
    el("span", { class: "dur" }, fmtDuration(dur)),
  );
  track.append(slate);

  // visual slot
  let thumb;
  if (card.generating) {
    thumb = el("div", { class: "thumb generating" },
      el("div", { class: "shimmer" }),
      el("div", { class: "gen-label" },
        el("span", {}, t("generating")),
        el("span", { class: "sub" }, card.generating_tool || "")));
  } else if (card.visual && card.visual.exists) {
    const v = card.visual;
    const badge = [v.model || v.source_tool, v.cost_usd != null ? fmtMoney(v.cost_usd) : null,
      v.quality_score != null ? `q ${v.quality_score}` : null].filter(Boolean).join(" · ");
    if (v.type === "video") {
      thumb = el("div", { class: "thumb approved thumb-video", title: t("playSceneVideo") },
        el("video", { src: mediaURL(s.project_id, v.path), muted: "", preload: "metadata", playsinline: "" }),
        el("span", { class: "play" }, "▶"),
        badge ? el("span", { class: "badge" }, badge) : null);
      thumb.onclick = () => openSceneVideoModal(s, card, v);
    } else {
      const img = el("img", { src: thumbURL(s.project_id, v.path, 640), loading: "lazy", alt: "" });
      // A thumbnail that fails to load must never show a broken-image icon —
      // fall back to the shot spec in place (F: broken links).
      img.onerror = () => {
        const t = img.closest(".thumb");
        if (!t) return;
        t.className = "thumb spec";
        t.innerHTML = "";
        t.append(el("div", { class: "spec-in" },
          el("div", { class: "spec-desc" }, card.description || t("assetUnavailable")),
          el("div", { class: "spec-shot" }, [card.framing, card.movement].filter(Boolean).join(" · ").slice(0, 70))));
      };
      thumb = el("div", { class: "thumb approved" }, img,
        v.snapshot ? el("span", { class: "badge" }, "snapshot") : (badge ? el("span", { class: "badge" }, badge) : null));
      thumb.style.cursor = "pointer";
      thumb.title = t("clickReadPrompt");
      thumb.onclick = () => openSceneImageModal(s, card, v);
    }
  } else if (card.type === "animation") {
    // Bespoke/atelier scene with no snapshot yet — name it as such rather
    // than "no asset yet" (the composition IS the asset).
    thumb = el("div", { class: "thumb spec bespoke" },
      el("div", { class: "spec-in" },
        el("span", { class: "bespoke-tag" }, t("bespoke")),
        el("div", { class: "spec-desc" }, card.description || ""),
        el("div", { class: "spec-shot" }, t("handAuthored"))));
  } else if (card.visual && !card.visual.exists) {
    thumb = el("div", { class: "thumb missing" },
      el("div", { class: "spec-in" },
        el("span", { class: "warn-ic" }, "⚑"),
        el("div", { class: "spec-desc" }, t("assetMissing")),
        el("div", { class: "spec-shot" }, card.visual.path || "")));
  } else if (card.type === "text_card") {
    thumb = el("div", { class: "thumb textcard" },
      el("div", { class: "tc-copy" }, (card.narration || card.description || "").slice(0, 48)));
  } else if (card.required_assets.length) {
    thumb = el("div", { class: "thumb missing" },
      el("div", { class: "spec-in" },
        el("span", { class: "warn-ic" }, "⚑"),
        el("div", { class: "spec-desc" }, t("noAssetYet")),
        el("div", { class: "spec-shot" }, (card.required_assets[0].description || "").slice(0, 60))));
  } else {
    thumb = el("div", { class: "thumb spec" },
      el("div", { class: "spec-in" },
        el("div", { class: "spec-desc" }, card.description || ""),
        el("div", { class: "spec-shot" }, [card.framing, card.movement].filter(Boolean).join(" · ").slice(0, 70))));
  }
  track.append(thumb);

  // shot language chips
  const sl = card.shot_language;
  if (sl) {
    track.append(el("div", { class: "shotchips" },
      [sl.shot_size, sl.camera_movement, sl.lens_mm ? `${sl.lens_mm}mm` : null, sl.lighting_key]
        .filter(Boolean)
        .map((chip) => el("span", { class: "shotchip" }, String(chip).replaceAll("_", " ")))));
  }

  // takes drawer
  if (card.takes.length > 1) {
    const takes = el("div", { class: "takes" });
    card.takes.forEach((t, i) => {
      const isActive = card.visual && (
        t === card.visual
        || (t.path && t.path === card.visual.path)
        || (t.id && t.id === card.visual.id)
      );
      const tk = el("span", { class: `tk${isActive ? " active" : ""}`, title: `take ${i + 1}` });
      if (t.exists && t.type === "image") tk.append(el("img", { src: thumbURL(s.project_id, t.path, 320), loading: "lazy", alt: "" }));
      takes.append(tk);
    });
    takes.append(el("span", { class: "tk-label" }, t("takes", { n: card.takes.length })));
    track.append(takes);
  }

  // narration + audio — clickable to read in full (F: narration text cut off)
  if (card.narration) {
    const long = card.narration.length > 90;
    details.append(el("div", {
      class: `narr${long ? " clip" : ""}`,
      title: t("clickReadNarration"),
      onclick: () => openNarrModal(card),
    }, card.narration, long ? el("span", { class: "narr-more" }, "⤢") : null));
  } else if (card.shot_intent || card.description) {
    details.append(el("div", { class: "narr tc-note" }, (card.shot_intent || card.description || "").slice(0, 110)));
  }

  const prompt = sceneGenerationPrompt(card);
  if (prompt) {
    const longPrompt = prompt.length > 120;
    details.append(el("div", {
      class: `sc-prompt${longPrompt ? " clip" : ""}`,
      title: t("clickReadPrompt"),
      onclick: (e) => {
        e.stopPropagation();
        openScenePromptModal(card, prompt);
      },
    },
      prompt,
      longPrompt ? el("span", { class: "narr-more" }, "⤢") : null));
  }

  const narrAudio = card.audio.find((a) => a.exists && (a.type === "narration" || a.type === "audio"));
  if (narrAudio) {
    const wave = el("div", { class: "wave", style: "cursor:pointer", title: t("playNarration") });
    waveBars(wave, card.id + narrAudio.path);
    wave.append(el("span", { class: "wv-time" }, narrAudio.duration_seconds ? fmtDuration(narrAudio.duration_seconds) : "♪"));
    wave.onclick = () => {
      player.src = mediaURL(s.project_id, narrAudio.path);
      player.play();
    };
    details.append(wave);
  }

  wrap.append(track);
  if (details.childNodes.length) wrap.append(details);
  return wrap;
}

function scenePlanSceneRow(scene) {
  const start = scene.start_seconds;
  const end = scene.end_seconds;
  const dur = start != null && end != null ? Math.max(0, end - start) : null;
  const timing = start != null && end != null
    ? `${fmtDuration(start)} – ${fmtDuration(end)}`
    : null;
  const shotBits = [scene.framing, scene.movement, scene.shot_intent].filter(Boolean);
  const sl = scene.shot_language;
  if (sl) {
    for (const bit of [sl.shot_size, sl.camera_movement, sl.lens_mm ? `${sl.lens_mm}mm` : null, sl.lighting_key]) {
      if (bit) shotBits.push(String(bit).replaceAll("_", " "));
    }
  }
  return el("div", { class: "scene-plan-row" },
    el("div", { class: "scene-plan-head" },
      el("span", { class: "scene-plan-id" }, sceneLabel(scene.id)),
      timing ? el("span", { class: "scene-plan-time" }, timing) : null,
      dur != null ? el("span", { class: "scene-plan-dur" }, fmtDuration(dur)) : null,
      scene.hero_moment ? el("span", { class: "scene-plan-hero" }, t("hero")) : null),
    scene.description ? el("p", { class: "scene-plan-desc" }, scene.description) : null,
    shotBits.length ? el("p", { class: "scene-plan-shot" }, shotBits.join(" · ")) : null,
    scene.narration ? el("p", { class: "scene-plan-narr" }, scene.narration) : null,
  );
}

function renderScenePlanBody(s, artifact) {
  const board = s.storyboard;
  if (board && Array.isArray(board.scenes) && board.scenes.length) {
    const strip = el("div", { class: "filmstrip" });
    for (const card of board.scenes) strip.append(sceneCard(s, card));
    return el("div", { class: "strip-outer scene-plan-inline" }, strip);
  }
  const scenes = artifact.scenes || [];
  return el("div", { class: "scene-plan-list scene-plan-inline" },
    ...scenes.map((scene) => scenePlanSceneRow(scene)),
  );
}

function renderStoryboard(s) {
  const board = s.storyboard;
  if (!board) return null;
  const strip = el("div", { class: "filmstrip" });
  for (const card of board.scenes) strip.append(sceneCard(s, card));
  const meta = board.total_duration_seconds
    ? t("storyboardMeta", { n: board.scenes.length, dur: fmtDuration(board.total_duration_seconds) })
    : t("scenes", { n: board.scenes.length });
  return wrapArtifactBlock(s, "scene_plan", "scene_plan",
    el("div", { class: "strip-outer" }, strip),
    meta,
  );
}

// ---------------------------------------------------------------------------
// renders + degraded media
// ---------------------------------------------------------------------------

function renderRenders(s) {
  const renders = s.media.renders;
  if (!renders.length) return null;
  if (activeRender >= renders.length) activeRender = 0;
  const current = renders[activeRender];
  const src = mediaURL(s.project_id, current.path);
  let video = takePinnedMedia(src);
  if (!video) {
    video = el("video", { src, controls: "", preload: "metadata" });
    video.addEventListener("click", () => { if (video.paused) video.play().catch(() => {}); });
  }
  const versions = el("div", { class: "render-meta" },
    renders.map((r, i) => el("span", {
      class: `v${i === activeRender ? " active" : ""}`,
      onclick: () => { activeRender = i; render(); },
    }, `${r.path.split("/").pop()}${r.at_root ? t("root") : ""}`)),
    el("span", { style: "margin-left:auto" }, `${(current.size / 1048576).toFixed(1)} MB`),
  );
  return wrapArtifactBlock(s, "render_report", "compose",
    el("div", {},
      el("div", { class: "render-hero" }, video),
      versions,
    ),
    t("renderVersions", { n: renders.length }),
  );
}

function renderPublishExports(s) {
  const publishStage = s.stages.find((x) => x.name === "publish");
  if (!publishStage) return null;
  if (!["completed", "awaiting_human", "in_progress"].includes(publishStage.status)) return null;

  const exportsMedia = publishExportMedia(s);
  const cover = exportsMedia.find((m) => m.type === "image" && m.exists && m.renderable);
  const exportVideo = exportsMedia.find((m) => m.type === "video" && m.exists && m.renderable);
  if (!cover && !exportVideo) return null;

  const body = el("div", { class: "publish-export-body" });
  if (cover) {
    body.append(el("div", { class: "publish-cover-hero" },
      el("img", {
        src: thumbURL(s.project_id, cover.path, 960),
        alt: "",
        loading: "lazy",
      }),
    ));
  }
  if (exportVideo) {
    body.append(el("div", { class: "publish-export-video" },
      el("video", {
        src: mediaURL(s.project_id, exportVideo.path),
        controls: "",
        preload: "metadata",
      }),
    ));
  }

  return wrapArtifactBlock(s, "publish_log", "publish", body, t("publishExportPack"));
}

function renderFoundMedia(s) {
  // Degraded view: show discovered snapshots when there's no storyboard.
  if (s.storyboard || !s.media.snapshots.length) return null;
  const grid = el("div", { class: "found-grid" });
  for (const snap of s.media.snapshots.slice(0, 12)) {
    grid.append(el("div", { class: "thumb" },
      el("img", { src: thumbURL(s.project_id, snap.path, 640), loading: "lazy", alt: "" })));
  }
  return el("div", {},
    el("div", { class: "section-title" }, t("watcherFound"),
      el("span", { class: "meta" }, t("snapshotsMeta"))),
    grid);
}

function renderNoState(s) {
  if (s.has_pipeline_state) return null;
  return el("div", { class: "notice", style: "border-color:#2b2b33;background:var(--surface-2);color:var(--text-3)" },
    el("span", { style: "font-size:calc(15px * var(--fs-scale))" }, "◌"),
    el("span", {},
      el("b", { style: "color:var(--text-2)" }, t("noPipelineState")),
      t("noPipelineStateDetail")));
}

// ---------------------------------------------------------------------------
// headless-agent stage channel — run / approve / reject / cancel / log
// ---------------------------------------------------------------------------

function activeRun(s) {
  return (s.runs || []).find((r) => r.status === "queued" || r.status === "running");
}

function nextRunStage(s) {
  if (activeRun(s)) return null;
  const awaiting = s.stages.find((x) => x.status === "awaiting_human");
  if (awaiting) return null;
  const nextName = s.next_stage;
  const next = nextName ? s.stages.find((x) => x.name === nextName) : null;
  if (next && next.status === "pending") {
    const idx = s.stages.findIndex((x) => x.name === nextName);
    const prev = idx > 0 ? s.stages[idx - 1] : null;
    if (prev?.status === "completed") return null;
  }
  return s.stages.find((x) => !x.undeclared && x.status !== "completed") || null;
}

function pendingAutoRunStage(s) {
  if (activeRun(s)) return null;
  if (s.stages.some((x) => x.status === "awaiting_human")) return null;
  const nextName = s.next_stage;
  if (!nextName) return null;
  const next = s.stages.find((x) => x.name === nextName);
  if (!next || next.status !== "pending") return null;
  const idx = s.stages.findIndex((x) => x.name === nextName);
  const prev = idx > 0 ? s.stages[idx - 1] : null;
  if (!prev || prev.status !== "completed") return null;
  return next;
}

let autoRunInFlight = false;

async function maybeAutoRunNextStage(s) {
  const next = pendingAutoRunStage(s);
  if (!next || autoRunInFlight) return;
  autoRunInFlight = true;
  try {
    await postJSON(`/api/project/${encodedProjectId}/stage/run`, { stage: next.name });
    render();
  } catch (err) {
    console.error("auto-run failed", err);
    await refresh();
  } finally {
    autoRunInFlight = false;
  }
}

async function runNextStage(stageName, { gated = true } = {}) {
  if (gated && !window.confirm(t("stageRunNextConfirm", { stage: stageLabel(stageName) }))) return;
  try {
    await postJSON(`/api/project/${encodedProjectId}/stage/run`, { stage: stageName });
    render(); // SSE 也会刷新；立即 re-render 让运行态马上出现
  } catch (err) {
    window.alert(err.message || String(err));
    render();
  }
}

function firstPipelineStageName(s) {
  const declared = (s.pipeline?.stages || []).find((st) => st.name);
  if (declared?.name) return declared.name;
  const rail = (s.stages || []).find((st) => !st.undeclared);
  return rail?.name || null;
}

async function resetPipelineFromStart(stageName) {
  if (!window.confirm(t("stageResetFromStartConfirm", { stage: stageLabel(stageName) }))) return;
  try {
    const result = await postJSON(`/api/project/${encodedProjectId}/pipeline/reset`, {});
    render();
    if (result?.next_stage) {
      window.alert(t("stageResetDone", { stage: stageLabel(result.next_stage) }));
    }
  } catch (err) {
    window.alert(err.message || t("stageResetFailed"));
    render();
  }
}

function renderResetFromStartButton(s, { primary = false } = {}) {
  const first = firstPipelineStageName(s);
  const canReset = Boolean(first)
    && (s.has_pipeline_state || (s.stages || []).some((st) => st.status === "completed"));
  if (!canReset) return null;
  return el("button", {
    type: "button",
    class: primary ? "run-btn run-btn-primary" : "run-btn run-btn-ghost",
    onclick: () => resetPipelineFromStart(first),
  }, t("stageResetFromStart", { stage: stageLabel(first) }));
}

async function approveStageNow(stageName) {
  if (!window.confirm(t("stageRunApproveConfirm", { stage: stageLabel(stageName) }))) return;
  try {
    await postJSON(`/api/project/${encodedProjectId}/stage/approve`, { stage: stageName, notes: "" });
    render();
  } catch (err) {
    window.alert(err.message || String(err));
    render();
  }
}

function rejectPanel(stageName, anchor) {
  const panel = el("div", { class: "run-panel" },
    el("div", { class: "run-panel-title" },
      t("stageRunRejectTitle", { stage: stageLabel(stageName) })),
    el("textarea", {
      class: "run-panel-feedback", rows: 3, maxlength: 4000, minlength: 5,
      placeholder: t("stageRunRejectFeedback"),
    }),
    el("div", { class: "run-panel-actions" },
      el("button", {
        type: "button", class: "run-btn run-btn-ghost",
        onclick: () => { anchor.innerHTML = ""; render(); },
      }, t("stageRunRejectCancel")),
      el("button", {
        type: "button", class: "run-btn run-btn-primary",
        onclick: () => submitReject(stageName, panel),
      }, t("stageRunRejectSubmit"))),
  );
  anchor.innerHTML = "";
  anchor.append(panel);
  const ta = panel.querySelector(".run-panel-feedback");
  if (ta) ta.focus();
}

async function submitReject(stageName, panel) {
  const ta = panel.querySelector(".run-panel-feedback");
  const feedback = (ta.value || "").trim();
  if (feedback.length < 5) {
    window.alert(t("stageRunRejectFeedback"));
    if (ta) ta.focus();
    return;
  }
  try {
    await postJSON(`/api/project/${encodedProjectId}/stage/reject`, { stage: stageName, feedback });
    render();
  } catch (err) {
    window.alert(err.message || String(err));
    render();
  }
}

function approvalButtons(stageName) {
  return el("div", { class: "run-btn-group" },
    el("button", {
      type: "button", class: "run-btn run-btn-primary",
      onclick: () => approveStageNow(stageName),
    }, t("stageRunApprove")),
    el("button", {
      type: "button", class: "run-btn run-btn-reject",
      onclick: (evt) => rejectPanel(stageName, evt.currentTarget.parentElement),
    }, t("stageRunReject")));
}

async function cancelRunNow(taskId) {
  if (!window.confirm(t("stageRunCancelConfirm"))) return;
  try {
    await postJSON(`/api/project/${encodedProjectId}/stage/run/${encodeURIComponent(taskId)}/cancel`, {});
    render();
  } catch (err) {
    window.alert(err.message || String(err));
  }
}

/** 运行日志弹窗打开时的 live 会话（SSE + 轻量轮询）。 */
let runLogSession = null;

function stopRunLogSession() {
  if (!runLogSession) return;
  if (runLogSession.pollTimer) clearInterval(runLogSession.pollTimer);
  if (runLogSession.debounceTimer) clearTimeout(runLogSession.debounceTimer);
  runLogSession = null;
}

function maybeRefreshRunLog() {
  if (!runLogSession || !modal.classList.contains("open")) return;
  const run = (state?.runs || []).find((r) => r.task_id === runLogSession.taskId);
  const active = Boolean(run && (run.status === "running" || run.status === "queued"));
  runLogSession.active = active;
  if (runLogSession.liveBadge) {
    runLogSession.liveBadge.hidden = !active;
  }
  if (!active && runLogSession.pollTimer) {
    clearInterval(runLogSession.pollTimer);
    runLogSession.pollTimer = null;
  }
  clearTimeout(runLogSession.debounceTimer);
  runLogSession.debounceTimer = setTimeout(() => {
    if (runLogSession) void runLogSession.loadLog({ soft: true });
  }, 300);
}

function parseRunLogResultBlock(lines, start) {
  const line = lines[start];
  const isErr = line.startsWith("  ✗");
  const headerText = line.trim();
  const bodyLines = [];
  let i = start + 1;
  while (i < lines.length && lines[i].startsWith("    ")) {
    bodyLines.push(lines[i].slice(4));
    i += 1;
  }
  const entry = el("div", { class: `run-log-entry${isErr ? " run-log-entry--err" : ""}` });
  entry.append(el("div", { class: "run-log-entry-head" }, headerText));
  if (bodyLines.length) {
    entry.append(el("pre", { class: "run-log-entry-body" }, bodyLines.join("\n")));
  }
  return { entry, next: i };
}

function renderRunLogView(lines) {
  const wrap = el("div", { class: "run-log-view" });
  if (!lines || !lines.length) {
    wrap.append(el("div", { class: "run-log-empty" }, t("stageRunLogEmpty")));
    return wrap;
  }
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("▸")) {
      const group = el("div", { class: "run-log-group" });
      while (i < lines.length && lines[i].startsWith("▸")) {
        group.append(el("div", { class: "run-log-line run-log-tool" }, lines[i]));
        i += 1;
      }
      while (i < lines.length && (lines[i].startsWith("  ✓") || lines[i].startsWith("  ✗"))) {
        const parsed = parseRunLogResultBlock(lines, i);
        group.append(parsed.entry);
        i = parsed.next;
      }
      wrap.append(group);
      continue;
    }
    if (line.startsWith("  ✓") || line.startsWith("  ✗")) {
      const parsed = parseRunLogResultBlock(lines, i);
      wrap.append(parsed.entry);
      i = parsed.next;
      continue;
    }
    if (line.startsWith("●")) {
      wrap.append(el("div", { class: "run-log-line run-log-meta" }, line));
    } else {
      wrap.append(el("div", { class: "run-log-line run-log-text" }, line));
    }
    i += 1;
  }
  return wrap;
}

function openRunLogModal(run) {
  stopRunLogSession();
  modal.innerHTML = "";
  const logHost = el("div", { class: "run-log-host" });
  const liveBadge = el("span", { class: "run-log-live", hidden: true }, t("stageRunLogLive"));
  const page = el("div", { class: "modal-page modal-page-run-log" },
    el("div", { class: "run-log-head" },
      el("h2", {}, t("stageRunLogTitle", { stage: stageLabel(run.stage) })),
      liveBadge,
      el("button", { type: "button", class: "run-btn run-btn-ghost", onclick: () => loadLog() }, t("stageRunLogRefresh")),
    ),
    logHost);
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, t("escClose")),
    page);
  modal.classList.add("open");
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";

  async function loadLog(opts = {}) {
    const soft = opts.soft === true;
    const stickBottom = !soft
      || (logHost.scrollHeight - logHost.scrollTop - logHost.clientHeight < 48);
    const prevScroll = logHost.scrollTop;
    const prevHeight = logHost.scrollHeight;
    try {
      const res = await getJSON(
        `/api/project/${encodedProjectId}/stage/run/${encodeURIComponent(run.task_id)}/log?limit=2000`);
      if (soft && res.total === runLogSession?.lastTotal) return;
      if (runLogSession) runLogSession.lastTotal = res.total;
      logHost.replaceChildren(renderRunLogView(res.lines || []));
      if (stickBottom) {
        logHost.scrollTop = logHost.scrollHeight;
      } else if (soft && logHost.scrollHeight !== prevHeight) {
        logHost.scrollTop = prevScroll + (logHost.scrollHeight - prevHeight);
      }
    } catch (err) {
      logHost.replaceChildren(el("div", { class: "run-log-empty run-log-entry--err" }, String(err.message || err)));
    }
  }

  const active = run.status === "running" || run.status === "queued";
  liveBadge.hidden = !active;
  runLogSession = {
    taskId: run.task_id,
    loadLog,
    liveBadge,
    active,
    pollTimer: null,
    debounceTimer: null,
    lastTotal: null,
  };
  void loadLog();
  if (active) {
    // SSE（runs/*.log 写入）为主；Windows 上 watch 可能漏事件，1s 轮询兜底。
    runLogSession.pollTimer = setInterval(() => {
      if (!runLogSession || !modal.classList.contains("open")) {
        stopRunLogSession();
        return;
      }
      if (runLogSession.active) void runLogSession.loadLog({ soft: true });
    }, 1000);
  }
}

function renderRunControl(s) {
  const run = activeRun(s);
  if (run) {
    return el("div", { class: "stage-run-ctl active" },
      el("span", { class: "spinner" }, "◌"),
      el("span", {}, t("stageRunRunning", { stage: stageLabel(run.stage) })),
      el("button", {
        type: "button", class: "run-btn run-btn-ghost",
        onclick: () => openRunLogModal(run),
      }, t("stageRunLog")),
      el("button", {
        type: "button", class: "run-btn run-btn-ghost",
        onclick: () => cancelRunNow(run.task_id),
      }, t("stageRunCancel")));
  }
  const next = nextRunStage(s);
  const autoNext = pendingAutoRunStage(s);
  const resetBtn = renderResetFromStartButton(s, { primary: !next && !autoNext });
  if (!next && !autoNext) {
    const failed = (s.runs || []).find((r) => r.status === "failed");
    if (failed) {
      return el("div", { class: "stage-run-ctl failed" },
        el("span", { style: "color:var(--red)" },
          t("stageRunFailed", { error: failed.error || failed.status })),
        el("button", {
          type: "button", class: "run-btn run-btn-ghost",
          onclick: () => openRunLogModal(failed),
        }, t("stageRunLog")),
        resetBtn);
    }
    if (resetBtn) {
      return el("div", { class: "stage-run-ctl" }, resetBtn);
    }
    return null;
  }
  if (autoNext) {
    return el("div", { class: "stage-run-ctl active" },
      el("span", { class: "spinner" }, "◌"),
      el("span", {}, t("stageRunAutoNext", { stage: stageLabel(autoNext.name) })),
      resetBtn);
  }
  return el("div", { class: "stage-run-ctl" },
    el("button", {
      type: "button", class: "run-btn run-btn-primary",
      onclick: () => runNextStage(next.name),
    }, t("stageRunNext", { stage: stageLabel(next.name) })),
    resetBtn);
}

function renderAwaitingNotice(s) {
  const awaiting = s.stages.find((x) => x.status === "awaiting_human");
  if (!awaiting) return null;
  return el("div", { class: "notice" },
    el("span", { style: "font-size:calc(16px * var(--fs-scale))" }, "◈"),
    el("span", {},
      el("b", {}, t("stageWaiting", { stage: stageLabel(awaiting.name) })),
      t("agentPaused"), el("b", {}, t("inChat")), t("approveOrChange")),
    el("div", { style: "margin-left:auto" }, approvalButtons(awaiting.name)));
}

// ---------------------------------------------------------------------------
// replay — scrub a completed run from its timestamps
// ---------------------------------------------------------------------------

// Python writers emit tz-aware UTC isoformat, but treat tz-naive strings as
// UTC too — mixing local-parsed and UTC-parsed timestamps would skew replay
// ordering by the user's UTC offset.
const ts = (iso) => {
  if (!iso) return null;
  let s = String(iso);
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += "Z";
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : null;
};

function replayBounds(s) {
  const moments = [];
  for (const st of s.stages) {
    for (const h of st.history_entries || []) {
      const t = ts(h.timestamp);
      if (t) moments.push(t);
    }
  }
  for (const ev of s.events || []) {
    const t = ts(ev.ts);
    if (t) moments.push(t);
  }
  if (moments.length < 2) return null;
  return { t0: Math.min(...moments), t1: Math.max(...moments) };
}

function stateAt(s, T) {
  const view = structuredClone(s);
  for (const st of view.stages) {
    const past = (st.history_entries || []).filter((h) => ts(h.timestamp) != null && ts(h.timestamp) <= T);
    if (!past.length) {
      st.status = "pending"; st.review = null; st.timestamp = null;
      st.gate_skipped = false; st.partial_progress = null;
    } else {
      const cur = past[past.length - 1];
      st.status = cur.status || "pending";
      st.timestamp = cur.timestamp;
    }
  }
  view.events = (view.events || []).filter((ev) => ts(ev.ts) != null && ts(ev.ts) <= T);

  // Storyboard: visuals appear as their scene finishes (events) or when the
  // assets stage has completed as of T (legacy runs without events).
  if (view.storyboard) {
    const assetsStage = view.stages.find((x) => x.name === "assets");
    const assetsDone = assetsStage && assetsStage.status === "completed";
    const finished = new Set();
    const startedNow = new Map();
    for (const ev of view.events) {
      if (!ev.scene_id) continue;
      if (ev.event === "finish") { finished.add(ev.scene_id); startedNow.delete(ev.scene_id); }
      else if (ev.event === "start") startedNow.set(ev.scene_id, ev);
      else if (ev.event === "error") startedNow.delete(ev.scene_id);
    }
    const scenePlanStage = view.stages.find((x) => x.name === "scene_plan");
    const scenePlanDone = scenePlanStage && ["completed", "awaiting_human"].includes(scenePlanStage.status);
    if (!scenePlanDone) {
      view.storyboard = null;
    } else {
      for (const card of view.storyboard.scenes) {
        const visible = assetsDone || finished.has(card.id);
        if (!visible) { card.visual = null; card.takes = []; card.audio = []; }
        card.generating = startedNow.has(card.id);
        card.generating_tool = (startedNow.get(card.id) || {}).tool;
      }
    }
  }
  // Final artifacts hide until their stage happened — for every project
  // shape, storyboard or not (a degraded run must not show the finished
  // movie before its stages ran).
  const scriptStage = view.stages.find((x) => x.name === "script");
  if (!(scriptStage && ["completed", "awaiting_human"].includes(scriptStage.status))) {
    delete view.artifacts.script;
  }
  const composeStage = view.stages.find((x) => x.name === "compose");
  if (!(composeStage && composeStage.status === "completed")) {
    view.media.renders = [];
  }
  return view;
}

function renderReplayBar(s, runCtl = null) {
  const bounds = replayBounds(s);
  if (replay) {
    const pos = (replay.t - replay.t0) / Math.max(1, replay.t1 - replay.t0);
    const timeLabel = el("span", { class: "rp-time" },
      new Date(replay.t).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    const setT = (value) => {
      replay.t = replay.t0 + (Number(value) / 1000) * (replay.t1 - replay.t0);
      timeLabel.textContent = new Date(replay.t)
        .toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    };
    return el("div", { class: "replay-bar replay-bar-active" },
      el("span", { class: "rp-btn", onclick: toggleReplayPlay }, replay.playing ? "❚❚" : "▶"),
      el("input", {
        type: "range", min: "0", max: "1000", value: String(Math.round(pos * 1000)),
        onpointerdown: () => { replay.playing = false; },
        oninput: (e) => setT(e.target.value),
        onchange: (e) => { setT(e.target.value); render(); },
      }),
      timeLabel,
      el("span", { class: "rp-btn", onclick: stopReplay }, t("exitReplay")),
    );
  }

  if (!bounds && !runCtl) return null;

  const left = el("div", { class: "pipeline-actions-left" });
  if (runCtl) left.append(runCtl);

  const right = el("div", { class: "pipeline-actions-right" });
  if (bounds) {
    right.append(
      el("span", { class: "rp-time", title: t("replayRunHint") }, t("scrubRun")),
      el("span", { class: "rp-btn", title: t("replayRunHint"), onclick: startReplay }, t("replayRun")),
    );
  }

  return el("div", { class: "replay-bar pipeline-footer" }, left, right);
}

let replayTimer = null;

function startReplay() {
  const bounds = replayBounds(state);
  if (!bounds) return;
  replay = { ...bounds, t: bounds.t0, playing: true };
  document.body.classList.add("replaying");
  scheduleTick();
  render();
}

function stopReplay() {
  replay = null;
  clearTimeout(replayTimer);
  document.body.classList.remove("replaying");
  render();
}

function toggleReplayPlay() {
  if (!replay) return;
  replay.playing = !replay.playing;
  if (replay.playing) scheduleTick();
  render();
}

function scheduleTick() {
  // Single pending tick, ever — rapid pause/play must not stack chains.
  clearTimeout(replayTimer);
  replayTimer = setTimeout(tickReplay, 100);
}

function tickReplay() {
  if (!replay || !replay.playing) return;
  // A full run replays in ~20 seconds regardless of real duration
  // (10 renders/second — full re-render per tick, keep it modest).
  const step = (replay.t1 - replay.t0) / 200;
  replay.t = Math.min(replay.t1, replay.t + step);
  if (replay.t >= replay.t1) replay.playing = false;
  render();
  if (replay.playing) scheduleTick();
}

// ---------------------------------------------------------------------------
// page assembly
// ---------------------------------------------------------------------------

function render() {
  if (!state) return;
  const s = replay ? stateAt(state, replay.t) : state;
  document.title = `Backlot — ${s.title}`;
  document.body.classList.toggle("first", firstPaint);
  firstPaint = false;
  pinMediaElements();
  app.innerHTML = "";
  app.append(renderSlate(s));

  // Zone 1 — pipeline: stage rail + replay scrubber (one visual unit)
  const pipeline = el("section", { class: "board-pipeline", "aria-label": t("boardPipelineAria") });
  pipeline.append(renderRail(s));
  const runCtl = renderRunControl(s);
  const replayBar = renderReplayBar(state, runCtl);
  if (replayBar) pipeline.append(replayBar);
  else if (runCtl) pipeline.append(runCtl);
  app.append(pipeline);

  // Zone 2 — workspace: alerts, stage drawer, main content
  const workspace = el("section", { class: "board-workspace" });
  const alerts = el("div", { class: "board-alerts" });
  const awaitingNotice = renderAwaitingNotice(s);
  if (awaitingNotice) alerts.append(awaitingNotice);
  const noState = renderNoState(s);
  if (noState) alerts.append(noState);
  if (alerts.childNodes.length) workspace.append(alerts);

  const drawer = renderDrawer(s);
  if (drawer) workspace.append(drawer);

  const main = el("div", { class: "main-col" });
  const sourceMedia = renderSourceMedia(s);
  if (sourceMedia) main.append(sourceMedia);

  const refAnalysis = renderReferenceAnalysisCard(s);
  if (refAnalysis) main.append(refAnalysis);

  const approvalReview = renderApprovalReview(s);
  if (approvalReview) main.append(approvalReview);
  const script = renderScriptCard(s);
  if (script) main.append(script);

  const mediaBlock = el("div", { class: "board-media-block" });
  const storyboard = renderStoryboard(s);
  const found = renderFoundMedia(s);
  const renders = renderRenders(s);
  const publishExports = renderPublishExports(s);
  for (const section of [storyboard, found, renders, publishExports]) {
    if (section) mediaBlock.append(section);
  }
  if (mediaBlock.childNodes.length) main.append(mediaBlock);

  const aside = el("aside", {});
  const decisions = renderDecisions(s);
  const activity = renderActivity(s);
  if (decisions) aside.append(decisions);
  if (activity) aside.append(activity);
  const hasAside = aside.childNodes.length > 0;

  if (main.childNodes.length || hasAside) {
    workspace.append(
      el("div", { class: "board-workspace-head" }, t("boardWorkspaceLabel")),
      el("div", { class: `board${hasAside ? "" : " solo"}` }, main, hasAside ? aside : null),
    );
  }

  if (workspace.childNodes.length) app.append(workspace);
  releaseUnusedPinnedMedia();
}

// Defensive normalization (F-02): the server contract guarantees these
// fields, but a sparse/legacy payload must degrade, never crash the board.
function normalize(s) {
  s.pipeline = s.pipeline || { pipeline_type: "unknown", label_zh: t("unknown"), stages: [], known: false };
  s.stages = Array.isArray(s.stages) ? s.stages : [];
  for (const stage of s.stages) {
    stage.produces = Array.isArray(stage.produces) ? stage.produces : [];
  }
  s.artifacts = s.artifacts || {};
  s.project_summary = s.project_summary || { artifacts: [], media: [], counts: {} };
  s.deliverable = s.deliverable || null;
  s.media = s.media || {};
  s.media.renders = Array.isArray(s.media.renders) ? s.media.renders : [];
  s.media.snapshots = Array.isArray(s.media.snapshots) ? s.media.snapshots : [];
  s.media.music = Array.isArray(s.media.music) ? s.media.music : [];
  if (s.source_media && typeof s.source_media === "object") {
    s.source_media.exists = Boolean(s.source_media.exists);
    s.source_media.playable = Boolean(s.source_media.playable);
  } else {
    s.source_media = null;
  }
  s.events = Array.isArray(s.events) ? s.events : [];
  s.runs = Array.isArray(s.runs) ? s.runs : [];
  if (typeof s.production_active !== "boolean") {
    s.production_active = undefined;
  }
  if (s.storyboard && Array.isArray(s.storyboard.scenes)) {
    for (const c of s.storyboard.scenes) {
      c.takes = Array.isArray(c.takes) ? c.takes : [];
      c.audio = Array.isArray(c.audio) ? c.audio : [];
      c.required_assets = Array.isArray(c.required_assets) ? c.required_assets : [];
    }
  } else {
    s.storyboard = null;
  }
  return s;
}

async function refresh() {
  state = normalize(await getJSON(`/api/project/${encodeURIComponent(projectId)}/state`));
  render();
  maybeRefreshRunLog();
  void maybeAutoRunNextStage(state);
}

refresh().catch((err) => {
  app.innerHTML = "";
  app.append(el("div", { class: "empty", style: "margin-top:80px" },
    el("div", { class: "big" }, t("projectNotFound")),
    el("div", {}, String(err))));
});
// ?static=1 disables the live feed (screenshots, static exports).
if (!new URLSearchParams(location.search).has("static")) {
  subscribe(`/api/project/${encodeURIComponent(projectId)}/events`, () => refresh().catch(console.error));
}
