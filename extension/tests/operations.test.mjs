import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import {webcrypto} from "node:crypto";
import {flowOperation} from "../operations.mjs";
import {validInput, validRequest} from "../protocol.mjs";

const project = "12345678-1234-1234-1234-123456789abc";
const media = "12345678-1234-1234-1234-123456789abd";
const scope = {tab_id: 7, document_id: "doc", origin: "https://flow.google.com", project_id: project};
const image = {prompt: 'literal " __CAPTCHA__ </script>', model: "nano_banana_2", ratio: "1:1", references: []};
const video = {prompt: "test", model: "omni", ratio: "16:9", duration: 8, resolution: "720p", start: null, end: null, references: []};

function harness(payload, options = {}) {
  const calls = [];
  const timers = [];
  const context = vm.createContext({
    URL, URLSearchParams, TextDecoder, AbortSignal, crypto: webcrypto,
    location: {origin: scope.origin, pathname: `/project/${project}`},
    document: {scripts: [{src: "https://www.google.com/recaptcha/enterprise.js?render=actual_site_key_1234567890"}], documentElement: {lang: "en"}},
    WIZ_global_data: {SNlM0e: "private-at", FdrFJe: "sid", cfb2h: "build"},
    grecaptcha: options.noCaptcha ? undefined : {enterprise: {
      ready: callback => callback(), execute: async (key, {action}) => {
        assert.equal(key, "actual_site_key_1234567890");
        calls.push({action}); return "native-token";
      }
    }},
    setTimeout: (fn, delay) => { const timer = setTimeout(fn, delay); timer.unref(); timers.push(timer); },
    fetch: async (url, spec) => {
      const rpc = new URL(url, scope.origin).searchParams.get("rpcids");
      const envelope = JSON.parse(spec.body.get("f.req"));
      calls.push({rpc, inner: JSON.parse(envelope[0][0][1]), spec, url});
      if (options.failFetch) throw new Error("network failed");
      const body = ")]}'\n123\n" + JSON.stringify([["wrb.fr", rpc, JSON.stringify(payload)]]) + "\n";
      if (options.failBody) return new Response(new ReadableStream({start(controller) { controller.error(new Error("secret body error")); }}));
      return new Response(options.body ?? body, {status: options.status ?? 200});
    }
  });
  const run = vm.runInContext(`(${flowOperation.toString()})`, context);
  return {calls, context, run: async (op, input) => {
    try { return JSON.parse(JSON.stringify(await run(op, {scope: options.scope || scope, input, diagnostics: options.diagnostics, ...(options.pageScope ? {page_scope: options.pageScope} : {})}))); }
    finally { for (const timer of timers) clearTimeout(timer); }
  }};
}

test("captured upscale requests are constrained and unknown receipts never retry", async () => {
  for (const resolution of ["2K", "4K"]) {
    const h = harness([[media], "A".repeat(200)]);
    const input = {media_id: media, resolution};
    assert.equal(validInput("upscale_image", input), true);
    assert.equal((await h.run("upscale_image", input)).state, "completed");
    assert.equal(h.calls[1].rpc, "SPrCad");
    assert.deepEqual(h.calls[1].inner.slice(0, 2), [media, resolution === "2K" ? 1 : 2]);
    assert.equal(h.calls[1].inner[2][5], null);
  }
  const input = {media_id: media, scene_id: project, ratio: "16:9", resolution: "1080p"};
  assert.equal(validInput("upscale_video", input), true);
  assert.equal(validInput("upscale_video", {...input, resolution: "4K"}), false);
  const h = harness([null, null, [[media, project]]]);
  assert.equal((await h.run("upscale_video", input)).state, "pending");
  assert.equal(h.calls[1].rpc, "p0UkFb");
  const item = h.calls[1].inner[0][0];
  assert.equal(item.length, 32);
  assert.deepEqual(item[0], [null, media]);
  assert.equal(item[31], "veo_3_1_upsampler_1080p");
  const bad = harness([]);
  assert.equal((await bad.run("upscale_video", input)).state, "submitted_unverified");
  assert.equal(bad.calls.filter(call => call.rpc).length, 1);
});

