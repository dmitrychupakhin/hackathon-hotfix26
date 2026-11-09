import assert from "node:assert/strict";
import { test } from "node:test";
import { changeEmailSchema } from "../../../src/_pages/change-email/ui/change-email-schema";
import { changePasswordSchema } from "../../../src/_pages/change-password/ui/change-password-schema";

test("password change requires current password and matching confirmation", () => {
  const values = { old_password: "old", password: "new", confirm: "new" };
  assert.equal(changePasswordSchema.safeParse(values).success, true);
  for (const change of [
    { old_password: "" },
    { password: "" },
    { confirm: "other" },
  ]) {
    assert.equal(
      changePasswordSchema.safeParse({ ...values, ...change }).success,
      false,
    );
  }
});

test("email change normalizes email and code and rejects missing confirmation", () => {
  assert.deepEqual(
    changeEmailSchema.parse({ email: " user@example.com ", code: " 123 " }),
    { email: "user@example.com", code: "123" },
  );
  for (const values of [
    { email: "invalid", code: "123" },
    { email: "user@example.com", code: " " },
  ]) {
    assert.equal(changeEmailSchema.safeParse(values).success, false);
  }
});
