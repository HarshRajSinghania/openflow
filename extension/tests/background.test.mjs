import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const tick = () => new Promise(resolve => setImmediate(resolve));
const source = readFileSync(new URL("../background.js", import.meta.url), "utf8");
const inspectSource = source.slice(source.indexOf("function inspectPage()"), source.indexOf("async function inspect(tabId"));
const email = "reader@example.test";
function node(label, text = "", attrs = {}) {
  return {
    innerText: text, parentElement: null, hidden: false,
    getAttribute: key => ({"aria-label": label, ...attrs})[key] ?? null,
    getClientRects: () => [1], querySelectorAll: () => []
  };
}
function observe({labels = [`Conta do Google: Test Reader (${email}), Assinatura do Google`],
  text = "143 créditos do Google Flow", dialogEmail = email, href = `https://accounts.google.com/AccountChooser?Email=${email}`,
  closed = false, hidden = false, duplicate = false, extraDialog = false, linkHidden = false,
  dialogLabel = "Configurações da conta", cssHidden = false, ariaHidden = false} = {}) {
  const link = node(null, text, href === null ? {} : {href});
  const dialog = node(dialogLabel, dialogEmail, ariaHidden ? {"aria-hidden": "true"} : {});
  dialog.hidden = hidden;
  link.parentElement = dialog;
  link.hidden = linkHidden;
  dialog.querySelectorAll = () => duplicate ? [link, link] : [link];
  const context = vm.createContext({URL, Date, location: {origin: "https://flow.google.com", pathname: "/"},
    getComputedStyle: current => ({display: cssHidden && current === dialog ? "none" : "block", visibility: "visible", opacity: "1"}),
    document: {querySelectorAll: selector => selector.startsWith("button") ? labels.map(label => node(label)) :
      closed ? [] : extraDialog ? [dialog, dialog] : [dialog]}});
  return vm.runInContext(`${inspectSource}; inspectPage()`, context);
}

test("localized current account and dialog credits are read without UI side effects", () => {
  for (const [text, credits] of [["143 créditos do Google Flow", 143], ["1.234 créditos do Google Flow", 1234],
    ["1,234 Google Flow credits", 1234], ["1\u202f234 créditos do Google Flow", 1234], ["0 Google Flow credits", 0]]) {
    const result = observe({text});
    assert.equal(result.email, email);
    assert.equal(result.credits, credits);
    assert.equal(result.credits_source, "account_settings_dialog");
    assert.ok(Number.isFinite(Date.parse(result.observed_at)));
  }
  assert.equal(observe({labels: [`Google Account: Reader (${email})`]}).email, email);
  assert.equal(observe({href: null}).credits, 143);
  assert.equal(observe({dialogEmail: ""}).credits, 143);
  assert.equal(observe({dialogEmail: "", href: null}).credits, null);
  assert.equal(observe({dialogLabel: "Account settings", text: "143 Google Flow credits"}).credits, 143);
});

test("closed, hidden, ambiguous and mismatched account evidence fails closed", () => {
  for (const options of [{closed: true}, {hidden: true}, {cssHidden: true}, {ariaHidden: true},
    {dialogLabel: "Unrelated settings"}, {linkHidden: true}, {duplicate: true}, {extraDialog: true},
    {dialogEmail: "other@example.test"}, {dialogEmail: `${email} other@example.test`},
    {href: "https://accounts.google.com/AccountChooser?Email=other@example.test"},
    {href: "https://accounts.google.com/AccountChooser"}, {href: "javascript:alert(1)"},
    {text: "143 unrelated credits"}, {text: "1,23 Google Flow credits"}, {text: "143 créditos do Google Flow extra"}]) {
    const result = observe(options);
    assert.equal(result.email, email);
    assert.equal(result.credits, null);
    assert.equal(result.credits_source, "unavailable");
  }
  for (const labels of [[], [`Google Account: ${email}`, "Conta do Google: other@example.test"],
    [`Google Account: ${email} other@example.test`]]) {
    const result = observe({labels});
    assert.equal(result.email, null);
    assert.equal(result.credits, null);
    assert.equal(result.observed_at, null);
  }
});

