"use strict";

(() => {
  const TERMINAL_JOB_STATES = new Set(["completed", "failed", "cancelled"]);
  const watchedJobs = new Set();
  const notifiedJobs = new Set();
  let focusedJobId = null;
  let confirmAction = null;
  let jobPollRunning = false;

  const originalRenderActionForm = window.renderActionForm;
  const originalInstallOperationCatalog = window.installOperationCatalog;
  const originalFormPayload = window.formPayload;
  const originalExecuteForm = window.executeForm;
  const originalRunSecurity = window.runSecurity;
  const originalLoadPackages = window.loadPackages;

  function operationFields(action) {
    const config = typeof operation === "function" ? operation(action) : null;
    return Array.isArray(config?.fields) ? config.fields : [];
  }

  function hardenSecretFields(action) {
    for (const field of operationFields(action)) {
      if (field.field_type !== "secret") continue;
      const input = document.querySelector(`#dynamicFields [name="${CSS.escape(field.name)}"]`);
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
      if (field.required && (value === "" || value === null || value === undefined)) {
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
    if (!firstInvalid) return;
    firstInvalid.focus({preventScroll:true});
    firstInvalid.scrollIntoView({behavior:"smooth", block:"center"});
    throw new Error(firstInvalid.closest("label")?.querySelector(".ux371-field-error")?.textContent || "Review the highlighted fields.");
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
      const head = consoleNode.closest(".console-panel")?.querySelector(".panel-head");
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
      return;
    }
    button.textContent = button.dataset.ux371Label || button.textContent;
    delete button.dataset.ux371Label;
    button.disabled = false;
    button.classList.remove("ux371-busy");
    button.removeAttribute("aria-busy");
  }

  function scheduleJobPoll() {
    if (!watchedJobs.size || state.jobTimer || jobPollRunning) return;
    state.jobTimer = setTimeout(() => {
      state.jobTimer = null;
      void pollWatchedJobs();
    }, document.hidden ? 3500 : 1200);
  }

  async function pollWatchedJobs() {
    if (jobPollRunning) return;
    jobPollRunning = true;
    try {
      const rows = (await api("/api/jobs")).data || [];
      state.jobs = rows;
      renderWorkspace();
      const focused = rows.find(job => job.id === focusedJobId);
      if (focused) setOutput(focused);
      for (const jobId of [...watchedJobs]) {
        const job = rows.find(item => item.id === jobId);
        if (!job) {
          watchedJobs.delete(jobId);
          continue;
        }
        if (!TERMINAL_JOB_STATES.has(job.status)) continue;
        watchedJobs.delete(jobId);
        if (notifiedJobs.has(jobId)) continue;
        notifiedJobs.add(jobId);
        if (job.result) collectArtifacts(job.result);
        toast(`${job.action} ${job.status}`, job.status === "failed");
      }
    } catch (error) {
      watchedJobs.clear();
      toast(error.message, true);
    } finally {
      jobPollRunning = false;
      scheduleJobPoll();
    }
  }

  function watchJob371(jobId) {
    if (!jobId) return;
    watchedJobs.add(jobId);
    focusedJobId = jobId;
    notifiedJobs.delete(jobId);
    if (!jobPollRunning && !state.jobTimer) void pollWatchedJobs();
  }

  window.watchJob = watchJob371;

  window.renderActionForm = function renderActionForm371(action) {
    const result = originalRenderActionForm(action);
    hardenSecretFields(action);
    clearFieldErrors();
    return result;
  };

  window.installOperationCatalog = function installOperationCatalog371(items) {
    const result = originalInstallOperationCatalog(items);
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
    try {
      return await originalExecuteForm();
    } finally {
      setBusy(button, false);
      button.textContent = config?.long_running ? "Queue operation" : "Execute operation";
    }
  };

  window.runSecurity = async function runSecurity371(mode = "security") {
    const button = document.querySelector(mode === "mastg" ? "#runMastg" : "#runSecurity");
    if (button?.disabled) return;
    setBusy(button, true, mode === "mastg" ? "Building…" : "Running…");
    try {
      return await originalRunSecurity(mode);
    } finally {
      setBusy(button, false);
    }
  };

  window.loadPackages = async function loadPackages371() {
    const button = document.querySelector("#loadPackages");
    if (button?.disabled) return;
    setBusy(button, true, "LOADING…");
    try {
      return await originalLoadPackages();
    } finally {
      setBusy(button, false);
    }
  };

  function initializeDialogs() {
    const confirmForm = document.querySelector("#ux371ConfirmForm");
    confirmForm?.addEventListener("submit", async event => {
      if (!confirmAction) return;
      event.preventDefault();
      const button = document.querySelector("#ux371ConfirmAction");
      if (button?.disabled) return;
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
    if (!cancelJob) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const jobId = cancelJob.dataset.job;
    requestConfirmation({
      title: "Cancel background job?",
      message: `ADB-Gath will request cancellation of ${jobId}. Already-created evidence is retained.`,
      confirmText: "Cancel job",
      action: async () => {
        await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method:"POST", body:"{}"});
        watchJob371(jobId);
      },
    });
  }, true);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden || !watchedJobs.size) return;
    if (state.jobTimer) {
      clearTimeout(state.jobTimer);
      state.jobTimer = null;
    }
    if (!jobPollRunning) void pollWatchedJobs();
  });

  document.addEventListener("DOMContentLoaded", () => {
    initializeDialogs();
    installCopyButtons();
    const toastNode = document.querySelector("#toast");
    if (toastNode) {
      toastNode.setAttribute("role", "status");
      toastNode.setAttribute("aria-live", "polite");
      toastNode.setAttribute("aria-atomic", "true");
    }
  });
})();
