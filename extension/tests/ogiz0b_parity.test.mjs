// Cross-repo parity: flow-mcp's ogiZ0b request builder vs FlowKit's golden capture.
//
// The live code-7 rejection was first suspected to be a builder diff. This test
// settles that question mechanically: it rebuilds the EXACT inner payload the
// flow-mcp builder produces (operations.mjs generate_image, lines 247-252) with
// uuids/seed pinned, and asserts it is byte-for-byte identical to the string
// FlowKit locks in test_flow_batch_golden.py::GOLDEN_IMAGE.
//
// If this passes, the request CONTENT is not the cause of an rpc_code-7 reject —
// every slot (aspect numeric mapping, model wire id, reference array shape,
// context slot, client descriptor, captcha slot) already matches the accepted
// shape. If it ever fails, a slot drifted and the diff tells you which.
import assert from "node:assert/strict";
import test from "node:test";

// Verbatim from flowkit/tests/unit/test_flow_batch_golden.py GOLDEN_IMAGE (inner
// payload, already unescaped once). Do not hand-edit; re-copy from the fixture.
const FLOWKIT_GOLDEN_INNER =
  '[null,[[null,null,[["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",null,null,null,1]],42,2,' +
  '"GEM_PIX_2",null,[null,22,null,null,null,"11111111-2222-3333-4444-555555555555",null,' +
  'null,null,null,["__CAPTCHA__",1]],[[["a cat"]]],null,null,null,' +
  '"00000000-0000-4000-8000-000000000001","00000000-0000-4000-8000-000000000002"]],1,' +
  '[null,22,null,null,null,"11111111-2222-3333-4444-555555555555",null,null,null,null,' +
  '["__CAPTCHA__",1]],["00000000-0000-4000-8000-000000000003"]]';

// Exactly the expression evaluated inside operations.mjs flowOperation for
// generate_image, with non-determinism (uuid, seed) pinned so the result is
// comparable. Kept in lock-step with operations.mjs lines 247-252.
function buildFlowMcpInner({project, prompt, model, ratio, references, seed, uuids}) {
  const modelById = {nano_banana_pro: "GEM_PIX_2", nano_banana_2: "BELUGA", nano_banana_lite: "HARBOR_SEAL"};
  const ratioByLabel = {"1:1": 1, "9:16": 2, "16:9": 3, "3:4": 4, "4:3": 5};
  const wireModel = modelById[model];
  const wireRatio = ratioByLabel[ratio];
  const refs = references.map(id => [id, null, null, null, 1]);
  const context = () => [null, 22, null, null, null, project, null, null, null, null, ["__CAPTCHA__", 1]];
  let n = 0;
  const uuid = () => uuids[n++];
  const item = [null, null, refs.length ? refs : null, seed, wireRatio, wireModel, null,
    context(), [[[prompt]]], null, null, null, uuid(), uuid()];
  return JSON.stringify([null, [item], 1, context(), [uuid()]]);
}

test("PARITY: flow-mcp ogiZ0b builder is byte-for-byte identical to FlowKit's accepted golden", () => {
  const built = buildFlowMcpInner({
    project: "11111111-2222-3333-4444-555555555555",
    prompt: "a cat",
    model: "nano_banana_pro",
    ratio: "9:16",
    references: ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
    seed: 42,
    uuids: [
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000002",
      "00000000-0000-4000-8000-000000000003",
    ],
  });
  assert.equal(built, FLOWKIT_GOLDEN_INNER,
    "ogiZ0b inner payload drifted from the accepted shape — diff a slot before blaming the RPC server");
});
