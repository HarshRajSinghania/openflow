import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import {webcrypto} from "node:crypto";
import {flowOperation, operationErrorMatcher} from "../operations.mjs";
import {sameScope, validRequest, operationErrorSource} from "../protocol.mjs";

const project = "00000000-0000-4000-8000-000000000010";
const media = "12345678-1234-1234-1234-123456789abd";
const scope = {tab_id: 7, origin: "https://flow.google.com", project_id: project, document_id: "doc"};

// Emulate chrome.scripting.executeScript MAIN-world boundary EXACTLY as Chrome 153 does:
//   - func: serialized via toString(), recompiled in the page world
//   - args: JSON-serialized (a RegExp becomes {})
//   - if the injected function throws, Chrome SWALLOWS it and returns InjectionResult.result = null
function mainWorldExecute(func, args) {
  const serializedArgs = JSON.parse(JSON.stringify(args));
  return {funcText: func.toString(), serializedArgs};
}

function makeMainWorld(body) {
  return new vm.createContext({
    URL, URLSearchParams, TextDecoder, AbortSignal, crypto: webcrypto,
    location: {origin: scope.origin, pathname: `/project/${project}`},
    document: {scripts: [{src: "https://www.google.com/recaptcha/enterprise.js?render=actual_site_key_1234567890"}], documentElement: {lang: "en"}},
    WIZ_global_data: {SNlM0e: "private-at", FdrFJe: "sid", cfb2h: "build"},
    grecaptcha: {enterprise: {ready: cb => cb(), execute: async () => "native-token"}},
    setTimeout, fetch: async () => new Response(body, {status: 200})
  });
}

function realExecuteScript(mainWorld) {
  return async spec => {
    if (spec.world === "MAIN") {
      const {funcText, serializedArgs} = mainWorldExecute(spec.func, spec.args);
      const fn = vm.runInContext(`(${funcText})`, mainWorld);
      let result = null;
      try {
        result = await fn(...serializedArgs);
      } catch {
        result = null; // Chrome swallows injected-function throws -> null injection result
      }
      return [{frameId: 0, documentId: "doc", result: JSON.parse(JSON.stringify(result ?? null))}];
    }
    return [{frameId: 0, documentId: "doc", result: {origin: scope.origin, pathname: `/project/${project}`}}];
  };
}

function dispatchContext(mainWorld, operationErrorSourceArg) {
  const source = readFileSync(new URL("../background.js", import.meta.url), "utf8");
  const helper = source.slice(source.indexOf("async function dispatch(message)"),
                              source.indexOf("async function connect()"));
  const context = vm.createContext({
    sameScope, validRequest, operationErrorSource: operationErrorSourceArg,
    flowOperation,
    inspect: async (tabId, pinned) => pinned,
    chrome: {
      tabs: {get: async () => ({url: `https://flow.google.com/project/${project}`, status: "complete", discarded: false})},
      scripting: {executeScript: realExecuteScript(mainWorld)}
    }
  });
  vm.runInContext(`let selected = ${JSON.stringify(scope)}; let derived = null; let epoch = 0; ${helper}`, context);
  return context;
}

const request = {type: "request", id: "12345678-1234-1234-1234-123456789abd",
  operation: "generate_image",
  params: {scope, input: {prompt: "cube", model: "nano_banana_2", ratio: "1:1", references: []}}};

test("FIX: real generate_image dispatch returns a completed result across the executeScript boundary", async () => {
  const payload = [[`https://flow-content.google/image/${media}?Signature=live`]];
  const body = ")]}'\n123\n" + JSON.stringify([["wrb.fr", "ogiZ0b", JSON.stringify(payload)]]) + "\n";
  const context = dispatchContext(makeMainWorld(body), operationErrorSource);
  assert.equal(validRequest(request), true);
  const result = await vm.runInContext(`dispatch(${JSON.stringify(request)})`, context);
  assert.notEqual(result, null, "dispatch returned null -> reply result:null -> python invalid_response:python_parse");
  assert.equal(result.state, "completed");
  assert.equal(result.assets[0].media_id, media);
});

test("FIX: a rejected ogiZ0b surfaces rpc_rejected (not a swallowed null) through real dispatch", async () => {
  // entry[2] == null => flowOperation throws rpc_rejected => catch uses the classifier.
  const body = `)]}'\n12\n[["wrb.fr","ogiZ0b",null,null,null,[8]]]`;
  const context = dispatchContext(makeMainWorld(body), operationErrorSource);
  const result = await vm.runInContext(`dispatch(${JSON.stringify(request)})`, context);
  assert.notEqual(result, null);
  assert.equal(result.state, "submitted_unverified");
  assert.equal(result.error, "rpc_rejected");
  assert.equal(result.diagnostics.rpc_code, 8);
});