test("native account transport prefix stays same origin and rejects alternate endpoints", async () => {
  const home = {...scope, project_id: null};
  for (const base of ["/u/1/_/AiSandboxAngularFrontend/", "https://evil.test/", "/other/"]) {
    const h = harness([], {scope: home, noCaptcha: true, diagnostics: true});
    h.context.location.pathname = "/";
    h.context.WIZ_global_data.eptZe = base;
    const result = await h.run("list_projects");
    if (base.startsWith("/u/1/")) {
      assert.equal(result.state, "completed");
      assert.equal(new URL(h.calls[0].url, scope.origin).pathname, base + "data/batchexecute");
    } else {
      assert.equal(result.state, "not_submitted");
      assert.equal(h.calls.length, 0);
    }
  }
});

test("frontend GetProjects is read only and normalizes serialized home scope", async () => {
  const home = {...scope, project_id: null};
  const serialized = {...home};
  delete serialized.project_id;
  for (const status of [200, 400]) {
    const h = harness([[[project, ["OpenFlow project"]]]], {scope: serialized, noCaptcha: true, diagnostics: true, status});
    h.context.location.pathname = "/";
    const result = await h.run("list_projects");
    assert.deepEqual(result.scope, home);
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].rpc, "UpteDb");
    assert.deepEqual(h.calls[0].inner, ["projects/*", 100]);
    assert.equal(result.selected, undefined);
    if (status === 200) assert.deepEqual(result.projects, [{project_id: project, title: "OpenFlow project"}]);
    else assert.equal(result.diagnostics.http_status, 400);
  }
  const request = {type: "request", id: media, operation: "list_projects", params: {scope: home}};
  assert.equal(validRequest(request), true);
  assert.equal(validRequest({...request, params: {scope}}), false);
  assert.equal(validRequest({...request, params: {scope: home, input: []}}), false);
});

test("readonly probe uses FlowKit project_media_request slots without exposing content", async () => {
  const h = harness([["private-title", "private-url"]], {diagnostics: true, noCaptcha: true});
  const result = await h.run("probe", {project_id: project});
  assert.equal(result.rpc_verified, true);
  assert.equal(result.diagnostics.auth_present, true);
  assert.equal(result.diagnostics.phase, "validated_envelope");
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].rpc, "Zzl0ze");
  assert.deepEqual(h.calls[0].inner, [`projects/${project}`, null, null, null, [1]]);
  assert.ok(!JSON.stringify(result).includes("private"));
  const request = {type: "request", id: media, operation: "probe", params: {scope, input: {project_id: project}, diagnostics: true}};
  assert.equal(validRequest(request), true);
  assert.equal(validRequest({...request, params: {...request.params, url: "https://evil.test"}}), false);
  assert.equal(validRequest({...request, params: {...request.params, input: {project_id: "invalid"}}}), false);
});

test("home probe keeps page scope and only sends the fixed listing RPC", async () => {
  const home = {...scope, project_id: null};
  const h = harness([], {scope: home, diagnostics: true, noCaptcha: true});
  h.context.location.pathname = "/";
  const result = await h.run("probe", {project_id: project});
  assert.equal(result.rpc_verified, true);
  assert.deepEqual(result.scope, home);
  assert.equal(result.selected, undefined);
  assert.deepEqual(h.calls.map(call => call.rpc), ["Zzl0ze"]);
  assert.deepEqual(h.calls[0].inner, [`projects/${project}`, null, null, null, [1]]);
  assert.equal(new URL(h.calls[0].url, scope.origin).searchParams.get("source-path"), "/");
  const serializedHome = {...home};
  delete serializedHome.project_id;
  const serialized = harness([], {scope: serializedHome, diagnostics: true, noCaptcha: true});
  serialized.context.location.pathname = "/";
  assert.equal((await serialized.run("probe", {project_id: project})).rpc_verified, true);
  assert.equal((await serialized.run("create_project")).error, "invalid_project_response");
  assert.equal(serialized.calls.length, 2);
  const bad = harness({unknown: true}, {scope: home, diagnostics: true});
  bad.context.location.pathname = "/";
  assert.equal((await bad.run("probe", {project_id: project})).error, "invalid_project_response");
  const moved = harness([], {scope: home, diagnostics: true});
  assert.equal((await moved.run("probe", {project_id: project})).error, "scope_changed");
  assert.equal(moved.calls.length, 0);
  const request = {type: "request", id: media, operation: "probe", params: {scope: home, input: {project_id: project}, diagnostics: true}};
  assert.equal(validRequest(request), true);
  for (const key of ["rpc", "url", "method", "page_scope"]) {
    assert.equal(validRequest({...request, params: {...request.params, [key]: "arbitrary"}}), false);
  }
  assert.equal(validRequest({...request, operation: "upload"}), false);
  assert.equal(validRequest({...request, operation: "generate_image"}), false);
});

