import { describe, expect, it } from "vitest";

import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("escapes raw HTML instead of rendering it", () => {
    expect(renderMarkdown("<script>alert(1)</script>")).toBe(
      "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>",
    );
  });

  it("renders headings", () => {
    expect(renderMarkdown("# Titulo\n## Subtitulo")).toBe("<h3>Titulo</h3><h4>Subtitulo</h4>");
  });

  it("renders bold and italic", () => {
    expect(renderMarkdown("**fuerte** y *cursiva*")).toBe("<p><strong>fuerte</strong> y <em>cursiva</em></p>");
  });

  it("renders a bullet list as a single ul", () => {
    expect(renderMarkdown("- uno\n- dos")).toBe("<ul><li>uno</li><li>dos</li></ul>");
  });

  it("renders an http link", () => {
    expect(renderMarkdown("[Fabric](https://app.fabric.microsoft.com)")).toBe(
      '<p><a href="https://app.fabric.microsoft.com" target="_blank" rel="noopener noreferrer">Fabric</a></p>',
    );
  });

  it("refuses to render a javascript: link as a real link", () => {
    const html = renderMarkdown("[click](javascript:alert(1))");
    expect(html).not.toContain("<a ");
    expect(html).toContain("[click](javascript:alert(1))");
  });

  it("separates paragraphs on blank lines", () => {
    expect(renderMarkdown("primero\n\nsegundo")).toBe("<p>primero</p><p>segundo</p>");
  });
});
