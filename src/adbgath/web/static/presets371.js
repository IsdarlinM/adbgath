"use strict";

(() => {
  const LEGACY_V1 = "adbgath.operationPresets.v1";
  const LEGACY_V2_PREFIX = "adbgath.operationPresets.v2";
  let cache = [];
  let saveInFlight = false;
  let serverConfirmAction = null;

  const inheritedInstallOperationCatalog = window.installOperationCatalog;

  function scopeParts() {
    const username = document.querySelector(".auth370-account > span")?.textContent?.trim() || "local";
    const workspace = document.querySelector("#auth370WorkspaceSelect");
    const workspaceId = workspace?.value || "default";
    const workspaceName = workspace?.selectedOptions?.[0]?.textContent?.trim() || workspaceId;
    return {username, workspaceId, workspaceName};
  }

  function legacyV2Key() {
    const {username, workspaceId} = scopeParts();
    return `${LEGACY_V2_PREFIX}:${encodeURIComponent(username.toLowerCase())}:${encodeURIComponent(workspaceId)}`;
  }

  function detachLegacyStorage() {
    const values = new Map();
    for (const key of [LEGACY_V1, legacyV2Key()]) {
      try {
        const raw = localStorage.getItem(key);
        if (raw) {
          values.set(key, raw);
          localStorage.removeItem(key);
        }
      } catch (_) { /* local storage can be unavailable */ }
    }
    return values;
  }

  function restoreLegacyStorage(values) {
    for (const [key, raw] of values || []) {
      try { localStorage.setItem(key, raw); } catch (_) { /* best effort */ }
    }
  }

  function parseLegacy(values) {
    const byName = new Map();
    for (const raw of values?.values?.() || []) {
      try {
        const rows = JSON.parse(raw);
        if (!Array.isArray(rows)) continue;
        for (const item of rows) {
          if (!item || typeof item.name !== "string" || typeof item.action !== "string") continue;
          byName.set(item.name.trim().toLowerCase(), item);
        }
      } catch (_) { /* ignore malformed legacy browser data */ }
    }
    return [...byName.values()];
  }

  function operationFields(action) {
    const config = typeof operation === "function" ? operation(action) : null;
    return Array.isArray(config?.fields) ? config.fields : [];
  }

  function scrubPayload(action, payload) {
    const fields = new Map(operationFields(action).map(field => [field.name, field]));
    const clean = {};
    for (const [name, value] of Object.entries(payload || {})) {
      const field = fields.get(name);
      if (!field || field.field_type === "secret") continue;
      clean[name] = value;
    }
    return clean;
  }

  function sanitizeLegacy(item) {
    if (!item || !state.operations.has(item.action)) return null;
    const name = String(item.name || "").trim().slice(0, 80);
    if (!name) return null;
    return {name, action:item.action, payload:scrubPayload(item.action, item.payload)};
  }

  function selectedPreset() {
    const index = Number(document.querySelector("#presetSelect")?.value);
    return Number.isInteger(index) && cache[index] ? {index, preset:cache[index]} : null;
  }

  function updateScopeHint() {
    const {username, workspaceName} = scopeParts();
    const hint = document.querySelector("#ux371PresetScope");
    if (hint) hint.innerHTML = `Presets are stored in <strong>${escapeHtml(username)} / ${escapeHtml(workspaceName)}</strong>. Secret fields are never saved.`;
    const select = document.querySelector("#presetSelect");
    if (select) select.title = `Server-side preset scope: ${username} / ${workspaceName}`;
  }

  function renderPresetSelectServer() {
    const select = document.querySelector("#presetSelect");
    if (!select) return;
    const previousId = cache[Number(select.value)]?.id || "";
    select.innerHTML = '<option value="">Saved workspace presets</option>' + cache.map((item, index) => `<option value="${index}">${escapeHtml(item.name)} · ${escapeHtml(item.action)}</option>`).join("");
    if (previousId) {
      const index = cache.findIndex(item => item.id === previousId);
      if (index >= 0) select.value = String(index);
    }
    updateScopeHint();
  }

  async function fetchPresets() {
    cache = (await api("/api/presets")).data || [];
    renderPresetSelectServer();
    return cache;
  }

  async function migrateLegacy(values) {
    const rows = parseLegacy(values).map(sanitizeLegacy).filter(Boolean);
    if (!rows.length) return true;
    try {
      for (const item of rows) {
        await api("/api/presets", {
          method:"POST",
          body:JSON.stringify(item),
        });
      }
      toast(`${rows.length} legacy preset${rows.length === 1 ? "" : "s"} migrated into this workspace`);
      return true;
    } catch (error) {
      restoreLegacyStorage(values);
      toast(`Legacy presets were kept in the browser because migration failed: ${error.message}`, true);
      return false;
    }
  }

  async function refreshPresets(values = null) {
    try {
      if (values?.size) await migrateLegacy(values);
      await fetchPresets();
    } catch (error) {
      if (values?.size) restoreLegacyStorage(values);
      cache = [];
      renderPresetSelectServer();
      toast(`Unable to load workspace presets: ${error.message}`, true);
    }
  }

  function updateSaveStatus() {
    const input = document.querySelector("#ux371PresetName");
    const status = document.querySelector("#ux371PresetSaveStatus");
    const button = document.querySelector("#ux371PresetSaveConfirm");
    if (!input || !status || !button) return;
    const name = input.value.trim().toLowerCase();
    const existing = cache.find(item => item.name.toLowerCase() === name);
    const secretCount = operationFields(document.querySelector("#actionSelect")?.value || "").filter(field => field.field_type === "secret").length;
    status.textContent = existing
      ? `“${existing.name}” already exists in this workspace and will be replaced.`
      : secretCount
        ? `${secretCount} secret field${secretCount === 1 ? "" : "s"} will not be sent to preset storage.`
        : "This preset is stored in the authenticated ADB-Gath workspace, not browser local storage.";
    button.textContent = existing ? "Replace preset" : "Save preset";
  }

  function openSaveDialog() {
    try {
      formPayload();
      const action = document.querySelector("#actionSelect")?.value;
      if (!action || !state.operations.has(action)) return toast("Select a valid operation first.", true);
      const current = selectedPreset();
      const input = document.querySelector("#ux371PresetName");
      const label = document.querySelector("#ux371PresetScopeLabel");
      const {username, workspaceName} = scopeParts();
      input.value = current?.preset?.action === action ? current.preset.name : `${action} preset`;
      label.textContent = `${username} / ${workspaceName}`;
      updateSaveStatus();
      const dialog = document.querySelector("#ux371PresetDialog");
      if (typeof dialog?.showModal === "function") dialog.showModal(); else dialog?.setAttribute("open", "");
      queueMicrotask(() => { input.focus(); input.select(); });
    } catch (error) {
      toast(error.message, true);
    }
  }

  function loadSelectedPresetServer() {
    const selected = selectedPreset();
    if (!selected || !state.operations.has(selected.preset.action)) return toast("Select a valid preset.", true);
    document.querySelector("#actionSelect").value = selected.preset.action;
    renderActionForm(selected.preset.action);
    for (const [name, value] of Object.entries(selected.preset.payload || {})) {
      const input = document.querySelector(`#dynamicFields [name="${CSS.escape(name)}"]`);
      if (!input) continue;
      if (input.type === "checkbox") input.checked = Boolean(value);
      else input.value = Array.isArray(value) ? value.join("\n") : String(value ?? "");
    }
    toast("Preset loaded from the active workspace");
  }

  async function commitServerPreset() {
    if (saveInFlight) return;
    const action = document.querySelector("#actionSelect")?.value || "";
    const name = document.querySelector("#ux371PresetName")?.value?.trim().slice(0, 80) || "";
    if (!name) return toast("Preset name is required.", true);
    saveInFlight = true;
    const button = document.querySelector("#ux371PresetSaveConfirm");
    const previous = button.textContent;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Saving…";
    try {
      const payload = scrubPayload(action, formPayload());
      const saved = (await api("/api/presets", {
        method:"POST",
        body:JSON.stringify({name, action, payload}),
      })).data;
      await fetchPresets();
      const index = cache.findIndex(item => item.id === saved.id);
      if (index >= 0) document.querySelector("#presetSelect").value = String(index);
      document.querySelector("#ux371PresetDialog")?.close?.();
      toast("Preset saved in the active ADB-Gath workspace");
    } catch (error) {
      toast(error.message, true);
    } finally {
      saveInFlight = false;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = previous;
      updateSaveStatus();
    }
  }

  function openServerConfirmation({title, message, confirmText, action}) {
    serverConfirmAction = action;
    document.querySelector("#ux371ConfirmTitle").textContent = title;
    document.querySelector("#ux371ConfirmMessage").textContent = message;
    document.querySelector("#ux371ConfirmAction").textContent = confirmText;
    const dialog = document.querySelector("#ux371ConfirmDialog");
    if (typeof dialog?.showModal === "function") dialog.showModal(); else dialog?.setAttribute("open", "");
  }

  function deleteSelectedPresetServer() {
    const selected = selectedPreset();
    if (!selected) return toast("Select a preset to delete.", true);
    const {username, workspaceName} = scopeParts();
    openServerConfirmation({
      title:"Delete saved preset?",
      message:`“${selected.preset.name}” will be removed from ${username} / ${workspaceName}.`,
      confirmText:"Delete preset",
      action: async () => {
        await api(`/api/presets/${encodeURIComponent(selected.preset.id)}`, {method:"DELETE"});
        await fetchPresets();
        toast("Preset deleted from the active workspace");
      },
    });
  }

  window.readPresets = () => cache;
  window.writePresets = () => { throw new Error("Presets are managed by the authenticated workspace."); };
  window.renderPresetSelect = renderPresetSelectServer;
  window.saveCurrentPreset = openSaveDialog;
  window.loadSelectedPreset = loadSelectedPresetServer;
  window.deleteSelectedPreset = deleteSelectedPresetServer;
  window.adbgathOpenPresetDialog = openSaveDialog;

  window.installOperationCatalog = function installOperationCatalogServer371(items) {
    const legacy = detachLegacyStorage();
    const result = inheritedInstallOperationCatalog(items);
    void refreshPresets(legacy);
    return result;
  };

  document.addEventListener("input", event => {
    if (event.target?.id === "ux371PresetName") updateSaveStatus();
  });

  document.addEventListener("submit", event => {
    if (event.target?.id === "ux371PresetForm") {
      event.preventDefault();
      event.stopImmediatePropagation();
      void commitServerPreset();
      return;
    }
    if (event.target?.id === "ux371ConfirmForm" && serverConfirmAction) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const action = serverConfirmAction;
      serverConfirmAction = null;
      const button = document.querySelector("#ux371ConfirmAction");
      const previous = button.textContent;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = "Working…";
      void Promise.resolve(action())
        .then(() => document.querySelector("#ux371ConfirmDialog")?.close?.())
        .catch(error => toast(error.message, true))
        .finally(() => {
          button.disabled = false;
          button.removeAttribute("aria-busy");
          button.textContent = previous;
        });
    }
  }, true);

  // Capture preset controls before the legacy app.js target listeners.  This
  // makes the authenticated 3.7 flow deterministic even if browser/global
  // binding semantics differ: native prompt/localStorage handlers never run.
  document.addEventListener("click", event => {
    const save = event.target?.closest?.("#savePreset");
    if (save) {
      event.preventDefault();
      event.stopImmediatePropagation();
      openSaveDialog();
      return;
    }
    const load = event.target?.closest?.("#loadPreset");
    if (load) {
      event.preventDefault();
      event.stopImmediatePropagation();
      loadSelectedPresetServer();
      return;
    }
    const remove = event.target?.closest?.("#deletePreset");
    if (remove) {
      event.preventDefault();
      event.stopImmediatePropagation();
      deleteSelectedPresetServer();
      return;
    }
    if (event.target?.closest?.("#ux371ConfirmDialog [data-ux371-close]")) serverConfirmAction = null;
  }, true);

  document.addEventListener("DOMContentLoaded", () => {
    updateScopeHint();
    renderPresetSelectServer();
    document.querySelector("#ux371ConfirmDialog")?.addEventListener("cancel", () => { serverConfirmAction = null; });
  });
})();
