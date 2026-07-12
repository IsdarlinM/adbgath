"use strict";

const state = {
  devices: [],
  packages: [],
  artifacts: [],
  uploads: [],
  destructive: new Set(),
  socket: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const ACTIONS = {
  devices: { label: "Devices / list connected targets", fields: [] },
  connect: { label: "Devices / wireless connect", fields: [{name:"target", label:"Host and port", placeholder:"192.168.1.50:5555", required:true}] },
  disconnect: { label: "Devices / wireless disconnect", fields: [{name:"target", label:"Host and port", placeholder:"192.168.1.50:5555", required:true}] },
  users: { label: "Inventory / Android users and profiles", fields: [] },
  packages: { label: "Inventory / installed packages", fields: [{name:"include_paths", label:"Include APK paths", type:"checkbox"},{name:"system", label:"Package scope", type:"select", options:[["","All"],["true","System"],["false","Third-party"]]}] },
  paths: { label: "Apps / resolve APK paths", fields: [{name:"package", label:"Optional package name", placeholder:"Blank lists all APK paths"}] },
  download: { label: "APKs / download packages or remote paths", fields: [{name:"packages", label:"Packages (comma-separated)", placeholder:"com.example.one, com.example.two", full:true},{name:"remote_paths", label:"Remote APK paths (comma-separated)", placeholder:"/data/app/.../base.apk", full:true},{name:"output", label:"Output directory", placeholder:"Leave empty for workspace/apks", full:true}] },
  install: { label: "APKs / install staged files", danger:true, fields: [{name:"files", label:"Local APK paths (comma-separated)", placeholder:"Use an uploaded file path", full:true, required:true},{name:"replace_existing", label:"Replace existing application", type:"checkbox"},{name:"grant_runtime_permissions", label:"Grant runtime permissions", type:"checkbox"}] },
  uninstall: { label: "APKs / uninstall packages", danger:true, fields: [{name:"packages", label:"Packages (comma-separated)", placeholder:"com.example.app", full:true, required:true},{name:"keep_data", label:"Keep app data", type:"checkbox"}] },
  replace: { label: "APKs / replace package with staged APK", danger:true, fields: [{name:"package", label:"Package", placeholder:"com.example.app"},{name:"file", label:"Replacement APK path", placeholder:"Workspace upload path"},{name:"replacement_pairs", label:"Optional batch pairs: APK_PATH PACKAGE (one per line)", placeholder:"C:\\path\\app.apk com.example.app", full:true}] },
  info: { label: "Device / information", fields: [{name:"mode", label:"Information profile", type:"select", options:[["basic","Basic"],["system","System"],["network","Network"],["security","Security"],["all","All"]]}] },
  app: { label: "Apps / package summary and permissions", fields: [{name:"package", label:"Package name", placeholder:"com.example.app", required:true}] },
  runtime: { label: "Runtime / processes, activities, services", fields: [{name:"mode", label:"Runtime view", type:"select", options:[["summary","Summary"],["processes","Processes"],["activities","Activities"],["services","Services"]]},{name:"package", label:"Optional package", placeholder:"com.example.app"}] },
  logs_capture: { label: "Logs / timed logcat capture", fields: [{name:"package", label:"Package filter", placeholder:"com.example.app"},{name:"pid", label:"PID", type:"number"},{name:"regex", label:"Regex", placeholder:"token|password|exception"},{name:"duration", label:"Duration (seconds)", type:"number", value:"30"},{name:"format", label:"Logcat format", type:"select", options:[["threadtime","threadtime"],["brief","brief"],["time","time"],["process","process"]]},{name:"clear", label:"Clear buffer first", type:"checkbox"},{name:"output", label:"Output file", placeholder:"Leave empty for workspace/logs", full:true}] },
  logs_clear: { label: "Logs / clear logcat buffer", fields: [] },
  sniff_interfaces: { label: "Network / list device interfaces", fields: [] },
  sniff_capture: { label: "Network / rooted tcpdump capture", fields: [{name:"interface", label:"Interface", value:"wlan0"},{name:"duration", label:"Duration (seconds)", type:"number", value:"30"},{name:"output", label:"Output PCAP", placeholder:"Leave empty for workspace/captures", full:true}] },
  push_tcpdump: { label: "Network / push tcpdump binary", danger:true, fields: [{name:"file", label:"Local tcpdump path", placeholder:"Workspace upload path", required:true, full:true}] },
  proxy: { label: "Network / global HTTP proxy", danger:true, fields: [{name:"mode", label:"Proxy action", type:"select", options:[["show","Show"],["set","Set"],["clear","Clear"]]},{name:"spec", label:"Proxy host and port", placeholder:"127.0.0.1:8080"}] },
  forward: { label: "Network / ADB TCP mapping", danger:true, fields: [{name:"mode", label:"Mapping direction", type:"select", options:[["forward","Forward"],["reverse","Reverse"]]},{name:"local_port", label:"Local port", type:"number", value:"8080"},{name:"remote_port", label:"Remote port", type:"number", value:"8080"}] },
  backup: { label: "Evidence / debuggable app data backup", fields: [{name:"package", label:"Package", placeholder:"com.example.app", required:true},{name:"output", label:"Output TAR", placeholder:"Leave empty for workspace/backups"}] },
  content: { label: "Apps / content providers", fields: [{name:"package", label:"Optional package filter", placeholder:"com.example.app"}] },
  frida: { label: "Instrumentation / Frida tools", fields: [{name:"mode", label:"Frida action", type:"select", options:[["ps","List apps/processes"],["attach","Attach"],["spawn","Spawn"]]},{name:"package", label:"Package", placeholder:"com.example.app"},{name:"script", label:"Optional script path", placeholder:"Workspace upload path", full:true}] },
  static: { label: "Static / local APK analysis", fields: [{name:"file", label:"Local APK path", placeholder:"Workspace upload path", required:true, full:true},{name:"output", label:"Output JSON", placeholder:"Leave empty for workspace/reports", full:true}] },
  security: { label: "Security / device posture audit", fields: [{name:"output", label:"Output JSON", placeholder:"Leave empty for workspace/reports", full:true}] },
  collect: { label: "Evidence / full device collection", fields: [{name:"output", label:"Output directory", placeholder:"Leave empty for workspace/collections", full:true}] },
  mastg: { label: "Evidence / OWASP MASTG-oriented bundle", fields: [{name:"output", label:"Output directory", placeholder:"Leave empty for workspace/collections", full:true}] },
  doctor: { label: "System / dependency doctor", fields: [] },
  inventory: { label: "Inventory / device and application export", fields: [{name:"output", label:"Optional output JSON", placeholder:"Workspace path", full:true}] },
};

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast show${error ? " error" : ""}`;
  clearTimeout(node._timer);
  node._timer = setTimeout(() => node.className = "toast", 3200);
}

function selectedDevice() { return $("#deviceSelect").value || null; }
function selectedUser() { return $("#userInput").value.trim() || null; }

function setOutput(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  $$('[data-console]').forEach(node => { node.textContent = text; node.scrollTop = node.scrollHeight; });
  collectArtifacts(value);
}

function collectArtifacts(value) {
  const found = [];
  const walk = node => {
    if (!node) return;
    if (Array.isArray(node)) return node.forEach(walk);
    if (typeof node === "object") {
      Object.entries(node).forEach(([key, item]) => {
        if (["artifact", "artifacts"].includes(key)) {
          if (Array.isArray(item)) found.push(...item);
          else if (typeof item === "string") found.push(item);
        }
        walk(item);
      });
    }
  };
  walk(value);
  found.filter(Boolean).forEach(path => { if (!state.artifacts.includes(path)) state.artifacts.push(path); });
  renderArtifacts();
}

async function api(url, options = {}) {
  const response = await fetch(url, {credentials:"same-origin", ...options, headers:{"Content-Type":"application/json", ...(options.headers || {})}});
  const data = await response.json().catch(() => ({ok:false, error:`HTTP ${response.status}`}));
  if (!response.ok || data.ok === false) throw new Error(data.error || data.detail || `HTTP ${response.status}`);
  return data;
}

async function execute(action, payload = {}, confirmation = null) {
  const merged = {device:selectedDevice(), user:selectedUser(), ...payload};
  setOutput(`Executing ${action}…`);
  const response = await api("/api/execute", {method:"POST", body:JSON.stringify({action, payload:merged, confirmation})});
  setOutput(response.data);
  toast(`${action} completed`);
  return response.data;
}

function switchView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === name));
  const titles = {overview:"Operations overview", operations:"Command center", packages:"Apps and APK workspace", logs:"Live logcat", security:"Security audit", artifacts:"Generated artifacts"};
  $("#pageTitle").textContent = titles[name] || "adbgath";
}

function renderDevices(devices) {
  state.devices = devices || [];
  const select = $("#deviceSelect");
  const previous = select.value;
  select.innerHTML = '<option value="">Auto-select</option>' + state.devices.map(device => {
    const root = device.rooted === true ? " · root" : "";
    const label = `${device.model || device.product || "Android"} · ${device.serial} · ${device.state}${root}`;
    return `<option value="${escapeHtml(device.serial)}">${escapeHtml(label)}</option>`;
  }).join("");
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
  if (!select.value && state.devices.filter(d => d.state === "device").length === 1) select.value = state.devices.find(d => d.state === "device").serial;
  $("#deviceCount").textContent = state.devices.filter(d => d.state === "device").length;
  $("#deviceHint").textContent = state.devices.length ? "ADB transport detected" : "No authorized device";
}

function renderDoctor(doctor) {
  const checks = doctor?.checks || [];
  $("#healthValue").textContent = doctor?.ok ? "READY" : "CHECK";
  $("#healthHint").textContent = doctor?.ok ? "Core dependencies available" : (doctor?.error || "Review dependencies");
  $("#engineStatus").textContent = doctor?.ok ? "ENGINE ONLINE" : "ATTENTION";
  $(".status-dot").className = `status-dot ${doctor?.ok ? "online" : "offline"}`;
  $("#doctorChecks").innerHTML = checks.slice(0, 7).map(check => `<div class="check-item ${check.ok ? "ok" : "fail"}"><span>${escapeHtml(check.name)}</span><span title="${escapeHtml(String(check.value))}">${escapeHtml(String(check.value))}</span></div>`).join("") || `<div class="empty-state">${escapeHtml(doctor?.error || "No diagnostics available")}</div>`;
}

async function bootstrap() {
  try {
    const data = await api("/api/bootstrap");
    $("#versionValue").textContent = data.version;
    state.destructive = new Set(data.destructive_actions || []);
    renderDevices(data.devices);
    renderDoctor(data.doctor);
    setOutput({status:"ready", version:data.version, workspace:data.workspace, devices:data.devices.length});
  } catch (error) {
    renderDoctor({ok:false, error:error.message, checks:[]});
    setOutput({error:error.message});
    toast(error.message, true);
  }
}

async function refreshDevices() {
  try { renderDevices((await api("/api/devices")).data); toast("Device list refreshed"); }
  catch (error) { toast(error.message, true); }
}

function renderActionForm(action) {
  const config = ACTIONS[action];
  const root = $("#dynamicFields");
  root.innerHTML = "";
  config.fields.forEach(field => {
    const label = document.createElement("label");
    if (field.full) label.classList.add("full");
    if (field.type === "checkbox") label.classList.add("checkbox-field");
    if (field.type === "checkbox") {
      label.innerHTML = `<input type="checkbox" name="${field.name}"><span>${escapeHtml(field.label)}</span>`;
    } else {
      label.innerHTML = `<span>${escapeHtml(field.label)}${field.required ? " *" : ""}</span>`;
      let input;
      if (field.type === "select") {
        input = document.createElement("select");
        field.options.forEach(([value, text]) => input.add(new Option(text, value)));
      } else {
        input = document.createElement("input");
        input.type = field.type || "text";
        input.placeholder = field.placeholder || "";
        input.value = field.value || "";
      }
      input.name = field.name;
      input.required = Boolean(field.required);
      label.appendChild(input);
    }
    root.appendChild(label);
  });
  $("#dangerConfirm").classList.toggle("hidden", !config.danger);
  $("#authorizedCheck").checked = false;
}

function formPayload() {
  const action = $("#actionSelect").value;
  const config = ACTIONS[action];
  const payload = {};
  for (const field of config.fields) {
    const input = $(`[name="${field.name}"]`, $("#dynamicFields"));
    let value;
    if (field.type === "checkbox") value = input.checked;
    else value = input.value.trim();
    if (field.required && !value) throw new Error(`${field.label} is required.`);
    if (field.type === "number" && value !== "") value = Number(value);
    if (["files", "packages", "remote_paths", "filters"].includes(field.name)) value = value ? value.split(",").map(item => item.trim()).filter(Boolean) : [];
    if (field.name === "system") value = value === "" ? null : value === "true";
    if (field.name === "replacement_pairs") {
      value = value ? value.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
        const splitAt = line.lastIndexOf(" ");
        if (splitAt < 1) throw new Error("Each replacement line must use: APK_PATH PACKAGE");
        return {file:line.slice(0, splitAt).trim(), package:line.slice(splitAt + 1).trim()};
      }) : [];
      if (value.length) payload.replacements = value;
      continue;
    }
    if (value !== "" && value !== null) payload[field.name] = value;
  }
  return payload;
}

async function executeForm() {
  const action = $("#actionSelect").value;
  const config = ACTIONS[action];
  if (config.danger && !$("#authorizedCheck").checked) return toast("Confirm that the target is authorized.", true);
  try {
    const payload = formPayload();
    if (action === "replace" && !payload.replacements?.length && !(payload.package && payload.file)) {
      throw new Error("Provide Package + APK path, or one or more replacement pairs.");
    }
    await execute(action, payload, config.danger ? "AUTHORIZED" : null);
  }
  catch (error) { setOutput({ok:false, error:error.message}); toast(error.message, true); }
}

function presetAction(action) {
  if (!ACTIONS[action]) return;
  $("#actionSelect").value = action;
  renderActionForm(action);
  switchView("operations");
}

async function loadPackages() {
  try {
    const data = await execute("packages", {include_paths:$("#includePaths").checked});
    state.packages = data;
    renderPackages();
  } catch (error) { toast(error.message, true); }
}

function renderPackages() {
  const term = $("#packageSearch").value.toLowerCase();
  const rows = state.packages.filter(item => item.name.toLowerCase().includes(term));
  $("#packageList").classList.toggle("empty-state", rows.length === 0);
  $("#packageList").innerHTML = rows.length ? rows.map(item => `<div class="package-item" data-package="${escapeHtml(item.name)}"><strong>${escapeHtml(item.name)}</strong>${item.apk_paths?.length ? `<small>${escapeHtml(item.apk_paths.join(" · "))}</small>` : ""}</div>`).join("") : "No matching packages.";
  $$(".package-item").forEach(item => item.addEventListener("click", () => { presetAction("app"); $('[name="package"]').value = item.dataset.package; }));
}

async function uploadFile(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  $("#uploadResult").textContent = `Uploading ${file.name}…`;
  try {
    const response = await fetch("/api/upload", {method:"POST", credentials:"same-origin", body:form});
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || "Upload failed");
    state.uploads.push(data.path);
    $("#uploadResult").textContent = `${data.path} · ${formatBytes(data.size)}`;
    toast("File staged in local workspace");
  } catch (error) { $("#uploadResult").textContent = error.message; toast(error.message, true); }
}

function startLogs() {
  if (state.socket) state.socket.close();
  const params = new URLSearchParams();
  if (selectedDevice()) params.set("device", selectedDevice());
  if ($("#logPackage").value.trim()) params.set("package", $("#logPackage").value.trim());
  if ($("#logRegex").value.trim()) params.set("regex", $("#logRegex").value.trim());
  params.set("format", $("#logFormat").value);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws/logs?${params}`);
  state.socket = socket;
  $("#liveConsole").textContent = "Connecting to logcat…\n";
  $("#startLogs").disabled = true; $("#stopLogs").disabled = false;
  socket.onmessage = event => {
    const data = JSON.parse(event.data);
    $("#liveConsole").textContent += data.line ? `${data.line}\n` : `[error] ${data.error}\n`;
    $("#liveConsole").scrollTop = $("#liveConsole").scrollHeight;
  };
  socket.onerror = () => toast("Log stream connection failed", true);
  socket.onclose = () => { state.socket = null; $("#startLogs").disabled = false; $("#stopLogs").disabled = true; };
}

