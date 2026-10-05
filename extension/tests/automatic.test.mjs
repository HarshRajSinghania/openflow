import assert from "node:assert/strict";
import test from "node:test";
import {readFile} from "node:fs/promises";
import vm from "node:vm";

const tick = () => new Promise(resolve => setImmediate(resolve));

test("automatic pairing, discovery, alarm backoff, durable disconnect and worker restart", async () => {
  const config = {};
  const sockets = [];
  const alarms = [];
  const events = {};
  let failImmediately = true;
  let rejectAlarm = false;
  const unhandled = [];
  const onUnhandled = error => unhandled.push(error);
  process.on("unhandledRejection", onUnhandled);
  let activeTabs = [{id: 7, status: "complete", url: "https://flow.google.com/"}];
  const event = name => ({addListener: fn => { events[name] = fn; }});
  globalThis.chrome = {
    storage: {local: {
      get: async () => ({...config}), set: async data => Object.assign(config, data),
      remove: async key => { delete config[key]; }, setAccessLevel: async () => {}
    }},
    alarms: {create: async (name, spec) => {
      if (rejectAlarm) throw new Error("alarm unavailable");
      alarms.push({name, ...spec});
      await tick();
    },
      clear: async () => {}, onAlarm: event("alarm")},
    tabs: {query: async () => activeTabs, get: async id => activeTabs.find(t => t.id === id),
      onUpdated: event("updated"), onRemoved: event("removed")},
    scripting: {executeScript: async spec => [{frameId: 0, documentId: `doc-${spec.target.tabId}`,
      result: {origin: "https://flow.google.com", pathname: "/"}}]},
    runtime: {id: "test", getURL: name => `chrome-extension://test/${name}`,
      onMessage: event("message"), onStartup: event("startup"), onInstalled: event("installed")}
  };
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor(url) {
      this.url = url;
      sockets.push(this);
      if (failImmediately) queueMicrotask(() => {
        assert.equal(typeof this.onerror, "function");
        assert.equal(typeof this.onclose, "function");
        this.onerror({});
        void this.close();
      });
    }
    send(data) { this.sent.push(JSON.parse(data)); }
    close(code = 1006, reason = "") { this.readyState = 3; return this.onclose?.({code, reason}); }
  };
  const popup = message => new Promise(resolve => events.message(message,
    {id: "test", url: "chrome-extension://test/popup.html"}, resolve));
  const incoming = (ws, message) => ws.onmessage({data: JSON.stringify(message)});
  try {
    await import(`../background.js?auto=1`);
    await tick();
    await tick();
    assert.equal(sockets[0].readyState, 3);
    assert.equal((await popup({type: "status"})).status, "waiting");
    assert.equal((await popup({type: "status"})).retry_delay_minutes, 0.5);
    const elements = new Map();
    const document = {getElementById: id => {
      if (!elements.has(id)) elements.set(id, {value: "", replaceChildren() {}});
      return elements.get(id);
    }, createElement: () => ({})};
    const popupSource = await readFile(new URL("../popup.js", import.meta.url), "utf8");
    await vm.runInNewContext(`(async () => {${popupSource}\n})()`, {
      document, chrome: {runtime: {sendMessage: popup}}, setInterval() {}
    });
    assert.equal(elements.get("status").textContent,
      "Aguardando MCP; nova tentativa automática em até 30 s");
    assert.equal(elements.get("enabled").checked, true);
    assert.equal(elements.get("authorization").hidden, true);
    assert.equal((await popup({type: "status"})).pairing_id, null);
    events.alarm({name: "openflow-reconnect"});
    await tick();
    await tick();
    assert.equal((await popup({type: "status"})).status, "waiting");
    assert.equal(alarms.at(-1).delayInMinutes, 1);
    failImmediately = false;
    rejectAlarm = true;
    events.alarm({name: "openflow-reconnect"});
    await tick();
    await tick();
    assert.equal(sockets.at(-1).readyState, 3);
    assert.equal((await popup({type: "status"})).status, "retry_unavailable");
    rejectAlarm = false;
    await popup({type: "connect"});
    const first = sockets.at(-1);
    assert.equal(first.url, "ws://127.0.0.1:9233/");
    first.onopen();
    assert.equal(first.sent[0].type, "pair");
    const identity = config.installation_id;
    assert.ok(identity);
    await incoming(first, {type: "pairing_pending", pairing_id: "safe-code"});
    assert.equal((await popup({type: "status"})).pairing_id, "safe-code");
    await incoming(first, {type: "provisioned", secret: "s".repeat(64)});
    assert.equal(first.sent.at(-1).type, "hello");
    await incoming(first, {type: "paired"});
    assert.equal((await popup({type: "status"})).selected.tab_id, 7);
    activeTabs.push({id: 8, status: "complete", url: "https://flow.google.com/"});
    events.updated(8, {status: "complete"});
    await tick();
    assert.equal((await popup({type: "status"})).selected.tab_id, 7);
    events.updated(7, {status: "loading"});
    assert.equal((await popup({type: "status"})).selected, null);
    events.updated(7, {status: "complete"});
    await tick();
    assert.equal((await popup({type: "status"})).selected, null);
    const realNow = Date.now;
    try {
      const future = realNow() + 46000;
      Date.now = () => future;
      await incoming(first, {type: "pong"});
      assert.equal((await popup({type: "status"})).status, "paired");
      Date.now = () => future + 46000;
      const stale = await popup({type: "status"});
      assert.equal(stale.status, "waiting");
      assert.equal(stale.selected, null);
      assert.equal(first.readyState, 3);
      await tick();
    } finally { Date.now = realNow; }
    assert.equal(alarms.at(-1).delayInMinutes, 0.5);
    for (let i = 0; i < 8; i++) {
      events.alarm({name: "openflow-reconnect"});
      await tick();
      const ws = sockets.at(-1);
      ws.onopen();
      assert.equal(ws.sent[0].type, "hello");
      assert.equal(ws.sent[0].installation_id, identity);
      await ws.close();
      assert.ok(alarms.at(-1).delayInMinutes <= 5);
    }
    assert.equal(alarms.at(-1).delayInMinutes, 5);
    events.alarm({name: "openflow-reconnect"});
    await tick();
    const restarted = sockets.at(-1);
    assert.equal((await popup({type: "status"})).status, "waiting");
    restarted.onopen();
    assert.equal(restarted.sent[0].type, "hello");
    await incoming(restarted, {type: "paired"});
    assert.equal((await popup({type: "status"})).status, "paired");
    assert.equal((await popup({type: "status"})).pairing_id, null);
    assert.equal(config.retryAttempt, 0);
    await restarted.close();
    assert.equal((await popup({type: "status"})).status, "waiting");
    assert.equal((await popup({type: "status"})).enabled, true);
    await tick();
    const get = chrome.storage.local.get;
    let releaseRead;
    chrome.storage.local.get = () => new Promise(resolve => {
      const snapshot = {...config};
      releaseRead = () => resolve(snapshot);
    });
    events.alarm({name: "openflow-reconnect"});
    await tick();
    const beforeDisable = sockets.length;
    await popup({type: "disconnect"});
    releaseRead();
    chrome.storage.local.get = get;
    await tick();
    assert.equal(sockets.length, beforeDisable);
    const count = sockets.length;
    events.alarm({name: "openflow-reconnect"});
    events.startup();
    await tick();
    assert.equal(sockets.length, count);
    await import(`../background.js?auto=2`);
    events.installed();
    events.startup();
    events.alarm({name: "openflow-reconnect"});
    await tick();
    assert.equal(sockets.length, count);
    assert.equal((await popup({type: "status"})).enabled, false);
    assert.equal(config.disabled, true);
    elements.get("enabled").checked = true;
    await elements.get("enabled").onchange();
    assert.equal(sockets.length, count + 1);
    const ws = sockets.at(-1);
    ws.onopen();
    await ws.close(1000, "revoked");
    assert.equal(config.secret, undefined);
    assert.equal(config.disabled, true);
    await popup({type: "connect"});
    sockets.at(-1).onopen();
    assert.equal(sockets.at(-1).sent[0].type, "pair");
    await popup({type: "disconnect"});
    await tick();
    assert.equal((await popup({type: "status"})).status, "disconnected");
    assert.deepEqual(unhandled, []);
  } finally {
    process.removeListener("unhandledRejection", onUnhandled);
    for (const ws of sockets) if (ws.readyState !== 3) await ws.close();
    delete globalThis.chrome;
    delete globalThis.WebSocket;
  }
});
