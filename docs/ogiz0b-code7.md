# rpc_code 7 on ogiZ0b (generate_image) — diagnosis

Historical diagnosis: this document records the investigation before the bypass was implemented. Statements about missing implementation and failing tests describe that earlier state, not the current code.

Evidence gathered read-only; no generation was submitted while
producing this. Live symptom: image submit reached a Google `HTTP 200`
batchexecute envelope carrying an error slot `[7, null, [[[]]]]` — i.e.
`entry[5] = [7, null, [[[]]]]`, code `7`, empty detail.

## What the envelope code is

`operations.mjs:parse()` reads the batchexecute error slot as
`entry[5]?.[0]` (`operations.mjs:97-101`). On the batch transport that slot is a
**bare integer code**, not the REST `PUBLIC_ERROR_*` reason:

- `flowkit/agent/services/flow_batch.py:310-314` — "index 5 is the error slot;
  it is `[5]`-style codes, not text".
- `flowkit/docs/IMAGE_API.md:41-47` — FlowKit treats image RPC `[8]` as a
  *transient* rejection ("seen under image load") and retries it once after a
  34 s cooldown (`flow_client.py:44-49`, `728-743`).
- The reason strings (`PUBLIC_ERROR_UNSAFE_GENERATION` etc.) belong to the old
  REST path and to the worker taxonomy (`flowkit/skills/fk-doctor.md:91-101`);
  they do not arrive as `[7]`.

So `7` is a distinct Flow-side rejection code, in the same family as `8`, and
the empty detail block (`[[[]]]`) means Google encoded **no reason text** — the
message is the code alone.

## What is NOT the cause (ruled out with evidence)

1. **Request content / builder diff** — ruled out. flow-mcp's `ogiZ0b` inner
   payload is byte-for-byte identical to FlowKit's accepted golden:
   - flow-mcp builder: `extension/operations.mjs:247-252`
   - FlowKit golden: `flowkit/tests/unit/test_flow_batch_golden.py:36-46,70-74`
   - proof: `extension/tests/ogiz0b_parity.test.mjs` (passes). Every slot
     matches — reference array `[id,null,null,null,1]`, seed, aspect `2` for
     `9:16`, model `"GEM_PIX_2"`, the 14-slot item, the `[null,22,…,[captcha,1]]`
     context, and the `[null,[item],1,context,[uuid]]` envelope.

2. **Aspect numeric mapping** — matches (`1:1→1 … 4:3→5`, `operations.mjs:249`;
   `flow_batch.py:78-99`).

3. **Model wire id** — matches (`nano_banana_pro→GEM_PIX_2`,
   `operations.mjs:248`; `flow_batch.py:63-72`).

4. **Count / reference shape / context slot / client descriptor** — match; see
   parity test.

5. **Page base path `/u/1`** — not the cause. flow-mcp builds the endpoint from
   `WIZ_global_data.eptZe` or defaults to `/_/AiSandboxAngularFrontend/`, and its
   own regex accepts an optional `/u/N/` prefix (`operations.mjs:126-129`);
   `source-path` is `location.pathname` (`operations.mjs:122`), matching
   FlowKit's `location.pathname` (`flowkit/extension/background.js:613`).

6. **Missing required field / project-session mismatch / region-tier** — the
   envelope was accepted (HTTP 200, one `wrb.fr` envelope with our rpc id) and
   the project id rode the same `[null,22,…,project,…]` context FlowKit
   accepts. A missing field or unknown id would surface as a data error, not a
   bare code with empty detail.

## The suspected cause: captcha action poisoned by Flow's x2a trap

flow-mcp mints the reCAPTCHA with the **raw public** `grecaptcha.enterprise.execute`:

- `extension/operations.mjs:201-218` — reads `globalThis.grecaptcha.enterprise`,
  then `enterprise.execute([...keys][0], {action})`.

That call runs from `flowOperation`, injected at operation time in the page MAIN
world (`background.js:336-341`). Flow's frontend ships a trap (documented as
`x2a`) that **overwrites `grecaptcha.enterprise.execute`** so every token minted
through the public function carries `action: "extension_hijack_detected"`
instead of `IMAGE_GENERATION`. The backend then refuses the generation.

FlowKit works only because it defeats that trap:

