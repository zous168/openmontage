/** Schema-aligned pipeline manifest form — editable vs read-only fields. */

import { el } from "/ui/lib.js";
import { t } from "/ui/i18n.js";

function fmtValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? t("mfYes") : t("mfNo");
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function mfKey(key) {
  return String(key).replace(/\./g, "_");
}

function fieldLabel(key) {
  return t(`mf_${mfKey(key)}`) || key;
}

function enumLabel(key, opt) {
  const labelKey = `mf_enum_${mfKey(key)}_${opt}`;
  const label = t(labelKey);
  return label === labelKey ? opt : label;
}

function fieldHint(key, hint) {
  return hint || t(`mf_${mfKey(key)}_hint`) || null;
}

export function renderReadonlyField(key, value, hint) {
  const isMultiline = typeof value === "object" && value !== null && !Array.isArray(value);
  const display = isMultiline
    ? el("pre", { class: "mf-readonly-pre" }, fmtValue(value))
    : el("div", { class: "lib-field-readonly-value" }, fmtValue(value));
  const hintText = fieldHint(key, hint);
  return el("div", { class: "lib-field" },
    el("span", { class: "lib-field-label" }, fieldLabel(key)),
    display,
    hintText ? el("span", { class: "lib-field-hint" }, hintText) : null,
  );
}

function fieldShell(key, editable, body, hint) {
  const hintText = fieldHint(key, hint);
  const Tag = editable ? "label" : "div";
  return el(Tag, { class: "lib-field" },
    el("span", { class: "lib-field-label" }, fieldLabel(key)),
    body,
    hintText ? el("span", { class: "lib-field-hint" }, hintText) : null,
  );
}

function deriveStageSkillEntries(manifest) {
  const entries = [];
  const seen = new Set();
  const orch = String(manifest.orchestration?.skill || "").trim();
  if (orch && !seen.has(orch)) {
    seen.add(orch);
    entries.push({ label: "orchestration", skill: orch });
  }
  for (const stage of manifest.stages || []) {
    const skill = String(stage.skill || "").trim();
    if (!skill || seen.has(skill)) continue;
    seen.add(skill);
    entries.push({ label: stage.name || skill, skill });
  }
  return entries;
}

function pipelineLevelSkills(required, stageSkills) {
  const stageSet = new Set(stageSkills);
  return (required || []).filter((s) => s && !stageSet.has(s));
}

export function renderStageLegacySection(stage) {
  const legacy = [
    ["agent", stage.agent],
    ["preferred_tools", stage.preferred_tools],
    ["fallback_tools", stage.fallback_tools],
    ["required_tools", stage.required_tools],
    ["optional_tools", stage.optional_tools],
  ].filter(([, v]) => v && (Array.isArray(v) ? v.length : String(v).trim()));

  if (!legacy.length) return null;

  return el("section", { class: "mf-legacy-section" },
    el("h3", { class: "mf-section-title" }, t("mfStageLegacy")),
    el("p", { class: "lib-field-hint" }, t("mfStageLegacyHint")),
    ...legacy.map(([key, value]) => renderReadonlyField(key, value, t(`mf_${key}_hint`))),
  );
}

/**
 * @param {object} manifest
 * @param {{ onDirty?: () => void, listEditor?: Function, hints?: object }} opts
 * @returns {{ host: HTMLElement, collect: () => object }}
 */
