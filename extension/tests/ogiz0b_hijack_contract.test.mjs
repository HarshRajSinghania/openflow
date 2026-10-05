import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import {knownOperationErrors} from "../operations.mjs";

test("native restriction falls back to enterprise.execute only when pristine absent", () => {
  assert.ok(knownOperationErrors.test("native_recaptcha_automation_unsupported"));
  const source = readFileSync(new URL("../operations.mjs", import.meta.url), "utf8");
  assert.match(source, /const hijack = globalThis\.__fk_hijack;/);
  assert.match(source, /execute = hijack\.pristine;/);
  assert.match(source, /execute = enterprise\.execute;/);
  assert.doesNotMatch(source, /Object\.defineProperty/);
});
