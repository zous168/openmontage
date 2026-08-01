import { staticFile } from "remotion";

/**
 * Resolve a media path for Remotion media components.
 *
 * NEVER returns file:// — headless Chrome blocks local file URLs during render.
 * OpenMontage passes --public-dir=<project_root> and relative paths in props;
 * absolute paths are stripped back to project-relative form when possible.
 */
export function resolveAsset(src: string): string {
  if (!src) {
    return src;
  }
  if (
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("data:")
  ) {
    return src;
  }

  let clean = src.replace(/^file:\/\/\/?/, "").replace(/\\/g, "/");

  // Absolute path (Windows drive or POSIX) → project-relative for staticFile().
  if (/^[A-Za-z]:\//.test(clean) || (clean.startsWith("/") && !clean.startsWith("//"))) {
    const projectsMatch = clean.match(/\/projects\/[^/]+\/(.+)$/i);
    if (projectsMatch) {
      return staticFile(projectsMatch[1]);
    }
    const assetsIdx = clean.indexOf("/assets/");
    if (assetsIdx >= 0) {
      return staticFile(clean.slice(assetsIdx + 1));
    }
    const basename = clean.split("/").pop();
    if (basename) {
      return staticFile(basename);
    }
  }

  // Already relative (e.g. assets/images/sc1.jpg)
  const relative = clean.startsWith("/") ? clean.slice(1) : clean;
  return staticFile(relative);
}
