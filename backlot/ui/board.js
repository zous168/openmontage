// Backlot project board — renders BoardState and stays live via SSE.

import {
  STAGE_ICONS, brandMark, el, fmtAgo, fmtClock, fmtDuration, fmtMoney,
  getJSON, mediaURL, subscribe, thumbURL, waveBars,
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
    s.style_playbook ? el("span", { class: "chip" }, s.style_playbook) : null,
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
        el("a", { class: "wordmark backlink", href: "/" }, t("backlot")),
        el("h1", {}, s.title),
        chips.length ? el("div", { class: "slate-chips" }, ...chips) : null,
      ),
    ),
    el("div", { class: "slate-actions" },
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
      el("a", {
        class: "board-settings-btn board-global-settings-btn",
        href: "/?app-settings=1",
        title: t("globalSettings"),
      }, t("globalSettings")),
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
  return statusLabel(st.status || "pending");
}

function renderRail(s) {
  const rail = el("nav", { class: "rail" });
  let pendingIndex = 1;
  for (const st of s.stages) {
    const cls = st.status === "completed" ? "done"
      : st.status === "in_progress" ? (st.stalled ? "active stalled" : "active")
      : st.status === "awaiting_human" ? "await"
      : st.status === "failed" ? "failed" : "pending";
    const icon = STAGE_ICONS[st.status] || String(pendingIndex);
    if (!STAGE_ICONS[st.status]) pendingIndex += 1;
    const statusCls = st.stalled ? "stalled"
      : st.status === "completed" ? "done"
      : st.status === "in_progress" ? "active"
      : st.status === "awaiting_human" ? "await"
      : st.status === "failed" ? "failed" : "pending";
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
  selectedStage = selectedStage === stageName ? null : stageName;
  render();
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
    body.append(
      el("div", { class: "d-cat", style: "font-family:var(--mono);font-size:calc(9.5px * var(--fs-scale));color:var(--text-3);letter-spacing:.1em;text-transform:uppercase;margin:6px 0 4px" }, artifactLabel(name)),
      el("pre", {}, JSON.stringify(artifact, null, 2)),
    );
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
  return item?.type === "audio" || /\.(mp3|wav|aac|m4a|ogg|flac)$/i.test(path);
}

function isImageMedia(item) {
  const path = String(item?.path || "");
  return item?.type === "image" || (item?.renderable && /\.(png|jpe?g|gif|webp|svg)$/i.test(path));
}

function buildArtifactPreview(s, entry) {
  const artifact = s.artifacts[entry.name];
  if (!artifact) return el("p", { class: "hint" }, t("artifactMissing"));
  return el("pre", { class: "asset-preview-pre" }, JSON.stringify(artifact, null, 2));
}

function buildMediaPreview(s, item) {
  if (item.type === "url" && item.path) {
    return el("div", { class: "asset-preview-body" },
      el("a", {
        class: "asset-preview-link",
        href: item.path,
        target: "_blank",
        rel: "noopener noreferrer",
      }, item.path),
    );
  }
  if (!item.exists) return el("p", { class: "hint" }, t("assetMissing"));
  if (isVideoMedia(item)) {
    return el("div", { class: "asset-preview-body" },
      el("video", {
        class: "asset-preview-media",
        src: mediaURL(s.project_id, item.path),
        controls: "",
        preload: "metadata",
      }),
    );
  }
  if (isAudioMedia(item)) {
    return el("div", { class: "asset-preview-body" },
      el("audio", {
        class: "asset-preview-media asset-preview-audio",
        src: mediaURL(s.project_id, item.path),
        controls: "",
        preload: "metadata",
      }),
    );
  }
  if (isImageMedia(item)) {
    return el("div", { class: "asset-preview-body" },
      el("img", {
        class: "asset-preview-media asset-preview-image",
        src: mediaURL(s.project_id, item.path),
        alt: "",
      }),
    );
  }
  return el("p", { class: "hint" }, t("summaryMediaFileHint"));
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

function artifactReviewContent(name, artifact) {
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
    const plan = artifact.production_plan || {};
    const cost = artifact.cost_estimate || {};
    return [
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
    const first = (artifact.sections || [])[0];
    return [
      reviewFacts([
        reviewFact(t("duration"), fmtDuration(artifact.total_duration_seconds)),
        reviewFact(t("sections"), (artifact.sections || []).length),
      ]),
      first && first.text ? el("p", { class: "approval-lead" }, shortText(first.text, 220)) : null,
      el("p", { class: "approval-guidance" }, t("scriptPreviewBelow")),
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
      titledItems(scenes),
      el("p", { class: "approval-guidance" }, t("reviewStoryboard")),
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
      titledItems(assets),
      el("p", { class: "approval-guidance" }, t("inspectFilmstrip")),
    ].filter(Boolean);
  }
  if (name === "edit_decisions") {
    return [
      reviewFacts([
        reviewFact(t("cuts"), Array.isArray(artifact.cuts) ? artifact.cuts.length : null),
        reviewFact(t("runtime"), artifact.render_runtime || (artifact.metadata || {}).render_runtime),
      ]),
      titledItems(artifact.cuts),
    ].filter(Boolean);
  }
  if (name === "render_report") {
    return [
      reviewFacts([
        reviewFact(t("outputs"), Array.isArray(artifact.outputs) ? artifact.outputs.length : null),
        reviewFact(t("duration"), artifact.duration_seconds != null ? fmtDuration(artifact.duration_seconds) : null),
      ]),
      titledItems(artifact.outputs),
    ].filter(Boolean);
  }
  if (name === "publish_log") {
    return [
      reviewFacts([reviewFact(t("destinations"), Array.isArray(artifact.entries) ? artifact.entries.length : null)]),
      titledItems((artifact.entries || []).map((entry) => ({
        title: entry.platform || entry.destination || t("publishDestination"),
        description: [entry.status, entry.url].filter(Boolean).join(" · "),
      }))),
    ].filter(Boolean);
  }
  if (name === "video_analysis_brief") {
    const source = artifact.source || {};
    const content = artifact.content_analysis || {};
    return [
      content.summary ? el("p", { class: "approval-lead" }, shortText(content.summary, 220)) : null,
      reviewFacts([
        reviewFact(t("duration"), source.duration_seconds != null ? fmtDuration(source.duration_seconds) : null),
        reviewFact(t("scenesField"), (artifact.structure_analysis || {}).total_scenes),
        reviewFact("来源", source.title || source.url || source.local_path),
      ]),
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

  const artifacts = entries.map(([name, artifact]) => el("article", {
    class: "approval-artifact",
    "data-artifact": name,
  },
    el("div", { class: "approval-artifact-kicker" }, humanize(name)),
    el("h2", {}, artifactReviewTitle(name, artifact, s)),
    ...artifactReviewContent(name, artifact),
  ));

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
      el("button", { type: "button", onclick: () => toggleDrawer(awaiting.name) }, t("openFullArtifact")),
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

function openSceneVideoModal(s, card, visual) {
  modal.innerHTML = "";
  const meta = [sceneLabel(card.id), card.section_label, fmtDuration(card.duration_seconds)]
    .filter(Boolean).join(" · ");
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
        visual.path ? el("code", { class: "doc-viewer-path doc-viewer-path--head" }, visual.path) : null,
      ),
    ),
  );
  modal.classList.add("open");
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  modal.classList.remove("open");
  modal.innerHTML = "";
  modal.removeAttribute("role");
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
modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

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
      statusEl,
    ];
    if (errText) {
      const copyBtn = el("button", {
        type: "button",
        class: "act-copy-btn",
        title: t("copyError"),
        onclick: (e) => {
          e.stopPropagation();
          copyActivityError(errText, copyBtn);
        },
      }, t("copyError"));
      rowKids.push(
        el("div", { class: "act-err-block" },
          el("pre", { class: "act-err" }, errText),
          copyBtn,
        ),
      );
    }
    body.append(el("div", { class: `act-row${failed ? " act-row--failed" : ""}` }, ...rowKids));
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
  const wrap = el("div", { class: "scene-card", style: `width:${width}px` });

  const slate = el("div", { class: "sc-slate" },
    el("span", { class: "num" }, sceneLabel(card.id)),
    card.takes.length > 1 ? el("span", { class: "take" }, `T${card.takes.length}`) : null,
    card.hero_moment ? el("span", { class: "hero" }, t("hero")) : null,
    el("span", { class: "dur" }, fmtDuration(dur)),
  );
  wrap.append(slate);

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
  wrap.append(thumb);

  // shot language chips
  const sl = card.shot_language;
  if (sl) {
    wrap.append(el("div", { class: "shotchips", style: "display:flex;flex-wrap:wrap;gap:4px;padding:7px 2px 0" },
      [sl.shot_size, sl.camera_movement, sl.lens_mm ? `${sl.lens_mm}mm` : null, sl.lighting_key]
        .filter(Boolean)
        .map((t) => el("span", { style: "font-family:var(--mono);font-size:calc(8.5px * var(--fs-scale));letter-spacing:.04em;color:#62626c;border:1px solid #212129;border-radius:3px;padding:1px 5px" }, String(t).replaceAll("_", " ")))));
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
    wrap.append(takes);
  }

  // narration + audio — clickable to read in full (F: narration text cut off)
  if (card.narration) {
    const long = card.narration.length > 90;
    wrap.append(el("div", {
      class: `narr${long ? " clip" : ""}`,
      title: t("clickReadNarration"),
      onclick: () => openNarrModal(card),
    }, card.narration, long ? el("span", { class: "narr-more" }, "⤢") : null));
  } else if (card.shot_intent || card.description) {
    wrap.append(el("div", { class: "narr tc-note" }, (card.shot_intent || card.description || "").slice(0, 110)));
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
    wrap.append(wave);
  }
  return wrap;
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
  // Full re-renders (every SSE refresh) must not reset an in-progress
  // watch: carry playback position/state over to the recreated element.
  const prev = document.querySelector(".render-hero video");
  const src = mediaURL(s.project_id, current.path);
  // preload="metadata" gives the element its intrinsic aspect ratio (and a
  // poster frame) before playback — without it a portrait 9:16 render sits
  // in a letterboxed 100%-wide black box that reads as landscape.
  const video = el("video", { src, controls: "", preload: "metadata" });
  // Click the frame to start playback (controls handle pause/scrub) — the
  // big player was inert to a click on the picture itself.
  video.addEventListener("click", () => { if (video.paused) video.play().catch(() => {}); });
  if (prev && prev.getAttribute("src") === src && (prev.currentTime > 0 || !prev.paused)) {
    const t = prev.currentTime;
    const wasPlaying = !prev.paused && !prev.ended;
    video.addEventListener("loadedmetadata", () => { video.currentTime = t; }, { once: true });
    video.setAttribute("preload", "metadata");
    if (wasPlaying) video.autoplay = true;
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

function renderAwaitingNotice(s) {
  const awaiting = s.stages.find((x) => x.status === "awaiting_human");
  if (!awaiting) return null;
  return el("div", { class: "notice" },
    el("span", { style: "font-size:calc(16px * var(--fs-scale))" }, "◈"),
    el("span", {},
      el("b", {}, t("stageWaiting", { stage: stageLabel(awaiting.name) })),
      t("agentPaused"), el("b", {}, t("inChat")), t("approveOrChange")));
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

function renderReplayBar(s) {
  const bounds = replayBounds(s);
  if (!bounds) return null;
  if (!replay) {
    // collapsed: just the entry button
    return el("div", { class: "replay-bar", style: "justify-content:flex-end" },
      el("span", { class: "rp-time" }, t("scrubRun")),
      el("span", { class: "rp-btn", onclick: startReplay }, t("replayRun")));
  }
  const pos = (replay.t - replay.t0) / Math.max(1, replay.t1 - replay.t0);
  const timeLabel = el("span", { class: "rp-time" },
    new Date(replay.t).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  const setT = (value) => {
    replay.t = replay.t0 + (Number(value) / 1000) * (replay.t1 - replay.t0);
    timeLabel.textContent = new Date(replay.t)
      .toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  return el("div", { class: "replay-bar" },
    el("span", { class: "rp-btn", onclick: toggleReplayPlay }, replay.playing ? "❚❚" : "▶"),
    el("input", {
      type: "range", min: "0", max: "1000", value: String(Math.round(pos * 1000)),
      // A full render() would destroy this slider mid-drag: while dragging,
      // only pause + track the time label; re-render the board on release.
      onpointerdown: () => { replay.playing = false; },
      oninput: (e) => setT(e.target.value),
      onchange: (e) => { setT(e.target.value); render(); },
    }),
    timeLabel,
    el("span", { class: "rp-btn", onclick: stopReplay }, t("exitReplay")),
  );
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
  app.innerHTML = "";
  app.append(renderSlate(s));

  // Zone 1 — pipeline: stage rail + replay scrubber (one visual unit)
  const pipeline = el("section", { class: "board-pipeline", "aria-label": t("boardPipelineAria") });
  pipeline.append(renderRail(s));
  const replayBar = renderReplayBar(state);
  if (replayBar) pipeline.append(replayBar);
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

  const approvalReview = renderApprovalReview(s);
  if (approvalReview) main.append(approvalReview);
  const script = renderScriptCard(s);
  if (script) main.append(script);

  const mediaBlock = el("div", { class: "board-media-block" });
  const storyboard = renderStoryboard(s);
  const found = renderFoundMedia(s);
  const renders = renderRenders(s);
  for (const section of [storyboard, found, renders]) {
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
