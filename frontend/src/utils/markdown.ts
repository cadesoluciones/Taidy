/**
 * Small, dependency-free Markdown-subset -> safe HTML renderer for the
 * governance catalog's long description field. There's no markdown library
 * in package.json and this project's established bias is against adding a
 * new npm dependency for something this narrow (same call made for
 * drag-and-drop reordering, which uses native HTML5 DnD instead of a lib).
 *
 * Safety: the raw input is HTML-escaped FIRST, so any literal `<script>`
 * etc. the user types becomes inert text. Only afterwards do a small
 * whitelist of transforms (headings, bold, italic, bullet lists, links)
 * turn parts of that already-escaped text back into real tags -- there is
 * no path from user input to an unescaped attribute or tag name. Links are
 * further restricted to http(s)/mailto schemes to block `javascript:`.
 */

const ALLOWED_LINK_SCHEMES = ["http://", "https://", "mailto:"];

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(escapedText: string): string {
  let html = escapedText;
  // Bold before italic so **x** isn't first read as italic-italic.
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, text: string, url: string) => {
    const isAllowed = ALLOWED_LINK_SCHEMES.some((scheme) => url.toLowerCase().startsWith(scheme));
    if (!isAllowed) return match;
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  });
  return html;
}

export function renderMarkdown(source: string): string {
  const lines = escapeHtml(source).split("\n");
  const blocks: string[] = [];
  let listItems: string[] = [];

  function flushList() {
    if (listItems.length > 0) {
      blocks.push(`<ul>${listItems.map((li) => `<li>${renderInline(li)}</li>`).join("")}</ul>`);
      listItems = [];
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();
    const heading2 = /^##\s+(.*)$/.exec(trimmed);
    const heading1 = /^#\s+(.*)$/.exec(trimmed);
    const bullet = /^[-*]\s+(.*)$/.exec(trimmed);

    if (heading2) {
      flushList();
      blocks.push(`<h4>${renderInline(heading2[1] ?? "")}</h4>`);
    } else if (heading1) {
      flushList();
      blocks.push(`<h3>${renderInline(heading1[1] ?? "")}</h3>`);
    } else if (bullet) {
      listItems.push(bullet[1] ?? "");
    } else if (trimmed === "") {
      flushList();
    } else {
      flushList();
      blocks.push(`<p>${renderInline(trimmed)}</p>`);
    }
  }
  flushList();
  return blocks.join("");
}