test("account panel opens once, preserves an existing panel and rejects ambiguous controls", async () => {
  const panelSource = source.slice(source.indexOf("async function accountPanel("), source.indexOf("function inspectPage()"));
  let open = false;
  let clicks = 0;
  const close = node("Fechar painel da conta");
  close.click = () => { open = false; clicks++; };
  const dialog = node("Configurações da conta");
  dialog.querySelectorAll = () => [close];
  const button = node("Detalhes da conta");
  button.click = () => { open = true; clicks++; };
  let buttons = [button];
  const context = vm.createContext({setTimeout, getComputedStyle: () => ({visibility: "visible"}),
    document: {querySelectorAll: selector => selector.startsWith("[role=") ? (open ? [dialog] : []) : buttons}});
  const run = action => vm.runInContext(`${panelSource}; accountPanel(${JSON.stringify(action)})`, context);
  assert.equal(await run("open"), true);
  assert.equal(await run("open"), false);
  assert.equal(clicks, 1);
  assert.equal(await run("close"), true);
  buttons = [button, button];
  await assert.rejects(run("open"), /account_control_unavailable/);
  assert.equal(clicks, 2);
});

test("project creation uses MAIN RPC and keeps the same document without navigation", async () => {
  const {sameScope} = await import("../protocol.mjs");
  const helper = source.slice(source.indexOf("async function createProject("), source.indexOf("async function dispatch("));
  const scope = {tab_id: 7, origin: "https://flow.google.com", project_id: null, document_id: "old"};
  const next = {...scope, project_id: "12345678-1234-1234-1234-123456789abc"};
  let sends = 0;
  let account = email;
  const context = vm.createContext({scope, sameScope, inspectPage() {}, flowOperation() {},
    inspect: async () => scope,
    chrome: {scripting: {executeScript: async spec => {
      assert.equal(spec.target.documentIds[0], "old");
      if (spec.world === "ISOLATED") return [{frameId: 0, documentId: "old", result: {email: account}}];
      sends++;
      assert.equal(spec.world, "MAIN");
      assert.equal(spec.args[0], "create_project");
      assert.equal(spec.args[1].title, "Título background");
      return [{frameId: 0, documentId: "old", result: {scope, state: "completed", selected: next}}];
    }}}});
  vm.runInContext(`let derived = null; let epoch = 0; let selected = scope; ${helper}`, context);
  assert.equal((await vm.runInContext('createProject(scope, 0, false, "Título background")', context)).state, "completed");
  assert.equal(vm.runInContext("selected", context), next);
  assert.equal(vm.runInContext("derived.email", context), email);
  account = null;
  assert.equal((await vm.runInContext('createProject(scope, 0, false, "Título background")', context)).state, "not_submitted");
  assert.equal(sends, 1);
  assert.ok(!source.includes("clickNewProject"));
});

test("derived project inspection requires original document, page and account", async () => {
  const {sameScope, flowScope} = await import("../protocol.mjs");
  const helper = source.slice(source.indexOf("async function inspect(tabId"), source.indexOf("async function select("));
  const page = {tab_id: 7, origin: "https://flow.google.com", project_id: null, document_id: "doc"};
  const scope = {...page, project_id: "12345678-1234-1234-1234-123456789abc"};
  let account = email;
  let documentId = "doc";
  const context = vm.createContext({sameScope, flowScope, inspectPage() {}, scope,
    derived: {page, scope, email}, chrome: {
      tabs: {get: async () => ({url: "https://flow.google.com/", status: "complete"})},
      scripting: {executeScript: async () => [{frameId: 0, documentId,
        result: {origin: page.origin, pathname: "/", email: account}}]}
    }});
  vm.runInContext(helper, context);
  const run = () => vm.runInContext("inspect(7, scope)", context);
  assert.equal((await run()).project_id, scope.project_id);
  account = "other@example.test";
  await assert.rejects(run(), /scope_changed/);
  account = null;
  await assert.rejects(run(), /scope_changed/);
  account = email;
  documentId = "new";
  await assert.rejects(run(), /scope_changed/);
});

