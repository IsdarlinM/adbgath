const $ = (selector) => document.querySelector(selector);
const output = $("#output");
let socket = null;

function show(value) {
  output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

async function execute(action, payload = {}, destructive = false) {
  const response = await fetch("/api/execute", {
    method: "POST",
    credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({action, payload, confirmation: destructive ? "AUTHORIZED" : null}),
  });
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body.data;
}

function endpointButton(service, type) {
  const button = document.createElement("button");
  button.textContent = type === "pairing" ? "Use for pairing" : "Use for connection";
  button.addEventListener("click", () => {
    const field = type === "pairing" ? $("#pairEndpoint") : $("#connectEndpoint");
    field.value = service.endpoint;
    field.focus();
  });
  return button;
}

function renderServices(data) {
  const root = $("#services");
  const services = data.services || [];
  $("#serviceCount").textContent = `${services.length} service${services.length === 1 ? "" : "s"}`;
  root.replaceChildren();
  root.classList.toggle("empty", services.length === 0);
  if (!services.length) {
    root.textContent = "No ADB mDNS services discovered. You can still enter Android's displayed endpoints manually.";
    return;
  }
  for (const service of services) {
    const item = document.createElement("article");
    item.className = `service-item ${service.service_type}`;
    const heading = document.createElement("div");
    heading.innerHTML = `<strong>${service.service_type === "pairing" ? "Pairing" : "Connection"}</strong><code>${service.endpoint}</code>`;
    const details = document.createElement("p");
    details.textContent = [service.given_name, service.model, service.serial, service.hostname].filter(Boolean).join(" · ") || service.instance;
    item.append(heading, details, endpointButton(service, service.service_type));
    root.append(item);
  }
}

function renderHealth(status) {
  const server = status.server_status || {};
  const health = $("#wirelessHealth");
  const services = status.discovery?.services?.length || 0;
  health.innerHTML = `<strong>ADB ${status.adb_version || "unknown"}</strong><span>mDNS: ${server.mdns_enabled === true ? "enabled" : "unavailable"}</span><span>Backend: ${server.mdns_backend || "unknown"}</span><span>${services} services discovered</span>`;
}

function renderDiagnostics(data) {
  const root = $("#diagnostics");
  root.replaceChildren();
  for (const check of data.checks || []) {
    const item = document.createElement("div");
    item.className = check.ok ? "diagnostic ok" : "diagnostic warning";
    item.innerHTML = `<strong>${check.ok ? "✓" : "△"} ${check.name}</strong><span>${String(check.value)}</span><small>${check.ok ? "" : check.recommendation || "Review this item."}</small>`;
    root.append(item);
  }
}

async function loadKnown() {
  const known = await execute("wireless_known");
  const root = $("#known");
  root.replaceChildren();
  root.classList.toggle("empty", known.length === 0);
  if (!known.length) {
    root.textContent = "No known targets.";
    return;
  }
  for (const target of known) {
    const item = document.createElement("article");
    item.className = "known-item";
    const title = target.alias || target.given_name || target.model || target.serial || target.instance || target.id;
    item.innerHTML = `<div><strong>${title}</strong><span>${target.last_host || "unknown host"}${target.connect_port ? `:${target.connect_port}` : ""}</span><small>${target.state} · last seen ${target.last_seen}</small></div>`;
    const controls = document.createElement("div");
    const alias = document.createElement("button");
    alias.textContent = "Alias";
    alias.addEventListener("click", async () => {
      const value = window.prompt("Local alias", target.alias || "");
      if (!value) return;
      try { show(await execute("wireless_alias", {identifier: target.id, alias: value})); await loadKnown(); }
      catch (error) { show({ok: false, error: error.message}); }
    });
    const forget = document.createElement("button");
    forget.textContent = "Forget local record";
    forget.addEventListener("click", async () => {
      if (!window.confirm("Remove only ADB-Gath's local record? Android trust must be revoked on the device.")) return;
      try { show(await execute("wireless_forget", {identifier: target.id}, true)); await loadKnown(); }
      catch (error) { show({ok: false, error: error.message}); }
    });
    controls.append(alias, forget);
    item.append(controls);
    root.append(item);
  }
}

async function refresh() {
  try {
    const status = await execute("wireless_status", {discover: true});
    renderHealth(status);
    renderServices(status.discovery || {services: []});
    await loadKnown();
    show(status);
  } catch (error) {
    show({ok: false, error: error.message});
  }
}

$("#discover").addEventListener("click", async () => {
  try { const data = await execute("wireless_discover", {refresh: true, detailed: true}); renderServices(data); show(data); await loadKnown(); }
  catch (error) { show({ok: false, error: error.message}); }
});

$("#pair").addEventListener("click", async () => {
  const endpoint = $("#pairEndpoint").value.trim();
  const field = $("#pairCode");
  const code = field.value.trim();
  try {
    if (!/^\d{6}$/.test(code)) throw new Error("Enter the six-digit code shown by Android.");
    const result = await execute("wireless_pair", {target: endpoint, pairing_code: code}, true);
    show(result);
    await refresh();
  } catch (error) {
    show({ok: false, error: error.message});
  } finally {
    field.value = "";
  }
});

$("#connect").addEventListener("click", async () => {
  try { show(await execute("wireless_connect", {target: $("#connectEndpoint").value.trim()})); await refresh(); }
  catch (error) { show({ok: false, error: error.message}); }
});

$("#disconnect").addEventListener("click", async () => {
  try { show(await execute("wireless_disconnect", {target: $("#connectEndpoint").value.trim()})); await refresh(); }
  catch (error) { show({ok: false, error: error.message}); }
});

$("#autoConnect").addEventListener("click", async () => {
  try { show(await execute("wireless_auto_connect")); await refresh(); }
  catch (error) { show({ok: false, error: error.message}); }
});

$("#diagnose").addEventListener("click", async () => {
  try { const data = await execute("wireless_diagnose", {fix: false, persist: false}); renderDiagnostics(data); show(data); }
  catch (error) { show({ok: false, error: error.message}); }
});

$("#repair").addEventListener("click", async () => {
  if (!window.confirm("Write ADB-Gath-scoped mDNS settings and restart the local ADB server?")) return;
  try { const data = await execute("wireless_diagnose", {fix: true, persist: true}); renderDiagnostics(data); show(data); await refresh(); }
  catch (error) { show({ok: false, error: error.message}); }
});

$("#watch").addEventListener("click", () => {
  if (socket) {
    socket.close();
    socket = null;
    $("#watch").textContent = "Start live watch";
    return;
  }
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${location.host}/ws/wireless`);
  socket.onopen = () => { $("#watch").textContent = "Stop live watch"; };
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.ok) renderServices(message.data);
  };
  socket.onerror = () => show({ok: false, error: "Wireless discovery WebSocket failed."});
  socket.onclose = () => { socket = null; $("#watch").textContent = "Start live watch"; };
});

$("#refreshAll").addEventListener("click", refresh);
refresh();
