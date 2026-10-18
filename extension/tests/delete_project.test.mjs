// Observed protocol: QI2zvc ["projects/<uuid>"] returns [] HTTP 200.
// Synthetic account, IDs, titles and envelopes; no live requests.
import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import {createHash, webcrypto} from "node:crypto";
import {flowOperation} from "../operations.mjs";
import {validRequest} from "../protocol.mjs";

const target = "11111111-2222-3333-4444-555555555555";
const scope = {tab_id: 1, origin: "https://flow.google.com", project_id: null, document_id: "synthetic"};
const email = "synthetic@example.test";
const input = {project_id: target, expected_title: "Disposable", account_sha256: createHash("sha256").update(email).digest("hex")};
function harness(options = {}) {
  const calls = [];
  let currentEmail = options.unknown ? null : email;
  const node = {parentElement: null, hidden: false, getClientRects: () => [1],
    getAttribute: key => key === "aria-label" ? `Google Account: Synthetic (${currentEmail})` : null};
  const context = vm.createContext({URL, URLSearchParams, TextDecoder, TextEncoder, AbortSignal,
    crypto: webcrypto, Uint8Array, location: {origin: scope.origin, pathname: "/"},
    getComputedStyle: () => ({display: "block", visibility: "visible", opacity: "1"}),
    document: {documentElement: {lang: "en"}, querySelectorAll: () => currentEmail ? [node] : []},
    WIZ_global_data: {SNlM0e: "synthetic-auth"},
    fetch: async (url, spec) => {
      const name = new URL(url, scope.origin).searchParams.get("rpcids");
      const body = JSON.parse(spec.body.get("f.req"));
      calls.push({name, payload: JSON.parse(body[0][0][1])});
      let payload;
      if (name === "UpteDb") {
        payload = options.missing ? [[]] : [[[target, [options.title ?? "Disposable"]]]];
        if (options.switchAccount) currentEmail = "changed@example.test";
        if (options.navigate) context.location.pathname = "/u/1/";
      } else {
        assert.equal(name, "QI2zvc");
        if (options.timeout) throw Object.assign(new Error("synthetic"), {name: "TimeoutError"});
        payload = options.reply ?? [];
      }
      return new Response(")]}'\n" + JSON.stringify([["wrb.fr", name, JSON.stringify(payload)]]), {status: 200});
    }});
  const run = vm.runInContext(`(${flowOperation.toString()})`, context);
  return {calls, run: async (p = input, selected = scope) => JSON.parse(JSON.stringify(
    await run("delete_project", {scope: selected, input: p})
  ))};
}

test("delete uses exact observed payload and empty receipt", async () => {
  const h = harness();
  const reply = await h.run();
  assert.equal(reply.state, "completed");
  assert.equal(reply.deleted_project_id, target);
  assert.deepEqual(h.calls, [
    {name: "UpteDb", payload: ["projects/*", 100]},
    {name: "QI2zvc", payload: [`projects/${target}`]},
  ]);
  assert.ok(!JSON.stringify(reply).includes(email));
  assert.ok(!JSON.stringify(reply).includes(input.account_sha256));
});

test("invalid target or non-home scope never sends RPC", async () => {
  for (const p of [{...input, project_id: "../projects/all"}, {...input, project_id: null}, {...input, extra: 1}]) {
    const h = harness();
    assert.equal((await h.run(p)).state, "not_submitted");
    assert.equal(h.calls.length, 0);
  }
  const h = harness();
  assert.equal((await h.run(input, {...scope, project_id: target})).state, "not_submitted");
  assert.equal(h.calls.length, 0);
});

test("account/title/target/path changes block destructive RPC", async () => {
  for (const opts of [{unknown: true}, {switchAccount: true}, {title: "Changed"}, {missing: true}, {navigate: true}]) {
    const h = harness(opts);
    assert.equal((await h.run()).state, "not_submitted");
    assert.equal(h.calls.filter(c => c.name === "QI2zvc").length, 0);
  }
});

test("nonempty receipt and timeout remain unknown, never retry", async () => {
  for (const options of [{reply: [null]}, {timeout: true}]) {
    const h = harness(options);
    assert.equal((await h.run()).state, "submitted_unverified");
    assert.equal(h.calls.filter(c => c.name === "QI2zvc").length, 1);
  }
});

test("legacy extension explicitly rejects delete; managed-only", () => {
  assert.equal(validRequest({type: "request", id: target, operation: "delete_project", params: {scope, input}}), false);
});
