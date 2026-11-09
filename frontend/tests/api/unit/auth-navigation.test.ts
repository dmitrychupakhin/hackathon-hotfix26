import assert from "node:assert/strict";
import { test } from "node:test";
import {
  afterLoginPath,
  isProtectedPath,
  loginPath,
  safeReturnPath,
} from "../../../src/shared/auth/navigation";

test("all cabinet routes require a session, without matching public lookalikes", () => {
  for (const route of [
    "/chats",
    "/prompt",
    "/comparisons",
    "/profile",
    "/change-email",
    "/change-password",
  ])
    assert.equal(isProtectedPath(route), true);
  for (const route of [
    "/",
    "/login",
    "/register",
    "/chats-other",
    "/api/chats",
  ])
    assert.equal(isProtectedPath(route), false);
});

test("login round trip retains citation chat, query and fragment", () => {
  const target = "/chats?chat=123#citation=abc&start=42";
  const login = new URL(loginPath(target), "https://site.test");
  assert.equal(login.pathname, "/login");
  assert.equal(afterLoginPath(login.search, login.hash), target);
  assert.equal(login.searchParams.get("next"), "/chats?chat=123");
  assert.equal(login.hash, "#citation=abc&start=42");
  assert.equal(
    afterLoginPath("?next=%2Fchats%3Fchat%3D123", "#citation=abc&start=42"),
    target,
  );
  assert.equal(
    afterLoginPath("?next=%2Fchats%23explicit", "#inherited"),
    "/chats#explicit",
  );
});

test("authentication next cannot navigate off origin or back into auth pages", () => {
  for (const target of [
    null,
    "",
    "https://evil.test/chats",
    "//evil.test/chats",
    "/\\evil.test/chats",
    "javascript:alert(1)",
    "/login",
    "/register",
    "/chats/../../evil",
    "/%2f%2fevil.test",
    "/chats\n//evil.test",
  ])
    assert.equal(safeReturnPath(target), "/profile", String(target));
  assert.equal(
    safeReturnPath("/chats?next=https://example.test"),
    "/chats?next=https://example.test",
  );
});
