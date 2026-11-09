import assert from "node:assert/strict";
import { test } from "node:test";
import { registerSchema } from "../../../src/_pages/register/ui/register-schema";

test("registration validates API fields, matching passwords and trimmed email", () => {
  const valid = {
    email: "  user@example.com  ",
    password: "secret",
    confirm: "secret",
    code: "123",
  };
  assert.equal(registerSchema.parse(valid).email, "user@example.com");
  for (const changes of [
    { email: "invalid" },
    { password: "" },
    { confirm: "other" },
    { code: "" },
  ]) {
    assert.equal(
      registerSchema.safeParse({ ...valid, ...changes }).success,
      false,
    );
  }
  const pending = registerSchema.safeParse({
    ...valid,
    confirm: "other",
    code: "",
  });
  assert.ok(
    !pending.success &&
      pending.error.issues.some((issue) => issue.path[0] === "confirm"),
  );
});
