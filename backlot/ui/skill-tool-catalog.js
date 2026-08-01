/** Skill & tool catalog tab — Layer 1 tools + Layer 2/3 skills. */

import { el } from "/ui/lib.js";
import { capabilityLabel, t } from "/ui/i18n.js";

function layerLabel(layer) {
  if (layer?.label_key) return t(layer.label_key);
  return layer?.id || "";
}

function groupLabel(group) {
  if (group?.label_key) return t(group.label_key);
  return group?.label || group?.id || "";
}

function statusDot(status) {
  const ok = status === "available";
  return el("span", {
    class: ok ? "catalog-status catalog-status-ok" : "catalog-status catalog-status-bad",
    title: ok ? t("depsOk") : t("depsMissing"),
  }, ok ? "●" : "○");
}

function categoryLabel(category) {
  const key = {
    core: "catalogCategoryCore",
    creative: "catalogCategoryCreative",
    meta: "catalogCategoryMeta",
    pipelines: "catalogCategoryPipelines",
    agent_skills: "catalogCategoryAgent",
  }[category];
  return key ? t(key) : category || "";
}

function renderSkillRow(item) {
  const meta = [];
  if (item.pipeline) meta.push(item.pipeline);
  if (item.stage_label_zh) meta.push(item.stage_label_zh);
  else if (item.stage) meta.push(item.stage.replace(/-director$/, "").replace(/-/g, " "));
  if (item.subcategory) meta.push(item.subcategory);
  const cat = categoryLabel(item.category);
  const label = item.name_zh || item.name || item.id;
  const techName = item.name_zh && item.name && item.name !== item.name_zh ? item.name : null;
  return el("div", { class: "catalog-row catalog-row-skill" },
    el("div", { class: "catalog-row-head" },
      cat ? el("span", { class: "catalog-row-cat" }, cat) : null,
      el("span", { class: "catalog-row-name" }, label),
      techName ? el("code", { class: "catalog-row-tech" }, techName) : null,
    ),
    item.description_zh
      ? el("p", { class: "catalog-row-desc" }, item.description_zh)
      : null,
    meta.length ? el("span", { class: "catalog-row-meta" }, meta.join(" · ")) : null,
    el("code", { class: "catalog-row-path" }, item.path || item.id),
  );
}

function renderToolRow(item) {
  return el("div", { class: "catalog-row catalog-row-tool" },
    statusDot(item.status),
    el("span", { class: "catalog-row-name" }, item.name),
    el("span", { class: "catalog-row-meta" },
      [item.provider, capabilityLabel(item.capability)].filter(Boolean).join(" · "),
    ),
    item.agent_skills?.length
      ? el("span", { class: "catalog-row-skills" },
        t("catalogLinkedSkills", { n: item.agent_skills.length }),
        " ",
        item.agent_skills.slice(0, 4).join(", "),
        item.agent_skills.length > 4 ? "…" : "",
      )
      : null,
  );
}

function renderItem(item) {
  return item.kind === "tool" ? renderToolRow(item) : renderSkillRow(item);
}

function renderGroupBody(group) {
  if (group.subgroups?.length) {
    const host = el("div", { class: "catalog-subgroups" });
    for (const sub of group.subgroups) {
      host.append(el("details", { class: "catalog-subgroup" },
        el("summary", { class: "catalog-subgroup-summary" },
          el("span", {}, sub.label || sub.id),
          el("span", { class: "catalog-count" }, String((sub.items || []).length)),
        ),
        el("div", { class: "catalog-list" }, ...(sub.items || []).map(renderItem)),
      ));
    }
    return host;
  }
  return el("div", { class: "catalog-list" }, ...(group.items || []).map(renderItem));
}

function renderSummary(summary) {
  if (!summary) return null;
  return el("div", { class: "deps-summary catalog-summary" },
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, String(summary.layer2_skills ?? 0)),
      el("span", { class: "deps-summary-label" }, t("catalogLayer2Count")),
    ),
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, String(summary.layer3_skills ?? 0)),
      el("span", { class: "deps-summary-label" }, t("catalogLayer3Count")),
    ),
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, String(summary.pipelines_with_skills ?? 0)),
      el("span", { class: "deps-summary-label" }, t("catalogPipelineCount")),
    ),
  );
}

export function renderCatalogReport(data) {
  const host = el("div", { class: "catalog-report" },
    renderSummary(data.summary),
  );

  for (const layer of data.layers || []) {
    const section = el("section", { class: "catalog-layer" },
      el("h3", { class: "catalog-layer-title" }, layerLabel(layer)),
    );
    for (const group of layer.groups || []) {
      const count = group.item_count
        ?? (group.subgroups
          ? group.subgroups.reduce((n, sg) => n + (sg.items?.length || 0), 0)
          : (group.items?.length || 0));
      section.append(el("details", { class: "catalog-group", open: layer.layer === 2 ? "open" : null },
        el("summary", { class: "catalog-group-summary" },
          el("span", {}, groupLabel(group)),
          el("span", { class: "catalog-count" }, String(count)),
        ),
        renderGroupBody(group),
      ));
    }
    host.append(section);
  }
  return host;
}
