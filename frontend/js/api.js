/* 共用：API 網址、登入憑證、管理密碼、後端喚醒重試（spec: access-control / cloud-deployment）。

   後端（Render 免費方案）閒置會休眠，喚醒約一分鐘：請求 3 秒沒回應就顯示提示，
   連線失敗或閘道錯誤（502/503/504，代表請求還沒到達後端）時以遞增間隔重試，最長 3 分鐘。 */
window.App = (() => {
  const base = ((window.APP_CONFIG || {}).apiBase || "").replace(/\/+$/, "");
  const KEYS = { token: "seat.token", studentId: "seat.studentId", admin: "seat.adminToken" };
  const WAKE_HINT_MS = 3000;
  const WAKE_LIMIT_MS = 3 * 60 * 1000;
  const RETRY_STATUS = new Set([502, 503, 504]);

  // 隱私模式或封鎖網站資料時 storage 可能丟例外；登入狀態就只維持在本頁
  const memory = {};
  function store(kind) {
    try {
      const s = kind === "session" ? window.sessionStorage : window.localStorage;
      s.getItem("probe");
      return s;
    } catch {
      return null;
    }
  }
  function getItem(kind, key) {
    const s = store(kind);
    return s ? s.getItem(key) : memory[key] || null;
  }
  function setItem(kind, key, value) {
    const s = store(kind);
    if (s) {
      if (value === null) s.removeItem(key);
      else s.setItem(key, value);
    } else if (value === null) {
      delete memory[key];
    } else {
      memory[key] = value;
    }
  }

  // ---- 登入憑證（localStorage）與管理密碼（sessionStorage，關閉分頁即清除）----

  const auth = {
    token: () => getItem("local", KEYS.token),
    studentId: () => getItem("local", KEYS.studentId),
    save(token, studentId) {
      setItem("local", KEYS.token, token);
      setItem("local", KEYS.studentId, studentId);
    },
    clear() {
      setItem("local", KEYS.token, null);
      setItem("local", KEYS.studentId, null);
    },
    requireLogin() {
      if (!auth.token()) {
        location.replace("index.html");
        return false;
      }
      return true;
    },
    logout() {
      auth.clear();
      location.replace("index.html");
    },
  };

  const admin = {
    token: () => getItem("session", KEYS.admin),
    save: (value) => setItem("session", KEYS.admin, value),
    clear: () => setItem("session", KEYS.admin, null),
  };

  // ---- 喚醒提示 ----

  let wakeBanner = null;
  function showWake(message, kind = "warning") {
    if (!wakeBanner) {
      wakeBanner = document.createElement("div");
      wakeBanner.className = "wake-banner";
      wakeBanner.setAttribute("role", "status");
      document.body.appendChild(wakeBanner);
    }
    wakeBanner.className = `wake-banner is-${kind}`;
    wakeBanner.textContent = message;
  }
  function hideWake() {
    if (wakeBanner) {
      wakeBanner.remove();
      wakeBanner = null;
    }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /** 發出請求；後端休眠時自動等待重試。回傳 Response，超過 3 分鐘仍失敗則丟出錯誤。 */
  async function request(path, { method = "GET", body, student = false, adminAuth = false } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (student && auth.token()) headers.Authorization = `Bearer ${auth.token()}`;
    if (adminAuth && admin.token()) headers["X-Admin-Token"] = admin.token();

    const started = Date.now();
    const hint = setTimeout(() => showWake("伺服器喚醒中，約需一分鐘…"), WAKE_HINT_MS);
    let delay = 2000;
    try {
      for (;;) {
        const remaining = WAKE_LIMIT_MS - (Date.now() - started);
        const ctrl = new AbortController();
        const abort = setTimeout(() => ctrl.abort(), Math.max(remaining, 0));
        let res = null;
        try {
          res = await fetch(base + path, {
            method, headers, signal: ctrl.signal,
            body: body === undefined ? undefined : JSON.stringify(body),
          });
        } catch {
          res = null;  // 連線失敗或逾時：後端可能還在開機
        } finally {
          clearTimeout(abort);
        }
        if (res && !RETRY_STATUS.has(res.status)) {
          hideWake();
          if (res.status === 401 && student) auth.logout();  // 憑證失效：回登入頁
          return res;
        }
        if (Date.now() - started + delay >= WAKE_LIMIT_MS) {
          showWake("伺服器暫時無法連線，請稍後重新整理", "danger");
          throw new Error("server unreachable");
        }
        await sleep(delay);
        delay = Math.min(delay * 1.5, 10000);
      }
    } finally {
      clearTimeout(hint);
    }
  }

  /** request() 後解析 JSON；回應不是 JSON 時回傳空物件。 */
  async function json(path, options) {
    const res = await request(path, options);
    let data = {};
    try {
      data = await res.json();
    } catch {
      data = {};
    }
    return { res, data };
  }

  /** WebSocket 網址：apiBase 的 http(s) 換成 ws(s)；未設定時用目前頁面的主機。 */
  function wsUrl(path) {
    const origin = base || `${location.protocol}//${location.host}`;
    return origin.replace(/^http/, "ws") + path;
  }

  let configCache = null;
  async function config() {
    if (!configCache) {
      const { res, data } = await json("/api/config");
      if (res.ok) configCache = data;
    }
    return configCache || {};
  }

  return { base, auth, admin, request, json, wsUrl, config, showWake, hideWake };
})();