test("captured FlowKit project RPC sends exact slots without captcha or clicks", async () => {
  const home = {...scope, project_id: null};
  const h = harness([project, ["OpenFlow project"]], {scope: home, noCaptcha: true});
  h.context.location.pathname = "/";
  const result = await h.run("create_project");
  assert.equal(result.state, "completed");
  assert.deepEqual(result.selected, {...home, project_id: project});
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].rpc, "jHPbke");
  assert.deepEqual(h.calls[0].inner, ["projects/*", [null, ["OpenFlow project"]], [null, 22]]);
  assert.equal(h.calls[0].spec.credentials, "include");
  assert.equal(h.calls[0].spec.redirect, "error");
});

test("FlowKit framed multiline envelopes and decoded payloads replay without live calls", async () => {
  for (const payload of [JSON.stringify([project, ['private title ] " é']]), [project, ["private title"]]]) {
    const chunk = JSON.stringify([["wrb.fr", "other", "[]"], ["wrb.fr", "jHPbke", payload]], null, 2);
    const h = harness(null, {scope: {...scope, project_id: null}, diagnostics: true, body: ")]}'\n\n999\n" + chunk});
    h.context.location.pathname = "/";
    const result = await h.run("create_project");
    assert.equal(result.state, "completed");
    assert.equal(result.diagnostics.http_status, 200);
    assert.equal(result.diagnostics.rpc, "jHPbke");
    assert.equal(result.diagnostics.payload_shape.type, "array");
    assert.ok(!JSON.stringify(result.diagnostics).includes("private"));
    assert.equal(h.calls.length, 1);
    assert.equal(new URL(h.calls[0].url, scope.origin).searchParams.get("source-path"), "/");
  }
});

test("sanitized diagnostics distinguish failures and never retry", async () => {
  for (const [options, error] of [
    [{failFetch: true}, "rpc_transport_error"],
    [{failBody: true}, "rpc_body_read_error"],
    [{status: 403}, "rpc_http_error"],
    [{body: ')]}\'\n12\n[["wrb.fr","jHPbke",null,null,null,[8]]]'}, "rpc_rejected"],
    [{body: '[["wrb.fr","jHPbke","secret invalid json"]]'}, "invalid_rpc_payload"],
    [{body: '[["wrb.fr","other","[]"]]'}, "rpc_envelope_missing"],
    [{body: "secret html"}, "invalid_batch_response"],
    [{}, "invalid_project_response"],
  ]) {
    const h = harness(["secret"], {...options, scope: {...scope, project_id: null}, diagnostics: true});
    h.context.location.pathname = "/";
    const result = await h.run("create_project");
    assert.equal(result.state, "submitted_unverified");
    assert.equal(result.error, error);
    assert.equal(h.calls.length, 1);
    assert.ok(!JSON.stringify(result).includes("secret"));
    if (error === "rpc_rejected") assert.equal(result.diagnostics.rpc_code, 8);
  }
  const h = harness([], {scope: {...scope, project_id: null}});
  h.context.location.pathname = "/";
  h.context.WIZ_global_data = {};
  const result = await h.run("create_project");
  assert.equal(result.state, "not_submitted");
  assert.equal(result.error, "page_auth_unavailable");
  assert.equal(result.diagnostics, undefined);
  assert.equal(h.calls.length, 0);
});