export function buildPipelineManifestForm(manifest, { onDirty, listEditor, hints = {} } = {}) {
  const host = el("div", { class: "mf-manifest-form" });
  const controls = {};
  const markDirty = () => { if (onDirty) onDirty(); };

  function textInput(key, value, { multiline = false, readonly = false } = {}) {
    const node = multiline
      ? el("textarea", {
        class: "lib-field-input lib-field-textarea",
        rows: multiline ? "3" : "2",
        readonly: readonly ? "true" : null,
      }, value ?? "")
      : el("input", {
        class: "lib-field-input",
        type: "text",
        value: value ?? "",
        readonly: readonly ? "true" : null,
        spellcheck: "false",
      });
    if (!readonly) {
      node.addEventListener("input", markDirty);
    }
    controls[key] = () => (multiline ? node.value : node.value.trim());
    return node;
  }

  function numberInput(key, value) {
    const node = el("input", {
      class: "lib-field-input",
      type: "number",
      value: value ?? "",
      step: key.includes("budget") ? "0.01" : "1",
    });
    node.addEventListener("input", markDirty);
    controls[key] = () => {
      const raw = node.value.trim();
      if (!raw) return null;
      return key.includes("budget") ? Number(raw) : parseInt(raw, 10);
    };
    return node;
  }

  function selectInput(key, value, options) {
    const node = el("select", { class: "lib-field-input" },
      ...options.map((opt) => el("option", {
        value: opt,
        selected: value === opt ? "true" : null,
      }, enumLabel(key, opt))),
    );
    node.addEventListener("change", markDirty);
    controls[key] = () => node.value;
    return node;
  }

  function checkboxInput(key, value) {
    const node = el("input", { type: "checkbox", checked: value ? "true" : null });
    node.addEventListener("change", markDirty);
    controls[key] = () => node.checked;
    return el("label", { class: "lib-field pipe-hidden-field" },
      node,
      el("span", { class: "lib-field-label" }, fieldLabel(key)),
    );
  }

  function jsonArea(key, value) {
    const text = value && typeof value === "object" ? JSON.stringify(value, null, 2) : "";
    const node = el("textarea", {
      class: "lib-field-input lib-field-textarea mf-json-input",
      rows: "4",
      spellcheck: "false",
    }, text);
    node.addEventListener("input", markDirty);
    controls[key] = () => {
      const raw = node.value.trim();
      if (!raw) return null;
      return JSON.parse(raw);
    };
    return node;
  }

  // ── Root scalars ──
  host.append(el("section", { class: "mf-section" },
    el("h3", { class: "mf-section-title" }, t("mfSectionCore")),
    fieldShell("name", false, textInput("name", manifest.name || manifest.id, { readonly: true }), t("mf_name_hint")),
    fieldShell("version", true, textInput("version", manifest.version || "")),
    fieldShell("description", true, textInput("description", manifest.description || "", { multiline: true })),
    fieldShell("category", true, selectInput("category", manifest.category || "custom", [
      "talking_head", "generated", "hybrid", "screen_recording", "animation", "cinematic", "custom",
    ])),
    fieldShell("stability", true, selectInput("stability", manifest.stability || "beta", ["production", "beta"])),
    fieldShell("default_checkpoint_policy", true, selectInput(
      "default_checkpoint_policy",
      manifest.default_checkpoint_policy || "guided",
      ["guided", "manual_all", "auto_noncreative"],
    )),
  ));

  // ── required_skills (pipeline-level only; step skills merged on save) ──
  const stageSkillRefs = deriveStageSkillEntries(manifest).map((e) => e.skill);

  if (listEditor) {
    const pipelineSkills = pipelineLevelSkills(manifest.required_skills, stageSkillRefs);
    const skillsEd = listEditor(pipelineSkills, t("mfSkillPlaceholder"), hints.skills || []);
    skillsEd.host.addEventListener("input", markDirty);
    controls.required_skills = () => {
      const pipeline = skillsEd.values();
      const orchBlock = controls.orchestration ? controls.orchestration() : {};
      const stageRefs = deriveStageSkillEntries({
        ...manifest,
        orchestration: { ...(manifest.orchestration || {}), ...orchBlock },
      }).map((e) => e.skill);
      return [...new Set([...pipeline, ...stageRefs])];
    };
    host.append(el("section", { class: "mf-section" },
      el("h3", { class: "mf-section-title" }, t("mfSectionSkills")),
      fieldShell("required_skills", true, skillsEd.host, t("mf_required_skills_hint")),
    ));
  }

  // ── compatible_playbooks ──
  const cp = manifest.compatible_playbooks;
  const cpIsObject = cp && !Array.isArray(cp);
  if (cpIsObject && listEditor) {
    const recEd = listEditor(cp.recommended || [], t("mfPlaybookPlaceholder"));
    const alsoEd = listEditor(cp.also_works || [], t("mfPlaybookPlaceholder"));
    recEd.host.addEventListener("input", markDirty);
    alsoEd.host.addEventListener("input", markDirty);
    const customAllowed = el("input", {
      type: "checkbox",
      checked: cp.custom_allowed ? "true" : null,
    });
    customAllowed.addEventListener("change", markDirty);
    controls.compatible_playbooks = () => ({
      recommended: recEd.values(),
      also_works: alsoEd.values(),
      custom_allowed: customAllowed.checked,
    });
    host.append(el("section", { class: "mf-section" },
      el("h3", { class: "mf-section-title" }, t("mfSectionPlaybooks")),
      fieldShell("compatible_playbooks.recommended", true, recEd.host),
      fieldShell("compatible_playbooks.also_works", true, alsoEd.host),
      el("label", { class: "lib-field pipe-hidden-field" },
        customAllowed,
        el("span", { class: "lib-field-label" }, t("mf_compatible_playbooks_custom_allowed")),
      ),
    ));
  } else if (listEditor) {
    const cpEd = listEditor(Array.isArray(cp) ? cp : [], t("mfPlaybookPlaceholder"));
    cpEd.host.addEventListener("input", markDirty);
    controls.compatible_playbooks = () => cpEd.values();
    host.append(el("section", { class: "mf-section" },
      el("h3", { class: "mf-section-title" }, t("mfSectionPlaybooks")),
      fieldShell("compatible_playbooks", true, cpEd.host, t("mf_compatible_playbooks_hint")),
    ));
  }

  // ── reference_input ──
  const ref = manifest.reference_input || {};
  const refSupported = el("input", { type: "checkbox", checked: ref.supported ? "true" : null });
  refSupported.addEventListener("change", markDirty);
  const refDepth = selectInput("reference_input.analysis_depth", ref.analysis_depth || "standard", [
    "transcript_only", "standard", "deep",
  ]);
  let refToolsEd = null;
  if (listEditor) {
    refToolsEd = listEditor(
      ref.analysis_tools || [],
      t("pipeToolPlaceholder"),
      hints.tool_options?.length ? hints.tool_options : hints.tools || [],
    );
    refToolsEd.host.addEventListener("input", markDirty);
  }
  controls.reference_input = () => ({
    supported: refSupported.checked,
    analysis_depth: refDepth.value,
    analysis_tools: refToolsEd ? refToolsEd.values() : [],
  });
  host.append(el("section", { class: "mf-section" },
    el("h3", { class: "mf-section-title" }, t("mfSectionReference")),
    el("label", { class: "lib-field pipe-hidden-field" },
      refSupported,
      el("span", { class: "lib-field-label" }, t("mf_reference_input_supported")),
    ),
    fieldShell("reference_input.analysis_depth", true, refDepth),
    refToolsEd ? fieldShell("reference_input.analysis_tools", true, refToolsEd.host) : null,
  ));

  // ── orchestration ──
  const orch = manifest.orchestration || {};
  const orchMode = textInput("orchestration.mode", orch.mode || "");
  const orchSkill = textInput("orchestration.skill", orch.skill || "", { multiline: false });
  const orchBudget = numberInput("orchestration.budget_default_usd", orch.budget_default_usd);
  const orchRev = numberInput("orchestration.max_revisions_per_stage", orch.max_revisions_per_stage);
  const orchSend = numberInput("orchestration.max_send_backs", orch.max_send_backs);
  const orchWall = numberInput("orchestration.max_wall_time_minutes", orch.max_wall_time_minutes);
  controls.orchestration = () => {
    const out = {};
    const mode = orchMode.value.trim();
    const skill = orchSkill.value.trim();
    if (mode) out.mode = mode;
    if (skill) out.skill = skill;
    const readNum = (key) => controls[key]?.() ?? null;
    const budget = readNum("orchestration.budget_default_usd");
    if (budget !== null && !Number.isNaN(budget)) out.budget_default_usd = budget;
    for (const [k, key] of [
      ["max_revisions_per_stage", "orchestration.max_revisions_per_stage"],
      ["max_send_backs", "orchestration.max_send_backs"],
      ["max_wall_time_minutes", "orchestration.max_wall_time_minutes"],
    ]) {
      const v = readNum(key);
      if (v !== null && !Number.isNaN(v)) out[k] = v;
    }
    return out;
  };
  host.append(el("section", { class: "mf-section" },
    el("h3", { class: "mf-section-title" }, t("mfSectionOrchestration")),
    fieldShell("orchestration.mode", true, orchMode),
    fieldShell("orchestration.skill", true, orchSkill),
    fieldShell("orchestration.budget_default_usd", true, orchBudget),
    fieldShell("orchestration.max_revisions_per_stage", true, orchRev),
    fieldShell("orchestration.max_send_backs", true, orchSend),
    fieldShell("orchestration.max_wall_time_minutes", true, orchWall),
  ));

  // ── extensions ──
  const ext = manifest.extensions || {};
  const extKeys = ["custom_scripts", "custom_playbooks", "custom_skills", "custom_tools"];
  const extChecks = {};
  for (const k of extKeys) {
    extChecks[k] = el("input", {
      type: "checkbox",
      checked: ext[k] !== false ? "true" : null,
    });
    extChecks[k].addEventListener("change", markDirty);
  }
  controls.extensions = () => {
    const out = {};
    for (const k of extKeys) out[k] = extChecks[k].checked;
    return out;
  };
  host.append(el("section", { class: "mf-section" },
    el("h3", { class: "mf-section-title" }, t("mfSectionExtensions")),
    ...extKeys.map((k) => el("label", { class: "lib-field pipe-hidden-field" },
      extChecks[k],
      el("span", { class: "lib-field-label" }, t(`mf_extensions_${k}`) || k),
    )),
  ));

  // ── ui ──
  const ui = manifest.ui || {};
  const uiLabel = textInput("ui.label_zh", ui.label_zh || manifest.label_zh || "");
  const uiSummary = textInput("ui.summary_zh", ui.summary_zh || manifest.summary_zh || "", { multiline: true });
  const uiHidden = el("input", { type: "checkbox", checked: ui.hidden ? "true" : null });
  uiHidden.addEventListener("change", markDirty);
  const uiSkillDir = textInput("ui.skill_dir", ui.skill_dir || "");
  controls.ui = () => {
    const out = {};
    const lz = uiLabel.value.trim();
    const sz = uiSummary.value.trim();
    const sd = uiSkillDir.value.trim();
    if (lz) out.label_zh = lz;
    if (sz) out.summary_zh = sz;
    if (uiHidden.checked) out.hidden = true;
    if (sd) out.skill_dir = sd;
    return out;
  };
  host.append(el("section", { class: "mf-section" },
    el("h3", { class: "mf-section-title" }, t("mfSectionUi")),
    fieldShell("ui.label_zh", true, uiLabel),
    fieldShell("ui.summary_zh", true, uiSummary),
    el("label", { class: "lib-field pipe-hidden-field" },
      uiHidden,
      el("span", { class: "lib-field-label" }, t("mf_ui_hidden")),
    ),
    fieldShell("ui.skill_dir", true, uiSkillDir, t("mf_ui_skill_dir_hint")),
  ));

  // ── metadata (JSON) ──
  host.append(el("section", { class: "mf-section" },
    el("h3", { class: "mf-section-title" }, t("mfSectionMetadata")),
    fieldShell("metadata", true, jsonArea("metadata", manifest.metadata), t("mf_metadata_hint")),
  ));

  return {
    host,
    collect() {
      const payload = {};
      const scalarKeys = [
        "version", "description", "category", "stability",
        "default_checkpoint_policy", "required_skills", "compatible_playbooks", "metadata",
      ];
      for (const key of scalarKeys) {
        if (!controls[key]) continue;
        try {
          const val = controls[key]();
          if (val !== null && val !== undefined && val !== "") payload[key] = val;
        } catch {
          throw new Error(t("mfJsonInvalid", { field: key }));
        }
      }
      if (controls.orchestration) payload.orchestration = controls.orchestration();
      if (controls.extensions) payload.extensions = controls.extensions();
      if (controls.ui) payload.ui = controls.ui();
      if (controls.reference_input) payload.reference_input = controls.reference_input();
      return payload;
    },
  };
}
