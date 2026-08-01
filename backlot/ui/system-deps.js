/** System dependency reports — embedded in global settings. */

import { el, getJSON } from "/ui/lib.js";
import { capabilityLabel, t } from "/ui/i18n.js";
import { renderCatalogReport } from "/ui/skill-tool-catalog.js";

function statusBadge(ok, labelOk, labelBad) {
  return el("span", { class: ok ? "deps-badge deps-badge-ok" : "deps-badge deps-badge-bad" },
    ok ? labelOk : labelBad);
}

function renderSummaryBar(data) {
  const s = data.summary || {};
  const manifest = data.status_mode === "manifest";
  const depsTotal = s.deps_total ?? 0;
  const depsOk = manifest
    ? `—/${depsTotal}`
    : `${s.deps_ok ?? 0}/${depsTotal}`;
  const binaries = manifest
    ? `—/${s.binaries_total ?? 0}`
    : `${s.binaries_ok ?? 0}/${s.binaries_total ?? 0}`;
  const missing = manifest ? "—" : String(s.deps_missing ?? 0);
  const bar = el("div", { class: "deps-summary" },
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, depsOk),
      el("span", { class: "deps-summary-label" }, t(manifest ? "depsPackagesTotal" : "depsPackagesOk")),
    ),
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, binaries),
      el("span", { class: "deps-summary-label" }, t("depsBinariesOk")),
    ),
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, missing),
      el("span", { class: "deps-summary-label" }, t(manifest ? "depsMissingPending" : "depsMissing")),
    ),
  );
  if (manifest) {
    return el("div", { class: "deps-summary-wrap" }, bar);
  }
  return bar;
}

function renderRuntimeEngines(engines) {
  const items = Object.entries(engines || {}).map(([name, ok]) =>
    el("div", { class: "deps-engine" },
      ok === null || ok === undefined
        ? el("span", { class: "deps-badge deps-badge-pending" }, "—")
        : statusBadge(ok, t("depsOk"), t("depsMissing")),
      el("span", {}, t({ ffmpeg: "depsRuntimeFfmpeg", remotion: "depsRuntimeRemotion", hyperframes: "depsRuntimeHyperframes" }[name] || name)),
    ),
  );
  if (!items.length) return null;
  return el("section", { class: "deps-section" },
    el("h3", { class: "deps-section-title" }, t("depsCompositionRuntimes")),
    el("div", { class: "deps-engine-row" }, ...items),
  );
}

function renderBinaries(binaries) {
  if (!binaries?.length) return null;
  const list = el("div", { class: "deps-binary-list" });
  for (const b of binaries) {
    list.append(el("div", { class: "deps-binary-row" },
      b.ok === null || b.ok === undefined
        ? el("span", { class: "deps-badge deps-badge-pending" }, "—")
        : statusBadge(b.ok, "OK", "—"),
      el("span", { class: "deps-binary-name" },
        el("span", { class: "deps-binary-label" }, b.label_zh || b.name),
        b.label_zh && b.label_zh !== b.name
          ? el("code", { class: "deps-binary-tech" }, b.name)
          : null,
      ),
      el("span", { class: "deps-binary-purpose" }, b.purpose || "—"),
      el("code", { class: "deps-binary-path" }, b.path || t("depsPathPending")),
      el("span", { class: "deps-binary-detail" }, b.detail || "—"),
    ));
  }
  return el("section", { class: "deps-section" },
    el("h3", { class: "deps-section-title" }, t("depsCoreBinaries")),
    list,
  );
}

function renderWarnings(warnings) {
  if (!warnings?.length) return null;
  return el("section", { class: "deps-section" },
    el("h3", { class: "deps-section-title" }, t("depsRuntimeWarnings")),
    el("ul", { class: "deps-warn-list" },
      ...warnings.map((w) => el("li", {}, w)),
    ),
  );
}

function renderSetupOffers(offers) {
  if (!offers?.length) return null;
  const list = el("div", { class: "deps-offer-list" });
  for (const offer of offers.slice(0, 12)) {
    const label = offer.tool_label_zh || offer.tool || "—";
    const hint = offer.install_hint_zh || offer.install_instructions || "";
    list.append(el("div", { class: "deps-offer" },
      el("div", { class: "deps-offer-head" },
        el("span", { class: "deps-offer-tool" },
          el("span", { class: "deps-offer-label" }, label),
          offer.tool_label_zh && offer.tool && offer.tool !== offer.tool_label_zh
            ? el("code", { class: "deps-offer-tech" }, offer.tool)
            : null,
        ),
        el("span", { class: "deps-offer-cap" }, capabilityLabel(offer.capability)),
      ),
      hint ? el("p", { class: "deps-offer-hint" }, hint) : null,
      offer.env_vars?.length
        ? el("p", { class: "deps-offer-env" }, t("depsOfferEnvVars", { vars: offer.env_vars.join("、") }))
        : null,
    ));
  }
  return el("section", { class: "deps-section" },
    el("h3", { class: "deps-section-title" }, t("depsSetupOffers")),
    list,
  );
}

