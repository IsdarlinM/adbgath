"use strict";

(() => {
  let brokerSocket = null;

  const q = selector => document.querySelector(selector);

  function notify(message, error = false) {
    if (typeof window.toast === "function") return window.toast(message, error);
    const node = q("#toast");
    if (!node) return;
    node.textContent = message;
    node.className = `toast show${error ? " error" : ""}`;
    clearTimeout(node._integratedTimer);
    node._integratedTimer = setTimeout(() => { node.className = "toast"; }, 3000);
  }

  async function request(url, options = {}) {
    const headers = options.body === undefined ? (options.headers || {}) : {"Content-Type":"application/json", ...(options.headers || {})};
    const response = await fetch(url, {credentials:"same-origin", ...options, headers});
    const data = await response.json().catch(() => ({ok:false, error:`HTTP ${response.status}`}));
    if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data;
  }

  async function execute(action, payload = {}, confirmation = null) {
    const response = await request("/api/execute", {
      method:"POST",
      body:JSON.stringify({action, payload, confirmation}),
    });
    return response.data;
  }

  function setAdvancedOutput(selector, value) {
    const node = q(selector);
    if (!node) return;
    node.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    node.scrollTop = node.scrollHeight;
  }

  function setAdvancedBadge(text, state = "") {
    const node = q("#dashAdvancedState");
    if (!node) return;
    node.textContent = text;
    node.classList.remove("ok", "fail");
    if (state) node.classList.add(state);
  }

  function syncViewUrl(view, advanced = false) {
    const url = new URL(location.href);
    if (!view || view === "overview") url.searchParams.delete("view");
    else url.searchParams.set("view", view);
    if (view === "wireless-main" && advanced) url.searchParams.set("advanced", "1");
    else url.searchParams.delete("advanced");
    history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function toggleAdvanced(force = null, updateUrl = true) {
    const panel = q("#advancedWirelessPanel");
    const button = q("#toggleAdvancedWireless");
    if (!panel || !button) return;
    const show = force === null ? panel.classList.contains("hidden") : Boolean(force);
    panel.classList.toggle("hidden", !show);
    button.textContent = show ? "Hide advanced wireless controls" : "Advanced wireless controls";
    if (updateUrl) syncViewUrl("wireless-main", show);
    if (show) panel.scrollIntoView({behavior:"smooth", block:"start"});
  }

  async function diagnose(fix = false) {
    setAdvancedBadge(fix ? "REPAIRING" : "CHECKING");
    try {
      const result = await execute("wireless_diagnose", {fix, persist:false});
      setAdvancedOutput("#dashDiagnosticOutput", result);
      setAdvancedBadge(result?.ok === false ? "ATTENTION" : "READY", result?.ok === false ? "fail" : "ok");
      notify(fix ? "Wireless repair completed" : "Wireless diagnostics completed", result?.ok === false);
    } catch (error) {
      setAdvancedOutput("#dashDiagnosticOutput", {ok:false, error:error.message});
      setAdvancedBadge("FAILED", "fail");
      notify(error.message, true);
    }
  }

  async function disconnectCurrent() {
    const target = q("#dashConnectTarget")?.value.trim();
    if (!target) return notify("Enter or select a connection endpoint first.", true);
    try {
      const result = await execute("wireless_disconnect", {target});
      setAdvancedOutput("#dashDiagnosticOutput", result);
      notify(result?.ok === false ? "Wireless disconnect failed" : "Wireless endpoint disconnected", result?.ok === false);
      if (result?.ok !== false) {
        const state = q("#dashWirelessState");
        if (state) { state.textContent = "READY"; state.classList.remove("ok", "fail"); }
      }
    } catch (error) {
      notify(error.message, true);
    }
  }

  async function forgetKnown(identifier) {
    try {
      await execute("wireless_forget", {identifier}, "AUTHORIZED");
      notify("Local wireless record removed");
      await loadKnown();
    } catch (error) {
      notify(error.message, true);
    }
  }

  async function saveAlias(identifier, input) {
    const alias = input.value.trim();
    if (!alias) return notify("Enter an alias first.", true);
    try {
      await execute("wireless_alias", {identifier, alias});
      notify("Wireless alias updated");
      await loadKnown();
    } catch (error) {
      notify(error.message, true);
    }
  }

  function renderKnown(rows) {
    const root = q("#dashKnownWireless");
    if (!root) return;
    const items = Array.isArray(rows) ? rows : (rows?.targets || rows?.devices || rows?.known || []);
    root.innerHTML = "";
    root.classList.toggle("empty-state", !items.length);
    if (!items.length) {
      root.textContent = "No known wireless targets.";
      return;
    }
    items.forEach((item, index) => {
      const identifier = String(item.id || item.serial || item.instance || item.alias || item.endpoint || "");
      const row = document.createElement("div");
      row.className = "advanced-known-row";
      const details = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.alias || item.given_name || item.model || identifier || `Target ${index + 1}`;
      const meta = document.createElement("small");
      meta.textContent = [item.serial, item.endpoint || item.last_endpoint, item.state, item.last_seen].filter(Boolean).join(" · ");
      const aliasInput = document.createElement("input");
      aliasInput.className = "advanced-alias-input";
      aliasInput.placeholder = "Local alias";
      aliasInput.value = item.alias || "";
      details.append(title, meta, aliasInput);
      const actions = document.createElement("div");
      actions.className = "advanced-known-actions";
      const aliasButton = document.createElement("button");
      aliasButton.className = "secondary";
      aliasButton.textContent = "Save alias";
      aliasButton.disabled = !identifier;
      aliasButton.addEventListener("click", () => saveAlias(identifier, aliasInput));
      const forgetButton = document.createElement("button");
      forgetButton.className = "secondary";
      forgetButton.textContent = "Forget local";
      forgetButton.disabled = !identifier;
      forgetButton.addEventListener("click", () => forgetKnown(identifier));
      actions.append(aliasButton, forgetButton);
      row.append(details, actions);
      root.appendChild(row);
    });
  }

  async function loadKnown() {
    try {
      const result = await execute("wireless_known", {});
      renderKnown(result);
      return result;
    } catch (error) {
      notify(error.message, true);
      return null;
    }
  }

  function startBrokerWatch() {
    if (brokerSocket) brokerSocket.close();
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${location.host}/ws/wireless`);
    brokerSocket = socket;
    q("#dashStartWirelessWatch").disabled = true;
    q("#dashStopWirelessWatch").disabled = false;
    setAdvancedBadge("LIVE", "ok");
    setAdvancedOutput("#dashBrokerOutput", "Connecting to shared wireless broker…");
    socket.onmessage = event => {
      try {
        const data = JSON.parse(event.data);
        setAdvancedOutput("#dashBrokerOutput", data.data || data);
      } catch (_) {
        setAdvancedOutput("#dashBrokerOutput", event.data);
      }
    };
    socket.onerror = () => {
      setAdvancedBadge("ERROR", "fail");
      notify("Wireless broker connection failed", true);
    };
    socket.onclose = () => {
      if (brokerSocket === socket) brokerSocket = null;
      const start = q("#dashStartWirelessWatch");
      const stop = q("#dashStopWirelessWatch");
      if (start) start.disabled = false;
      if (stop) stop.disabled = true;
      if (q("#dashAdvancedState")?.textContent === "LIVE") setAdvancedBadge("IDLE");
    };
  }

  function stopBrokerWatch() {
    if (brokerSocket) brokerSocket.close();
    brokerSocket = null;
    setAdvancedOutput("#dashBrokerOutput", "Live wireless events are stopped.");
  }

  function selectViewFromUrl() {
    const params = new URLSearchParams(location.search);
    const view = params.get("view");
    if (!view) return;
    const nav = q(`.nav-item[data-view="${CSS.escape(view)}"]`);
    if (nav) nav.click();
    if (view === "wireless-main" && params.get("advanced") === "1") toggleAdvanced(true, false);
  }

  function wire() {
    document.querySelectorAll(".nav-item[data-view]").forEach(nav => {
      nav.addEventListener("click", () => {
        const view = nav.dataset.view || "overview";
        const advanced = view === "wireless-main" && !q("#advancedWirelessPanel")?.classList.contains("hidden");
        syncViewUrl(view, advanced);
      });
    });
    q('[data-view="lab-main"]')?.addEventListener("click", () => {
      const title = q("#pageTitle");
      if (title) title.textContent = "Distributed Lab";
      if (typeof window.adbgathLabRefresh === "function") window.adbgathLabRefresh();
    });
    q('[data-view="wireless-main"]')?.addEventListener("click", () => {
      const title = q("#pageTitle");
      if (title) title.textContent = "Wireless Debugging";
    });
    q("#toggleAdvancedWireless")?.addEventListener("click", () => toggleAdvanced());
    q("#dashDiagnose")?.addEventListener("click", () => diagnose(false));
    q("#dashRepair")?.addEventListener("click", () => diagnose(true));
    q("#dashDisconnect")?.addEventListener("click", disconnectCurrent);
    q("#dashRefreshKnown")?.addEventListener("click", loadKnown);
    q("#dashStartWirelessWatch")?.addEventListener("click", startBrokerWatch);
    q("#dashStopWirelessWatch")?.addEventListener("click", stopBrokerWatch);
    selectViewFromUrl();
  }

  document.addEventListener("DOMContentLoaded", wire);
  window.addEventListener("beforeunload", () => { if (brokerSocket) brokerSocket.close(); });
})();
