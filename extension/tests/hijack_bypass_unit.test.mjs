import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import {readFileSync} from "node:fs";

const source = readFileSync(new URL("../hijack_bypass.js", import.meta.url), "utf8");

function createPage() {
  const ctx = vm.createContext({
    window: {},
    Object,
    setInterval: () => 0,
    setTimeout: () => 0,
    clearInterval: () => {},
  });
  ctx.window = ctx;
  vm.runInContext(source, ctx);
  return ctx;
}

test("captures execute before Flow overwrites it", async () => {
  const page = createPage();
  const pristine = async () => "token";
  page.grecaptcha = {enterprise: {ready: () => {}, execute: pristine}};
  assert.equal(page.__fk_hijack.source, "L3-immediate");
  assert.equal(typeof page.__fk_hijack.pristine, "function");
  assert.equal(await page.__fk_hijack.pristine(), "token");
});

test("rejects trapped execute and records trap", () => {
  const page = createPage();
  const trapped = async () => "extension_hijack_detected";
  page.grecaptcha = {enterprise: {ready: () => {}, execute: trapped}};
  assert.equal(page.__fk_hijack.pristine, null);
  assert.equal(page.__fk_hijack.trapped, true);
});

test("captures execute assigned later via setter", async () => {
  const page = createPage();
  const pristine = async () => "token";
  page.grecaptcha = {enterprise: {ready: () => {}}};
  page.grecaptcha.enterprise.execute = pristine;
  assert.equal(page.__fk_hijack.source, "L3-setter");
  assert.equal(typeof page.__fk_hijack.pristine, "function");
  assert.equal(await page.__fk_hijack.pristine(), "token");
});

test("captures execute when grecaptcha is assigned later", async () => {
  const page = createPage();
  const pristine = async () => "token";
  page.grecaptcha = {enterprise: {ready: () => {}, execute: pristine}};
  assert.equal(typeof page.__fk_hijack.pristine, "function");
  assert.equal(await page.__fk_hijack.pristine(), "token");
});

test("__fk_hijack is non-enumerable and safe", () => {
  const page = createPage();
  assert.equal(Object.keys(page).includes("__fk_hijack"), false);
  assert.equal(typeof page.__fk_hijack.pristine, "object");
  assert.equal(typeof page.__fk_hijack.trapped, "boolean");
});