test("home probe pins actual document before and after without deriving a project", async () => {
  const {sameScope, flowScope} = await import("../protocol.mjs");
  const helper = source.slice(source.indexOf("async function inspect(tabId"), source.indexOf("async function connect()"));
  const scope = {tab_id: 7, origin: "https://flow.google.com", project_id: null, document_id: "doc"};
  let documentId = "doc";
  let changeAfter = false;
  let sends = 0;
  const context = vm.createContext({sameScope, flowScope, operationErrorSource: "^rpc_[a-z_]+$",
    scope, inspectPage() {}, flowOperation() {},
    chrome: {
      tabs: {get: async () => ({url: "https://flow.google.com/", status: "complete"})},
      scripting: {executeScript: async spec => {
        assert.deepEqual(Array.from(spec.target.documentIds), ["doc"]);
        if (spec.world === "MAIN") {
          sends++;
          assert.equal(spec.args[0], "probe");
          assert.equal(spec.args[1].scope.project_id, null);
          assert.equal(spec.args[1].page_scope.project_id, null);
          if (changeAfter) documentId = "different";
          return [{frameId: 0, documentId: "doc", result: {scope, state: "completed", rpc_verified: true}}];
        }
        return [{frameId: 0, documentId, result: {origin: scope.origin, pathname: "/"}}];
      }}
    }});
  vm.runInContext(`let selected = scope; let derived = null; let epoch = 0; ${helper}`, context);
  const run = () => vm.runInContext(`dispatch({operation: "probe", params: {scope, input: {project_id: "12345678-1234-1234-1234-123456789abc"}, diagnostics: true}})`, context);
  assert.equal((await run()).rpc_verified, true);
  assert.equal(vm.runInContext("selected.project_id", context), null);
  assert.equal(vm.runInContext("derived", context), null);
  documentId = "different";
  await assert.rejects(run(), /scope_changed/);
  assert.equal(sends, 1);
  documentId = "doc";
  changeAfter = true;
  await assert.rejects(run(), /scope_changed/);
  assert.equal(sends, 2);
});

test("service worker routes only exact selected document and invalidates navigation", async () => {
  let listener;
  let updated;
  let removed;
  const executions = [];
  const socketList = [];
  const tabMap = new Map([
    [7, {id: 7, url: "https://flow.google.com/", status: "complete"}],
    [8, {id: 8, url: "https://flow.google.com/", status: "complete"}]
  ]);
  const config = {secret: "s".repeat(64), nickname: "test",
    installation_id: "12345678-1234-1234-1234-123456789abc"};
  globalThis.chrome = {
    alarms: {
      create: async () => {}, clear: async () => {},
      onAlarm: {addListener: () => {}}
    },
    storage: {local: {
      get: async () => ({...config}), set: async value => Object.assign(config, value),
      setAccessLevel: async () => {}
    }},
    tabs: {
      query: async () => [...tabMap.values()], get: async id => tabMap.get(id),
      onUpdated: {addListener: fn => { updated = fn; }},
      onRemoved: {addListener: fn => { removed = fn; }}
    },
    scripting: {executeScript: async spec => {
      executions.push(spec);
      return [{frameId: 0, documentId: `doc-${spec.target.tabId}`,
        result: {origin: "https://flow.google.com", pathname: "/"}}];
    }},
    runtime: {
      id: "extension", getURL: name => `chrome-extension://extension/${name}`,
      onMessage: {addListener: fn => { listener = fn; }},
      onStartup: {addListener: () => {}}, onInstalled: {addListener: () => {}}
    }
  };
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor(url) { this.url = url; socketList.push(this); }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() { this.readyState = 3; this.onclose?.(); }
  };
  const popup = message => new Promise(resolve => listener(message, {
    id: "extension", url: "chrome-extension://extension/popup.html"
  }, resolve));
  await import("../background.js");
  try {
    await popup({type: "connect"});
    const ws = socketList[0];
    ws.onopen();
    assert.equal(ws.sent[0].type, "hello");
    await ws.onmessage({data: JSON.stringify({type: "paired"})});
    const request = async (operation, params = {}, suffix = "1") => {
      await ws.onmessage({data: JSON.stringify({type: "request",
        id: `12345678-1234-1234-1234-123456789ab${suffix}`, operation, params})});
      return ws.sent.at(-1);
    };
    const selected = await request("select", {tab_id: 7});
    assert.equal(selected.type, "reply");
    assert.equal(selected.result.tab_id, 7);
    assert.ok(!ws.sent.some(message => message.type === "invalidated"));
    assert.deepEqual(executions[0].target, {tabId: 7, frameIds: [0]});
    const account = await request("inspect", {scope: selected.result}, "2");
    assert.deepEqual(executions[1].target, {tabId: 7, documentIds: ["doc-7"]});
    assert.equal(account.result.email, null);
    assert.equal(account.result.credits, null);
    const popupStatus = await popup({type: "status"});
    assert.ok(!JSON.stringify(popupStatus).includes(config.secret));
    updated(8, {status: "loading"});
    assert.equal((await popup({type: "status"})).selected.tab_id, 7);
    updated(7, {status: "loading"});
    assert.equal(ws.sent.at(-1).type, "invalidated");
    assert.equal((await popup({type: "status"})).selected, null);
    const rejected = await request("inspect", {scope: selected.result}, "3");
    assert.equal(rejected.error, "scope_changed");
    assert.equal(executions.length, 7);
    await popup({type: "select", tab_id: 8});
    removed(8);
    assert.equal((await popup({type: "status"})).selected, null);
    await request("eval", {code: "secret"}, "4");
    assert.equal(ws.readyState, 3);
    await tick();
  } finally {
    for (const ws of socketList) ws.close();
    delete globalThis.chrome;
    delete globalThis.WebSocket;
  }
});

