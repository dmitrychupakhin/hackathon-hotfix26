import assert from "node:assert/strict";
import { test } from "node:test";
import { loginSchema } from "../../../src/_pages/login/ui/login-schema";

test("login validation uses the API rules and trims email", () => {
  assert.deepEqual(
    loginSchema.parse({
      email: "  user@example.com  ",
      password: "secret",
      remember_me: true,
    }),
    { email: "user@example.com", password: "secret", remember_me: true },
  );
  assert.equal(
    loginSchema.parse({ email: "user@example.com", password: "x" }).remember_me,
    false,
  );
  assert.equal(
    loginSchema.safeParse({ email: "invalid", password: "x" }).success,
    false,
  );
  assert.equal(
    loginSchema.safeParse({ email: "user@example.com", password: "" }).success,
    false,
  );
});