function stopLogs() { if (state.socket) state.socket.close(); }

async function runSecurity(mode = "security") {
  try {
    const result = await execute(mode, {});
    const report = mode === "security" ? result : result.security;
    renderFindings(report);
    switchView("security");
  } catch (error) { toast(error.message, true); }
}

function renderFindings(report) {
  const summary = report?.summary || {};
  const categories = [["total","TOTAL"],["high","HIGH"],["medium","MEDIUM"],["low","LOW"],["info","INFO"]];
  $("#findingSummary").innerHTML = categories.map(([key,label]) => `<article class="metric"><span>${label}</span><strong>${summary[key] ?? 0}</strong></article>`).join("");
  const findings = report?.findings || [];
  const root = $("#findings");
  root.classList.toggle("empty-state", findings.length === 0);
  root.innerHTML = findings.length ? findings.map(finding => `<article class="finding ${escapeHtml(finding.severity)}"><div class="finding-head"><strong>${escapeHtml(finding.title)}</strong><span class="severity">${escapeHtml(finding.severity.toUpperCase())}</span></div><p><b>Evidence:</b> <code>${escapeHtml(finding.evidence)}</code></p><p><b>Mitigation:</b> ${escapeHtml(finding.mitigation)}</p></article>`).join("") : "No findings were generated by the current checks.";
}

