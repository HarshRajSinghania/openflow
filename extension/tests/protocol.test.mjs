import assert from "node:assert/strict";
import test from "node:test";
import {flowScope, sameScope, serverUrl, validRequest} from "../protocol.mjs";

test("loopback URL validation", () => {
  assert.equal(serverUrl("ws://127.0.0.1:9233"), "ws://127.0.0.1:9233/");
  for (const url of ["wss://example.com:9233", "ws://127.0.0.1:9222", "ws://localhost:9233/?secret=x",
    "ws://localhost.evil:9233", "ws://user:pass@localhost:9233", "ws://localhost:9233/rpc"]) {
    assert.throws(() => serverUrl(url));
  }
});

test("scope excludes URL queries and unrelated pages", () => {
  assert.deepEqual(flowScope("https://flow.google.com/?token=secret"), {
    origin: "https://flow.google.com", project_id: null
  });
  assert.equal(flowScope("https://flow.google.com.evil/"), null);
  assert.equal(flowScope("https://labs.google/unrelated"), null);
  assert.ok(flowScope("https://labs.google/fx/tools/flow"));
  assert.ok(flowScope("https://labs.google/fx/en/tools/flow"));
});

test("multiaccount project scope preserves project and excludes query secrets", () => {
  const project = "00000000-0000-4000-8000-000000000010";
  for (const prefix of ["/", "/u/0/", "/u/1/"]) {
    assert.deepEqual(flowScope(`https://flow.google.com${prefix}project/${project}?secret=hidden`), {
      origin: "https://flow.google.com", project_id: project
    });
  }
});

test("RPC allowlist excludes executable code and generation", () => {
  const message = {type: "request", id: "12345678-1234-1234-1234-123456789abc", params: {}};
  assert.ok(validRequest({...message, operation: "snapshot"}));
  assert.ok(validRequest({...message, operation: "select", params: {tab_id: 7}}));
  assert.ok(!validRequest({...message, operation: "inspect"}));
  for (const operation of ["eval", "generate", "upload", "fetch"]) assert.ok(!validRequest({...message, operation}));
});

test("exact document and project pin", () => {
  const scope = {tab_id: 1, origin: "https://flow.google.com", project_id: null, document_id: "one"};
  assert.ok(sameScope(scope, {...scope}));
  assert.ok(!sameScope(scope, {...scope, tab_id: 2}));
  assert.ok(!sameScope(scope, {...scope, document_id: "two"}));
  assert.ok(!sameScope(scope, {...scope, project_id: "different"}));
});

test("scope and input generation accepts optional diagnostics flag", () => {
  const project = "00000000-0000-4000-8000-000000000010";
  const scope = {tab_id: 1, origin: "https://flow.google.com", project_id: project, document_id: "one"};
  const input = {prompt: "cube", model: "nano_banana_2", ratio: "1:1", references: []};
  const base = {type: "request", id: "12345678-1234-1234-1234-123456789abc", operation: "generate_image"};
  assert.ok(validRequest({...base, params: {scope, input}}));
  assert.ok(validRequest({...base, params: {scope, input, diagnostics: true}}));
  assert.ok(validRequest({...base, params: {scope, input, diagnostics: false}}));
  assert.ok(!validRequest({...base, params: {scope, input, diagnostics: "yes"}}));
  assert.ok(!validRequest({...base, params: {scope, input, diagnostics: true, click: "x"}}));
});
