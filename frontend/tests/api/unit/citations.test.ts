import assert from "node:assert/strict";
import { test } from "node:test";
import {
  citationPage,
  citationRange,
  parseCitations,
  parsePreviewLink,
  previewLink,
} from "../../../src/_pages/chats/model/citations";
import type { ChatCitation } from "../../../src/shared/api/chats/document-preview-api";

const hash = "a".repeat(64);
const citation: ChatCitation = {
  id: "e1",
  file_id: "file-a",
  file_name: "Договор.txt",
  quote: "5%",
  start: 8,
  end: 10,
  text_sha256: hash,
  version: "v1",
  locations: [{ page: 2 }],
};

test("citation offsets use Unicode code points and select the second repeated value", () => {
  const text = "😀 5% и 5%";
  const c = { ...citation, start: 7, end: 9 };
  const range = citationRange({ text, text_sha256: hash, version: "v1" }, c);
  assert.deepEqual(range, { start: 8, end: 10 });
  assert.ok(range);
  assert.equal(text.slice(range.start, range.end), "5%");
});

test("stale versions, stale hashes and mismatched quote never get a guessed highlight", () => {
  const preview = { text: "😀 5% и 5%", text_sha256: hash, version: "v1" };
  assert.equal(
    citationRange(preview, { ...citation, version: "v2" }),
    undefined,
  );
  assert.equal(
    citationRange(preview, { ...citation, text_sha256: "b".repeat(64) }),
    undefined,
  );
  assert.equal(citationRange(preview, citation), undefined);
  assert.equal(
    citationRange(preview, { ...citation, start: 7, end: 999 }),
    undefined,
  );
});

test("copy links preserve Cyrillic, exact quote, source version and page inside fragment", () => {
  const c = { ...citation, quote: "5%\n😀 <script>" };
  const selection = { chatId: "chat-1", fileId: "file-a", citation: c };
  const url = new URL(
    previewLink(selection, "https://site.test/profile?tab=chats"),
  );
  assert.equal(url.origin, "https://site.test");
  assert.equal(url.search, "?tab=chats");
  assert.deepEqual(parsePreviewLink(url.hash), selection);
  assert.equal(citationPage(c), 2);
});

test("malformed evidence and unbounded hash are ignored", () => {
  assert.deepEqual(
    parseCitations([
      { ...citation, start: -1 },
      { ...citation, quote: "" },
      { ...citation, text_sha256: "fake" },
      null,
    ]),
    [],
  );
  assert.equal(parsePreviewLink(`#${"x".repeat(64001)}`), undefined);
  assert.equal(parsePreviewLink("#chat=one"), undefined);
  assert.deepEqual(parsePreviewLink("#chat=one&file=two&start=NaN"), {
    chatId: "one",
    fileId: "two",
    citation: undefined,
  });
});

test("DOCX and text links do not invent PDF page coordinates", () => {
  const c = { ...citation, file_name: "Договор.docx", locations: [] };
  const selection = { chatId: "chat-1", fileId: "file-a", citation: c };
  const url = new URL(previewLink(selection, "https://site.test/chats"));
  assert.equal(new URLSearchParams(url.hash.slice(1)).has("page"), false);
  assert.deepEqual(parsePreviewLink(url.hash), selection);
});
