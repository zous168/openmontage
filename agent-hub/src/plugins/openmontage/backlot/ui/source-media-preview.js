/** Shared source / reference media preview (board + project settings). */

import { el, fmtDuration, mediaURL, takePinnedMedia, thumbURL } from "/ui/lib.js";
import { t } from "/ui/i18n.js";

/**
 * @param {string} projectId
 * @param {object|null|undefined} src
 * @param {{ compact?: boolean }} [opts]
 */
export function renderSourceMediaSection(projectId, src, opts = {}) {
  if (!src || !src.path) return null;

  const compact = Boolean(opts.compact);
  const title = src.kind === "reference" ? t("referenceMediaTitle") : t("sourceMediaTitle");
  const metaParts = [
    src.duration_seconds != null ? fmtDuration(src.duration_seconds) : null,
    src.resolution || null,
    src.format ? src.format.toUpperCase() : null,
  ].filter(Boolean);
  const meta = metaParts.length
    ? t("sourceMediaMeta", { dur: metaParts[0], res: metaParts[1] || "—", fmt: metaParts[2] || "—" })
    : src.path.split("/").pop();

  const sectionClass = compact ? "source-media source-media--compact" : "source-media";
  const section = el("section", { class: sectionClass });
  if (!opts.hideTitle) {
    section.append(el("div", { class: "section-title" }, title,
      el("span", { class: "meta" }, meta)));
  }

  if (!src.exists) {
    section.append(el("div", { class: "notice warn" }, t("sourceMissing"),
      el("div", { class: "meta", style: "margin-top:6px;font-family:var(--mono)" }, src.path)));
    return section;
  }

  const hero = el("div", { class: "render-hero source-hero" });
  const playbackPath = src.playback_path || (src.playable ? src.path : src.preview_path);

  if (playbackPath) {
    const url = mediaURL(projectId, playbackPath);
    let video = takePinnedMedia(url);
    if (!video) {
      video = el("video", {
        src: url,
        controls: "",
        preload: "metadata",
        playsinline: "",
        poster: src.poster ? thumbURL(projectId, src.poster, 720) : null,
      });
      video.addEventListener("click", () => { if (video.paused) video.play().catch(() => {}); });
    }
    hero.append(video);
  } else if (src.poster) {
    hero.append(el("img", {
      src: thumbURL(projectId, src.poster, 720),
      alt: "",
      loading: "lazy",
    }));
  } else {
    hero.append(el("div", { class: "empty", style: "padding:48px 24px" },
      el("div", { class: "big" }, src.format ? src.format.toUpperCase() : "VIDEO"),
      el("div", {}, src.path)));
  }
  section.append(hero);

  if (!src.playable && playbackPath && playbackPath !== src.path) {
    section.append(el("p", { class: "source-hint" },
      t("sourceBrowserPreview", { fmt: (src.codec || src.format || "源文件").toUpperCase() })));
  } else if (!src.playable && !playbackPath && src.format) {
    section.append(el("p", { class: "source-hint" },
      t("sourceNotPlayable", { fmt: src.format.toUpperCase() })));
  }

  if (src.summary) {
    section.append(el("p", { class: "source-summary" }, src.summary));
  }

  section.append(el("div", { class: "meta source-path" },
    `${t("sourcePath")}: ${src.path}`));

  return section;
}