- `flowkit/extension/hijack_bypass.js` — captured the **pristine** execute at
  `document_start` (via `manifest.json` `content_scripts`), before x2a replaced
  it; exposed as `window.__fk_hijack.pristine`.
- `flowkit/extension/injected.js:108-118,153-192` — `executeWithPristine`
  prefers that pristine function; a fallback neuters `Object.assign`.
- `flowkit/extension/background.js:611-619` — even comments that the trap
  behavior forced matching Flow's own WIZ metadata.
- Introduced in flowkit commit `083fed7` "feat: bypass
  extension_hijack_detected + Trusted Types CSP" (v0.5.2, 2026-09-25), which
  also distinguishes `[HIJACK]` errors (`flow_client.py:563-582`) from real
  abuse blocks and stops burning retry counts (`processor.py:450-461`).

**flow-mcp has no equivalent.** `extension/manifest.json` declares **no
`content_scripts`** at all, so there is no document_start capture and no
pristine execute. It therefore always mints through the trapped public API.

Two independent lines point at the trap rather than abuse:

- The action FlowKit guards against is exactly the one that would be rejected
  after a *content* rejection is ruled out.
- Code `7` with **empty detail** fits a system-level trap rejection better than
  a content/safety rejection, which normally carries a reason block.

Residual uncertainty: the mapping of integer code `7` (vs the known-transient
`8`) to specifically the hijack path is inferred, not captured. `8` is
documented; `7` is not. Confirming the mapping is the point of the experiment
below.

## Smallest non-paid experiment to confirm

Do **not** submit a generation. Instead, prove the mint is poisoned, which is
free and needs no credits:

1. Open the signed-in `https://flow.google.com` Flow tab the extension targets.
2. In DevTools console (page MAIN world), run the same mint flow-mcp uses and
   inspect the action the token was actually minted for, and whether a wrapper
   is present:

   ```js
   const exec = grecaptcha.enterprise.execute;
   console.log(String(exec).includes("extension_hijack_detected")); // true => trapped
   console.log(typeof window.__fk_hijack?.pristine);                 // "function" if a bypass captured it
   ```

   - `grecaptcha.enterprise.execute.toString()` containing
     `extension_hijack_detected` ⟹ the public path is trapped (root cause
     confirmed).
   - `window.__fk_hijack?.pristine` undefined ⟹ flow-mcp has no pristine path,
     so its mint is poisoned.

3. Optional, still free: mint one token from each path and compare the `action`
   claim carried inside the token payload (decode the JWT-ish blob's `action`
   field) — public vs pristine. They must differ.

4. Only after (2) confirms the trap: the paid A/B is one image submit each
   through (a) the current public-execute path and (b) a pristine-capture path.
   (a) should reproduce code `7`; (b) should return a signed CDN url. Do this
   manually, single-shot, and only if you are willing to spend the credits.

## Exact fix if (2) confirms the trap

Port FlowKit's bypass into flow-mcp (no builder change — the payload is already
correct):

1. Add `extension/hijack_bypass.js` replicating `flowkit/extension/hijack_bypass.js`
   (three-level `defineProperty` capture of `grecaptcha.enterprise.execute`,
   plus the 2 ms poll and `ready()` race; verify `toString()` excludes
   `extension_hijack_detected`; expose `window.__fk_hijack.pristine`).
2. Register it as a `content_scripts` entry with `"run_at": "document_start"`,
   `"world": "MAIN"`, matching `https://flow.google.com/*` in
   `extension/manifest.json` (currently absent).
3. In `extension/operations.mjs` (`generate_image`/`generate_video`/upscale),
   replace the direct `enterprise.execute(...)` call (lines 214-217) with a mint
   that prefers `globalThis.__fk_hijack?.pristine`, falling back to a
   `Object.assign` neuter, and **refuses to submit** if only the trapped public
   path is available (raise `native_recaptcha_hijack_suspected`) instead of
   burning a paid generation.
4. Flip the guard in `extension/tests/ogiz0b_hijack_contract.test.mjs` from the
   failing expectation to the passing one.

## Tests added (read-only otherwise)

- `extension/tests/ogiz0b_parity.test.mjs` — **passes**; proves the builder is
  not the cause by locking flow-mcp's inner payload to FlowKit's golden.
- `extension/tests/ogiz0b_hijack_contract.test.mjs` — **fails by design**;
  codifies that a hijack-poisoned mint must not be submitted. It goes green when
  the bypass above is ported.
