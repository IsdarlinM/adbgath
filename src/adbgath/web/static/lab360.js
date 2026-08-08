"use strict";

(() => {
  const byId = id => document.getElementById(id);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials:"same-origin",
      ...options,
      headers:{"Content-Type":"application/json", ...(options.headers || {})},
    });
    const data = await response.json().catch(() => ({ok:false, error:`HTTP ${response.status}`}));
    if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data.data;
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  }

  function toast(message, bad = false) {
    const node = byId("labToast") || document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("error", bad);
    node.classList.add("show");
    clearTimeout(node._labTimer);
    node._labTimer = setTimeout(() => node.classList.remove("show"), 2500);
  }

  async function refresh() {
    if (!byId("agents")) return;
    try {
      const status = await api("/api/lab/status");
      byId("agentCount").textContent = status.agents.length;
      byId("poolCount").textContent = status.pools.length;
      byId("jobCount").textContent = status.jobs.length;
      byId("auditState").textContent = status.audit.ok ? "VALID" : "BROKEN";
      byId("agents").innerHTML = status.agents.length
        ? status.agents.map(agent => `<div class='lab-row'><strong>${esc(agent.name)}</strong><span>${esc(agent.status)}</span><small>${esc(agent.last_seen || "never seen")}</small></div>`).join("")
        : "No agents enrolled.";
      byId("jobs").innerHTML = status.jobs.length
        ? status.jobs.slice(0, 20).map(job => `<div class='lab-row'><strong>${esc(job.action)}</strong><span>${esc(job.status)}</span><small>${esc(job.id)}</small></div>`).join("")
        : "No distributed jobs.";
      const events = await api("/api/lab/audit?limit=50");
      byId("auditEvents").innerHTML = events.length
        ? events.map(event => `<div class='audit-row'><span>${esc(event.created_at)}</span><strong>${esc(event.action)}</strong><em>${esc(event.decision)}</em><small>${esc(event.actor)}</small></div>`).join("")
        : "No events.";
      const artifacts = await api("/api/artifact-store/status");
      byId("artifactStatus").innerHTML = `<div class='lab-row'><strong>${artifacts.objects} objects</strong><span>${artifacts.references} refs</span><small>${artifacts.stored_bytes} stored bytes</small></div>`;
    } catch (error) {
      toast(error.message, true);
    }
  }

  function wire() {
    if (!byId("agents")) return;
    byId("refreshLab")?.addEventListener("click", refresh);
    byId("submitJob")?.addEventListener("click", async () => {
      try {
        const payload = JSON.parse(byId("jobPayload").value || "{}");
        await api("/api/lab/job", {
          method:"POST",
          body:JSON.stringify({
            agent:byId("jobAgent").value,
            action:byId("jobAction").value,
            payload,
            role:byId("jobRole").value,
            approved:byId("jobApproved").checked,
          }),
        });
        toast("Job queued");
        await refresh();
      } catch (error) {
        toast(error.message, true);
      }
    });
    byId("checkPolicy")?.addEventListener("click", async () => {
      try {
        byId("policyOutput").textContent = JSON.stringify(await api("/api/lab/policy/check", {
          method:"POST",
          body:JSON.stringify({role:byId("policyRole").value, action:byId("policyAction").value}),
        }), null, 2);
      } catch (error) {
        toast(error.message, true);
      }
    });
    byId("verifyArtifacts")?.addEventListener("click", async () => {
      try {
        byId("artifactOutput").textContent = JSON.stringify(await api("/api/artifact-store/verify"), null, 2);
      } catch (error) {
        toast(error.message, true);
      }
    });
    byId("verifyAudit")?.addEventListener("click", async () => {
      try {
        const value = await api("/api/lab/audit/verify");
        toast(value.ok ? `Audit chain valid (${value.checked})` : `Audit chain broken at ${value.failed_id}`, !value.ok);
        await refresh();
      } catch (error) {
        toast(error.message, true);
      }
    });
  }

  window.adbgathLabRefresh = refresh;
  document.addEventListener("DOMContentLoaded", wire);
})();
