"use strict";

(() => {
  let qrSessionId = null;
  let qrSocket = null;

  const q = selector => document.querySelector(selector);

  function output(value) {
    const node = q("#dashWirelessOutput");
    if (!node) return;
    node.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    node.scrollTop = node.scrollHeight;
  }

  function notify(message, error = false) {
    if (typeof window.toast === "function") return window.toast(message, error);
    const node = q("#toast");
    if (!node) return;
    node.textContent = message;
    node.className = `toast show${error ? " error" : ""}`;
    clearTimeout(node._pairTimer);
    node._pairTimer = setTimeout(() => { node.className = "toast"; }, 3200);
  }

  async function request(url, options = {}) {
    const headers = {"Content-Type":"application/json", ...(options.headers || {})};
    const response = await fetch(url, {credentials:"same-origin", ...options, headers});
    const data = await response.json().catch(() => ({ok:false, error:`HTTP ${response.status}`}));
    if (!response.ok || data.ok === false) throw new Error(data.error || data.detail || `HTTP ${response.status}`);
    return data;
  }

  async function execute(action, payload = {}, confirmation = null) {
    return request("/api/execute", {
      method:"POST",
      body:JSON.stringify({action, payload, confirmation}),
    });
  }

  function setBadge(selector, text, state = "") {
    const badge = q(selector);
    if (!badge) return;
    badge.textContent = text;
    badge.classList.remove("ok", "fail");
    if (state) badge.classList.add(state);
  }

  function clearQrUi(message = "No active QR session.") {
    if (qrSocket) {
      qrSocket.close();
      qrSocket = null;
    }
    qrSessionId = null;
    const img = q("#dashQrImage");
    const placeholder = q("#dashQrPlaceholder");
    if (img) { img.hidden = true; img.removeAttribute("src"); }
    if (placeholder) placeholder.hidden = false;
    if (q("#dashQrCreate")) q("#dashQrCreate").disabled = false;
    if (q("#dashQrCancel")) q("#dashQrCancel").disabled = true;
    if (q("#dashQrStatus")) q("#dashQrStatus").textContent = message;
    setBadge("#dashQrBadge", "IDLE");
  }

  function watchQr(sessionId) {
    if (qrSocket) qrSocket.close();
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${location.host}/ws/wireless/qr/${encodeURIComponent(sessionId)}`);
    qrSocket = socket;

    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      const data = message.data || {};
      const state = String(data.state || data.status || "waiting");
      const remaining = data.remaining_seconds ?? data.remaining ?? null;
      q("#dashQrStatus").textContent = remaining === null ? state : `${state} · ${remaining}s remaining`;
      setBadge("#dashQrBadge", state.toUpperCase(), ["paired","connected","completed"].includes(state) ? "ok" : (["failed","expired","cancelled"].includes(state) ? "fail" : ""));
      output(data);
      if (data.terminal) {
        if (["paired","connected","completed"].includes(state)) notify(`QR pairing ${state}`);
        else notify(`QR pairing ${state}`, true);
        setTimeout(() => clearQrUi(`QR session ${state}.`), 1000);
      }
    };
    socket.onerror = () => {
      setBadge("#dashQrBadge", "ERROR", "fail");
      q("#dashQrStatus").textContent = "Unable to monitor the QR session.";
    };
    socket.onclose = () => { if (qrSocket === socket) qrSocket = null; };
  }

  async function createQr() {
    if (!q("#dashQrAuthorized").checked) return notify("Confirm that the device is authorized and in scope.", true);
    q("#dashQrCreate").disabled = true;
    try {
      const response = await request("/api/wireless/qr", {
        method:"POST",
        body:JSON.stringify({
          ttl_seconds:Number(q("#dashQrTtl").value || 120),
          auto_connect:q("#dashQrAutoConnect").checked,
          confirmation:"AUTHORIZED",
        }),
      });
      qrSessionId = response.data.id;
      const img = q("#dashQrImage");
      img.src = `${response.svg_url}?t=${Date.now()}`;
      img.hidden = false;
      q("#dashQrPlaceholder").hidden = true;
      q("#dashQrCancel").disabled = false;
      q("#dashQrStatus").textContent = "Waiting for Android to scan the QR…";
      setBadge("#dashQrBadge", "WAITING");
      output(response.data);
      watchQr(qrSessionId);
    } catch (error) {
      q("#dashQrCreate").disabled = false;
      setBadge("#dashQrBadge", "ERROR", "fail");
      notify(error.message, true);
      output({ok:false, error:error.message});
    }
  }

  async function cancelQr() {
    if (!qrSessionId) return clearQrUi();
    try {
      await request(`/api/wireless/qr/${encodeURIComponent(qrSessionId)}/cancel`, {method:"POST", body:"{}"});
      clearQrUi("QR session cancelled.");
      notify("QR pairing cancelled");
    } catch (error) {
      notify(error.message, true);
    }
  }

  async function pairWithCode() {
    const target = q("#dashPairTarget").value.trim();
    const codeInput = q("#dashPairCode");
    const code = codeInput.value.trim();
    if (!q("#dashPairAuthorized").checked) return notify("Confirm that the device is authorized and in scope.", true);
    if (!target) return notify("Enter the temporary pairing HOST:PORT shown by Android.", true);
    if (!/^\d{6}$/.test(code)) return notify("The pairing code must contain exactly six digits.", true);
    q("#dashPairSubmit").disabled = true;
    try {
      const response = await execute("wireless_pair", {target, pairing_code:code}, "AUTHORIZED");
      output(response.data);
      if (response.data?.ok === false) throw new Error(response.data.stdout || response.data.stderr || "ADB pairing failed.");
      notify("Device paired successfully");
      q("#dashConnectTarget").focus();
      await discover();
    } catch (error) {
      notify(error.message, true);
      output({ok:false, error:error.message});
    } finally {
      codeInput.value = "";
      q("#dashPairSubmit").disabled = false;
    }
  }

  function renderServices(rootSelector, services, mode) {
    const root = q(rootSelector);
    root.innerHTML = "";
    root.classList.toggle("empty-state", !services.length);
    if (!services.length) {
      root.textContent = mode === "pair" ? "No pairing services discovered." : "No connection services discovered.";
      return;
    }
    for (const service of services) {
      const row = document.createElement("div");
      row.className = "wireless-service-item";
      const info = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = service.endpoint || `${service.host}:${service.port}`;
      const detail = document.createElement("small");
      detail.textContent = [service.model, service.given_name, service.instance].filter(Boolean).join(" · ") || service.service || mode;
      info.append(title, detail);
      const button = document.createElement("button");
      button.className = "secondary";
      button.textContent = mode === "pair" ? "Use" : "Connect";
      button.addEventListener("click", () => {
        const endpoint = service.endpoint || `${service.host}:${service.port}`;
        if (mode === "pair") {
          q("#dashPairTarget").value = endpoint;
          q("#dashPairCode").focus();
        } else {
          q("#dashConnectTarget").value = endpoint;
          connect();
        }
      });
      row.append(info, button);
      root.appendChild(row);
    }
  }

  async function discover() {
    q("#dashDiscover").disabled = true;
    try {
      const response = await execute("wireless_discover", {refresh:true, detailed:true});
      const data = response.data || {};
      renderServices("#dashPairingServices", data.pairing_services || [], "pair");
      renderServices("#dashConnectServices", data.connect_services || [], "connect");
      output(data);
      notify(`Wireless discovery found ${data.service_count ?? (data.services || []).length} service(s)`);
      return data;
    } catch (error) {
      notify(error.message, true);
      output({ok:false, error:error.message});
      return null;
    } finally {
      q("#dashDiscover").disabled = false;
    }
  }

  async function connect() {
    const target = q("#dashConnectTarget").value.trim();
    if (!target) return notify("Enter the post-pairing connection HOST:PORT.", true);
    q("#dashConnect").disabled = true;
    setBadge("#dashWirelessState", "CONNECTING");
    try {
      const response = await execute("wireless_connect", {target});
      output(response.data);
      if (response.data?.ok === false) throw new Error(response.data.stdout || response.data.stderr || "ADB connection failed.");
      setBadge("#dashWirelessState", "CONNECTED", "ok");
      notify("Wireless ADB connected");
      if (q("#refreshDevices")) q("#refreshDevices").click();
    } catch (error) {
      setBadge("#dashWirelessState", "FAILED", "fail");
      notify(error.message, true);
      output({ok:false, error:error.message});
    } finally {
      q("#dashConnect").disabled = false;
    }
  }

  async function autoConnect() {
    q("#dashAutoConnect").disabled = true;
    try {
      const response = await execute("wireless_auto_connect", {});
      output(response.data);
      const connected = Number(response.data?.connected || 0);
      setBadge("#dashWirelessState", connected ? "CONNECTED" : "READY", connected ? "ok" : "");
      notify(connected ? `${connected} known wireless target(s) connected` : "No previously paired target auto-connected");
      if (connected && q("#refreshDevices")) q("#refreshDevices").click();
    } catch (error) {
      notify(error.message, true);
      output({ok:false, error:error.message});
    } finally {
      q("#dashAutoConnect").disabled = false;
    }
  }

  function wire() {
    const nav = q('[data-view="wireless-main"]');
    if (!nav) return;
    nav.addEventListener("click", () => {
      const title = q("#pageTitle");
      if (title) title.textContent = "Wireless Debugging";
    });
    q("#dashQrCreate")?.addEventListener("click", createQr);
    q("#dashQrCancel")?.addEventListener("click", cancelQr);
    q("#dashPairSubmit")?.addEventListener("click", pairWithCode);
    q("#dashDiscover")?.addEventListener("click", discover);
    q("#dashConnect")?.addEventListener("click", connect);
    q("#dashAutoConnect")?.addEventListener("click", autoConnect);
    q("#dashPairCode")?.addEventListener("keydown", event => { if (event.key === "Enter") pairWithCode(); });
    q("#dashConnectTarget")?.addEventListener("keydown", event => { if (event.key === "Enter") connect(); });
  }

  document.addEventListener("DOMContentLoaded", wire);
  window.addEventListener("beforeunload", () => { if (qrSocket) qrSocket.close(); });
})();
