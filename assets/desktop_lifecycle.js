(function () {
  function makeClientId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    const randomPart = Math.random().toString(16).slice(2);
    return "pvw-" + Date.now().toString(16) + "-" + randomPart;
  }

  const clientId = makeClientId();
  let instanceToken = null;
  let heartbeatTimer = null;

  function postLifecycle(url, payload, useBeacon) {
    if (useBeacon && navigator.sendBeacon) {
      const form = new FormData();
      Object.keys(payload).forEach(function (key) {
        form.append(key, payload[key]);
      });
      return navigator.sendBeacon(url, form);
    }
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: useBeacon,
    }).catch(function () {
      return null;
    });
  }

  function sendHeartbeat() {
    if (!instanceToken) {
      return;
    }
    postLifecycle("/__desktop/client/heartbeat", {
      client_id: clientId,
      instance_token: instanceToken,
    }, false);
  }

  function sendDisconnect() {
    if (!instanceToken) {
      return;
    }
    postLifecycle("/__desktop/client/disconnect", {
      client_id: clientId,
      instance_token: instanceToken,
    }, true);
  }

  function startLifecycle() {
    sendHeartbeat();
    heartbeatTimer = window.setInterval(sendHeartbeat, 5000);
    window.addEventListener("pagehide", sendDisconnect);
    window.addEventListener("beforeunload", sendDisconnect);
  }

  fetch("/__desktop/health", { cache: "no-store" })
    .then(function (response) {
      return response.ok ? response.json() : null;
    })
    .then(function (payload) {
      if (!payload || !payload.auto_shutdown_enabled || !payload.instance_token) {
        return;
      }
      instanceToken = payload.instance_token;
      startLifecycle();
    })
    .catch(function () {
      return null;
    });

  window.addEventListener("unload", function () {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
    }
  });
})();
