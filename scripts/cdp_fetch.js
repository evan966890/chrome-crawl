#!/usr/bin/env node
// cdp_fetch.js — Fetch a URL via Chrome CDP and write HTML to file
// Usage: node cdp_fetch.js <cdp_port> <url> <output_file>
//
// Uses the real Chrome TLS fingerprint to avoid WeChat anti-crawl detection.
// Reuses an existing about:blank or mp.weixin tab (creates one if needed).

const fs = require("fs");

const CDP_PORT = process.argv[2];
const TARGET_URL = process.argv[3];
const OUTPUT_FILE = process.argv[4];

if (!CDP_PORT || !TARGET_URL || !OUTPUT_FILE) {
  console.error("Usage: node cdp_fetch.js <port> <url> <output_file>");
  process.exit(1);
}

let mid = 0;
const pending = new Map();
const eventHandlers = [];

function setupWs(ws) {
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id !== undefined && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result || {});
      return;
    }
    if (msg.method) {
      for (const h of eventHandlers) h(msg.method, msg.params);
    }
  });
}

function send(ws, method, params = {}) {
  const id = ++mid;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

function waitForEvent(name, timeout = 30000) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeout);
    const handler = (evName, params) => {
      if (evName === name) {
        clearTimeout(timer);
        const idx = eventHandlers.indexOf(handler);
        if (idx >= 0) eventHandlers.splice(idx, 1);
        resolve(params);
      }
    };
    eventHandlers.push(handler);
  });
}

async function findOrCreateTab() {
  const resp = await fetch(`http://127.0.0.1:${CDP_PORT}/json`);
  const tabs = await resp.json();

  // Reuse an existing blank or WeChat tab (must have wsUrl available)
  let tab = tabs.find(
    (t) =>
      t.type === "page" &&
      t.webSocketDebuggerUrl &&
      (t.url === "about:blank" ||
        t.url.startsWith("https://mp.weixin.qq.com"))
  );

  if (!tab) {
    const r = await fetch(
      `http://127.0.0.1:${CDP_PORT}/json/new?about:blank`,
      { method: "PUT" }
    );
    tab = await r.json();
  }

  if (!tab.webSocketDebuggerUrl) {
    throw new Error("No WebSocket URL for tab " + tab.id);
  }
  return tab;
}

async function main() {
  const tab = await findOrCreateTab();
  const ws = new WebSocket(tab.webSocketDebuggerUrl);

  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve);
    ws.addEventListener("error", reject);
    setTimeout(() => reject(new Error("WS connect timeout")), 5000);
  });
  setupWs(ws);

  // Navigate and wait for load
  await send(ws, "Page.enable");
  const loadPromise = waitForEvent("Page.loadEventFired", 30000);
  await send(ws, "Page.navigate", { url: TARGET_URL });
  await loadPromise;

  // Brief wait for WeChat JS to populate content
  await new Promise((r) => setTimeout(r, 1500));

  // Extract full HTML
  const evalResult = await send(ws, "Runtime.evaluate", {
    expression: "document.documentElement.outerHTML",
    returnByValue: true,
  });

  const html = evalResult.result?.value || "";
  fs.writeFileSync(OUTPUT_FILE, html, "utf-8");

  // Output byte count for the caller
  console.log(html.length);

  ws.close();
  process.exit(0);
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

// Hard timeout
setTimeout(() => {
  console.error("Global timeout (45s)");
  process.exit(1);
}, 45000);