test("project failures remain uncertain after exactly one request", async () => {
  for (const options of [{failFetch: true}, {}]) {
    const h = harness(["not-a-uuid"], {...options, scope: {...scope, project_id: null}, noCaptcha: true});
    h.context.location.pathname = "/";
    assert.equal((await h.run("create_project")).state, "submitted_unverified");
    assert.equal(h.calls.length, 1);
  }
});

test("home document can poll only explicitly derived scope, unknown ops never send", async () => {
  const h = harness([null, 50, [[media, project, null, "working"]]], {noCaptcha: true, pageScope: {...scope, project_id: null}});
  h.context.location.pathname = "/";
  assert.equal((await h.run("poll", {operation_id: media, media_id: null, kind: "video"})).state, "pending");
  const invalid = harness([]);
  assert.equal((await invalid.run("arbitrary")).state, "not_submitted");
  assert.equal(invalid.calls.length, 0);
});

test("MAIN helper serializes standalone and emits captured image slots without prompt substitution", async () => {
  const h = harness([[`https://flow-content.google/image/${media}?Signature=test`]]);
  const result = await h.run("generate_image", image);
  assert.equal(result.state, "completed");
  assert.equal(result.assets[0].media_id, media);
  assert.equal(h.calls[1].rpc, "ogiZ0b");
  const item = h.calls[1].inner[1][0];
  assert.equal(item[5], "NARWHAL");
  assert.equal(item[4], 1);
  assert.equal(item[8][0][0][0], image.prompt);
  assert.equal(item[7][10][0], "native-token");
  assert.ok(!JSON.stringify(result).includes("private-at"));
});

for (const [label, input, rpc, modelIndex, model] of [
  ["text", video, "YhhmEf", 1, "abra_t2v_8s"],
  ["start", {...video, start: media}, "eb1hJf", 1, "abra_i2v_8s"],
  ["start end", {...video, start: media, end: project}, "nprQif", 1, "omni_flash_i2v_8s_first_last"],
  ["reference", {...video, references: [media]}, "MZZa6b", 2, "abra_r2v_8s"],
  ["veo", {...video, start: media, model: "veo_lite"}, "eb1hJf", 1, "veo_3_1_i2v_lite"],
]) test(`captured ${label} video builder`, async () => {
  const payload = rpc === "YhhmEf" ? [null, null, null, [[media, project, media, "pending"]]] : [null, 50, [[media, project, null, "pending"]]];
  const h = harness(payload);
  const result = await h.run("generate_video", input);
  assert.equal(result.state, "pending");
  assert.equal(h.calls[1].rpc, rpc);
  assert.equal(h.calls[1].inner[0][0][modelIndex], model);
});

test("upload response verifies project", async () => {
  const h = harness([[media, project, media, "CAE"]]);
  assert.equal((await h.run("upload", {data: "aGVsbG8=", mime: "image/png", name: "x.png"})).assets[0].media_id, media);
  assert.equal(h.calls[1].rpc, "maseQ");
});

test("unavailable native recaptcha is descriptive and does not submit", async () => {
  const h = harness([], {noCaptcha: true});
  assert.equal((await h.run("generate_image", image)).error, "native_recaptcha_enterprise_unavailable");
  assert.equal(h.calls.length, 0);
});

test("sitekey missing or ambiguous fails before network", async () => {
  const h = harness([]);
  h.context.document.scripts = [];
  assert.equal((await h.run("generate_image", image)).error, "native_recaptcha_sitekey_unavailable_or_ambiguous");
  assert.equal(h.calls.length, 0);
});

test("network failure after send is uncertain and never retried", async () => {
  const h = harness([], {failFetch: true});
  assert.equal((await h.run("generate_image", image)).state, "submitted_unverified");
  assert.equal(h.calls.filter(x => x.rpc).length, 1);
});

