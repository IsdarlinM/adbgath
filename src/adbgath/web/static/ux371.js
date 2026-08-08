"use strict";

(() => {
  const LEGACY_PRESET_KEY = "adbgath.operationPresets.v1";
  const PRESET_KEY_PREFIX = "adbgath.operationPresets.v2";
  const ACTIVE_JOB_STATES = new Set(["queued", "running", "cancelling"]);
  const TERMINAL_JOB_STATES = new Set(["completed", "failed", "cancelled"]);
  const watchedJobs = new Set();
  const notifiedJobs = new Set();
  let focusedJobId = null;
  let confirmAction = null;

  const originalRenderActionForm = window.renderActionForm;
  const originalInstallOperationCatalog = window.installOperationCatalog;
  const originalFormPayload = window.formPayload;
  const originalExecuteForm = window.executeForm;
  const originalRunSecurity = window.runSecurity;
  const originalLoadPackages = window.loadPackages;

  function scopeParts() {
    const username = document.querySelector(".auth370-account > span")?.textContent?.trim() || "local";
    const workspace = document.querySelector("#auth370WorkspaceSelect");
    const workspaceId = workspace?.value || "default";
    const workspaceName = workspace?.selectedOptions?.[0]?.textContent?.trim() || workspaceId;
    return {username, workspaceId, workspaceName};
  }

  function presetStorageKey() {
    const {username, workspaceId} = scopeParts();
    return `${PRESET_KEY_PREFIX}:${encodeURIComponent(username.toLowerCase())}:${encodeURIComponent(workspaceId)}`;
  }

  function parsePresetArray(raw) {
    try {
      const value = JSON.parse(raw || "[]");
      return Array.isArray(value) ? value.filter(item => item && typeof item.name === "string" && typeof item.action === "string") : [];
    } catch (_) {
      return [];
    }
  }

  function operationFields(action) {
    const config = typeof operation === "function" ? operation(action) : null;
    return Array.isArray(config?.fields) ? config.fields : [];
  }

  function scrubPayload(action, payload) {
    const fields = operationFields(action);
    if (!fields.length) return {...(payload || {})};
    const allowed = new Map(fields.map(field => [field.name, field]));
    const clean = {};
    for (const [name, value] of Object.entries(payload || {})) {
      const field = allowed.get(name);
      if (!field || field.field_type === "secret") continue;
      clean[name] = value;
    }
    return clean;
  }

  function sanitizePreset(item) {
    if (!item || typeof item.name !== "string" || typeof item.action !== "string") return null;
    const name = item.name.trim().slice(0, 80);
    if (!name) return null;
    if (state.operations.size && !state.operations.has(item.action)) return null;
    return {
      name,
      action: item.action,
      payload: scrubPayload(item.action, item.payload),
      updatedAt: typeof item.updatedAt === "string" ? item.updatedAt : new Date().toISOString(),
    };
  }

  function readPresets371() {
    try {
      return parsePresetArray(localStorage.getItem(presetStorageKey())).map(sanitizePreset).filter(Boolean).slice(0, 100);
    } catch (_) {
      return [];
    }
  }

  function writePresets371(items) {
    const clean = (items || []).map(sanitizePreset).filter(Boolean).slice(0, 100);
    try {
      localStorage.setItem(presetStorageKey(), JSON.stringify(clean));
    } catch (error) {
      toast(`Unable to save presets locally: ${error.message}`, true);
      return false;
    }
    renderPresetSelect371();
    return true;
  }

  function migrateLegacyPresets() {
    let legacyRaw = null;
    try { legacyRaw = localStorage.getItem(LEGACY_PRESET_KEY); } catch (_) { return; }
    if (!legacyRaw) return;
    const currentKey = presetStorageKey();
    let existing = null;
    try { existing = localStorage.getItem(currentKey); } catch (_) { return; }
    if (!existing) {
      const migrated = parsePresetArray(legacyRaw).map(sanitizePreset).filter(Boolean).slice(0, 100);
      if (migrated.length) {
        try { localStorage.setItem(currentKey, JSON.stringify(migrated)); }
        catch (_) { return; }
      }
    }
    try { localStorage.removeItem(LEGACY_PRESET_KEY); } catch (_) { /* best effort */ }
  }

  function scopeLabel() {
    const {username, workspaceName} = scopeParts();
    return `${username} / ${workspaceName}`;
  }

  function updatePresetScopeHint() {
    const row = document.querySelector(".preset-row");
    if (!row) return;
    let hint = document.querySelector("#ux371PresetScope");
    if (!hint) {
      hint = document.createElement("small");
      hint.id = "ux371PresetScope";
      hint.className = "ux371-preset-scope";
      row.insertAdjacentElement("afterend", hint);
    }
    hint.innerHTML = `Presets are local to <strong>${escapeHtml(scopeLabel())}</strong>. Secret fields are never stored.`;
    const select = document.querySelector("#presetSelect");
    if (select) select.title = `Preset scope: ${scopeLabel()}`;
  }

  function renderPresetSelect371() {
    const select = document.querySelector("#presetSelect");
    if (!select) return;
    const previous = select.value;
    const presets = readPresets371();
    select.innerHTML = '<option value="">Saved form presets</option>' + presets.map((item, index) => `<option value="${index}">${escapeHtml(item.name)} · ${escapeHtml(item.action)}</option>`).join("");
    if ([...select.options].some(option => option.value === previous)) select.value = previous;
    updatePresetScopeHint();
  }

  function secretFieldNames(action) {
    return operationFields(action).filter(field => field.field_type === "secret").map(field => field.name);
  }

  function hardenSecretFields(action) {
    for (const name of secretFieldNames(action)) {
      const input = document.querySelector(`#dynamicFields [name="${CSS.escape(name)}"]`);
      if (!input || input.tagName !== "INPUT") continue;
      input.type = "password";
      input.autocomplete = "off";
      input.setAttribute("data-secret-field", "true");
      input.setAttribute("spellcheck", "false");
    }
  }

  function clearFieldErrors() {
    document.querySelectorAll("#dynamicFields .ux371-field-error").forEach(node => node.remove());
    document.querySelectorAll("#dynamicFields .ux371-invalid").forEach(node => node.classList.remove("ux371-invalid"));
  }

  function addFieldError(input, message) {
    input.classList.add("ux371-invalid");
    const error = document.createElement("small");
    error.className = "ux371-field-error";
    error.textContent = message;
    input.closest("label")?.appendChild(error);
  }

  function validateOperationFields() {
    clearFieldErrors();
    const config = typeof operation === "function" ? operation(document.querySelector("#actionSelect")?.value) : null;
    let firstInvalid = null;
    for (const field of config?.fields || []) {
      const input = document.querySelector(`#dynamicFields [name="${CSS.escape(field.name)}"]`);
      if (!input) continue;
      const value = field.field_type === "boolean" ? input.checked : input.value.trim();
      let message = "";
      if (field.required && (value === "" || value === null || value === undefined || (Array.isArray(value) && !value.length))) {
        message = `${field.label} is required.`;
      } else if (field.field_type === "number" && value !== "") {
        const number = Number(value);
        if (!Number.isFinite(number)) message = `${field.label} must be a number.`;
        else if (field.minimum !== null && field.minimum !== undefined && number < field.minimum) message = `${field.label} must be at least ${field.minimum}.`;
        else if (field.maximum !== null && field.maximum !== undefined && number > field.maximum) message = `${field.label} must be at most ${field.maximum}.`;
      }
      if (message) {
        addFieldError(input, message);
        firstInvalid ||= input;
      }
    }
    if (firstInvalid) {
      firstInvalid.focus({preventScroll:true});
      firstInvalid.scrollIntoView({behavior:"smooth", block:"center"});
      throw new Error(firstInvalid.closest("label")?.querySelector(".ux371-field-error")?.textContent || "Review the highlighted fields.");
    }
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function selectedPreset() {
    const select = document.querySelector("#presetSelect");
    const index = Number(select?.value);
    const presets = readPresets371();
    return Number.isInteger(index) && presets[index] ? {index, preset:presets[index]} : null;
  }

  function updateSaveDialogState() {
    const input = document.querySelector("#ux371PresetName");
    const status = document.querySelector("#ux371PresetSaveStatus");
    const button = document.querySelector("#ux371PresetSaveConfirm");
    if (!input || !status || !button) return;
    const name = input.value.trim().toLowerCase();
    const existing = readPresets371().find(item => item.name.toLowerCase() === name);
    const secretCount = secretFieldNames(document.querySelector("#actionSelect")?.value || "").length;
    status.textContent = existing
      ? `A preset named “${existing.name}” already exists in this workspace and will be replaced.`
      : secretCount
        ? `${secretCount} secret field${secretCount === 1 ? "" : "s"} will be excluded from local storage.`
        : "Only declared operation fields are stored locally.";
    button.textContent = existing ? "Replace preset" : "Save preset";
  }

  function saveCurrentPreset371() {
    try {
      validateOperationFields();
      const action = document.querySelector("#actionSelect")?.value;
      if (!action || !state.operations.has(action)) return toast("Select a valid operation first.", true);
      const current = selectedPreset();
      const input = document.querySelector("#ux371PresetName");
      const scope = document.querySelector("#ux371PresetScopeLabel");
      input.value = current?.preset?.action === action ? current.preset.name : `${action} preset`;
      scope.textContent = scopeLabel();
      updateSaveDialogState();
      const dialog = document.querySelector("#ux371PresetDialog");
      openDialog(dialog);
      queueMicrotask(() => { input.focus(); input.select(); });
    } catch (error) {
      toast(error.message, true);
    }
  }

  function commitPreset() {
    const action = document.querySelector("#actionSelect")?.value;
    const name = document.querySelector("#ux371PresetName")?.value?.trim().slice(0, 80) || "";
    if (!name) {
      document.querySelector("#ux371PresetName")?.focus();
      return toast("Preset name is required.", true);
    }
    try {
      const payload = scrubPayload(action, formPayload());
      const presets = readPresets371().filter(item => item.name.toLowerCase() !== name.toLowerCase());
      presets.unshift({name, action, payload, updatedAt:new Date().toISOString()});
      if (!writePresets371(presets)) return;
      document.querySelector("#presetSelect").value = "0";
      closeDialog(document.querySelector("#ux371PresetDialog"));
      toast("Preset saved for the active user and workspace");
    } catch (error) {
      toast(error.message, true);
    }
  }

  function requestConfirmation({title, message, confirmText = "Confirm", tone = "danger", action}) {
    const dialog = document.querySelector("#ux371ConfirmDialog");
    document.querySelector("#ux371ConfirmTitle").textContent = title;
    document.querySelector("#ux371ConfirmMessage").textContent = message;
    const button = document.querySelector("#ux371ConfirmAction");
    button.textContent = confirmText;
    button.dataset.confirmTone = tone;
    confirmAction = action;
    openDialog(dialog);
    queueMicrotask(() => button.focus());
  }

  function deleteSelectedPreset371() {
    const selected = selectedPreset();
    if (!selected) return toast("Select a preset to delete.", true);
    requestConfirmation({
      title: "Delete saved preset?",
      message: `“${selected.preset.name}” will be removed only from ${scopeLabel()}. This does not affect server-side projects or evidence.`,
      confirmText: "Delete preset",
      action: async () => {
        const presets = readPresets371();
        presets.splice(selected.index, 1);
        writePresets371(presets);
        toast("Preset deleted");
      },
    });
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const copied = document.execCommand("copy");
      area.remove();
      return copied;
    }
  }

  function installCopyButtons() {
    document.querySelectorAll("[data-console]").forEach(consoleNode => {
      const panel = consoleNode.closest(".console-panel");
      const head = panel?.querySelector(".panel-head");
      if (!head || head.querySelector(".ux371-copy-button")) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "text-button ux371-copy-button";
      button.textContent = "COPY";
      button.addEventListener("click", async () => {
        const ok = await copyText(consoleNode.textContent || "");
        toast(ok ? "Output copied" : "Unable to copy output", !ok);
      });
      const clear = head.querySelector(".clear-output");
      if (clear) clear.insertAdjacentElement("beforebegin", button);
      else head.appendChild(button);
    });
  }

  function setBusy(button, busy, busyText = "Working…") {
    if (!button) return;
    if (busy) {
      if (!button.dataset.ux371Label) button.dataset.ux371Label = button.textContent;
      button.textContent = busyText;
      button.disabled = true;
      button.classList.add("ux371-busy");
      button.setAttribute("aria-busy", "true");
    } else {
      button.textContent = button.dataset.ux371Label || button.textContent;
      delete button.dataset.ux371Label;
      button.disabled = false;
      button.classList.remove("ux371-busy");
      button.removeAttribute("aria-busy");
    }
  }

  async function pollWatchedJobs() {
    state.jobTimer = null;
    try {
      const rows = (await api("/api/jobs")).data || [];
      state.jobs = rows;
      renderWorkspace();
      const focused = rows.find(job => job.id === focusedJobId);
      if (focused) setOutput(focused);
      for (const jobId of [...watchedJobs]) {
        const job = rows.find(item => item.id === jobId);
        if (!job || !TERMINAL_JOB_STATES.has(job.status)) continue;
        watchedJobs.delete(jobId);
        if (!notifiedJobs.has(jobId)) {
          notifiedJobs.add(jobId);
          if (job.result) collectArtifacts(job.result);
          toast(`${job.action} ${job.status}`, job.status === "failed");
        }
      }
      if (watchedJobs.size) {
        state.jobTimer = setTimeout(pollWatchedJobs, document.hidden ? 3500 : 1200);
      }
    } catch (error) {
      watchedJobs.clear();
      state.jobTimer = null;
      toast(error.message, true);
    }
  }

  function watchJob371(jobId) {
    if (!jobId) return;
    watchedJobs.add(jobId);
    focusedJobId = jobId;
    notifiedJobs.delete(jobId);
    if (state.jobTimer) return;
    void pollWatchedJobs();
  }

  window.readPresets = readPresets371;
  window.writePresets = writePresets371;
  window.renderPresetSelect = renderPresetSelect371;
  window.saveCurrentPreset = saveCurrentPreset371;
  window.deleteSelectedPreset = deleteSelectedPreset371;
  window.watchJob = watchJob371;

  window.renderActionForm = function renderActionForm371(action) {
    const result = originalRenderActionForm(action);
    hardenSecretFields(action);
    clearFieldErrors();
    return result;
  };

  window.installOperationCatalog = function installOperationCatalog371(items) {
    const result = originalInstallOperationCatalog(items);
    migrateLegacyPresets();
    renderPresetSelect371();
    hardenSecretFields(document.querySelector("#actionSelect")?.value || "");
    return result;
  };

  window.formPayload = function formPayload371() {
    validateOperationFields();
    return originalFormPayload();
  };

  window.executeForm = async function executeForm371() {
    const button = document.querySelector("#executeAction");
    if (button?.disabled) return;
    const config = typeof operation === "function" ? operation(document.querySelector("#actionSelect")?.value) : null;
    setBusy(button, true, config?.long_running ? "Queueing…" : "Executing…");
    try { return await originalExecuteForm(); }
    finally {
      setBusy(button, false);
      button.textContent = config?.long_running ? "Queue operation" : "Execute operation";
    }
  };

  window.runSecurity = async function runSecurity371(mode = "security") {
    const button = document.querySelector(mode === "mastg" ? "#runMastg" : "#runSecurity");
    if (button?.disabled) return;
    setBusy(button, true, mode === "mastg" ? "Building…" : "Running…");
    try { return await originalRunSecurity(mode); }
    finally { setBusy(button, false); }
  };

  window.loadPackages = async function loadPackages371() {
    const button = document.querySelector("#loadPackages");
    if (button?.disabled) return;
    setBusy(button, true, "LOADING…");
    try { return await originalLoadPackages(); }
    finally { setBusy(button, false); }
  };

  function initializeDialogs() {
    const saveForm = document.querySelector("#ux371PresetForm");
    saveForm?.addEventListener("submit", event => { event.preventDefault(); commitPreset(); });
    document.querySelector("#ux371PresetName")?.addEventListener("input", updateSaveDialogState);

    const confirmForm = document.querySelector("#ux371ConfirmForm");
    confirmForm?.addEventListener("submit", async event => {
      event.preventDefault();
      const button = document.querySelector("#ux371ConfirmAction");
      if (!confirmAction || button?.disabled) return;
      const action = confirmAction;
      confirmAction = null;
      setBusy(button, true, "Working…");
      try {
        await action();
        closeDialog(document.querySelector("#ux371ConfirmDialog"));
      } catch (error) {
        toast(error.message, true);
      } finally {
        setBusy(button, false);
      }
    });

    document.querySelectorAll("[data-ux371-close]").forEach(button => button.addEventListener("click", () => {
      confirmAction = null;
      closeDialog(button.closest("dialog"));
    }));
    document.querySelector("#ux371ConfirmDialog")?.addEventListener("cancel", () => { confirmAction = null; });
  }

  document.addEventListener("input", event => {
    const input = event.target.closest?.("#dynamicFields .ux371-invalid");
    if (!input) return;
    input.classList.remove("ux371-invalid");
    input.closest("label")?.querySelector(".ux371-field-error")?.remove();
  });

  document.addEventListener("click", event => {
    const clearLogs = event.target.closest?.("#clearLogs");
    if (clearLogs) {
      event.preventDefault();
      event.stopImmediatePropagation();
      requestConfirmation({
        title: "Clear device log buffer?",
        message: "This removes the current device logcat buffer. Export or bookmark evidence first if it must be retained.",
        confirmText: "Clear buffer",
        action: async () => {
          await execute("logs_clear", {}, "AUTHORIZED");
          state.logLines = [];
          state.logBookmarks = [];
          renderLogBookmarks();
          document.querySelector("#liveConsole").textContent = "Device log buffer cleared.\n";
        },
      });
      return;
    }

    const cancelJob = event.target.closest?.(".cancel-job");
    if (cancelJob) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const jobId = cancelJob.dataset.job;
      requestConfirmation({
        title: "Cancel background job?",
        message: `ADB-Gath will request cancellation of ${jobId}. Already-created evidence is retained.`,
        confirmText: "Cancel job",
        action: async () => {
          await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method:"POST", body:"{}"});
          watchedJobs.add(jobId);
          focusedJobId = jobId;
          if (!state.jobTimer) void pollWatchedJobs();
        },
      });
    }
  }, true);

  document.addEventListener("DOMContentLoaded", () => {
    initializeDialogs();
    updatePresetScopeHint();
    installCopyButtons();
    const toastNode = document.querySelector("#toast");
    if (toastNode) {
      toastNode.setAttribute("role", "status");
      toastNode.setAttribute("aria-live", "polite");
      toastNode.setAttribute("aria-atomic", "true");
    }
  });
})();
