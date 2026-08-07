"use strict";

(() => {
  const create = document.getElementById("wirelessQrCreateButton");
  if (!create) return;
  const cancel = document.getElementById("wirelessQrCancelButton");
  const image = document.getElementById("wirelessQrImage");
  const status = document.getElementById("wirelessQrState");
  const authorized = document.getElementById("wirelessQrAuthorized");
  const ttl = document.getElementById("wirelessQrTtl");
  const autoConnect = document.getElementById("wirelessQrAutoConnect");
  let sessionId = null;
  let socket = null;

  function render(data) {
    status.textContent = `${data.state}: ${data.message} (${data.remaining_seconds}s)`;
    if (data.terminal) {
      cancel.disabled = true;
      create.disabled = false;
      if (socket) socket.close();
      socket = null;
      image.hidden = true;
      image.removeAttribute("src");
      sessionId = null;
    }
  }

  function watch(id) {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${location.host}/ws/wireless/qr/${encodeURIComponent(id)}`);
    socket.onmessage = event => {
      const payload = JSON.parse(event.data);
      if (payload.ok) render(payload.data);
    };
    socket.onerror = () => { status.textContent = "QR status stream disconnected."; };
  }

  create.addEventListener("click", async () => {
    if (!authorized.checked) {
      status.textContent = "Confirm that the target is authorized and in scope.";
      return;
    }
    create.disabled = true;
    status.textContent = "Creating one-time QR session…";
    const response = await fetch("/api/wireless/qr", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        ttl_seconds: Number(ttl.value || 120),
        auto_connect: autoConnect.checked,
        confirmation: "AUTHORIZED"
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      create.disabled = false;
      status.textContent = payload.detail || "Unable to create QR session.";
      return;
    }
    sessionId = payload.data.id;
    image.src = `${payload.svg_url}?t=${Date.now()}`;
    image.hidden = false;
    cancel.disabled = false;
    render(payload.data);
    watch(sessionId);
  });

  cancel.addEventListener("click", async () => {
    if (!sessionId) return;
    await fetch(`/api/wireless/qr/${encodeURIComponent(sessionId)}/cancel`, {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
  });
})();
