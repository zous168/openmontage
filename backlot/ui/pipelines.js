/** Dedicated pipeline config — stages, review checklists, director skill prompts. */

import { el, getJSON, patchJSON, postJSON, putJSON, deleteJSON } from "/ui/lib.js";
import { t, stageLabel } from "/ui/i18n.js";
import { createMdEditor } from "/ui/md-editor.js";
import { renderLoading, showLoading } from "/ui/loading.js";
import { buildPipelineManifestForm, renderStageLegacySection } from "/ui/manifest-form.js";
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

function normalizeSuggestions(suggestions) {
  return (suggestions || []).map((s) => {
    if (s && typeof s === "object" && !Array.isArray(s)) {
      const value = String(s.value ?? s.name ?? "").trim();
      if (!value) return null;
      const label = String(s.label_zh ?? s.label ?? value).trim() || value;
      return { value, label };
    }
    const value = String(s ?? "").trim();
    if (!value) return null;
    return { value, label: value };
  }).filter(Boolean);
}

function attachSuggestionMenu(input, suggestions) {
  const options = normalizeSuggestions(suggestions);
  if (!options.length) return;

  let menu = null;
  const wrap = () => input.closest(".pipe-list-input-wrap");

  function ensureMenu() {
    if (menu) return menu;
    const host = wrap();
    if (!host) return null;
    menu = el("div", { class: "pipe-suggest-menu", hidden: "true" });
    host.append(menu);
    return menu;
  }

  function filterOptions() {
    const q = input.value.trim().toLowerCase();
    if (!q) return options.slice(0, 20);
    return options.filter((o) =>
      o.value.toLowerCase().includes(q) || o.label.toLowerCase().includes(q),
    ).slice(0, 20);
  }

  function renderMenu() {
    const m = ensureMenu();
    if (!m) return;
    const matches = filterOptions();
    m.innerHTML = "";
    if (!matches.length) {
      m.hidden = true;
      return;
    }
    for (const o of matches) {
      m.append(el("button", {
        type: "button",
        class: "pipe-suggest-item",
        onmousedown: (e) => {
          e.preventDefault();
          input.value = o.value;
          m.hidden = true;
          input.dispatchEvent(new Event("input", { bubbles: true }));
        },
      },
        el("span", { class: "pipe-suggest-label" }, o.label),
        o.label !== o.value ? el("code", { class: "pipe-suggest-value" }, o.value) : null,
      ));
    }
    m.hidden = false;
  }

  input.addEventListener("focus", renderMenu);
  input.addEventListener("input", renderMenu);
  input.addEventListener("blur", () => setTimeout(() => { if (menu) menu.hidden = true; }, 120));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menu) menu.hidden = true;
  });
}

