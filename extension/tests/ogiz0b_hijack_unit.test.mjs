import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import {flowOperation, knownOperationErrors} from "../operations.mjs";

const project = "12345678-1234-1234-1234-123456789abc";
const scope = {tab_id: 7, document_id: "doc", origin: "https://flow.google.com", project_id: project};

const validInput = (operation) => {
  if (operation === "generate_image") return {prompt: "x", model: "nano_banana_2", ratio: "1:1", references: []};
  if (operation === "generate_video") return {prompt: "x", model: "omni", ratio: "16:9", duration: 8, resolution: "720p", start: null, end: null, references: []};
  if (operation === "upload") return {data: "aGVsbG8=", mime: "image/png", name: "x.png"};
  if (operation === "upscale_image") return {media_id: "12345678-1234-1234-1234-123456789abd", resolution: "2K"};
  if (operation === "upscale_video") return {media_id: "12345678-1234-1234-1234-123456789abd", scene_id: project, ratio: "16:9", resolution: "1080p"};
  return {};
};

for (const operation of ["generate_image", "generate_video", "upload", "upscale_image", "upscale_video"]) {
  test(`${operation} refuses native automation restriction before mint or send`, async () => {
    const events = [];
    const execute = async () => { events.push("mint"); return "extension_hijack_detected"; };
    const context = vm.createContext({
      URL, URLSearchParams,
      location: {origin: scope.origin, pathname: "/project/" + project},
      document: {scripts: [{src: "https://www.google.com/recaptcha/enterprise.js?render=actual_site_key_1234567890"}], documentElement: {lang: "en"}},
      grecaptcha: {enterprise: {ready: () => events.push("ready"), execute}},
      fetch: () => events.push("send")
    });
    const run = vm.runInContext("(" + flowOperation.toString() + ")", context);
    const result = await run(operation, {scope, input: validInput(operation), diagnostics: true});
    assert.equal(result.error, "native_recaptcha_automation_unsupported");
    assert.equal(result.state, "not_submitted");
    assert.ok(knownOperationErrors.test(result.error));
    assert.deepEqual(events, []);
  });
}

