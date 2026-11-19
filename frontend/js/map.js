/* 平面圖前端：全量快照 + WebSocket 增量更新（spec: floor-map-web）。
   API 呼叫一律經 App（js/api.js）：帶登入 token、組後端網址、處理後端喚醒。 */
(() => {
  if (!App.auth.token()) return;  // 未登入時 map.html 已導回登入頁

  const COLORS = {
    AVAILABLE: "var(--seat-available)",
    OCCUPIED: "var(--seat-busy)",
    RESERVED: "var(--seat-busy)",
    AWAY: "var(--seat-away)",
    MAINTENANCE: "var(--seat-maintenance)",
  };
  // 顏色以外的第二重狀態編碼，供色覺辨識障礙使用者判讀
  // （spec: floor-map-web / Non-Color Status Encoding）
  const ICONS = {
    AVAILABLE: "✓",
    OCCUPIED: "●",
    RESERVED: "●",
    AWAY: "⏱",
    MAINTENANCE: "✕",
  };
  const STATUS_TEXT = {
    AVAILABLE: "可預約",
    OCCUPIED: "使用中",
    RESERVED: "已預約",
    AWAY: "疑似佔位",
    MAINTENANCE: "維修中",
  };
  // 平面圖佈局：座位尺寸依座位數自動調整，間距恆定。
  // DB 的 map_x/map_y 只用來推導「第幾列第幾行」，實際像素尺寸在此重算，
  // 因此換一間座位數不同的自習室時，版面會自己適應而不需改座標。
  const VIEW_W = 640;      // viewBox 寬（高度依列數動態決定）
  const SEAT_GAP = 6;      // 座位間距，上下左右一致
  const STAGE_PAD = 6;     // 畫布內縮，與座位間距同值
  const SEAT_ASPECT = 1.2; // 座位寬高比（桌椅單元略寬）
  const SEAT_MAX_W = 150;  // 座位數很少時的尺寸上限，避免單一座位撐滿畫布

  // 事件流：來源的內部識別字串對使用者無意義，映射為中文標籤
  const SOURCE_LABELS = {
    booking: "預約",
    detection: "偵測",
    timeout: "逾時",
    admin: "管理",
  };
  const EVENT_LIMIT = 20;  // 與 API 預設一致，避免長時間開啟造成 DOM 無限增長

  const svg = document.getElementById("floor-map");
  const seats = new Map(); // label -> {data, group}
  let reserveTarget = null;
  let reconnectDelay = 1000;

  const modalEl = document.getElementById("reserve-modal");
  const reserveModal = new bootstrap.Modal(modalEl);

  // ---- 平面圖渲染 ----

  /** 由座位的 map_x / map_y 推導網格，再依畫布算出座位尺寸與位置。 */
  function computeLayout(list) {
    // 相同 x 視為同一行、相同 y 視為同一列
    const colsX = [...new Set(list.map((s) => s.map_x ?? 0))].sort((a, b) => a - b);
    const rowsY = [...new Set(list.map((s) => s.map_y ?? 0))].sort((a, b) => a - b);
    const cols = Math.max(colsX.length, 1);
    const rows = Math.max(rowsY.length, 1);

    // 先以寬度為準求座位寬，超過上限則收斂
    const availW = VIEW_W - STAGE_PAD * 2 - SEAT_GAP * (cols - 1);
    const w = Math.min(availW / cols, SEAT_MAX_W);
    const h = w / SEAT_ASPECT;

    const totalW = w * cols + SEAT_GAP * (cols - 1);
    const totalH = h * rows + SEAT_GAP * (rows - 1);
    // viewBox 高度剛好包住內容，避免上下出現大片留白
    const viewH = totalH + STAGE_PAD * 2;

    return {
      w, h, viewH,
      originX: (VIEW_W - totalW) / 2,
      originY: (viewH - totalH) / 2,
      colOf: (seat) => colsX.indexOf(seat.map_x ?? 0),
      rowOf: (seat) => rowsY.indexOf(seat.map_y ?? 0),
    };
  }

  function render(snapshot) {
    svg.innerHTML = "";
    seats.clear();

    const L = computeLayout(snapshot.seats);
    // 不鋪地板層，座位背後直接是頁面背景
    svg.setAttribute("viewBox", `0 0 ${VIEW_W} ${L.viewH}`);

    for (const seat of snapshot.seats) {
      const x = L.originX + L.colOf(seat) * (L.w + SEAT_GAP);
      const y = L.originY + L.rowOf(seat) * (L.h + SEAT_GAP);

      const g = document.createElementNS(svg.namespaceURI, "g");
      g.classList.add("seat");
      g.dataset.label = seat.label;

      // 玻璃層疊：底板（模糊地板 + 細亮邊）→ 狀態色。均勻平面，無漸層。
      const base = document.createElementNS(svg.namespaceURI, "rect");
      const fill = document.createElementNS(svg.namespaceURI, "rect");
      for (const [rect, cls] of [[base, "seat-base"], [fill, "seat-fill"]]) {
        rect.classList.add(cls);
        rect.setAttribute("x", x);
        rect.setAttribute("y", y);
        rect.setAttribute("width", L.w);
        rect.setAttribute("height", L.h);
      }

      // 標籤置於方塊上半、狀態圖示置於下半；字級隨座位尺寸縮放
      const text = document.createElementNS(svg.namespaceURI, "text");
      text.classList.add("seat-label");
      text.setAttribute("x", x + L.w / 2);
      text.setAttribute("y", y + L.h * 0.40);
      text.setAttribute("font-size", Math.round(L.h * 0.30));
      text.textContent = seat.label;

      const icon = document.createElementNS(svg.namespaceURI, "text");
      icon.classList.add("seat-icon");
      icon.setAttribute("x", x + L.w / 2);
      icon.setAttribute("y", y + L.h * 0.70);
      icon.setAttribute("font-size", Math.round(L.h * 0.24));

      // 原生 SVG tooltip：滑鼠停留顯示座位與狀態
      const title = document.createElementNS(svg.namespaceURI, "title");

      g.append(base, fill, text, icon, title);
      g.addEventListener("click", () => onSeatClick(seat.label));
      // 鍵盤可操作：可預約座位以 Enter／空白鍵發起預約
      g.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSeatClick(seat.label);
        }
      });
      svg.appendChild(g);
      seats.set(seat.label, { data: seat, group: g });
      paint(seat.label, seat.status);
    }
    updateAvailableCount();
  }

  function paint(label, status, animate = false) {
    const entry = seats.get(label);
    if (!entry) return;
    const g = entry.group;
    const statusText = STATUS_TEXT[status] || status;
    entry.data.status = status;

    // 只設填色；座位無邊框，形狀由填色與頂部高光界定
    g.querySelector(".seat-fill").setAttribute("fill", COLORS[status] || "#999");
    g.querySelector(".seat-icon").textContent = ICONS[status] || "";
    g.querySelector("title").textContent = `座位 ${label}：${statusText}`;

    const clickable = status === "AVAILABLE";
    g.classList.toggle("clickable", clickable);
    g.setAttribute("role", clickable ? "button" : "img");
    g.setAttribute("aria-label", `座位 ${label}：${statusText}`);
    if (clickable) {
      g.setAttribute("tabindex", "0");
    } else {
      g.removeAttribute("tabindex");
    }

    // 即時更新時的一次性脈動，讓遠處座位的變化不被錯過（design D6）
    if (animate) {
      g.classList.remove("just-changed");
      void g.getBoundingClientRect();  // 強制 reflow，使動畫可連續重播
      g.classList.add("just-changed");
      setTimeout(() => g.classList.remove("just-changed"), 900);
    }
  }

  function updateAvailableCount() {
    const n = [...seats.values()].filter((s) => s.data.status === "AVAILABLE").length;
    document.getElementById("available-count").textContent = n;
  }

  // ---- 預約互動（非綠色座位不可點，spec: Booking from the Map）----

  function onSeatClick(label) {
    const entry = seats.get(label);
    if (!entry) return;
    if (entry.data.status !== "AVAILABLE") {
      showBanner("warning", `座位 ${label} 目前不可預約`);
      return;
    }
    reserveTarget = label;
    document.getElementById("reserve-seat-label").textContent = label;
    reserveModal.show();
  }

  document.getElementById("reserve-confirm").addEventListener("click", async () => {
    if (!reserveTarget) return;
    const { res, data: body } = await App.json("/api/bookings", {
      method: "POST", student: true, body: { seat_label: reserveTarget },
    });
    reserveModal.hide();
    if (res.ok) {
      const deadline = new Date(body.checkin_deadline + "Z").toLocaleTimeString();
      showBanner("success", `預約成功！座位 ${body.seat_label}，請於 ${deadline} 前報到。`);
      refreshMyBooking();
    } else {
      showBanner("danger", body.detail || "預約失敗");
    }
    reserveTarget = null;
  });

  // ---- 我的座位狀態列（報到／取消） ----

  let leaveTimer = null;  // 收拾中倒數

  async function refreshMyBooking() {
    const { res, data } = await App.json("/api/me/booking", { student: true });
    if (!res.ok) return;
    const { booking, seat_status } = data;
    clearTimeout(leaveTimer);
    const box = document.getElementById("my-booking");
    if (!booking) {
      box.classList.add("d-none");
      return;
    }
    box.classList.remove("d-none");
    if (!booking.checked_in_at) {
      const deadline = new Date(booking.checkin_deadline + "Z").toLocaleTimeString();
      box.innerHTML = `我的預約：座位 <strong>${booking.seat_label}</strong>，
        請於 <strong>${deadline}</strong> 前報到
        <button class="btn btn-sm btn-primary ms-2" id="btn-checkin">報到</button>
        <button class="btn btn-sm btn-outline-danger ms-1" id="btn-cancel">取消預約</button>`;
      document.getElementById("btn-checkin").onclick = () =>
        bookingAction(booking.id, "checkin");
      document.getElementById("btn-cancel").onclick = () =>
        bookingAction(booking.id, "cancel");
    } else if (booking.leave_requested_at) {
      // 收拾中（spec: seat-booking / End of Use）：倒數到下次檢查，歸零後重新讀取結果
      box.innerHTML = `收拾中：座位 <strong>${booking.seat_label}</strong>，
        <span id="leave-countdown"></span>
        <div class="small mt-1">${LEAVE_HINTS[data.last_detection ?? "none"]}</div>
        <button class="btn btn-sm btn-outline-primary mt-2" id="btn-resume">繼續使用</button>`;
      document.getElementById("btn-resume").onclick = () =>
        bookingAction(booking.id, "resume");
      startLeaveCountdown(new Date(booking.leave_check_at + "Z"));
    } else {
      box.innerHTML = `使用中：座位 <strong>${booking.seat_label}</strong>` +
        (seat_status === "AWAY" ? "（離席中，請盡快返回或確認）" : "") +
        `<button class="btn btn-sm btn-outline-danger ms-2" id="btn-leave">結束使用</button>`;
      document.getElementById("btn-leave").onclick = () =>
        bookingAction(booking.id, "leave");
    }
  }

  const LEAVE_HINTS = {
    person_present: "目前仍偵測到您在座位上，離開後才會釋放。",
    person_left_belongings: "座位上仍有物品，請帶走個人物品。",
    seat_vacant: "已偵測到您離開，檢查後即釋放座位。",
    none: "此座位沒有偵測資料，倒數結束即釋放。",
  };

  /** 倒數到下次離開檢查；後端每 5 秒處理一次到期檢查，歸零後稍等再重新讀取。 */
  function startLeaveCountdown(checkAt) {
    clearTimeout(leaveTimer);
    const tick = () => {
      const el = document.getElementById("leave-countdown");
      if (!el) return;
      const remain = Math.ceil((checkAt - Date.now()) / 1000);
      if (remain > 0) {
        el.textContent = `${remain} 秒後檢查是否已離開`;
        leaveTimer = setTimeout(tick, 1000);
      } else {
        el.textContent = "檢查中…";
        leaveTimer = setTimeout(refreshMyBooking, 6000);
      }
    };
    tick();
  }

  async function bookingAction(id, action) {
    const { res, data: body } = await App.json(`/api/bookings/${id}/${action}`, {
      method: "POST", student: true,
    });
    if (!res.ok) showBanner("danger", body.detail || "操作失敗");
    else if (action === "leave") showBanner("info", "已結束使用，請收拾個人物品；確認離開後即釋放座位。");
    else if (action === "resume") showBanner("success", "已取消結束，座位繼續保留給您。");
    refreshMyBooking();
  }

  // ---- 通知（離席提示橫幅＋確認按鈕＋倒數，spec: seat-timeout）----

  /** 左下角浮出的短暫操作回饋，動態語彙與事件流一致。 */
  function showToast(kind, html, dismissAfter = 5000) {
    const area = document.getElementById("toast-area");
    const el = document.createElement("div");
    el.className = `toast-item is-${kind}`;
    el.innerHTML = html;
    area.appendChild(el);
    setTimeout(() => {
      el.classList.add("is-leaving");
      // 動畫播完才移除；若使用者關閉動畫則立即結束
      el.addEventListener("animationend", () => el.remove(), { once: true });
      setTimeout(() => el.remove(), 400);
    }, dismissAfter);
    return el;
  }

  /**
   * 通知呈現：會自動消失的操作回饋走左下角浮出提示；
   * 需要使用者處理的訊息（如離席警示）仍留在頁面頂端常駐。
   */
  function showBanner(kind, html, extra = "", autoDismiss = true) {
    // 失敗訊息多留一會兒，使用者才有時間看清原因
    if (autoDismiss) return showToast(kind, html, kind === "danger" ? 7000 : 5000);

    const area = document.getElementById("notification-area");
    const div = document.createElement("div");
    div.className = `alert alert-${kind} alert-dismissible fade show py-2 ${extra}`;
    div.innerHTML =
      html + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
    area.appendChild(div);
    return div;
  }

  function seatById(id) {
    return [...seats.values()].find((s) => s.data.id === id);
  }

  // 座位脫離 AWAY（本人返回／他分頁確認／被釋放）→ 自動關閉對應的倒數警示
  function clearAwayBanners(seatId, newStatus) {
    document
      .querySelectorAll(`.away-banner[data-seat-id="${seatId}"]`)
      .forEach((el) => {
        if (el.dataset.noteId) markRead(el.dataset.noteId);
        el.remove();
        if (newStatus === "OCCUPIED") {
          showBanner("success", "已確認您返回座位，釋放倒數已取消。");
        }
        // 釋放（AVAILABLE）時不另外提示，seat_released／checked_out 通知會接手顯示
        refreshMyBooking();
      });
  }

  function handleNotification(note) {
    if (note.type === "away_warning") {
      // 過期警示（座位已不在 AWAY，例如已被釋放）：直接標記已讀不顯示
      const seat = seatById(note.seat_id);
      if (seat && seat.data.status !== "AWAY") {
        markRead(note.id);
        return;
      }
      const minutes = note.payload.confirm_window_minutes;
      // 離席警示常駐顯示：按確認、本人返回（座位脫離 AWAY）或被釋放時才移除
      const banner = showBanner(
        "warning",
        `⚠️ ${note.payload.message}
         <button class="btn btn-sm btn-primary ms-2" id="btn-confirm-presence">我仍在使用</button>
         <span class="ms-2 countdown" data-seconds="${minutes * 60}"></span>`,
        "away-banner",
        false
      );
      banner.dataset.seatId = note.seat_id;
      banner.dataset.noteId = note.id;
      startCountdown(banner.querySelector(".countdown"));
      banner.querySelector("#btn-confirm-presence").onclick = async () => {
        const { res, data: body } = await App.json(`/api/seats/${note.seat_id}/confirm-presence`, {
          method: "POST", student: true,
        });
        if (res.ok) {
          banner.remove();
          showBanner("success", "已確認，座位保留。");
        } else {
          showBanner("danger", body.detail || "確認失敗");
        }
        markRead(note.id);
        refreshMyBooking();
      };
    } else if (note.type === "checked_in") {
      // 偵測自動報到：綠色提示，並更新「我的預約」列（報到期限換成「使用中」）
      showBanner("success", `✅ ${note.payload.message}`);
      markRead(note.id);
      refreshMyBooking();
    } else if (note.type === "checked_out") {
      // 結束使用後確認離開而釋放：正常結果，綠色短暫提示即可
      showBanner("success", `👋 ${note.payload.message}`);
      markRead(note.id);
      refreshMyBooking();
    } else {
      // 座位已釋放／逾期未報到：清掉殘留的離席警示，避免顯示過期倒數
      document.querySelectorAll(".away-banner").forEach((el) => el.remove());
      // 座位遭釋放是使用者必須知道的結果，常駐直到手動關閉
      showBanner("danger", note.payload.message || note.type, "", false);
      markRead(note.id);
      refreshMyBooking();
    }
  }

  function startCountdown(el) {
    let remain = parseInt(el.dataset.seconds, 10);
    const tick = () => {
      if (!el.isConnected) return;
      const m = Math.floor(remain / 60), s = remain % 60;
      el.textContent = `（剩餘 ${m}:${String(s).padStart(2, "0")}）`;
      if (remain-- > 0) setTimeout(tick, 1000);
    };
    tick();
  }

  function markRead(id) {
    App.request(`/api/notifications/${id}/read`, { method: "POST", student: true }).catch(() => {});
  }

  async function loadUnreadNotifications() {
    const { res, data } = await App.json("/api/notifications", { student: true });
    if (!res.ok) return;
    const { notifications } = data;
    notifications.forEach(handleNotification);
  }

  // ---- 即時動態事件流（spec: Live Status Event Stream）----

  /** 後端時間戳為 naive UTC（見 src/utils.py），需補 Z 才會被當成 UTC 解析。 */
  function parseUtc(s) {
    return new Date(/[Z+]|[+-]\d{2}:\d{2}$/.test(s) ? s : `${s}Z`);
  }

  function relativeTime(date) {
    const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return "剛剛";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} 分鐘前`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小時前`;
    return date.toLocaleDateString();
  }

  function renderEvent(ev, isNew = false) {
    const li = document.createElement("li");
    li.className = "event-item" + (isNew ? " is-new" : "");

    const when = parseUtc(ev.created_at);
    const from = STATUS_TEXT[ev.from_status] || ev.from_status || "—";
    const to = STATUS_TEXT[ev.to_status] || ev.to_status;
    // 未知來源回退為原始字串，新增來源時不會顯示空白
    const source = SOURCE_LABELS[ev.source] || ev.source || "";

    li.innerHTML = `
      <div class="event-line">
        <span class="event-seat">${ev.label}</span>
        <span class="event-transition">
          <span class="event-from">${from}</span>
          <span class="event-arrow" aria-hidden="true">→</span>
          <span class="event-to status-${ev.to_status}">${to}</span>
        </span>
      </div>
      <div class="event-meta">
        ${source ? `<span class="event-source src-${ev.source}">${source}</span>` : ""}
        <time class="event-time" datetime="${when.toISOString()}"
              title="${when.toLocaleString()}">${relativeTime(when)}</time>
      </div>`;
    return li;
  }

  function setStreamEmpty(list, empty) {
    list.classList.toggle("is-empty", empty);
    if (empty) {
      list.innerHTML = '<li class="event-empty">尚無狀態變更</li>';
    }
  }

  async function loadEvents() {
    const list = document.getElementById("event-stream");
    const { res, data } = await App.json(`/api/seats/events?limit=${EVENT_LIMIT}`);
    if (!res.ok) return;
    const { events } = data;
    if (!events.length) {
      setStreamEmpty(list, true);
      return;
    }
    setStreamEmpty(list, false);
    list.innerHTML = "";
    events.forEach((ev) => list.appendChild(renderEvent(ev)));
  }

  function pushEvent(ev) {
    const list = document.getElementById("event-stream");
    if (list.classList.contains("is-empty")) setStreamEmpty(list, false);
    list.prepend(renderEvent(ev, true));
    while (list.children.length > EVENT_LIMIT) list.lastElementChild.remove();
    // 側欄收合期間累計未讀，讓使用者知道有事情發生
    if (!streamIsOpen()) {
      unreadCount = Math.min(unreadCount + 1, 99);
      streamUnread.textContent = String(unreadCount);
    }
  }

  // 相對時間會隨時間推移失準（「剛剛」應變成「1 分鐘前」），定期重算
  setInterval(() => {
    document.querySelectorAll("#event-stream .event-time").forEach((el) => {
      el.textContent = relativeTime(new Date(el.dateTime));
    });
  }, 30000);

  // ---- 側欄開關 ----

  const streamPanel = document.getElementById("stream-panel");
  const streamToggle = document.getElementById("stream-toggle");
  const streamUnread = document.getElementById("stream-unread");
  let unreadCount = 0;

  function streamIsOpen() {
    return streamPanel.classList.contains("is-open");
  }

  function setStreamOpen(open) {
    streamPanel.classList.toggle("is-open", open);
    // 標籤不隱藏，改為貼到側欄左緣充當收回鈕
    streamToggle.classList.toggle("is-open", open);
    streamToggle.setAttribute("aria-expanded", String(open));
    streamToggle.setAttribute("aria-label", open ? "收合即時動態" : "展開即時動態");
    localStorage.setItem("streamOpen", open ? "1" : "0");
    if (open) {  // 開啟即視為已讀
      unreadCount = 0;
      streamUnread.textContent = "";
    }
  }

  streamToggle.addEventListener("click", () => setStreamOpen(!streamIsOpen()));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && streamIsOpen()) setStreamOpen(false);
  });

  // 還原上次的開關狀態；預設收合
  setStreamOpen(localStorage.getItem("streamOpen") === "1");

  // ---- WebSocket：增量更新＋斷線重連後重抓快照 ----

  async function loadSnapshot() {
    const { res, data } = await App.json("/api/seats");
    if (res.ok) render(data);
  }

  function setConnState(state, text) {
    const badge = document.getElementById("ws-status");
    badge.className = `conn-badge is-${state}`;
    document.getElementById("ws-status-text").textContent = text;
  }

  // 心跳：Render 免費方案把收到的 WebSocket 訊息計為活動，平面圖開著時後端不會休眠
  const HEARTBEAT_MS = 4 * 60 * 1000;
  let heartbeat = null;

  function connect() {
    // 瀏覽器無法替 WebSocket 加標頭，token 以查詢參數帶入，才能收到個人通知
    const token = encodeURIComponent(App.auth.token() || "");
    const sock = new WebSocket(App.wsUrl(`/ws/seats?token=${token}`));

    sock.onopen = async () => {
      setConnState("online", "即時連線中");
      reconnectDelay = 1000;
      clearInterval(heartbeat);
      heartbeat = setInterval(() => {
        if (sock.readyState === WebSocket.OPEN) sock.send("ping");
      }, HEARTBEAT_MS);
      await loadSnapshot(); // 重連後補償：重抓全量快照
    };
    sock.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "seat_update") {
        paint(msg.label, msg.status, true);
        updateAvailableCount();
        pushEvent({
          label: msg.label,
          from_status: msg.from_status,
          to_status: msg.status,
          source: msg.source,
          created_at: new Date().toISOString(),
        });
        if (msg.status !== "AWAY") {
          clearAwayBanners(msg.seat_id, msg.status);
        }
      } else if (msg.type === "notification") {
        handleNotification(msg.data);
      }
    };
    sock.onclose = () => {
      clearInterval(heartbeat);
      const seconds = Math.round(reconnectDelay / 1000);
      setConnState("offline", `已斷線，${seconds} 秒後重連…`);
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };
  }

  // 學號、登出、報到期限（原本由伺服器模板帶入）
  document.getElementById("nav-student").textContent = App.auth.studentId() || "";
  document.getElementById("logout-link").addEventListener("click", (e) => {
    e.preventDefault();
    App.auth.logout();
  });
  App.config().then((cfg) => {
    if (cfg.checkin_deadline_minutes !== undefined) {
      document.getElementById("checkin-minutes").textContent = cfg.checkin_deadline_minutes;
    }
  }).catch(() => {});

  (async () => {
    try {
      await loadSnapshot(); // 先有座位狀態，未讀通知才能判斷警示是否過期
    } catch {
      return;  // 後端 3 分鐘仍未喚醒：App 已顯示無法連線的提示
    }
    connect();
    refreshMyBooking();
    loadUnreadNotifications();
    loadEvents();
  })();
})();
