"use strict";

(() => {
  const ACTIVE_JOB_STATES = new Set(["queued", "running", "cancelling"]);
  const TERMINAL_JOB_STATES = new Set(["completed", "failed", "cancelled"]);
  const renderedSecurityJobs = new Set();
  const q = selector => document.querySelector(selector);
  const qa = selector => [...document.querySelectorAll(selector)];
  const inheritedRenderWorkspace = window.renderWorkspace;
  const inheritedRenderArtifacts = window.renderArtifacts;
  const inheritedRunSecurity = window.runSecurity;

  function sessionGet(key, fallback = "") {
    try { return sessionStorage.getItem(key) ?? fallback; } catch (_) { return fallback; }
  }

  function sessionSet(key, value) {
    try { sessionStorage.setItem(key, value); } catch (_) { /* optional per-tab preference */ }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = text;
      area.readOnly = true;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  }

  function installJobFilters() {
    const list = q("#jobList");
    if (!list || q("#ux372JobFilters")) return;
    const bar = document.createElement("div");
    bar.id = "ux372JobFilters";
    bar.className = "ux372-filterbar";
    bar.innerHTML = `
      <select id="ux372JobStatus" aria-label="Filter jobs by status">
        <option value="all">All job states</option>
        <option value="active">Active</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
        <option value="cancelled">Cancelled</option>
      </select>
      <input id="ux372JobSearch" type="search" autocomplete="off" placeholder="Filter by action or job ID" aria-label="Filter jobs">
      <span id="ux372JobCount" class="ux372-filter-count"></span>`;
    list.before(bar);
    q("#ux372JobStatus").value = sessionGet("adbgath.jobs.status", "all");
    q("#ux372JobSearch").value = sessionGet("adbgath.jobs.search", "");
    q("#ux372JobStatus").addEventListener("change", event => {
      sessionSet("adbgath.jobs.status", event.target.value);
      decorateJobs();
    });
    q("#ux372JobSearch").addEventListener("input", event => {
      sessionSet("adbgath.jobs.search", event.target.value);
      decorateJobs();
    });
  }

  function decorateJobs() {
    const list = q("#jobList");
    if (!list) return;
    const rows = qa("#jobList > .data-row");
    const statusFilter = q("#ux372JobStatus")?.value || "all";
    const term = (q("#ux372JobSearch")?.value || "").trim().toLowerCase();
    let visible = 0;
    rows.forEach((row, index) => {
      const job = state.jobs[index] || {};
      const status = String(job.status || "").toLowerCase();
      const action = String(job.action || "").toLowerCase();
      const id = String(job.id || "").toLowerCase();
      row.dataset.jobStatus = status;
      row.dataset.jobAction = action;
      const statusMatch = statusFilter === "all"
        || (statusFilter === "active" && ACTIVE_JOB_STATES.has(status))
        || status === statusFilter;
      const termMatch = !term || action.includes(term) || id.includes(term);
      row.hidden = !(statusMatch && termMatch);
      if (!row.hidden) visible += 1;
    });
    const count = q("#ux372JobCount");
    if (count) count.textContent = `${visible} / ${state.jobs.length} jobs`;
  }

  function installArtifactFilters() {
    const list = q("#artifactList");
    if (!list || q("#ux372ArtifactFilters")) return;
    const bar = document.createElement("div");
    bar.id = "ux372ArtifactFilters";
    bar.className = "ux372-filterbar";
    bar.innerHTML = `
      <input id="ux372ArtifactSearch" type="search" autocomplete="off" placeholder="Filter artifacts by path or filename" aria-label="Filter artifacts">
      <span></span>
      <span id="ux372ArtifactCount" class="ux372-filter-count"></span>`;
    list.before(bar);
    q("#ux372ArtifactSearch").value = sessionGet("adbgath.artifacts.search", "");
    q("#ux372ArtifactSearch").addEventListener("input", event => {
      sessionSet("adbgath.artifacts.search", event.target.value);
      decorateArtifacts();
    });
  }

  function decorateArtifacts() {
    const term = (q("#ux372ArtifactSearch")?.value || "").trim().toLowerCase();
    const rows = qa("#artifactList > .artifact-item");
    let visible = 0;
    rows.forEach(row => {
      const path = row.querySelector("code")?.textContent || "";
      row.hidden = Boolean(term) && !path.toLowerCase().includes(term);
      if (!row.hidden) visible += 1;
      if (!row.querySelector(".ux372-copy-path")) {
        const download = row.querySelector("a");
        if (download) {
          const tools = document.createElement("div");
          tools.className = "ux372-artifact-tools";
          const copy = document.createElement("button");
          copy.type = "button";
          copy.className = "text-button ux372-copy-path";
          copy.textContent = "COPY PATH";
          copy.addEventListener("click", async () => {
            const ok = await copyText(path);
            toast(ok ? "Artifact path copied" : "Unable to copy artifact path", !ok);
          });
          download.replaceWith(tools);
          tools.append(copy, download);
        }
      }
    });
    const count = q("#ux372ArtifactCount");
    if (count) count.textContent = `${visible} / ${rows.length} artifacts`;
  }

  function installSecurityStatus() {
    const root = q(".security-actions");
    if (!root || q("#ux372SecurityStatus")) return;
    const status = document.createElement("small");
    status.id = "ux372SecurityStatus";
    status.className = "ux372-security-status";
    status.textContent = "Security jobs run in the selected authenticated workspace.";
    root.appendChild(status);
  }

  function securityResult(job) {
    if (!job?.result || job.status !== "completed") return null;
    if (job.action === "security") return job.result;
    if (job.action === "mastg") return job.result.security || job.result.audit || null;
    return null;
  }

  function syncSecurityJobs() {
    const candidates = state.jobs.filter(job => job.action === "security" || job.action === "mastg");
    const latest = candidates[0];
    const status = q("#ux372SecurityStatus");
    if (latest && status) {
      status.dataset.state = ACTIVE_JOB_STATES.has(latest.status) ? "running" : latest.status;
      status.textContent = `${latest.action} · ${latest.status} · ${Number(latest.progress || 0)}%`;
    }
    for (const job of candidates) {
      if (!TERMINAL_JOB_STATES.has(job.status) || renderedSecurityJobs.has(job.id)) continue;
      renderedSecurityJobs.add(job.id);
      const report = securityResult(job);
      if (report && typeof renderFindings === "function") renderFindings(report);
    }
  }

  window.renderWorkspace = function renderWorkspace372() {
    const result = inheritedRenderWorkspace();
    installJobFilters();
    decorateJobs();
    syncSecurityJobs();
    return result;
  };
  try { renderWorkspace = window.renderWorkspace; } catch (_) {}

  window.renderArtifacts = function renderArtifacts372(rows = null) {
    const result = inheritedRenderArtifacts(rows);
    installArtifactFilters();
    decorateArtifacts();
    return result;
  };
  try { renderArtifacts = window.renderArtifacts; } catch (_) {}

  // Capture the Security buttons before the base target listener. Queue the
  // authenticated job but keep the operator in the Security view, where the
  // result is rendered automatically when polling observes completion.
  document.addEventListener("click", event => {
    const button = event.target?.closest?.("#runSecurity, #runMastg");
    if (!button || typeof inheritedRunSecurity !== "function") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const mode = button.id === "runMastg" ? "mastg" : "security";
    const status = q("#ux372SecurityStatus");
    if (status) {
      status.dataset.state = "running";
      status.textContent = mode === "mastg" ? "Queueing MASTG bundle…" : "Queueing security audit…";
    }
    void Promise.resolve(inheritedRunSecurity(mode))
      .then(() => {
        if (typeof switchView === "function") switchView("security");
        syncSecurityJobs();
      })
      .catch(error => toast(error.message || String(error), true));
  }, true);

  document.addEventListener("DOMContentLoaded", () => {
    installJobFilters();
    installArtifactFilters();
    installSecurityStatus();
    decorateJobs();
    decorateArtifacts();
    syncSecurityJobs();
  });
})();
