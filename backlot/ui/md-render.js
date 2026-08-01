/** Lightweight Markdown → HTML for Backlot preview (offline, no deps). */

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(text) {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return out;
}

function isTableRow(line) {
  return /^\|.+\|$/.test(line.trim());
}

function parseTableRow(line) {
  return line.trim().slice(1, -1).split("|").map((c) => c.trim());
}

function isTableSep(line) {
  return /^\|[\s:|-]+\|$/.test(line.trim());
}

/**
 * @param {string} source
 * @returns {string}
 */
export function renderMarkdown(source) {
  if (!source) return "";
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^```/.test(line)) {
      const lang = line.slice(3).trim();
      i += 1;
      const block = [];
      while (i < lines.length && !/^```/.test(lines[i])) {
        block.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      const cls = lang ? ` class="language-${escapeHtml(lang)}"` : "";
      html.push(`<pre><code${cls}>${escapeHtml(block.join("\n"))}</code></pre>`);
      continue;
    }

    if (/^#{1,6}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      html.push(`<h${level}>${renderInline(line.replace(/^#+\s*/, ""))}</h${level}>`);
      i += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const block = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        block.push(lines[i].replace(/^>\s?/, ""));
        i += 1;
      }
      html.push(`<blockquote>${block.map((l) => `<p>${renderInline(l)}</p>`).join("")}</blockquote>`);
      continue;
    }

    if (/^(-{3,}|_{3,}|\*{3,})$/.test(line.trim())) {
      html.push("<hr>");
      i += 1;
      continue;
    }

    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = parseTableRow(line);
      i += 2;
      const body = [];
      while (i < lines.length && isTableRow(lines[i])) {
        body.push(parseTableRow(lines[i]));
        i += 1;
      }
      html.push("<table><thead><tr>");
      for (const cell of header) html.push(`<th>${renderInline(cell)}</th>`);
      html.push("</tr></thead><tbody>");
      for (const row of body) {
        html.push("<tr>");
        for (const cell of row) html.push(`<td>${renderInline(cell)}</td>`);
        html.push("</tr>");
      }
      html.push("</tbody></table>");
      continue;
    }

    if (/^[-*+]\s/.test(line)) {
      html.push("<ul>");
      while (i < lines.length && /^[-*+]\s/.test(lines[i])) {
        html.push(`<li>${renderInline(lines[i].replace(/^[-*+]\s/, ""))}</li>`);
        i += 1;
      }
      html.push("</ul>");
      continue;
    }

    if (/^\d+\.\s/.test(line)) {
      html.push("<ol>");
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        html.push(`<li>${renderInline(lines[i].replace(/^\d+\.\s/, ""))}</li>`);
        i += 1;
      }
      html.push("</ol>");
      continue;
    }

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const para = [];
    while (i < lines.length && lines[i].trim() && !/^#{1,6}\s/.test(lines[i])
      && !/^```/.test(lines[i]) && !/^>\s?/.test(lines[i])
      && !/^[-*+]\s/.test(lines[i]) && !/^\d+\.\s/.test(lines[i])
      && !isTableRow(lines[i])) {
      para.push(lines[i]);
      i += 1;
    }
    if (para.length) {
      html.push(`<p>${renderInline(para.join(" "))}</p>`);
    } else {
      i += 1;
    }
  }

  return html.join("\n");
}