function renderVerifiedTools(tools) {
  if (!tools?.length) return null;
  const bad = tools.filter((toolRow) => toolRow.status !== "available" && toolRow.issues?.length);
  if (!bad.length) {
    return el("p", { class: "deps-verify-ok" }, t("depsVerifyAllOk"));
  }
  const list = el("div", { class: "deps-issue-list" });
  for (const tool of bad.slice(0, 40)) {
    list.append(el("div", { class: "deps-issue" },
      el("div", { class: "deps-issue-head" },
        el("span", { class: "deps-tool-name" }, tool.label_zh || tool.name),
        el("span", { class: "deps-tool-meta" }, capabilityLabel(tool.capability)),
      ),
      el("ul", {}, ...(tool.issues || []).map((issue) =>
        el("li", {}, el("code", {}, issue.dependency), ` — ${issue.message}`),
      )),
    ));
  }
  return el("section", { class: "deps-section" },
    el("h3", { class: "deps-section-title" }, t("depsVerifyDetails")),
    list,
  );
}

function normalizeDependency(dep) {
  if (dep && typeof dep === "object") return dep;
  const raw = String(dep || "");
  return { id: raw, name: raw, purpose: "—", path: null, ok: null };
}

function renderDependencyRow(dep, unchecked) {
  const item = normalizeDependency(dep);
  const depOk = item.ok;
  const badge = unchecked || depOk === null || depOk === undefined
    ? el("span", { class: "deps-badge deps-badge-pending" }, "—")
    : statusBadge(depOk, "✓", "✗");
  const label = item.label_zh || item.name || item.id || "—";
  const techName = item.label_zh && item.name && item.label_zh !== item.name ? item.name : null;
  const toolsZh = item.tools_zh?.length
    ? item.tools_zh
    : (item.tools || []).map((n) => n);
  const tools = toolsZh.length
    ? el("span", { class: "deps-dep-tools" }, t("depsUsedBy", { tools: toolsZh.join("、") }))
    : null;
  return el("div", { class: "deps-dep-row" },
    badge,
    el("span", { class: "deps-dep-name-cell" },
      el("span", { class: "deps-dep-label" }, label),
      techName ? el("code", { class: "deps-dep-tech" }, techName) : null,
    ),
    el("span", { class: "deps-dep-purpose" }, item.description_zh || item.purpose || "—"),
    el("code", { class: "deps-dep-path" }, item.path || t("depsPathPending")),
    tools,
    !unchecked && depOk === false && item.install_hint
      ? el("span", { class: "deps-dep-hint" }, item.install_hint)
      : null,
  );
}

function renderDependencyGroups(groups, statusMode) {
  if (!groups?.length) return null;
  const manifest = statusMode === "manifest";
  const unchecked = manifest;
  const root = el("div", { class: "deps-package-list" });
  for (const group of groups) {
    root.append(el("div", { class: "deps-package-group" },
      el("h4", { class: "deps-package-group-title" }, group.label || group.id),
      el("div", { class: "deps-checklist-deps" },
        el("div", { class: "deps-dep-head deps-dep-head-packages" },
          el("span", {}, ""),
          el("span", {}, t("depsColName")),
          el("span", {}, t("depsColPurpose")),
          el("span", {}, t("depsColPath")),
        ),
        ...(group.items || []).map((dep) => renderDependencyRow(dep, unchecked)),
      ),
    ));
  }
  return el("section", { class: "deps-section" },
    el("h3", { class: "deps-section-title" }, t("depsExternalPackages")),
    root,
  );
}

export function renderDepsReport(data) {
  const report = el("div", { class: "deps-report" },
    renderSummaryBar(data),
    renderDependencyGroups(data.dependency_groups, data.status_mode),
  );
  if (data.status_mode === "manifest") {
    report.append(
      renderRuntimeEngines(data.composition_runtimes),
      renderBinaries(data.binaries),
    );
    return report;
  }
  report.append(
    renderRuntimeEngines(data.composition_runtimes),
    renderBinaries(data.binaries),
    renderWarnings(data.runtime_warnings),
    renderSetupOffers(data.setup_offers),
    renderVerifiedTools(data.tools),
  );
  return report;
}

export async function loadDepsManifestInto(host, errorBox) {
  errorBox.hidden = true;
  host.innerHTML = "";
  host.append(el("p", { class: "deps-loading" }, t("depsManifestLoading")));
  try {
    const data = await getJSON("/api/system/dependencies");
    host.innerHTML = "";
    host.append(renderDepsReport(data));
  } catch (err) {
    errorBox.hidden = false;
    errorBox.textContent = err.message || t("depsLoadFailed");
    host.innerHTML = "";
  }
}

export async function loadDepsInto(host, errorBox, { verify = false } = {}) {
  errorBox.hidden = true;
  host.innerHTML = "";
  host.append(el("p", { class: "deps-loading" }, verify ? t("depsVerifying") : t("depsLoading")));
  try {
    const data = await getJSON(`/api/system/dependencies?check=1${verify ? "&verify=1" : ""}`);
    host.innerHTML = "";
    host.append(renderDepsReport(data));
  } catch (err) {
    errorBox.hidden = false;
    errorBox.textContent = err.message || t("depsLoadFailed");
    host.innerHTML = "";
  }
}

export async function loadCatalogInto(host, errorBox) {
  errorBox.hidden = true;
  host.innerHTML = "";
  host.append(el("p", { class: "deps-loading" }, t("catalogLoading")));
  try {
    const data = await getJSON("/api/system/catalog");
    host.innerHTML = "";
    host.append(renderCatalogReport(data));
  } catch (err) {
    errorBox.hidden = false;
    errorBox.textContent = err.message || t("catalogLoadFailed");
    host.innerHTML = "";
  }
}