test("REGRESSION GUARD: passing a raw RegExp as the classifier (old bug) yields null, proving the boundary", async () => {
  const payload = [[`https://flow-content.google/image/${media}?Signature=live`]];
  const body = ")]}'\n123\n" + JSON.stringify([["wrb.fr", "ogiZ0b", JSON.stringify(payload)]]) + "\n";
  // Simulate the OLD background: a RegExp arg. JSON round-trip lands as {}.
  const mainWorld = makeMainWorld(body);
  const {funcText, serializedArgs} = mainWorldExecute(flowOperation, [request.operation,
    {scope, input: request.params.input, diagnostics: true, page_scope: scope}, /^x$/]);
  assert.deepEqual(serializedArgs[2], {}, "RegExp arg must land as {} (Chrome JSON args)");
  const fn = vm.runInContext(`(${funcText})`, mainWorld);
  // Even the SUCCESS path is fine; the break is on the error path. Show the matcher normalizes,
  // and that a raw {} would throw when .test is invoked.
  const matcher = operationErrorMatcher(serializedArgs[2]);
  assert.equal(typeof matcher.test, "function", "operationErrorMatcher must always return a usable RegExp");
  assert.ok(matcher.test("rpc_rejected"));
});

test("operationErrorMatcher accepts RegExp, source string, and never returns a non-RegExp", () => {
  assert.ok(operationErrorMatcher(/^a$/) instanceof RegExp);
  assert.ok(operationErrorMatcher("^rpc_[a-z_]+$").test("rpc_rejected"));
  for (const value of [undefined, null, {}, 7, [], "", "(", {source: 7}]) {
    const matcher = operationErrorMatcher(value);
    assert.ok(matcher instanceof RegExp, `expected RegExp for ${JSON.stringify(value)}`);
    assert.equal(typeof matcher.test, "function");
  }
});


test("real dispatch carries explicit image seed across serialized MAIN boundary", async () => {
  const payload = [[`https://flow-content.google/image/${media}?Signature=test`]];
  const body = ")]}'\n123\n" + JSON.stringify([["wrb.fr", "ogiZ0b", JSON.stringify(payload)]]) + "\n";
  const world = makeMainWorld(body);
  let inner;
  world.fetch = async (url, spec) => {
    inner = JSON.parse(JSON.parse(spec.body.get("f.req"))[0][0][1]);
    return new Response(body);
  };
  const context = dispatchContext(world, operationErrorSource);
  const seeded = {...request, params: {...request.params, input: {...request.params.input, seed: 987654321}}};
  const result = await vm.runInContext(`dispatch(${JSON.stringify(seeded)})`, context);
  assert.equal(result.state, "completed");
  assert.equal(inner[1][0][3], 987654321);
});

test("real project dispatch forwards title through createProject helper and MAIN RPC", async () => {
  const source = readFileSync(new URL("../background.js", import.meta.url), "utf8");
  const helper = source.slice(source.indexOf("async function createProject("), source.indexOf("async function connect()"));
  const home = {...scope, project_id: null};
  const body = ")]}'\n123\n" + JSON.stringify([["wrb.fr", "jHPbke", JSON.stringify([project])]]) + "\n";
  const world = makeMainWorld(body);
  world.location.pathname = "/";
  let inner;
  world.fetch = async (url, spec) => {
    inner = JSON.parse(JSON.parse(spec.body.get("f.req"))[0][0][1]);
    return new Response(body);
  };
  const execute = realExecuteScript(world);
  const context = vm.createContext({
    sameScope, validRequest, operationErrorSource, flowOperation, inspectPage() {},
    inspect: async () => home,
    chrome: {
      tabs: {get: async () => ({url: "https://flow.google.com/", status: "complete", discarded: false})},
      scripting: {executeScript: async spec => spec.world === "MAIN" ? execute(spec) :
        [{frameId: 0, documentId: "doc", result: {email: "test@example.com", origin: home.origin, pathname: "/"}}]},
    },
  });
  vm.runInContext(`let selected = ${JSON.stringify(home)}; let derived = null; let epoch = 0; ${helper}`, context);
  const message = {type: "request", id: media, operation: "create_project", params: {scope: home, title: "Título dispatch"}};
  assert.equal((await vm.runInContext(`dispatch(${JSON.stringify(message)})`, context)).state, "completed");
  assert.deepEqual(inner, ["projects/*", [null, ["Título dispatch"]], [null, 22]]);
});