function renderArtifacts() {
  $("#artifactCount").textContent = state.artifacts.length;
  const root = $("#artifactList");
  root.classList.toggle("empty-state", state.artifacts.length === 0);
  root.innerHTML = state.artifacts.length ? state.artifacts.map(path => `<div class="artifact-item"><code>${escapeHtml(path)}</code><a href="/api/artifact?path=${encodeURIComponent(path)}">DOWNLOAD</a></div>`).join("") : "No artifacts generated in this session.";
}

function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value ?? ""); return div.innerHTML; }
function formatBytes(bytes) { if (!bytes) return "0 B"; const units=["B","KiB","MiB","GiB"]; const i=Math.min(Math.floor(Math.log(bytes)/Math.log(1024)),units.length-1); return `${(bytes/1024**i).toFixed(i?1:0)} ${units[i]}`; }

function wireEvents() {
  $$(".nav-item").forEach(item => item.addEventListener("click", () => switchView(item.dataset.view)));
  $$('[data-switch]').forEach(button => button.addEventListener("click", () => button.dataset.preset ? presetAction(button.dataset.preset) : switchView(button.dataset.switch)));
  $("#refreshDevices").addEventListener("click", refreshDevices);
  $("#runDoctor").addEventListener("click", async () => { try { renderDoctor(await execute("doctor", {})); } catch (error) { toast(error.message, true); } });
  $$(".clear-output").forEach(button => button.addEventListener("click", () => setOutput("Output cleared.")));
  $("#actionSelect").innerHTML = Object.entries(ACTIONS).map(([key,config]) => `<option value="${key}">${escapeHtml(config.label)}</option>`).join("");
  $("#actionSelect").addEventListener("change", event => renderActionForm(event.target.value));
  $("#executeAction").addEventListener("click", executeForm);
  $("#resetForm").addEventListener("click", () => renderActionForm($("#actionSelect").value));
  $$(".quick-action").forEach(button => button.addEventListener("click", () => button.dataset.action === "download" ? presetAction("download") : execute(button.dataset.action, {}).catch(error => toast(error.message,true))));
  $("#loadPackages").addEventListener("click", loadPackages);
  $("#packageSearch").addEventListener("input", renderPackages);
  $("#fileUpload").addEventListener("change", event => uploadFile(event.target.files[0]));
  const dropzone = $("#dropzone");
  ["dragenter","dragover"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add("drag"); }));
  ["dragleave","drop"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove("drag"); }));
  dropzone.addEventListener("drop", event => uploadFile(event.dataTransfer.files[0]));
  $("#startLogs").addEventListener("click", startLogs); $("#stopLogs").addEventListener("click", stopLogs);
  $("#clearLogs").addEventListener("click", async () => { try { await execute("logs_clear", {}); $("#liveConsole").textContent = "Device log buffer cleared.\n"; } catch (error) { toast(error.message,true); } });
  $("#runSecurity").addEventListener("click", () => runSecurity("security"));
  $("#runMastg").addEventListener("click", () => runSecurity("mastg"));
}

document.addEventListener("DOMContentLoaded", () => { wireEvents(); renderActionForm("devices"); bootstrap(); });
