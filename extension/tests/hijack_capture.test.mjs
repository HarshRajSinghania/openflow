import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";

const manifest = JSON.parse(readFileSync(new URL("../manifest.json", import.meta.url), "utf8"));

test("content script is registered at document_start in MAIN world", () => {
  assert.ok(Array.isArray(manifest.content_scripts));
  const cs = manifest.content_scripts.find(entry => entry.js?.includes("hijack_bypass.js"));
  assert.ok(cs, "hijack_bypass.js content script missing");
  assert.equal(cs.run_at, "document_start");
  assert.equal(cs.world, "MAIN");
  assert.deepEqual(cs.matches, ["https://flow.google.com/*", "https://labs.google/*"]);
  assert.equal(cs.all_frames, false);
});

test("runtime assets reference bypass hooks only through safe surface", () => {
  const ops = readFileSync(new URL("../operations.mjs", import.meta.url), "utf8");
  assert.match(ops, /__fk_hijack/);
  assert.doesNotMatch(ops, /Object\.defineProperty/);
  const manifestSource = readFileSync(new URL("../manifest.json", import.meta.url), "utf8");
  assert.match(manifestSource, /hijack_bypass\.js/);
});
