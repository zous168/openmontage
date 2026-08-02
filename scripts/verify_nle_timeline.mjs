/**
 * Verify Backlot NLE mirrors Remotion Studio composition tree.
 * Usage: node scripts/verify_nle_timeline.mjs [project_id]
 */
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const projectId = process.argv[2] || "my-copy-01";
const projectDir = path.join(ROOT, "projects", projectId);

function loadJson(rel) {
  const file = path.join(projectDir, rel);
  if (!fs.existsSync(file)) throw new Error(`Missing ${file}`);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function shortText(value, limit = 180) {
  const text = String(value || "").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1))}…`;
}

function editUsesAbsoluteTimeline(artifact) {
  const rt = artifact?.render_runtime || "ffmpeg";
  return rt === "remotion" || rt === "hyperframes";
}

function resolveCompositionProps(artifact) {
  const overlays = (artifact.overlays?.length)
    ? artifact.overlays
    : (artifact.metadata?.remotion_overlays || []);
  const captions = (artifact.captions?.length)
    ? artifact.captions
    : (artifact.metadata?.remotion_captions || []);
  return {
    cuts: artifact.cuts || [],
    overlays,
    captions,
    audio: artifact.audio || {},
    render_runtime: artifact.render_runtime || "ffmpeg",
  };
}

function overlayTiming(overlay) {
  const start = Number(overlay?.in_seconds ?? overlay?.start_seconds) || 0;
  const endRaw = overlay?.out_seconds ?? overlay?.end_seconds;
  const end = Number.isFinite(Number(endRaw)) ? Number(endRaw) : start;
  return { start, end, duration: Math.max(0, end - start) };
}

function cutSequenceName(cut) {
  const file = String(cut?.source || "").split("/").pop() || cut?.source || "";
  if (cut?.id && cut?.reason) return `${cut.id} · ${cut.reason}`;
  if (cut?.id && file) return `${cut.id} · ${file}`;
  return cut?.id || file || "cut";
}

function cutDisplayReason(state, cut) {
  if (cut?.reason) return cut.reason;
  const source = String(cut?.source || "");
  const scenes = state?.scene_plan?.scenes || [];
  const scene = scenes.find(
    (sc) => source === sc.id || source === `img_${sc.id}` || source.includes(sc.id),
  );
  if (!scene) return "";
  const sections = state?.script?.sections || [];
  const sec = sections.find((item) => item.id === scene.script_section_id);
  if (sec?.label) return `${scene.id} · ${sec.label}`;
  return scene.id || "";
}

function findScriptSectionAtTime(sections, time) {
  return sections.find((sec) => {
    const start = Number(sec.start_seconds) || 0;
    const endRaw = Number(sec.end_seconds);
    const end = Number.isFinite(endRaw) && endRaw > start ? endRaw : start + 999;
    return time >= start && time < end;
  });
}

function overlayNodeLabel(overlay, clipMeta, scriptSections) {
  const start = Number(overlay.in_seconds ?? overlay.start_seconds) || 0;
  const sec = findScriptSectionAtTime(scriptSections, start);
  if (sec?.label) return sec.label;
  const clip = clipMeta.find((item) => Math.abs(item.start - start) < 0.08);
  if (clip?.cut?.reason) return clip.cut.reason;
  const text = overlay.text || "";
  if (overlay.type === "section_title" && text.length <= 24) return text;
  return overlay.type || shortText(text, 12) || `overlay-${Math.round(start)}s`;
}

function overlaySequenceName(overlay, index) {
  if (overlay?.text) return overlay.text;
  return overlay?.type || `overlay-${index + 1}`;
}

function buildCaptionPages(captions, wordsPerPage = 6) {
  const pages = [];
  for (let index = 0; index < captions.length; index += wordsPerPage) {
    const pageWords = captions.slice(index, index + wordsPerPage);
    if (!pageWords.length) continue;
    pages.push({
      words: pageWords,
      startMs: Number(pageWords[0].startMs) || 0,
      endMs: Number(pageWords[pageWords.length - 1].endMs) || 0,
      preview: pageWords.map((w) => w.word || "").join("").slice(0, 12),
    });
  }
  return pages;
}

function captionPageTiming(page, pages, pageIndex, durationSeconds) {
  const start = Math.max(0, page.startMs / 1000);
  let end = pageIndex + 1 < pages.length
    ? Math.max(start, pages[pageIndex + 1].startMs / 1000)
    : Math.max(start, page.endMs / 1000 + 0.5);
  end = Math.min(end, durationSeconds);
  return { start, end, duration: Math.max(0, end - start) };
}

function editCutTimelineDuration(cut, artifact) {
  const raw = Math.max(0, (Number(cut.out_seconds) || 0) - (Number(cut.in_seconds) || 0));
  if (editUsesAbsoluteTimeline(artifact)) return raw;
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

function compositionDurationSeconds(artifact, clipMeta) {
  const cuts = artifact?.cuts || [];
  if (editUsesAbsoluteTimeline(artifact)) {
    if (!cuts.length) return 0;
    return Math.max(...cuts.map((cut) => Number(cut.out_seconds) || 0)) + 1;
  }
  return clipMeta.reduce((sum, clip) => sum + clip.duration, 0);
}

function buildNleCaptionTracksFromScript(state, totalSeconds) {
  const empty = { summary: [], detail: [] };
  if (!totalSeconds) return empty;
  const sections = (state?.script?.sections || []).filter((sec) => sec.text);
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

function buildCompositionTimeline(artifact, state) {
  const props = resolveCompositionProps(artifact);
  const clipMeta = buildEditClipMeta(props.cuts, artifact);
  const durationSeconds = compositionDurationSeconds(artifact, clipMeta);
  const absolute = editUsesAbsoluteTimeline(artifact);
  const scriptSections = state?.script?.sections || [];

  const overlayNodes = (props.overlays || [])
    .map((overlay, index) => {
      const { start, end, duration } = overlayTiming(overlay);
      if (duration <= 0) return null;
      const fullText = overlaySequenceName(overlay, index);
      const shortLabel = overlayNodeLabel(overlay, clipMeta, scriptSections) || fullText;
      return {
        track: "overlay",
        index,
        label: shortLabel,
        preview: fullText,
        start,
        duration,
      };
    })
    .filter(Boolean);

  const layers = [];
  layers.push({
    id: "cuts",
    kind: "sequence",
    nodes: clipMeta.map(({ cut, index, start, duration }) => {
      const reason = cutDisplayReason(state, cut);
      const displayCut = reason && !cut.reason ? { ...cut, reason } : cut;
      return { label: cutSequenceName(displayCut), children: [] };
    }),
  });

  if (overlayNodes.length) {
    layers.push({ id: "overlays", kind: "overlay", nodes: overlayNodes });
  }

  if (absolute) {
    const captionTracks = buildNleCaptionTracksFromScript(state, durationSeconds);
    if (captionTracks.summary.length && !overlayNodes.length) {
      layers.push({
        id: "script-captions-summary",
        kind: "script-caption",
        nodes: captionTracks.summary.map((item, index) => ({
          label: item.label,
          index,
        })),
      });
      layers.push({
        id: "script-captions-detail",
        kind: "script-caption",
        nodes: captionTracks.detail.map((item, index) => ({
          label: shortText(item.text, 48),
          index,
        })),
      });
    }
  }

  const captions = props.captions || [];
  if (absolute && captions.length && captions[0]?.startMs != null && !overlayNodes.length) {
    const pages = buildCaptionPages(captions, 1);
    layers.push({
      id: "captions",
      kind: "caption",
      nodes: pages.map((page, pageIndex) => {
        const { duration } = captionPageTiming(page, pages, pageIndex, durationSeconds);
        const preview = page.preview || "";
        return {
          label: shortText(preview, 16) || "caption",
          preview,
          duration,
        };
      }).filter((n) => n.duration > 0),
    });
  }

  return { durationSeconds, layers, absolute, overlayNodes, props };
}

function expandLayersForStaircase(layers, absolute) {
  if (!absolute) return layers;
  const expanded = [];
  for (const layer of layers) {
    if (layer.kind === "sequence") {
      for (const node of layer.nodes) {
        expanded.push({ ...layer, trackLabel: node.label, nodes: [node], staircase: true });
      }
      continue;
    }
    if (layer.kind === "overlay" || layer.kind === "caption" || layer.kind === "script-caption") {
      for (const node of layer.nodes) {
        expanded.push({ ...layer, trackLabel: node.label, preview: node.preview, nodes: [node] });
      }
      continue;
    }
    expanded.push(layer);
  }
  return expanded;
}

function assert(cond, msg) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
}

function main() {
  const artifact = loadJson("artifacts/edit_decisions.json");
  const script = loadJson("artifacts/script.json");
  const scenePlan = loadJson("artifacts/scene_plan.json");
  const state = { script, scene_plan: scenePlan };
  const composition = buildCompositionTimeline(artifact, state);
  const displayLayers = expandLayersForStaircase(composition.layers, composition.absolute);

  console.log(`\n=== NLE / Remotion tree verify: ${projectId} ===`);
  console.log(`runtime=${artifact.render_runtime} duration=${composition.durationSeconds.toFixed(2)}s`);
  console.log("\nDisplay rows (top → bottom):");
  for (const layer of displayLayers) {
    const tags = [
      layer.kind,
      layer.staircase ? "staircase" : null,
    ].filter(Boolean).join(", ");
    console.log(`  • ${layer.trackLabel || layer.id} [${tags}]`);
  }

  const layerIds = composition.layers.map((l) => l.id);
  assert(composition.absolute, "hyperframes/remotion uses absolute timeline");
  assert(layerIds.includes("cuts"), "cuts layer present");
  assert(layerIds.includes("overlays"), "overlay layer present");
  assert(!layerIds.includes("captions"), "no duplicate caption layer when overlays present");
  assert(!layerIds.includes("script-captions-summary"), "no duplicate script caption rows when overlays present");

  const cutLayer = composition.layers.find((l) => l.id === "cuts");
  assert(cutLayer.nodes[0].label.includes("Hook"), `cut label includes Hook, got ${cutLayer.nodes[0].label}`);

  const overlayLabels = composition.layers.find((l) => l.id === "overlays").nodes.map((n) => n.label);
  assert(overlayLabels[0] === "Hook", `first overlay is Hook, got ${overlayLabels[0]}`);
  assert(overlayLabels.length === 6, `six overlay rows, got ${overlayLabels.length}`);

  const overlayRows = displayLayers.filter((l) => l.kind === "overlay");
  const captionRows = displayLayers.filter((l) => l.kind === "caption");
  const scriptCaptionRows = displayLayers.filter((l) => l.kind === "script-caption");

  assert(overlayRows.length === 6, "one overlay row per burn-in cue");
  assert(captionRows.length === 0, "no duplicate remotion caption rows");
  assert(scriptCaptionRows.length === 0, "no duplicate script caption rows");

  console.log("\n✓ Composition tree has single overlay text track set\n");
}

try {
  main();
} catch (err) {
  console.error(err.message || err);
  process.exit(1);
}
