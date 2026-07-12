"use strict";

const state = {
  devices: [], packages: [], artifacts: [], uploads: [], jobs: [], projects: [],
  snapshots: [], findings: [], operations: new Map(), destructive: new Set(),
  longRunning: new Set(), socket: null, jobTimer: null, packagePage: 1, packagePageSize: 50,
  logLines: [], logsPaused: false, logBookmarks: [],
};

const PRESET_STORAGE_KEY = "adbgath.operationPresets.v1";
const MAX_LOG_LINES = 5000;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast show${error ? " error" : ""}`;
  clearTimeout(node._timer);
  node._timer = setTimeout(() => { node.className = "toast"; }, 3200);
}

function selectedDevice() { return $("#deviceSelect").value || null; }
function selectedUser() { return $("#userInput").value.trim() || null; }
function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value ?? ""); return div.innerHTML; }
function formatBytes(bytes) { if (!bytes) return "0 B"; const units=["B","KiB","MiB","GiB"]; const i=Math.min(Math.floor(Math.log(bytes)/Math.log(1024)),units.length-1); return `${(bytes/1024**i).toFixed(i?1:0)} ${units[i]}`; }
function operation(name) { return state.operations.get(name); }

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
        if (["artifact", "artifacts", "reports", "manifest"].includes(key)) {
          if (Array.isArray(item)) found.push(...item.filter(value => typeof value === "string"));
          else if (typeof item === "string") found.push(item);
          else if (item && typeof item === "object") found.push(...Object.values(item).filter(value => typeof value === "string"));
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
  const headers = options.body instanceof FormData ? (options.headers || {}) : {"Content-Type":"application/json", ...(options.headers || {})};
  const response = await fetch(url, {credentials:"same-origin", ...options, headers});
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
  await refreshWorkspace(false);
  return response.data;
}

async function submitJob(action, payload = {}, confirmation = null) {
  const merged = {device:selectedDevice(), user:selectedUser(), ...payload};
  setOutput(`Queueing ${action}…`);
  const response = await api("/api/jobs", {method:"POST", body:JSON.stringify({action, payload:merged, confirmation})});
  toast(`${action} queued`);
  switchView("workspace");
  await refreshWorkspace(false);
  watchJob(response.data.id);
  return response.data;
}

async function watchJob(jobId) {
  clearInterval(state.jobTimer);
  const poll = async () => {
    try {
      const job = (await api(`/api/jobs/${encodeURIComponent(jobId)}`)).data;
      setOutput(job);
      await refreshWorkspace(false);
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        clearInterval(state.jobTimer);
        state.jobTimer = null;
        if (job.result) collectArtifacts(job.result);
        toast(`${job.action} ${job.status}`, job.status === "failed");
      }
    } catch (error) { clearInterval(state.jobTimer); state.jobTimer = null; toast(error.message, true); }
  };
  await poll();
  if (!state.jobTimer) state.jobTimer = setInterval(poll, 1200);
}

function switchView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === name));
  const titles = {overview:"Operations overview", operations:"Command center", packages:"Apps and APK workspace", logs:"Live logcat", security:"Security audit", workspace:"Projects and execution jobs", artifacts:"Generated artifacts"};
  $("#pageTitle").textContent = titles[name] || "ADB-Gath";
  if (name === "workspace") refreshWorkspace(false);
  if (name === "artifacts") loadArtifacts();
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
  $("#doctorChecks").innerHTML = checks.slice(0, 8).map(check => `<div class="check-item ${check.ok ? "ok" : "fail"}"><span>${escapeHtml(check.name)}</span><span title="${escapeHtml(String(check.value))}">${escapeHtml(String(check.value))}</span></div>`).join("") || `<div class="empty-state">${escapeHtml(doctor?.error || "No diagnostics available")}</div>`;
}

function installOperationCatalog(items) {
  state.operations = new Map((items || []).map(item => [item.name, item]));
  const select = $("#actionSelect");
  const grouped = {};
  for (const item of items || []) (grouped[item.category] ||= []).push(item);
  select.innerHTML = Object.entries(grouped).map(([category, operations]) => `<optgroup label="${escapeHtml(category)}">${operations.map(item => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.title)}</option>`).join("")}</optgroup>`).join("");
  if (state.operations.has("devices")) select.value = "devices";
  renderActionForm(select.value);
}

