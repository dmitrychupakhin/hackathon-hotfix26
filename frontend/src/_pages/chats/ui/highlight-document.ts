/** Highlight only a unique visible occurrence. Canonical offsets are checked separately. */
export function highlightDocument(
  root: HTMLElement,
  quote: string,
  options: { scroll?: boolean; align?: ScrollLogicalPosition } = {},
): boolean {
  const nodes: Text[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode())
    nodes.push(node as Text);
  const source = nodes.map((node) => node.data).join("");
  const normalize = (value: string) => value.replace(/\s+/gu, " ").trim();
  const needle = normalize(quote);
  if (!needle) return false;
  // Keep a map into the original text while folding whitespace.
  let folded = "";
  const offsets: number[] = [];
  for (let i = 0; i < source.length; i++) {
    if (/\s/u.test(source[i])) {
      if (!folded.endsWith(" ")) {
        folded += " ";
        offsets.push(i);
      }
    } else {
      folded += source[i];
      offsets.push(i);
    }
  }
  const index = folded.indexOf(needle);
  if (index < 0 || folded.indexOf(needle, index + 1) !== -1) return false;
  const start = offsets[index],
    end = offsets[index + needle.length - 1] + 1;
  let cursor = 0;
  let first: HTMLElement | undefined;
  for (const node of nodes) {
    const from = Math.max(0, start - cursor),
      to = Math.min(node.length, end - cursor);
    cursor += node.length;
    if (to <= from) continue;
    const range = document.createRange();
    range.setStart(node, from);
    range.setEnd(node, to);
    const mark = document.createElement("mark");
    // PDF text layer is transparent above the canvas: an opaque mark obscures
    // the original glyphs. Keep its text inherited and the accent translucent.
    mark.style.backgroundColor = "rgba(171, 211, 122, 0.35)";
    mark.style.color = "inherit";
    mark.style.padding = "0";
    mark.style.outline = "1px solid rgba(139, 184, 90, 0.6)";
    range.surroundContents(mark);
    first ??= mark;
  }
  if (options.scroll !== false)
    first?.scrollIntoView({
      block: options.align ?? "start",
      behavior: "smooth",
    });
  return !!first;
}
