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

function cutMediaChild(cut) {
  const source = String(cut?.source || "");
  const base = source.split("/").pop() || source;
  if (!base) return null;
  const ext = base.includes(".") ? base.split(".").pop().toLowerCase() : "";
  if (["jpg", "jpeg", "png", "webp", "gif"].includes(ext)) {
    return { track: "media", kind: "image", label: `<Img> ${base}`, data: cut };
  }
  return null;
}

function buildCaptionPages(captions, wordsPerPage = 6) {
  const pages = [];
  for (let index = 0; index < captions.length; index += wordsPerPage) {
    const pageWords = captions.slice(index, index + wordsPerPage);
    if (!pageWords.length) continue;
    pages.push({
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

function overlaySequenceName(overlay, index) {
  if (overlay?.text) return overlay.text;
  return overlay?.type || `overlay-${index + 1}`;
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

function buildCompositionTimeline(artifact) {
  const props = resolveCompositionProps(artifact);
  const clipMeta = buildEditClipMeta(props.cuts, artifact);
  const durationSeconds = compositionDurationSeconds(artifact, clipMeta);
  const absolute = editUsesAbsoluteTimeline(artifact);

  const overlayNodes = (props.overlays || [])
    .map((overlay, index) => {
      const { start, end, duration } = overlayTiming(overlay);
      if (duration <= 0) return null;
      return {
        track: "overlay",
        index,
        label: overlaySequenceName(overlay, index),
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
      const child = cutMediaChild(cut);
      return {
        label: cutSequenceName(cut),
        children: child ? [child.label] : [],
      };
    }),
  });

  if (overlayNodes.length) {
    layers.push({ id: "overlays", kind: "overlay", nodes: overlayNodes });
  }

  const captions = props.captions || [];
  if (absolute && captions.length && captions[0]?.startMs != null) {
    const pages = buildCaptionPages(captions, 6);
    layers.push({
      id: "captions",
      kind: "caption",
      nodes: pages.map((page, pageIndex) => {
        const { duration } = captionPageTiming(page, pages, pageIndex, durationSeconds);
        const preview = page.preview || "";
        return {
          label: "caption",
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
        for (const childLabel of node.children || []) {
          expanded.push({ kind: "media", trackLabel: childLabel, nested: true, nodes: [{}] });
        }
      }
      continue;
    }
    if (layer.kind === "overlay" || layer.kind === "caption") {
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
  const composition = buildCompositionTimeline(artifact);
  const displayLayers = expandLayersForStaircase(composition.layers, composition.absolute);

  console.log(`\n=== NLE / Remotion tree verify: ${projectId} ===`);
  console.log(`runtime=${artifact.render_runtime} duration=${composition.durationSeconds.toFixed(2)}s`);
  console.log("\nDisplay rows (top → bottom):");
  for (const layer of displayLayers) {
    const tags = [
      layer.kind,
      layer.staircase ? "staircase" : null,
      layer.nested ? "nested" : null,
    ].filter(Boolean).join(", ");
    console.log(`  • ${layer.trackLabel || layer.id} [${tags}]`);
  }

  const layerIds = composition.layers.map((l) => l.id);
  assert(composition.absolute, "remotion project uses absolute timeline");
  assert(layerIds.includes("cuts"), "cuts layer present");
  assert(layerIds.includes("overlays"), "overlay layer present (Remotion overlays[])");
  assert(layerIds.includes("captions"), "caption pages layer present");

  const cutLayer = composition.layers.find((l) => l.id === "cuts");
  assert(cutLayer.nodes[0].label === "c1 · Hook", `cut label uses reason, got ${cutLayer.nodes[0].label}`);
  assert(cutLayer.nodes[0].children[0] === "<Img> sc1.jpg", "cut has nested Img child");

  const overlayLabels = composition.layers.find((l) => l.id === "overlays").nodes.map((n) => n.label);
  assert(overlayLabels[0] === "Hook", `first overlay is Hook, got ${overlayLabels[0]}`);

  const captionLayer = composition.layers.find((l) => l.id === "captions");
  assert(captionLayer.nodes.length >= 8, `caption pages expanded (~10), got ${captionLayer.nodes.length}`);
  assert(captionLayer.nodes[0].label === "caption", "caption row label is type only");
  assert(captionLayer.nodes[0].preview, "caption preview lives on node.preview");

  const sequenceRows = displayLayers.filter((l) => l.kind === "sequence" && l.staircase);
  const mediaRows = displayLayers.filter((l) => l.kind === "media");
  const overlayRows = displayLayers.filter((l) => l.kind === "overlay");
  const captionRows = displayLayers.filter((l) => l.kind === "caption");

  assert(sequenceRows.length === artifact.cuts.length, "one Sequence row per cut");
  assert(mediaRows.length === artifact.cuts.length, "one Img row per image cut");
  assert(overlayRows.length === composition.overlayNodes.length, "one overlay row each");
  assert(captionRows.length === captionLayer.nodes.length, "one caption page row each");

  console.log("\n✓ Composition tree matches Remotion Studio structure\n");
}

try {
  main();
} catch (err) {
  console.error(err.message || err);
  process.exit(1);
}
