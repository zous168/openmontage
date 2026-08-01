/** Dedicated pipeline config — stages, review checklists, director skill prompts. */

import { el, getJSON, patchJSON } from "/ui/lib.js";
import { t } from "/ui/i18n.js";
import { applyPreferences, readLocalPreferences } from "/ui/preferences.js";

readLocalPreferences();

const app = document.getElementById("pipeApp");
const pageTitle = document.getElementById("pipePageTitle");
const pageLead = document.getElementById("pipePageLead");

function pipelineIdFromPath() {
  const parts = location.pathname.replace(/\/+$/, "").split("/");
  if (parts.length >= 2 && parts[parts.length - 2] === "pipelines") {
    return decodeURIComponent(parts[parts.length - 1] || "");
  }
  return "";
}

function navigateToPipeline(id) {
  if (id) {
    history.pushState(null, "", `/pipelines/${encodeURIComponent(id)}`);
    void renderConfig(id);
  } else {
    history.pushState(null, "", "/pipelines");
    void renderList();
  }
}

function listEditor(items, placeholder) {
  const host = el("div", { class: "pipe-list-editor" });
  const rows = [];

  function syncHidden() {
    host.querySelectorAll('input[type="hidden"]').forEach((n) => n.remove());
  }

  function addRow(value = "") {
    const input = el("input", {
      class: "lib-field-input pipe-list-input",
      type: "text",
      value,
      placeholder,
    });
    const removeBtn = el("button", {
      class: "pipe-list-remove",
      type: "button",
      title: t("pipeRemoveItem"),
    }, "×");
    const row = el("div", { class: "pipe-list-row" }, input, removeBtn);
    removeBtn.addEventListener("click", () => {
      row.remove();
      rows.splice(rows.indexOf(input), 1);
    });
    rows.push(input);
    host.append(row);
    return input;
  }

  for (const item of items || []) addRow(item);
  if (!items?.length) addRow("");

  host.append(el("button", {
    class: "pipe-list-add",
    type: "button",
  }, t("pipeAddItem")));

  host.addEventListener("click", (ev) => {
    if (ev.target.closest(".pipe-list-add")) addRow("");
  });

  return {
    host,
    values() {
      return rows.map((input) => input.value.trim()).filter(Boolean);
    },
  };
}

async function renderList() {
  pageTitle.textContent = t("pipeConfigTitle");
  pageLead.textContent = t("pipeConfigLead");
  app.innerHTML = "";
  app.append(el("p", { class: "deps-loading" }, t("pipeLoading")));

  try {
    const data = await getJSON("/api/system/pipelines");
    app.innerHTML = "";
    const grid = el("div", { class: "pipe-config-grid" });
    for (const pipe of data.pipelines || []) {
      grid.append(el("article", { class: "pipe-config-card" },
        el("div", { class: "pipe-config-card-head" },
          pipe.hidden ? el("span", { class: "pipe-hidden-badge" }, t("pipeHiddenBadge")) : null,
          el("h2", { class: "pipe-config-card-title" }, pipe.label_zh || pipe.id),
          el("code", { class: "pipe-card-id" }, pipe.id),
        ),
        el("p", { class: "pipe-config-card-blurb" }, pipe.summary_zh || pipe.description || ""),
        el("div", { class: "pipe-config-card-meta" },
          el("span", {}, `${t("pipeStages")}: ${pipe.stage_count ?? 0}`),
          el("span", {}, pipe.stability_zh || pipe.stability),
        ),
        el("button", {
          class: "lib-form-submit pipe-config-open",
          type: "button",
          onclick: () => navigateToPipeline(pipe.id),
        }, t("pipeOpenConfig")),
      ));
    }
    app.append(grid);
  } catch (err) {
    app.innerHTML = "";
    app.append(el("div", { class: "notice warn" }, err.message || t("pipeLoadFailed")));
  }
}

