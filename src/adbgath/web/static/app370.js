"use strict";

(() => {
  const authState = {csrf: "", me: null};
  const q = selector => document.querySelector(selector);

  function readableDetail(detail, fallback) {
    if (!detail) return fallback;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map(item => {
        if (typeof item === "string") return item;
        const loc = Array.isArray(item?.loc) ? item.loc.filter(part => part !== "body").join(".") : "";
        const msg = item?.msg || item?.message || JSON.stringify(item);
        return loc ? `${loc}: ${msg}` : msg;
      }).join("; ");
    }
    if (typeof detail === "object") return detail.message || detail.error || JSON.stringify(detail);
    return String(detail);
  }

  async function rawJson(url, options = {}) {
    const isForm = options.body instanceof FormData;
    const headers = isForm ? {...(options.headers || {})} : {"Content-Type":"application/json", ...(options.headers || {})};
    const response = await fetch(url, {credentials:"same-origin", ...options, headers});
    const data = await response.json().catch(() => ({ok:false, error:`HTTP ${response.status}`}));
    if (!response.ok || data.ok === false) {
      const message = readableDetail(data.error ?? data.detail, `HTTP ${response.status}`);
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  async function ensureAuthContext() {
    if (authState.csrf && authState.me) return authState.me;
    const response = await rawJson("/api/auth/me");
    authState.me = response.data;
    authState.csrf = response.data?.csrf || "";
    return authState.me;
  }

  async function api370(url, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const isUnsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
    const isForm = options.body instanceof FormData;
    const headers = isForm ? {...(options.headers || {})} : {"Content-Type":"application/json", ...(options.headers || {})};
    if (isUnsafe) {
      if (!authState.csrf) await ensureAuthContext();
      headers["X-ADBGATH-CSRF"] = authState.csrf;
    }
    try {
      return await rawJson(url, {...options, headers});
    } catch (error) {
      if (error.status === 401) location.assign("/");
      throw error;
    }
  }

  window.api = api370;
  try { api = api370; } catch (_) {}

  async function submitJob370(action, payload = {}, confirmation = null) {
    const selectedDeviceFn = typeof selectedDevice === "function" ? selectedDevice : () => null;
    const selectedUserFn = typeof selectedUser === "function" ? selectedUser : () => null;
    const merged = {device:selectedDeviceFn(), user:selectedUserFn(), ...payload};
    if (typeof setOutput === "function") setOutput(`Queueing ${action}…`);
    const response = await api370("/api/jobs", {method:"POST", body:JSON.stringify({action, payload:merged, confirmation})});
    if (typeof toast === "function") toast(`${action} queued`);
    if (typeof switchView === "function") switchView("workspace");
    if (typeof refreshWorkspace === "function") await refreshWorkspace(false);
    if (typeof watchJob === "function") watchJob(response.data.id);
    return response.data;
  }
  window.submitJob = submitJob370;
  try { submitJob = submitJob370; } catch (_) {}

  function showError(error) {
    if (typeof toast === "function") toast(error.message || String(error), true);
  }

  function renderWorkspaceControl(me) {
    const select = q("#auth370WorkspaceSelect");
    if (!select) return;
    select.innerHTML = (me.workspaces || []).map(item => `<option value="${escapeHtml(item.id)}"${item.id === me.workspace.id ? " selected" : ""}>${escapeHtml(item.name)}</option>`).join("");
  }

  async function selectWorkspace(workspaceId) {
    const response = await api370(`/api/workspaces/${encodeURIComponent(workspaceId)}/select`, {method:"POST", body:"{}"});
    authState.me.workspace = response.data;
    location.reload();
  }

  async function createWorkspace() {
    const input = q("#auth370WorkspaceName");
    const name = input?.value.trim();
    if (!name) return showError(new Error("Enter a workspace name."));
    try {
      await api370("/api/workspaces", {method:"POST", body:JSON.stringify({name})});
      if (input) input.value = "";
      q("#auth370WorkspaceDialog")?.close();
      location.reload();
    } catch (error) { showError(error); }
  }

  async function logout() {
    try { await api370("/api/auth/logout", {method:"POST", body:"{}"}); }
    finally { location.assign("/"); }
  }

  function userRow(user) {
    const disabled = Boolean(user.disabled);
    const row = document.createElement("div");
    row.className = "data-row auth370-user-row";
    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = user.display_name || user.username;
    const meta = document.createElement("small");
    meta.textContent = `${user.username} · ${user.role}${disabled ? " · disabled" : ""}`;
    info.append(title, meta);
    const actions = document.createElement("div");
    actions.className = "auth370-user-actions";
    const toggle = document.createElement("button");
    toggle.className = "secondary compact-btn";
    toggle.textContent = disabled ? "Enable" : "Disable";
    toggle.disabled = authState.me?.user?.id === user.id;
    toggle.addEventListener("click", async () => {
      try {
        await api370(`/api/auth/users/${encodeURIComponent(user.id)}/disabled`, {method:"POST", body:JSON.stringify({disabled:!disabled})});
        await loadUsers();
      } catch (error) { showError(error); }
    });
    const reset = document.createElement("button");
    reset.className = "secondary compact-btn";
    reset.textContent = "Reset password";
    reset.addEventListener("click", async () => {
      const password = window.prompt(`New password for ${user.username} (minimum 12 characters):`);
      if (password === null) return;
      try {
        await api370(`/api/auth/users/${encodeURIComponent(user.id)}/password`, {method:"POST", body:JSON.stringify({password})});
        if (typeof toast === "function") toast(`Password reset for ${user.username}`);
      } catch (error) { showError(error); }
    });
    actions.append(toggle, reset);
    row.append(info, actions);
    return row;
  }

  async function loadUsers() {
    const root = q("#auth370UserList");
    if (!root) return;
    try {
      const response = await api370("/api/auth/users");
      const users = response.data || [];
      root.innerHTML = "";
      root.classList.toggle("empty-state", !users.length);
      if (!users.length) root.textContent = "No users.";
      users.forEach(user => root.appendChild(userRow(user)));
    } catch (error) {
      root.textContent = error.message;
      root.classList.add("empty-state");
    }
  }

  async function createUser() {
    const username = q("#auth370NewUsername")?.value.trim() || "";
    const displayName = q("#auth370NewDisplay")?.value.trim() || "";
    const role = q("#auth370NewRole")?.value || "user";
    const passwordInput = q("#auth370NewPassword");
    const password = passwordInput?.value || "";
    try {
      await api370("/api/auth/users", {method:"POST", body:JSON.stringify({username, display_name:displayName, role, password})});
      if (passwordInput) passwordInput.value = "";
      q("#auth370NewUsername").value = "";
      q("#auth370NewDisplay").value = "";
      if (typeof toast === "function") toast(`User ${username} created`);
      await loadUsers();
    } catch (error) { showError(error); }
  }

  function patchViewTitles() {
    if (typeof switchView !== "function" || window.__adbgath370SwitchPatched) return;
    const original = switchView;
    const wrapped = function(name) {
      const result = original(name);
      if (name === "users370" && q("#pageTitle")) q("#pageTitle").textContent = "Users and access";
      return result;
    };
    window.switchView = wrapped;
    try { switchView = wrapped; } catch (_) {}
    window.__adbgath370SwitchPatched = true;
  }

  async function initialize() {
    try {
      const me = await ensureAuthContext();
      renderWorkspaceControl(me);
      patchViewTitles();
      q("#auth370WorkspaceSelect")?.addEventListener("change", event => selectWorkspace(event.target.value));
      q("#auth370WorkspaceAdd")?.addEventListener("click", () => q("#auth370WorkspaceDialog")?.showModal());
      q("#auth370WorkspaceCreate")?.addEventListener("click", createWorkspace);
      q("#auth370Logout")?.addEventListener("click", logout);
      q("#auth370CreateUser")?.addEventListener("click", createUser);
      q("#auth370RefreshUsers")?.addEventListener("click", loadUsers);
      q('[data-view="users370"]')?.addEventListener("click", loadUsers);
    } catch (error) {
      if (error.status !== 401) showError(error);
    }
  }

  document.addEventListener("DOMContentLoaded", initialize);
})();