function listEditor(items, placeholder, suggestions = []) {
  const host = el("div", { class: "pipe-list-editor" });
  const rows = [];

  function addRow(value = "") {
    const input = el("input", {
      class: "lib-field-input pipe-list-input",
      type: "text",
      value,
      placeholder,
      autocomplete: "off",
    });
    const removeBtn = el("button", {
      class: "pipe-list-remove",
      type: "button",
      title: t("pipeRemoveItem"),
    }, "×");
    const inputWrap = el("div", { class: "pipe-list-input-wrap" }, input);
    attachSuggestionMenu(input, suggestions);
    const row = el("div", { class: "pipe-list-row" }, inputWrap, removeBtn);
    removeBtn.addEventListener("click", () => {
      row.remove();
      rows.splice(rows.indexOf(input), 1);
    });
    rows.push(input);
    host.insertBefore(row, host.querySelector(".pipe-list-add"));
    return input;
  }

  host.append(el("button", {
    class: "pipe-list-add",
    type: "button",
  }, t("pipeAddItem")));

  host.addEventListener("click", (ev) => {
    if (ev.target.closest(".pipe-list-add")) addRow("");
  });

  for (const item of items || []) addRow(item);

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
  showLoading(app, t("pipeLoading"));

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
  showLoading(app, t("pipeLoading"));

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

  const MANIFEST_ID = "__manifest__";
  const stages = config.stages || [];
  const hints = config.editor_hints || { artifacts: [], tools: [], tool_options: [], skills: [] };
  const toolSuggestions = hints.tool_options?.length ? hints.tool_options : hints.tools || [];
  let manifestDoc = { ...(config.manifest || {}), id: config.id };
  let manifestDirty = false;
  let activeStage = MANIFEST_ID;
  let activeTab = "structure";
  let manifestForm = null;

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

  function renderEditor() {
    if (activeStage === MANIFEST_ID) renderManifestEditor();
    else void renderStageEditor();
  }

  function renderManifestEditor() {
    editorHost.innerHTML = "";
    editorHost.className = "pipe-stage-editor pipe-manifest-panel";
    manifestForm = buildPipelineManifestForm(manifestDoc, {
      listEditor,
      hints,
      onDirty: () => {
        manifestDirty = true;
        saveBtn.hidden = false;
      },
    });
    const saveBtn = el("button", {
      class: "lib-form-submit",
      type: "button",
      hidden: manifestDirty ? null : "true",
    }, t("pipeSaveManifestRoot"));
    editorHost.append(
      el("header", { class: "pipe-stage-header" },
        el("h2", { class: "pipe-stage-title" }, t("pipeViewManifest")),
        el("code", { class: "pipe-skill-path" }, config.manifest_path),
      ),
      manifestForm.host,
      el("div", { class: "lib-form-actions pipe-editor-actions" }, saveBtn),
    );
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = t("pipeSaving");
      errorBox.hidden = true;
      try {
        const payload = manifestForm.collect();
        const updated = await patchJSON(
          `/api/system/pipelines/${encodeURIComponent(pipelineId)}/manifest`,
          payload,
        );
        manifestDoc = { ...(updated.manifest || {}), id: updated.id };
        config.label_zh = updated.label_zh;
        config.summary_zh = updated.summary_zh;
        pageTitle.textContent = updated.label_zh || updated.id;
        pageLead.textContent = updated.summary_zh || updated.description || updated.id;
        if (updated.stages) {
          stages.splice(0, stages.length, ...updated.stages);
          if (activeStage !== MANIFEST_ID && !stages.some((s) => s.name === activeStage)) {
            activeStage = stages[0]?.name || MANIFEST_ID;
          }
        }
        manifestDirty = false;
        renderStageNav();
        renderManifestEditor();
      } catch (err) {
        errorBox.hidden = false;
        errorBox.textContent = err.message || t("pipeSaveFailed");
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = t("pipeSaveManifestRoot");
      }
    };
  }

  function renderStageNav() {
    stageNav.innerHTML = "";
    stageNav.append(el("button", {
      class: `pipe-stage-nav-item pipe-manifest-nav${activeStage === MANIFEST_ID ? " active" : ""}`,
      type: "button",
      onclick: () => {
        activeStage = MANIFEST_ID;
        renderStageNav();
        renderEditor();
      },
    },
      el("span", { class: "pipe-stage-nav-label" }, t("pipeViewManifest")),
      el("code", { class: "pipe-stage-nav-id" }, "manifest"),
    ));
    stageNav.append(el("div", { class: "pipe-stage-nav-divider" }, t("pipeViewStages")));
    const stagesList = el("div", { class: "pipe-stage-nav-stages" });
    for (let i = 0; i < stages.length; i++) {
      const stage = stages[i];
      const btn = el("button", {
        class: `pipe-stage-nav-item${stage.name === activeStage ? " active" : ""}`,
        type: "button",
        onclick: () => {
          activeStage = stage.name;
          activeTab = "structure";
          renderStageNav();
          renderEditor();
        },
      },
        el("span", { class: "pipe-stage-nav-label" }, stage.label_zh || stageLabel(stage.name) || stage.name),
        el("code", { class: "pipe-stage-nav-id" }, stage.name),
        !stage.skill_ok && stage.skill
          ? el("span", { class: "deps-badge deps-badge-bad" }, "!")
          : null,
      );
      stagesList.append(btn);
    }
    stageNav.append(stagesList);
    stageNav.append(el("button", {
      class: "pipe-stage-nav-add",
      type: "button",
      onclick: async () => {
        errorBox.hidden = true;
        let name = t("pipeNewStageName");
        let n = 2;
        while (stages.some((s) => s.name === name)) {
          name = `${t("pipeNewStageName")}_${n}`;
          n += 1;
        }
        try {
          const created = await postJSON(
            `/api/system/pipelines/${encodeURIComponent(pipelineId)}/stages`,
            {
              name,
              insert_after: activeStage || undefined,
              checkpoint_required: true,
            },
          );
          created.label_zh = created.label_zh || created.name;
          const idx = stages.findIndex((s) => s.name === activeStage);
          if (idx >= 0) stages.splice(idx + 1, 0, created);
          else stages.push(created);
          activeStage = created.name;
          renderStageNav();
          await renderStageEditor();
        } catch (err) {
          errorBox.hidden = false;
          errorBox.textContent = err.message || t("pipeSaveFailed");
        }
      },
    }, t("pipeAddStage")));
  }

  async function renderStageEditor() {
    editorHost.className = "pipe-stage-editor";
    const stage = stages.find((s) => s.name === activeStage);
    if (!stage) {
      editorHost.innerHTML = "";
      editorHost.append(el("p", { class: "deps-idle-lead" }, t("pipeNoStage")));
      return;
    }

    editorHost.innerHTML = "";
    if (activeTab === "outputs") activeTab = "structure";
    const tabBar = el("div", { class: "sys-tabs pipe-editor-tabs", role: "tablist" });
    const tabs = [
      { id: "structure", label: t("pipeTabStructure") },
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
        el("h2", { class: "pipe-stage-title" }, stage.label_zh || stageLabel(stage.name) || stage.name),
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

    if (activeTab === "structure") {
      const stageIdx = stages.findIndex((s) => s.name === activeStage);
      const nameInput = el("input", {
        class: "lib-field-input",
        type: "text",
        value: stage.name,
        spellcheck: "false",
      });
      const skillListId = `pipe-skill-${stage.name}`;
      const skillInput = el("input", {
        class: "lib-field-input",
        type: "text",
        value: stage.skill || "",
        spellcheck: "false",
        autocomplete: "off",
        list: skillListId,
      });
      const skillDatalist = el("datalist", { id: skillListId },
        ...(hints.skills || []).map((s) => el("option", { value: s })),
      );
      const checkpointToggle = el("input", {
        type: "checkbox",
        checked: stage.checkpoint_required !== false ? "true" : null,
      });
      const producesEditor = listEditor(
        stage.produces,
        t("pipeArtifactPlaceholder"),
        hints.artifacts || [],
      );
      const requiredEditor = listEditor(
        stage.required_artifacts_in,
        t("pipeArtifactPlaceholder"),
        hints.artifacts || [],
      );
      const optionalEditor = listEditor(
        stage.optional_artifacts_in,
        t("pipeArtifactPlaceholder"),
        hints.artifacts || [],
      );
      const toolsEditor = listEditor(
        stage.tools_available,
        t("pipeToolPlaceholder"),
        toolSuggestions,
      );
      const subStagesRaw = stage.sub_stages?.length
        ? JSON.stringify(stage.sub_stages, null, 2)
        : "";
      const subStagesInput = el("textarea", {
        class: "lib-field-input lib-field-textarea mf-json-input",
        rows: "6",
        spellcheck: "false",
        placeholder: "[]",
      }, subStagesRaw);
      const approvalToggle = el("input", {
        type: "checkbox",
        checked: stage.human_approval_default ? "true" : null,
      });

      const legacySection = renderStageLegacySection(stage);

      pane.append(
        el("p", { class: "lib-field-hint" }, t("pipeStructureHint")),
        el("label", { class: "lib-field" },
          el("span", { class: "lib-field-label" }, t("pipeStageId")),
          nameInput,
          el("span", { class: "lib-field-hint" }, t("pipeStageIdHint")),
        ),
        el("label", { class: "lib-field" },
          el("span", { class: "lib-field-label" }, t("pipeSkillPath")),
          el("div", { class: "pipe-list-input-wrap" }, skillInput, skillDatalist),
          el("span", { class: "lib-field-hint" }, t("pipeSkillPathHint")),
          stage.skill && !stage.skill_ok
            ? el("span", { class: "notice warn pipe-skill-warn" }, t("pipeSkillMissing"))
            : null,
        ),
        el("label", { class: "lib-field pipe-hidden-field" },
          checkpointToggle,
          el("span", { class: "lib-field-label" }, t("pipeCheckpointRequired")),
        ),
        el("div", { class: "lib-field" },
          el("span", { class: "lib-field-label" }, t("pipeStageProduces")),
          producesEditor.host,
        ),
        el("div", { class: "lib-field" },
          el("span", { class: "lib-field-label" }, t("pipeRequiredArtifacts")),
          requiredEditor.host,
        ),
        el("div", { class: "lib-field" },
          el("span", { class: "lib-field-label" }, t("pipeOptionalArtifacts")),
          optionalEditor.host,
        ),
        el("div", { class: "lib-field" },
          el("span", { class: "lib-field-label" }, t("pipeToolsAvailable")),
          toolsEditor.host,
        ),
        el("label", { class: "lib-field pipe-hidden-field" },
          approvalToggle,
          el("span", { class: "lib-field-label" }, t("pipeApprovalDefault")),
        ),
        el("div", { class: "lib-field" },
          el("span", { class: "lib-field-label" }, t("pipeSubStages")),
          subStagesInput,
          el("span", { class: "lib-field-hint" }, t("mf_sub_stages_hint")),
        ),
        ...(legacySection ? [legacySection] : []),
        el("div", { class: "pipe-stage-actions" },
          el("button", {
            class: "lib-form-cancel pipe-move-btn",
            type: "button",
            disabled: stageIdx <= 0 ? "true" : null,
            onclick: async () => {
              if (stageIdx <= 0) return;
              const order = stages.map((s) => s.name);
              [order[stageIdx - 1], order[stageIdx]] = [order[stageIdx], order[stageIdx - 1]];
              try {
                const refreshed = await putJSON(
                  `/api/system/pipelines/${encodeURIComponent(pipelineId)}/stages/order`,
                  { stage_names: order },
                );
                stages.splice(0, stages.length, ...(refreshed.stages || []));
                renderStageNav();
                await renderStageEditor();
              } catch (err) {
                errorBox.hidden = false;
                errorBox.textContent = err.message || t("pipeSaveFailed");
              }
            },
          }, t("pipeMoveUp")),
          el("button", {
            class: "lib-form-cancel pipe-move-btn",
            type: "button",
            disabled: stageIdx < 0 || stageIdx >= stages.length - 1 ? "true" : null,
            onclick: async () => {
              if (stageIdx < 0 || stageIdx >= stages.length - 1) return;
              const order = stages.map((s) => s.name);
              [order[stageIdx], order[stageIdx + 1]] = [order[stageIdx + 1], order[stageIdx]];
              try {
                const refreshed = await putJSON(
                  `/api/system/pipelines/${encodeURIComponent(pipelineId)}/stages/order`,
                  { stage_names: order },
                );
                stages.splice(0, stages.length, ...(refreshed.stages || []));
                renderStageNav();
                await renderStageEditor();
              } catch (err) {
                errorBox.hidden = false;
                errorBox.textContent = err.message || t("pipeSaveFailed");
              }
            },
          }, t("pipeMoveDown")),
          stages.length > 1
            ? el("button", {
              class: "lib-form-cancel pipe-delete-stage",
              type: "button",
              onclick: async () => {
                if (!window.confirm(t("pipeDeleteStageConfirm"))) return;
                try {
                  await deleteJSON(
                    `/api/system/pipelines/${encodeURIComponent(pipelineId)}/stages/${encodeURIComponent(stage.name)}`,
                  );
                  stages.splice(stageIdx, 1);
                  activeStage = stages[Math.min(stageIdx, stages.length - 1)]?.name || MANIFEST_ID;
                  renderStageNav();
                  await renderStageEditor();
                } catch (err) {
                  errorBox.hidden = false;
                  errorBox.textContent = err.message || t("pipeSaveFailed");
                }
              },
            }, t("pipeDeleteStage"))
            : null,
        ),
      );

      const markDirty = () => {
        saveManifestBtn.hidden = false;
        saveManifestBtn.textContent = t("pipeSaveStructure");
      };
      [nameInput, skillInput, checkpointToggle, approvalToggle, subStagesInput].forEach((node) => {
        node.addEventListener("input", markDirty);
        node.addEventListener("change", markDirty);
      });
      [producesEditor, requiredEditor, optionalEditor, toolsEditor].forEach((ed) => {
        ed.host.addEventListener("input", markDirty);
      });

      saveManifestBtn.hidden = true;
      saveManifestBtn.textContent = t("pipeSaveStructure");
      saveManifestBtn.onclick = async () => {
        saveManifestBtn.disabled = true;
        saveManifestBtn.textContent = t("pipeSaving");
        errorBox.hidden = true;
        const payload = {
          produces: producesEditor.values(),
          required_artifacts_in: requiredEditor.values(),
          optional_artifacts_in: optionalEditor.values(),
          tools_available: toolsEditor.values(),
          checkpoint_required: checkpointToggle.checked,
          human_approval_default: approvalToggle.checked,
          skill: skillInput.value.trim(),
        };
        const subRaw = subStagesInput.value.trim();
        if (subRaw) {
          try {
            const parsed = JSON.parse(subRaw);
            if (!Array.isArray(parsed)) throw new Error("array");
            payload.sub_stages = parsed;
          } catch {
            errorBox.hidden = false;
            errorBox.textContent = t("mfJsonInvalid", { field: "sub_stages" });
            saveManifestBtn.disabled = false;
            saveManifestBtn.textContent = t("pipeSaveStructure");
            return;
          }
        } else {
          payload.sub_stages = [];
        }
        const newName = nameInput.value.trim();
        if (newName && newName !== stage.name) payload.new_name = newName;
        try {
          const updated = await patchJSON(
            `/api/system/pipelines/${encodeURIComponent(pipelineId)}/stages/${encodeURIComponent(stage.name)}`,
            payload,
          );
          Object.assign(stage, updated);
          if (updated.name !== activeStage) activeStage = updated.name;
          renderStageNav();
          saveManifestBtn.hidden = true;
        } catch (err) {
          errorBox.hidden = false;
          errorBox.textContent = err.message || t("pipeSaveFailed");
        } finally {
          saveManifestBtn.disabled = false;
          saveManifestBtn.textContent = t("pipeSaveStructure");
        }
      };
      return;
    }

    if (activeTab === "prompt") {
      pane.append(el("p", { class: "lib-field-hint pipe-prompt-hint" }, t("pipePromptHint")));
      if (!stage.skill) {
        pane.append(el("p", { class: "notice warn" }, t("pipeNoSkill")));
        return;
      }
      pane.append(renderLoading(t("pipeLoadingPrompt"), { compact: true, block: true }));
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
      const mdEditor = createMdEditor({
        value: skillData.content || "",
        placeholder: t("mdEditorPlaceholder"),
        onChange: () => {
          saveSkillBtn.hidden = false;
        },
      });
      pane.append(mdEditor.host);
      saveSkillBtn.hidden = true;
      saveSkillBtn.onclick = async () => {
        saveSkillBtn.disabled = true;
        saveSkillBtn.textContent = t("pipeSaving");
        errorBox.hidden = true;
        try {
          await patchJSON(`/api/system/skills/${encodeURIComponent(stage.skill)}`, {
            content: mdEditor.getValue(),
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
  renderEditor();
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