test("generation dispatch requests diagnostics and surfaces the rpc code", async () => {
  const source = readFileSync(new URL("../background.js", import.meta.url), "utf8");
  const helper = source.slice(source.indexOf("async function dispatch(message)"),
                              source.indexOf("async function connect()"));
  const {sameScope, validRequest} = await import("../protocol.mjs");
  const {knownOperationErrors} = await import("../operations.mjs");
  const project = "00000000-0000-4000-8000-000000000010";
  const scope = {tab_id: 7, origin: "https://flow.google.com", project_id: project, document_id: "doc"};
  let mainArgs;
  const rejected = {
    scope, state: "submitted_unverified", error: "rpc_rejected",
    diagnostics: {rpc: "ogiZ0b", http_status: 200, chunks: 1, envelopes: 1, rpc_code: 8,
      phase: "parse", rpc_error_shape: {type: "array", length: 1, items: ["number"]}},
  };
  const context = vm.createContext({sameScope, validRequest, operationErrorSource: knownOperationErrors.source,
    flowOperation: (op, params) => { mainArgs = params; return rejected; },
    inspect: async (tabId, pinned) => pinned,
    chrome: {
      tabs: {get: async () => ({url: `https://flow.google.com/project/${project}`, status: "complete", discarded: false})},
      scripting: {executeScript: async spec => {
        if (spec.world === "MAIN") {
          const result = spec.args ? spec.func(...spec.args) : spec.func();
          return [{frameId: 0, documentId: "doc", result}];
        }
        return [{frameId: 0, documentId: "doc",
          result: {origin: scope.origin, pathname: `/project/${project}`}}];
      }}
    }});
  vm.runInContext(`let selected = ${JSON.stringify(scope)}; let derived = null; let epoch = 0; const scope_pre = ${JSON.stringify(scope)}; ${helper}`,
    context);
  const request = {type: "request", id: "12345678-1234-1234-1234-123456789abd",
    operation: "generate_image",
    params: {scope, input: {prompt: "cube", model: "nano_banana_2", ratio: "1:1", references: []}}};
  assert.equal(validRequest(request), true);
  const result = await vm.runInContext(`dispatch(${JSON.stringify(request)})`, context);
  assert.equal(mainArgs.diagnostics, true);
  assert.equal(result.error, "rpc_rejected");
  assert.equal(result.diagnostics.rpc_code, 8);
});
