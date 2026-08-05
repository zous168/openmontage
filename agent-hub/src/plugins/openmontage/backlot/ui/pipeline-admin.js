/** Pipeline manifest admin — global settings tab. */

import { el, getJSON, patchJSON } from "/ui/lib.js";
import { t } from "/ui/i18n.js";
import { showLoading } from "/ui/loading.js";

function renderSummaryBar(summary) {
  const s = summary || {};
  return el("div", { class: "deps-summary pipe-summary" },
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, String(s.total ?? 0)),
      el("span", { class: "deps-summary-label" }, t("pipeTotal")),
    ),
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, String(s.visible ?? 0)),
      el("span", { class: "deps-summary-label" }, t("pipeVisible")),
    ),
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, String(s.production ?? 0)),
      el("span", { class: "deps-summary-label" }, t("pipeProduction")),
    ),
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, String(s.skill_issues ?? 0)),
      el("span", { class: "deps-summary-label" }, t("pipeSkillIssues")),
    ),
  );
}

function renderStageTable(stages) {
  const table = el("table", { class: "pipe-stage-table" },
    el("thead", {},
      el("tr", {},
        el("th", {}, t("pipeStageName")),
        el("th", {}, t("pipeStageSkill")),
        el("th", {}, t("pipeStageProduces")),
        el("th", {}, t("pipeStageApproval")),
      ),
    ),
    el("tbody"),
  );
  const tbody = table.querySelector("tbody");
  for (const stage of stages || []) {
    const skillCell = el("td", { class: "pipe-skill-cell" });
    if (stage.skill) {
      skillCell.append(
        stage.skill_ok
          ? el("span", { class: "deps-badge deps-badge-ok" }, "OK")
          : el("span", { class: "deps-badge deps-badge-bad" }, "!"),
        el("code", { class: "pipe-skill-path" }, stage.skill),
      );
    } else {
      skillCell.textContent = "—";
    }
    tbody.append(el("tr", {},
      el("td", {},
        el("span", { class: "pipe-stage-label" }, stage.label_zh || stage.name),
        stage.name && stage.label_zh !== stage.name
          ? el("code", { class: "pipe-stage-id" }, stage.name)
          : null,
      ),
      skillCell,
      el("td", { class: "pipe-produces" },
        (stage.produces || []).length
          ? (stage.produces || []).map((p) => el("code", { class: "pipe-artifact" }, p))
          : "—",
      ),
      el("td", {},
        stage.human_approval_default
          ? el("span", { class: "pipe-approval-yes" }, t("pipeApprovalYes"))
          : el("span", { class: "pipe-approval-no" }, t("pipeApprovalNo")),
      ),
    ));
  }
  return table;
}

