import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import {validRequest, sameScope} from "../protocol.mjs";

const source = readFileSync(new URL("../background.js", import.meta.url), "utf8");
const helper = source.slice(source.indexOf("async function dispatch(message)"), source.indexOf("async function connect()"));
const scope = {tab_id: 7, origin: "https://flow.google.com", project_id: null, document_id: "old"};
const request = {type: "request", id: "12345678-1234-1234-1234-123456789abc", operation: "reload_tab", params: {scope}};

function harness() {
  const reloads = [], scheduled = [];
  let changed = false;
  const context = vm.createContext({
    sameScope,
    setTimeout: fn => scheduled.push(fn),
    inspect: async () => { if (changed) throw new Error("scope_changed"); return {...scope}; },
    chrome: {tabs: {reload: async (id, options) => reloads.push({id, options})}}
  });
  vm.runInContext(`let selected = ${JSON.stringify(scope)}; let epoch = 0; function invalidate() { selected = null; epoch++; } ${helper}`, context);
  return {context, reloads, scheduled, change: () => { changed = true; },
    run: () => vm.runInContext(`dispatch(${JSON.stringify(request)})`, context)};
}

test("reload allowlist requires exact scope and rejects unrelated targets", () => {
  assert.equal(validRequest(request), true);
  for (const params of [{}, {scope, url: "other"}, {scope: {...scope, origin: "https://example.com"}}, {scope: {...scope, document_id: null}}]) {
    assert.equal(validRequest({...request, params}), false);
  }
});

test("reply precedes scheduled reload and captured tab survives invalidation", async () => {
  const h = harness();
  const result = await h.run();
  assert.equal(result.previous_document_id, "old");
  assert.equal(result.reloading, 7);
  assert.equal(h.reloads.length, 0);
  await h.scheduled[0]();
  assert.equal(vm.runInContext("selected", h.context), null);
  assert.equal(h.reloads.length, 1);
  assert.equal(h.reloads[0].id, 7);
});

test("null selection fails without scheduling", async () => {
  const h = harness();
  vm.runInContext("selected = null", h.context);
  await assert.rejects(h.run(), /select_flow_tab_required/);
  assert.equal(h.scheduled.length, 0);
});

test("changed selected scope fails without scheduling", async () => {
  const h = harness();
  vm.runInContext('selected.document_id = "other"', h.context);
  await assert.rejects(h.run(), /scope_changed/);
  assert.equal(h.scheduled.length, 0);
});

test("changed document before verification fails", async () => {
  const h = harness();
  h.change();
  await assert.rejects(h.run(), /scope_changed/);
  assert.equal(h.scheduled.length, 0);
});

test("changed document after reply cancels scheduled reload", async () => {
  const h = harness();
  await h.run();
  h.change();
  await h.scheduled[0]();
  assert.equal(h.reloads.length, 0);
});