test("rejected image and video submissions persist the rpc code and error shape without secrets", async () => {
  const rejected = rpc => `)]}'\n12\n[["wrb.fr","${rpc}",null,null,null,[8],"private-context"]]`;
  for (const [op, input, rpc] of [["generate_image", image, "ogiZ0b"], ["generate_video", video, "YhhmEf"]]) {
    const h = harness(null, {diagnostics: true, body: rejected(rpc)});
    const result = await h.run(op, input);
    assert.equal(result.state, "submitted_unverified");
    assert.equal(result.error, "rpc_rejected");
    assert.equal(result.diagnostics.rpc, rpc);
    assert.equal(result.diagnostics.rpc_code, 8);
    assert.equal(result.diagnostics.phase, "parse");
    assert.equal(result.diagnostics.rpc_error_shape.type, "array");
    assert.equal(result.diagnostics.rpc_error_shape.length, 1);
    assert.deepEqual(result.diagnostics.rpc_error_shape.items, ["number"]);
    assert.equal(result.diagnostics.envelope_shape.type, "array");
    assert.equal(h.calls.filter(call => call.rpc).length, 1);
    assert.ok(!JSON.stringify(result).includes("private-context"));
    assert.ok(!JSON.stringify(result).includes("private-at"));
  }
});

test("absent diagnostics stay absent and malformed diagnostics never leak", async () => {
  const noDiagnostics = harness([[`https://flow-content.google/image/${media}?Signature=test`]]);
  const ok = await noDiagnostics.run("generate_image", image);
  assert.equal(ok.state, "completed");
  assert.equal(ok.diagnostics, undefined);
  const rejected = harness(null, {body: `)]}'\n12\n[["wrb.fr","ogiZ0b",null,null,null,[8]]]`});
  const bare = await rejected.run("generate_image", image);
  assert.equal(bare.error, "rpc_rejected");
  assert.equal(bare.diagnostics, undefined);
  assert.equal(rejected.calls.filter(call => call.rpc).length, 1);
});

test("oversize and unknown rejected responses fail safe without escalating", async () => {
  const oversize = harness([], {diagnostics: true, status: 200, body: "secret html"});
  const big = await oversize.run("generate_image", image);
  assert.equal(big.state, "submitted_unverified");
  assert.equal(big.error, "invalid_batch_response");
  assert.equal(big.diagnostics.rpc, "ogiZ0b");
  assert.equal(big.diagnostics.chunks, undefined);
  assert.ok(!JSON.stringify(big).includes("secret"));
  assert.equal(oversize.calls.filter(call => call.rpc).length, 1);
  const unknown = harness([], {diagnostics: true, body: `)]}'\n12\n[["wrb.fr","other","[]"]]`});
  const missing = await unknown.run("generate_image", image);
  assert.equal(missing.error, "rpc_envelope_missing");
  assert.equal(missing.diagnostics.rpc_code, undefined);
  assert.equal(missing.diagnostics.envelopes, 1);
  assert.equal(unknown.calls.filter(call => call.rpc).length, 1);
});

test("read-only polling needs no recaptcha and validates record scope", async () => {
  const h = harness([null, 50, [[media, project, null, "working"]]], {noCaptcha: true});
  assert.equal((await h.run("poll", {operation_id: media, media_id: null, kind: "video"})).state, "pending");
  assert.equal(h.calls[0].rpc, "jwpduf");
  const bad = harness([null, 50, [[media, media, null, "working"]]], {noCaptcha: true});
  assert.equal((await bad.run("poll", {operation_id: media, media_id: null, kind: "video"})).error, "operation_scope_mismatch");
});

test("protocol rejects executable fields, mode degradation and alternate scope", () => {
  const request = {type: "request", id: media, operation: "generate_image", params: {scope, input: image}};
  assert.ok(validRequest(request));
  for (const input of [{...image, model: "arbitrary"}, {...image, code: "fetch('evil')"}, {...image, references: ["javascript:alert(1)"]}]) {
    assert.ok(!validRequest({...request, params: {scope, input}}));
  }
  assert.ok(!validInput("generate_video", {...video, model: "veo_lite"}));
  assert.ok(validInput("generate_video", {...video, model: "veo_lite", start: media}));
  assert.ok(!validInput("generate_video", {...video, start: media, references: [project]}));
  assert.ok(!validRequest({...request, params: {...request.params, scope: {...scope, project_id: null}}}));
});