function renderPipelineCard(pipe, errorBox, onUpdated) {
  const hiddenToggle = el("input", {
    type: "checkbox",
    class: "pipe-hidden-toggle",
    checked: pipe.hidden ? "true" : null,
    "aria-label": t("pipeHiddenToggle", { name: pipe.label_zh }),
  });

  const labelInput = el("input", {
    class: "lib-field-input pipe-label-input",
    type: "text",
    value: pipe.label_zh || "",
    maxlength: "80",
  });
  const summaryInput = el("input", {
    class: "lib-field-input pipe-summary-input",
    type: "text",
    value: pipe.summary_zh || "",
    maxlength: "200",
  });

  const saveBtn = el("button", {
    class: "lib-form-submit pipe-save-btn",
    type: "button",
    hidden: "true",
  }, t("pipeSaveUi"));

  let saving = false;

  const markDirty = () => {
    saveBtn.hidden = false;
  };
  hiddenToggle.addEventListener("change", markDirty);
  labelInput.addEventListener("input", markDirty);
  summaryInput.addEventListener("input", markDirty);

  saveBtn.addEventListener("click", async () => {
    if (saving) return;
    saving = true;
    saveBtn.disabled = true;
    saveBtn.textContent = t("pipeSaving");
    errorBox.hidden = true;
    try {
      await patchJSON(`/api/system/pipelines/${encodeURIComponent(pipe.id)}`, {
        hidden: hiddenToggle.checked,
        label_zh: labelInput.value.trim(),
        summary_zh: summaryInput.value.trim(),
      });
      saveBtn.hidden = true;
      if (onUpdated) await onUpdated();
    } catch (err) {
      errorBox.hidden = false;
      errorBox.textContent = err.message || t("pipeSaveFailed");
    } finally {
      saving = false;
      saveBtn.disabled = false;
      saveBtn.textContent = t("pipeSaveUi");
    }
  });

  const meta = el("div", { class: "pipe-meta-row" },
    el("span", { class: "pipe-meta-item" },
      el("span", { class: "pipe-meta-k" }, t("pipeCategory")),
      el("span", {}, pipe.category_zh || pipe.category),
    ),
    el("span", { class: "pipe-meta-item" },
      el("span", { class: "pipe-meta-k" }, t("pipeStability")),
      el("span", {
        class: pipe.stability === "production" ? "pipe-stab-prod" : "pipe-stab-beta",
      }, pipe.stability_zh || pipe.stability),
    ),
    el("span", { class: "pipe-meta-item" },
      el("span", { class: "pipe-meta-k" }, t("pipeVersion")),
      el("span", {}, pipe.version || "—"),
    ),
    el("span", { class: "pipe-meta-item" },
      el("span", { class: "pipe-meta-k" }, t("pipeStages")),
      el("span", {}, String(pipe.stage_count ?? 0)),
    ),
  );

  return el("details", { class: "pipe-card" },
    el("summary", { class: "pipe-card-summary" },
      el("span", { class: "pipe-card-title" },
        pipe.hidden ? el("span", { class: "pipe-hidden-badge" }, t("pipeHiddenBadge")) : null,
        el("span", { class: "pipe-card-label" }, pipe.label_zh || pipe.id),
        el("code", { class: "pipe-card-id" }, pipe.id),
      ),
      el("span", { class: "pipe-card-blurb" }, pipe.summary_zh || pipe.description || ""),
    ),
    el("div", { class: "pipe-card-body" },
      el("p", { class: "pipe-manifest-path" },
        el("code", {}, pipe.manifest_path),
        (pipe.issues?.manifest || []).length
          ? el("span", { class: "pipe-schema-warn" }, t("pipeSchemaWarn"))
          : null,
      ),
      meta,
      el("div", { class: "pipe-ui-fields" },
        el("label", { class: "lib-field pipe-field-inline" },
          el("span", { class: "lib-field-label" }, t("pipeLabelZh")),
          labelInput,
        ),
        el("label", { class: "lib-field pipe-field-inline" },
          el("span", { class: "lib-field-label" }, t("pipeSummaryZh")),
          summaryInput,
        ),
        el("label", { class: "lib-field pipe-hidden-field" },
          hiddenToggle,
          el("span", { class: "lib-field-label" }, t("pipeHiddenLabel")),
        ),
        saveBtn,
      ),
      el("h4", { class: "pipe-stages-title" }, t("pipeStageList")),
      renderStageTable(pipe.stages),
    ),
  );
}

function renderPipelineList(data, host, errorBox) {
  host.innerHTML = "";
  host.append(renderSummaryBar(data.summary));
  const list = el("div", { class: "pipe-list" });
  for (const pipe of data.pipelines || []) {
    list.append(renderPipelineCard(pipe, errorBox, async () => {
      const refreshed = await getJSON("/api/system/pipelines");
      renderPipelineList(refreshed, host, errorBox);
    }));
  }
  host.append(list);
}

export async function loadPipelinesInto(host, errorBox) {
  showLoading(host, t("pipeLoading"));
  errorBox.hidden = true;
  try {
    const data = await getJSON("/api/system/pipelines");
    renderPipelineList(data, host, errorBox);
  } catch (err) {
    host.innerHTML = "";
    errorBox.hidden = false;
    errorBox.textContent = err.message || t("pipeLoadFailed");
  }
}