async function renderConfig(pipelineId) {
  pageTitle.textContent = t("pipeConfigEditing");
  pageLead.textContent = pipelineId;
  app.innerHTML = "";
  app.append(el("p", { class: "deps-loading" }, t("pipeLoading")));

  let config;
  try {
    config = await getJSON(`/api/system/pipelines/${encodeURIComponent(pipelineId)}/config`);
  } catch (err) {
    app.innerHTML = "";
    app.append(
      el("div", { class: "notice warn" }, err.message || t("pipeLoadFailed")),
      el("button", {
        class: "lib-form-cancel",
        type: "button",
        onclick: () => navigateToPipeline(""),
      }, t("pipeBackToList")),
    );
    return;
  }

  pageTitle.textContent = config.label_zh || config.id;
  pageLead.textContent = config.summary_zh || config.description || config.id;

  const stages = config.stages || [];
  let activeStage = stages[0]?.name || "";
  let activeTab = "prompt";

  const errorBox = el("p", { class: "lib-form-error", hidden: "true" });
  const stageNav = el("nav", { class: "pipe-stage-nav", "aria-label": t("pipeStageList") });
  const editorHost = el("div", { class: "pipe-stage-editor" });
  const layout = el("div", { class: "pipe-config-layout" }, stageNav, editorHost);

  const selector = el("select", { class: "lib-field-input pipe-pipeline-select" });
  try {
    const catalog = await getJSON("/api/system/pipelines");
    for (const p of catalog.pipelines || []) {
      selector.append(el("option", {
        value: p.id,
        selected: p.id === pipelineId ? "true" : null,
      }, p.label_zh || p.id));
    }
  } catch { /* keep current only */ }
  selector.addEventListener("change", () => navigateToPipeline(selector.value));

  app.innerHTML = "";
  app.append(
    el("div", { class: "pipe-config-toolbar" },
      el("button", {
        class: "lib-form-cancel pipe-back-btn",
        type: "button",
        onclick: () => navigateToPipeline(""),
      }, t("pipeBackToList")),
      selector,
      el("code", { class: "pipe-manifest-path" }, config.manifest_path),
    ),
    errorBox,
    layout,
  );

  function renderStageNav() {
    stageNav.innerHTML = "";
    for (const stage of stages) {
      const btn = el("button", {
        class: `pipe-stage-nav-item${stage.name === activeStage ? " active" : ""}`,
        type: "button",
        onclick: () => {
          activeStage = stage.name;
          renderStageNav();
          void renderStageEditor();
        },
      },
        el("span", { class: "pipe-stage-nav-label" }, stage.label_zh || stage.name),
        el("code", { class: "pipe-stage-nav-id" }, stage.name),
        !stage.skill_ok && stage.skill
          ? el("span", { class: "deps-badge deps-badge-bad" }, "!")
          : null,
      );
      stageNav.append(btn);
    }
  }

  async function renderStageEditor() {
    const stage = stages.find((s) => s.name === activeStage);
    if (!stage) {
      editorHost.innerHTML = "";
      editorHost.append(el("p", { class: "deps-loading" }, t("pipeNoStage")));
      return;
    }

    editorHost.innerHTML = "";
    const tabBar = el("div", { class: "sys-tabs pipe-editor-tabs", role: "tablist" });
    const tabs = [
      { id: "prompt", label: t("pipeTabPrompt") },
      { id: "review", label: t("pipeTabReview") },
      { id: "criteria", label: t("pipeTabCriteria") },
    ];
    for (const tab of tabs) {
      tabBar.append(el("button", {
        class: `sys-tab${activeTab === tab.id ? " active" : ""}`,
        type: "button",
        role: "tab",
        "aria-selected": activeTab === tab.id ? "true" : "false",
        onclick: () => {
          activeTab = tab.id;
          void renderStageEditor();
        },
      }, tab.label));
    }

    const pane = el("div", { class: "pipe-editor-pane" });
    const saveManifestBtn = el("button", {
      class: "lib-form-submit",
      type: "button",
      hidden: "true",
    }, t("pipeSaveStage"));
    const saveSkillBtn = el("button", {
      class: "lib-form-submit",
      type: "button",
      hidden: "true",
    }, t("pipeSavePrompt"));

    editorHost.append(
      el("header", { class: "pipe-stage-header" },
        el("h2", { class: "pipe-stage-title" }, stage.label_zh || stage.name),
        el("code", { class: "pipe-skill-path" }, stage.skill || "—"),
        stage.produces?.length
          ? el("div", { class: "pipe-produces" },
              ...stage.produces.map((p) => el("code", { class: "pipe-artifact" }, p)))
          : null,
      ),
      tabBar,
      pane,
      el("div", { class: "lib-form-actions pipe-editor-actions" }, saveManifestBtn, saveSkillBtn),
    );

    if (activeTab === "prompt") {
      pane.append(el("p", { class: "lib-field-hint pipe-prompt-hint" }, t("pipePromptHint")));
      if (!stage.skill) {
        pane.append(el("p", { class: "notice warn" }, t("pipeNoSkill")));
        return;
      }
      pane.append(el("p", { class: "deps-loading" }, t("pipeLoadingPrompt")));
      let skillData;
      try {
        skillData = await getJSON(`/api/system/skills/${encodeURIComponent(stage.skill)}`);
      } catch (err) {
        pane.innerHTML = "";
        pane.append(el("p", { class: "notice warn" }, err.message || t("pipePromptLoadFailed")));
        return;
      }
      pane.innerHTML = "";
      pane.append(el("p", { class: "pipe-skill-file" },
        el("code", {}, skillData.file_path),
      ));
      const textarea = el("textarea", {
        class: "lib-field-input pipe-prompt-textarea",
        spellcheck: "false",
      }, skillData.content || "");
      pane.append(textarea);
      textarea.addEventListener("input", () => {
        saveSkillBtn.hidden = false;
      });
      saveSkillBtn.hidden = true;
      saveSkillBtn.onclick = async () => {
        saveSkillBtn.disabled = true;
        saveSkillBtn.textContent = t("pipeSaving");
        errorBox.hidden = true;
        try {
          await patchJSON(`/api/system/skills/${encodeURIComponent(stage.skill)}`, {
            content: textarea.value,
          });
          saveSkillBtn.hidden = true;
        } catch (err) {
          errorBox.hidden = false;
          errorBox.textContent = err.message || t("pipeSaveFailed");
        } finally {
          saveSkillBtn.disabled = false;
          saveSkillBtn.textContent = t("pipeSavePrompt");
        }
      };
      return;
    }

    if (activeTab === "review") {
      const reviewEditor = listEditor(stage.review_focus, t("pipeReviewPlaceholder"));
      pane.append(
        el("p", { class: "lib-field-hint" }, t("pipeReviewHint")),
        reviewEditor.host,
      );
      const approvalToggle = el("input", {
        type: "checkbox",
        checked: stage.human_approval_default ? "true" : null,
      });
      pane.append(el("label", { class: "lib-field pipe-hidden-field" },
        approvalToggle,
        el("span", { class: "lib-field-label" }, t("pipeApprovalDefault")),
      ));
      let dirty = false;
      const markDirty = () => {
        dirty = true;
        saveManifestBtn.hidden = false;
      };
      reviewEditor.host.addEventListener("input", markDirty);
      approvalToggle.addEventListener("change", markDirty);
      saveManifestBtn.hidden = true;
      saveManifestBtn.onclick = async () => {
        saveManifestBtn.disabled = true;
        saveManifestBtn.textContent = t("pipeSaving");
        errorBox.hidden = true;
        try {
          const updated = await patchJSON(
            `/api/system/pipelines/${encodeURIComponent(pipelineId)}/stages/${encodeURIComponent(stage.name)}`,
            {
              review_focus: reviewEditor.values(),
              human_approval_default: approvalToggle.checked,
            },
          );
          Object.assign(stage, updated);
          dirty = false;
          saveManifestBtn.hidden = true;
        } catch (err) {
          errorBox.hidden = false;
          errorBox.textContent = err.message || t("pipeSaveFailed");
        } finally {
          saveManifestBtn.disabled = false;
          saveManifestBtn.textContent = t("pipeSaveStage");
        }
      };
      return;
    }

    if (activeTab === "criteria") {
      const criteriaEditor = listEditor(stage.success_criteria, t("pipeCriteriaPlaceholder"));
      pane.append(
        el("p", { class: "lib-field-hint" }, t("pipeCriteriaHint")),
        criteriaEditor.host,
      );
      criteriaEditor.host.addEventListener("input", () => {
        saveManifestBtn.hidden = false;
      });
      saveManifestBtn.hidden = true;
      saveManifestBtn.textContent = t("pipeSaveStage");
      saveManifestBtn.onclick = async () => {
        saveManifestBtn.disabled = true;
        saveManifestBtn.textContent = t("pipeSaving");
        errorBox.hidden = true;
        try {
          const updated = await patchJSON(
            `/api/system/pipelines/${encodeURIComponent(pipelineId)}/stages/${encodeURIComponent(stage.name)}`,
            { success_criteria: criteriaEditor.values() },
          );
          Object.assign(stage, updated);
          saveManifestBtn.hidden = true;
        } catch (err) {
          errorBox.hidden = false;
          errorBox.textContent = err.message || t("pipeSaveFailed");
        } finally {
          saveManifestBtn.disabled = false;
          saveManifestBtn.textContent = t("pipeSaveStage");
        }
      };
    }
  }

  renderStageNav();
  await renderStageEditor();
}

window.addEventListener("popstate", () => {
  const id = pipelineIdFromPath();
  if (id) void renderConfig(id);
  else void renderList();
});

applyPreferences(readLocalPreferences());
const initialId = pipelineIdFromPath();
if (initialId) void renderConfig(initialId);
else void renderList();