async function bootstrap() {
  try {
    const data = await api("/api/bootstrap");
    $("#versionValue").textContent = data.version;
    state.destructive = new Set(data.destructive_actions || []);
    state.longRunning = new Set(data.long_running_actions || []);
    installOperationCatalog(data.operations || []);
    renderDevices(data.devices);
    renderDoctor(data.doctor);
    state.projects = data.projects || []; state.snapshots = data.snapshots || []; state.jobs = data.jobs || [];
    renderWorkspace();
    setOutput({status:"ready", version:data.version, workspace:data.workspace, devices:data.devices.length, operations:state.operations.size});
    await Promise.allSettled([loadArtifacts(), loadStoredFindings()]);
  } catch (error) {
    renderDoctor({ok:false, error:error.message, checks:[]});
    setOutput({error:error.message}); toast(error.message, true);
  }
}

async function refreshDevices() {
  try { renderDevices((await api("/api/devices")).data); toast("Device list refreshed"); }
  catch (error) { toast(error.message, true); }
}

function readPresets() {
  try {
    const value = JSON.parse(localStorage.getItem(PRESET_STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value.filter(item => item && typeof item.name === "string" && typeof item.action === "string") : [];
  } catch (_) { return []; }
}

function writePresets(items) {
  localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(items.slice(0, 100)));
  renderPresetSelect();
}

function renderPresetSelect() {
  const select = $("#presetSelect");
  if (!select) return;
  const previous = select.value;
  const presets = readPresets();
  select.innerHTML = '<option value="">Saved form presets</option>' + presets.map((item, index) => `<option value="${index}">${escapeHtml(item.name)} · ${escapeHtml(item.action)}</option>`).join("");
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}

function saveCurrentPreset() {
  try {
    const action = $("#actionSelect").value;
    const name = window.prompt("Preset name", `${action} preset`);
    if (!name) return;
    const safeName = name.trim().slice(0, 80);
    if (!safeName) return;
    const payload = formPayload();
    const presets = readPresets().filter(item => item.name !== safeName);
    presets.unshift({name:safeName, action, payload, updatedAt:new Date().toISOString()});
    writePresets(presets);
    $("#presetSelect").value = "0";
    toast("Preset saved locally in this browser");
  } catch (error) { toast(error.message, true); }
}

function loadSelectedPreset() {
  const index = Number($("#presetSelect").value);
  const preset = readPresets()[index];
  if (!preset || !state.operations.has(preset.action)) return toast("Select a valid preset.", true);
  $("#actionSelect").value = preset.action;
  renderActionForm(preset.action);
  for (const [name, value] of Object.entries(preset.payload || {})) {
    const input = $(`[name="${name}"]`, $("#dynamicFields"));
    if (!input) continue;
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = Array.isArray(value) ? value.join("\n") : String(value ?? "");
  }
  toast("Preset loaded");
}

function deleteSelectedPreset() {
  const index = Number($("#presetSelect").value);
  const presets = readPresets();
  if (!Number.isInteger(index) || !presets[index]) return toast("Select a preset to delete.", true);
  presets.splice(index, 1);
  writePresets(presets);
  toast("Preset deleted");
}

function renderActionForm(actionName) {
  const config = operation(actionName);
  const root = $("#dynamicFields");
  root.innerHTML = "";
  if (!config) return;
  const description = document.createElement("div");
  description.className = "operation-description full";
  description.innerHTML = `<strong>${escapeHtml(config.title)}</strong><span>${escapeHtml(config.description)}</span>${config.requirements?.length ? `<small>Requires: ${escapeHtml(config.requirements.join(", "))}</small>` : ""}`;
  root.appendChild(description);
  for (const field of config.fields || []) {
    const label = document.createElement("label");
    if (["textarea", "list", "file"].includes(field.field_type)) label.classList.add("full");
    if (field.field_type === "boolean") label.classList.add("checkbox-field");
    if (field.field_type === "boolean") {
      label.innerHTML = `<input type="checkbox" name="${escapeHtml(field.name)}" ${field.default ? "checked" : ""}><span>${escapeHtml(field.label)}</span>`;
    } else {
      label.innerHTML = `<span>${escapeHtml(field.label)}${field.required ? " *" : ""}</span>`;
      let input;
      if (field.field_type === "select") {
        input = document.createElement("select");
        for (const choice of field.choices || []) input.add(new Option(choice, choice));
      } else if (["textarea", "list"].includes(field.field_type)) {
        input = document.createElement("textarea");
        input.rows = field.field_type === "list" ? 3 : 4;
      } else {
        input = document.createElement("input");
        input.type = field.field_type === "number" ? "number" : "text";
      }
      input.name = field.name; input.required = Boolean(field.required);
      if (field.minimum !== null && field.minimum !== undefined) input.min = field.minimum;
      if (field.maximum !== null && field.maximum !== undefined) input.max = field.maximum;
      input.placeholder = field.placeholder || (field.field_type === "list" ? "Comma or newline separated values" : "");
      if (field.default !== null && field.default !== undefined) input.value = field.default;
      if (field.help) input.title = field.help;
      label.appendChild(input);
    }
    root.appendChild(label);
  }
  $("#dangerConfirm").classList.toggle("hidden", !config.destructive);
  $("#authorizedCheck").checked = false;
  $("#executeAction").textContent = config.long_running ? "Queue operation" : "Execute operation";
}

function formPayload() {
  const config = operation($("#actionSelect").value);
  const payload = {};
  for (const field of config?.fields || []) {
    const input = $(`[name="${field.name}"]`, $("#dynamicFields"));
    let value = field.field_type === "boolean" ? input.checked : input.value.trim();
    if (field.required && (value === "" || value === null || value === undefined)) throw new Error(`${field.label} is required.`);
    if (field.field_type === "number" && value !== "") value = Number(value);
    if (field.field_type === "list") value = value ? value.split(/[\r\n,]+/).map(item => item.trim()).filter(Boolean) : [];
    if (value !== "" && value !== null) payload[field.name] = value;
  }
  return payload;
}

async function executeForm() {
  const action = $("#actionSelect").value;
  const config = operation(action);
  if (!config) return;
  if (config.destructive && !$("#authorizedCheck").checked) return toast("Confirm that the target is authorized.", true);
  try {
    const payload = formPayload();
    const confirmation = config.destructive ? "AUTHORIZED" : null;
    if (config.long_running) await submitJob(action, payload, confirmation);
    else await execute(action, payload, confirmation);
  } catch (error) { setOutput({ok:false, error:error.message}); toast(error.message, true); }
}

function presetAction(action) {
  if (!state.operations.has(action)) return;
  $("#actionSelect").value = action; renderActionForm(action); switchView("operations");
}

async function loadPackages() {
  try { state.packages = await execute("packages", {include_paths:$("#includePaths").checked}); renderPackages(); }
  catch (error) { toast(error.message, true); }
}
function renderPackages() {
  const term = $("#packageSearch").value.toLowerCase();
  const direction = $("#packageSort").value === "desc" ? -1 : 1;
  state.packagePageSize = Number($("#packagePageSize").value || 50);
  const rows = state.packages
    .filter(item => item.name.toLowerCase().includes(term))
    .sort((left, right) => left.name.localeCompare(right.name) * direction);
  const pages = Math.max(1, Math.ceil(rows.length / state.packagePageSize));
  state.packagePage = Math.max(1, Math.min(state.packagePage, pages));
  const start = (state.packagePage - 1) * state.packagePageSize;
  const visible = rows.slice(start, start + state.packagePageSize);
  $("#packageList").classList.toggle("empty-state", rows.length === 0);
  $("#packageList").innerHTML = visible.length ? visible.map(item => `<div class="package-item" data-package="${escapeHtml(item.name)}"><strong>${escapeHtml(item.name)}</strong>${item.apk_paths?.length ? `<small>${escapeHtml(item.apk_paths.join(" · "))}</small>` : ""}</div>`).join("") : "No matching packages.";
  $("#packagePageLabel").textContent = rows.length ? `Page ${state.packagePage} of ${pages} · ${rows.length} packages` : "Page 0 of 0";
  $("#packagePrev").disabled = state.packagePage <= 1 || rows.length === 0;
  $("#packageNext").disabled = state.packagePage >= pages || rows.length === 0;
  $$(".package-item").forEach(item => item.addEventListener("click", () => { presetAction("app"); const input = $('[name="package"]'); if (input) input.value = item.dataset.package; }));
}

async function uploadFile(file) {
  if (!file) return;
  const form = new FormData(); form.append("file", file);
  $("#uploadResult").textContent = `Uploading ${file.name}…`;
  try {
    const data = await api("/api/upload", {method:"POST", body:form});
    state.uploads.push(data.path); $("#uploadResult").textContent = `${data.path} · ${formatBytes(data.size)} · SHA-256 ${data.sha256}`;
    toast("File staged in local workspace"); await loadArtifacts(); return data;
  } catch (error) { $("#uploadResult").textContent = error.message; toast(error.message, true); return null; }
}

async function uploadFiles(files) {
  const queue = [...(files || [])];
  if (!queue.length) return;
  const completed = []; const failed = [];
  for (const file of queue) {
    const result = await uploadFile(file);
    (result ? completed : failed).push(file.name);
  }
  $("#uploadResult").textContent = `${completed.length} staged${failed.length ? ` · ${failed.length} failed: ${failed.join(", ")}` : `: ${completed.join(", ")}`}`;
}

function renderLiveLogs() {
  if (state.logsPaused) return;
  $("#liveConsole").textContent = state.logLines.length ? `${state.logLines.join("\n")}\n` : "Live output will appear here.";
  $("#liveConsole").scrollTop = $("#liveConsole").scrollHeight;
}

function toggleLogPause() {
  state.logsPaused = !state.logsPaused;
  $("#pauseLogs").textContent = state.logsPaused ? "Resume" : "Pause";
  if (!state.logsPaused) renderLiveLogs();
  toast(state.logsPaused ? "Log rendering paused; collection continues" : "Log rendering resumed");
}

function bookmarkLog() {
  if (!state.logLines.length) return toast("No log lines to bookmark.", true);
  state.logBookmarks.push({line:state.logLines.length, text:state.logLines.at(-1), createdAt:new Date().toISOString()});
  renderLogBookmarks();
}

function renderLogBookmarks() {
  const root = $("#logBookmarks");
  root.classList.toggle("empty-state", state.logBookmarks.length === 0);
  root.innerHTML = state.logBookmarks.length ? state.logBookmarks.map(item => `<div class="bookmark-item"><strong>Line ${item.line}</strong><code>${escapeHtml(item.text)}</code><small>${escapeHtml(item.createdAt)}</small></div>`).join("") : "No log bookmarks.";
}

function exportLogs() {
  if (!state.logLines.length) return toast("No log lines to export.", true);
  const header = `# ADB-Gath local logcat export\n# Exported: ${new Date().toISOString()}\n# Device: ${selectedDevice() || "auto"}\n`;
  const blob = new Blob([header, state.logLines.join("\n"), "\n"], {type:"text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = `adbgath-logcat-${Date.now()}.log`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function startLogs() {
  if (state.socket) state.socket.close();
  state.logLines = []; state.logBookmarks = []; state.logsPaused = false; renderLogBookmarks();
  const params = new URLSearchParams();
  if (selectedDevice()) params.set("device", selectedDevice());
  if ($("#logPackage").value.trim()) params.set("package", $("#logPackage").value.trim());
  if ($("#logRegex").value.trim()) params.set("regex", $("#logRegex").value.trim());
  params.set("format", $("#logFormat").value);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws/logs?${params}`); state.socket = socket;
  $("#liveConsole").textContent = "Connecting to logcat…\n"; $("#startLogs").disabled = true; $("#stopLogs").disabled = false;
  $("#pauseLogs").disabled = false; $("#bookmarkLog").disabled = false; $("#exportLogs").disabled = false; $("#pauseLogs").textContent = "Pause";
  socket.onmessage = event => {
    const data = JSON.parse(event.data); const line = data.line || `[error] ${data.error}`;
    state.logLines.push(line);
    if (state.logLines.length > MAX_LOG_LINES) {
      const removed = state.logLines.length - MAX_LOG_LINES; state.logLines.splice(0, removed);
      state.logBookmarks = state.logBookmarks.map(item => ({...item, line:item.line-removed})).filter(item => item.line > 0);
      renderLogBookmarks();
    }
    renderLiveLogs();
  };
  socket.onerror = () => toast("Log stream connection failed", true);
  socket.onclose = () => { state.socket = null; $("#startLogs").disabled = false; $("#stopLogs").disabled = true; $("#pauseLogs").disabled = true; };
}
function stopLogs() { if (state.socket) state.socket.close(); }

async function runSecurity(mode = "security") {
  try {
    if (state.longRunning.has(mode)) { await submitJob(mode, {}); return; }
    const result = await execute(mode, {}); renderFindings(mode === "security" ? result : result.security); switchView("security");
  } catch (error) { toast(error.message, true); }
}
function renderFindings(report) {
  const summary = report?.summary || {}; const categories = [["total","TOTAL"],["critical","CRITICAL"],["high","HIGH"],["medium","MEDIUM"],["low","LOW"],["info","INFO"]];
  $("#findingSummary").innerHTML = categories.map(([key,label]) => `<article class="metric"><span>${label}</span><strong>${summary[key] ?? 0}</strong></article>`).join("");
  const chartKeys = [["critical","CRITICAL"],["high","HIGH"],["medium","MEDIUM"],["low","LOW"],["info","INFO"]];
  const maximum = Math.max(1, ...chartKeys.map(([key]) => Number(summary[key] || 0)));
  const chart = $("#severityChart"); chart.classList.remove("empty-state");
  chart.innerHTML = chartKeys.map(([key,label]) => `<div class="severity-row ${key}"><span>${label}</span><div><i style="width:${(Number(summary[key] || 0) / maximum) * 100}%"></i></div><strong>${summary[key] ?? 0}</strong></div>`).join("");
  const findings = report?.findings || []; const root = $("#findings"); root.classList.toggle("empty-state", findings.length === 0);
  root.innerHTML = findings.length ? findings.map(finding => `<article class="finding ${escapeHtml(finding.severity)}"><div class="finding-head"><strong>${escapeHtml(finding.title)}</strong><span class="severity">${escapeHtml(String(finding.severity).toUpperCase())}</span></div><p><b>Evidence:</b> <code>${escapeHtml(finding.evidence)}</code></p><p><b>Mitigation:</b> ${escapeHtml(finding.mitigation)}</p>${finding.cwe ? `<p><b>CWE:</b> ${escapeHtml(finding.cwe)}</p>` : ""}</article>`).join("") : "No findings were generated by the current checks.";
}

async function refreshWorkspace(showToast = true) {
  try {
    const [projects, jobs, snapshots, findings] = await Promise.all([api("/api/projects"), api("/api/jobs"), api("/api/snapshots"), api("/api/findings")]);
    state.projects = projects.data || []; state.jobs = jobs.data || []; state.snapshots = snapshots.data || []; state.findings = findings.data || [];
    renderWorkspace(); if (showToast) toast("Workspace refreshed");
  } catch (error) { if (showToast) toast(error.message, true); }
}
async function loadStoredFindings() { try { state.findings = (await api("/api/findings")).data || []; renderWorkspace(); } catch (_) { /* bootstrap remains usable */ } }
function renderWorkspace() {
  $("#projectCount").textContent = state.projects.length;
  $("#activeJobCount").textContent = state.jobs.filter(job => ["queued","running","cancelling"].includes(job.status)).length;
  $("#snapshotCount").textContent = state.snapshots.length; $("#storedFindingCount").textContent = state.findings.length;
  renderDataList("#projectList", state.projects, item => `<div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.id)} · ${escapeHtml(item.scope || "No scope")}</small></div>`);
  renderDataList("#snapshotList", state.snapshots, item => `<div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.device_serial || "device")} · ${escapeHtml(item.created_at || "")}</small></div>`);
  renderDataList("#storedFindingList", state.findings, item => `<div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.severity)} · ${escapeHtml(item.status)}</small></div>`);
  const jobs = $("#jobList"); jobs.classList.toggle("empty-state", state.jobs.length === 0);
  jobs.innerHTML = state.jobs.length ? state.jobs.map(job => `<div class="data-row"><div><strong>${escapeHtml(job.action)}</strong><small>${escapeHtml(job.status)} · ${Number(job.progress || 0)}%</small><div class="job-progress"><i style="width:${Math.max(0, Math.min(100, Number(job.progress || 0)))}%"></i></div></div>${["queued","running","cancelling"].includes(job.status) ? `<button class="text-button cancel-job" data-job="${escapeHtml(job.id)}">CANCEL</button>` : `<button class="text-button inspect-job" data-job="${escapeHtml(job.id)}">VIEW</button>`}</div>`).join("") : "No jobs.";
  $$(".cancel-job").forEach(button => button.addEventListener("click", async () => { try { await api(`/api/jobs/${encodeURIComponent(button.dataset.job)}/cancel`, {method:"POST", body:"{}"}); await refreshWorkspace(false); } catch (error) { toast(error.message, true); } }));
  $$(".inspect-job").forEach(button => button.addEventListener("click", async () => { try { setOutput((await api(`/api/jobs/${encodeURIComponent(button.dataset.job)}`)).data); } catch (error) { toast(error.message, true); } }));
}
function renderDataList(selector, rows, render) {
  const root = $(selector); root.classList.toggle("empty-state", rows.length === 0); root.innerHTML = rows.length ? rows.map(item => `<div class="data-row">${render(item)}</div>`).join("") : "No data.";
}

async function loadArtifacts() {
  try { const rows = (await api("/api/artifacts")).data || []; state.artifacts = rows.map(item => item.path); renderArtifacts(rows); }
  catch (_) { renderArtifacts(); }
}
function renderArtifacts(rows = null) {
  $("#artifactCount").textContent = state.artifacts.length;
  const root = $("#artifactList"); root.classList.toggle("empty-state", state.artifacts.length === 0);
  const metadata = new Map((rows || []).map(item => [item.path, item]));
  root.innerHTML = state.artifacts.length ? state.artifacts.map(path => { const item = metadata.get(path); return `<div class="artifact-item"><div><code>${escapeHtml(path)}</code>${item ? `<small>${formatBytes(item.size)}</small>` : ""}</div><a href="/api/artifact?path=${encodeURIComponent(path)}">DOWNLOAD</a></div>`; }).join("") : "No artifacts generated in this workspace.";
}

function wireEvents() {
  $$(".nav-item").forEach(item => item.addEventListener("click", () => switchView(item.dataset.view)));
  $$('[data-switch]').forEach(button => button.addEventListener("click", () => button.dataset.preset ? presetAction(button.dataset.preset) : switchView(button.dataset.switch)));
  $$('[data-preset]:not([data-switch])').forEach(button => button.addEventListener("click", () => presetAction(button.dataset.preset)));
  $("#refreshDevices").addEventListener("click", refreshDevices);
  $("#runDoctor").addEventListener("click", async () => { try { renderDoctor(await execute("doctor", {})); } catch (error) { toast(error.message, true); } });
  $$(".clear-output").forEach(button => button.addEventListener("click", () => setOutput("Output cleared.")));
  $("#actionSelect").addEventListener("change", event => renderActionForm(event.target.value));
  $("#executeAction").addEventListener("click", executeForm); $("#resetForm").addEventListener("click", () => renderActionForm($("#actionSelect").value));
  $("#savePreset").addEventListener("click", saveCurrentPreset); $("#loadPreset").addEventListener("click", loadSelectedPreset); $("#deletePreset").addEventListener("click", deleteSelectedPreset);
  $$(".quick-action").forEach(button => button.addEventListener("click", () => button.dataset.action === "download" ? presetAction("download") : (state.longRunning.has(button.dataset.action) ? submitJob(button.dataset.action, {}).catch(error => toast(error.message,true)) : execute(button.dataset.action, {}).catch(error => toast(error.message,true)))));
  $("#loadPackages").addEventListener("click", loadPackages);
  $("#packageSearch").addEventListener("input", () => { state.packagePage = 1; renderPackages(); });
  $("#packageSort").addEventListener("change", () => { state.packagePage = 1; renderPackages(); });
  $("#packagePageSize").addEventListener("change", () => { state.packagePage = 1; renderPackages(); });
  $("#packagePrev").addEventListener("click", () => { state.packagePage -= 1; renderPackages(); });
  $("#packageNext").addEventListener("click", () => { state.packagePage += 1; renderPackages(); });
  $("#fileUpload").addEventListener("change", event => uploadFiles(event.target.files));
  const dropzone = $("#dropzone");
  ["dragenter","dragover"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add("drag"); }));
  ["dragleave","drop"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove("drag"); }));
  dropzone.addEventListener("drop", event => uploadFiles(event.dataTransfer.files));
  $("#startLogs").addEventListener("click", startLogs); $("#stopLogs").addEventListener("click", stopLogs);
  $("#pauseLogs").addEventListener("click", toggleLogPause); $("#bookmarkLog").addEventListener("click", bookmarkLog); $("#exportLogs").addEventListener("click", exportLogs);
  $("#clearLogs").addEventListener("click", async () => { try { await execute("logs_clear", {}, "AUTHORIZED"); state.logLines = []; state.logBookmarks = []; renderLogBookmarks(); $("#liveConsole").textContent = "Device log buffer cleared.\n"; } catch (error) { toast(error.message,true); } });
  $("#runSecurity").addEventListener("click", () => runSecurity("security")); $("#runMastg").addEventListener("click", () => runSecurity("mastg"));
  $("#refreshWorkspace").addEventListener("click", () => refreshWorkspace(true));
}

document.addEventListener("DOMContentLoaded", () => { wireEvents(); renderPresetSelect(); renderLogBookmarks(); bootstrap(); });
