/* 平面圖前端：全量快照 + WebSocket 增量更新（spec: floor-map-web） */
(() => {
  const COLORS = {
    AVAILABLE: "var(--seat-available)",
    OCCUPIED: "var(--seat-busy)",
    RESERVED: "var(--seat-busy)",
    AWAY: "var(--seat-away)",
    MAINTENANCE: "var(--seat-maintenance)",
  };
  const SEAT_W = 80, SEAT_H = 60;

  const svg = document.getElementById("floor-map");
  const seats = new Map(); // label -> {data, group}
  let reserveTarget = null;
  let reconnectDelay = 1000;

  const modalEl = document.getElementById("reserve-modal");
  const reserveModal = new bootstrap.Modal(modalEl);

  // ---- 平面圖渲染 ----

  function render(snapshot) {
    svg.innerHTML = "";
    seats.clear();
    for (const seat of snapshot.seats) {
      const g = document.createElementNS(svg.namespaceURI, "g");
      g.classList.add("seat");
      g.dataset.label = seat.label;

      const rect = document.createElementNS(svg.namespaceURI, "rect");
      rect.setAttribute("x", seat.map_x);
      rect.setAttribute("y", seat.map_y);
      rect.setAttribute("width", SEAT_W);
      rect.setAttribute("height", SEAT_H);
      rect.setAttribute("rx", 8);

      const text = document.createElementNS(svg.namespaceURI, "text");
      text.setAttribute("x", seat.map_x + SEAT_W / 2);
      text.setAttribute("y", seat.map_y + SEAT_H / 2);
      text.textContent = seat.label;

      g.append(rect, text);
      g.addEventListener("click", () => onSeatClick(seat.label));
      svg.appendChild(g);
      seats.set(seat.label, { data: seat, group: g });
      paint(seat.label, seat.status);
    }
    updateAvailableCount();
  }

  function paint(label, status) {
    const entry = seats.get(label);
    if (!entry) return;
    entry.data.status = status;
    entry.group.querySelector("rect").setAttribute("fill", COLORS[status] || "#999");
    entry.group.classList.toggle("clickable", status === "AVAILABLE");
    entry.group
      .querySelector("rect")
      .setAttribute("aria-label", `座位 ${label}：${status}`);
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
    const res = await fetch("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seat_label: reserveTarget }),
    });
    reserveModal.hide();
    const body = await res.json();
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

  async function refreshMyBooking() {
    const res = await fetch("/api/me/booking");
    if (!res.ok) return;
    const { booking, seat_status } = await res.json();
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
    } else {
      box.innerHTML = `使用中：座位 <strong>${booking.seat_label}</strong>` +
        (seat_status === "AWAY" ? "（離席中，請盡快返回或確認）" : "");
    }
  }

  async function bookingAction(id, action) {
    const res = await fetch(`/api/bookings/${id}/${action}`, { method: "POST" });
    const body = await res.json();
    if (!res.ok) showBanner("danger", body.detail || "操作失敗");
    refreshMyBooking();
  }

  // ---- 通知（離席提示橫幅＋確認按鈕＋倒數，spec: seat-timeout）----

  function showBanner(kind, html, extra = "", autoDismiss = true) {
    const area = document.getElementById("notification-area");
    const div = document.createElement("div");
    div.className = `alert alert-${kind} alert-dismissible fade show py-2 ${extra}`;
    div.innerHTML =
      html + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
    area.appendChild(div);
    if (autoDismiss && (kind === "success" || kind === "warning")) {
      setTimeout(() => div.remove(), 8000);
    }
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
        // 釋放（AVAILABLE）時不另外提示，seat_released 通知會接手顯示
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
        const res = await fetch(`/api/seats/${note.seat_id}/confirm-presence`, {
          method: "POST",
        });
        const body = await res.json();
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
    } else {
      // 座位已釋放／逾期未報到：清掉殘留的離席警示，避免顯示過期倒數
      document.querySelectorAll(".away-banner").forEach((el) => el.remove());
      showBanner("danger", note.payload.message || note.type);
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
    fetch(`/api/notifications/${id}/read`, { method: "POST" });
  }

  async function loadUnreadNotifications() {
    const res = await fetch("/api/notifications");
    if (!res.ok) return;
    const { notifications } = await res.json();
    notifications.forEach(handleNotification);
  }

  // ---- WebSocket：增量更新＋斷線重連後重抓快照 ----

  async function loadSnapshot() {
    const res = await fetch("/api/seats");
    render(await res.json());
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const sock = new WebSocket(`${proto}://${location.host}/ws/seats`);
    const status = document.getElementById("ws-status");

    sock.onopen = async () => {
      status.textContent = "即時連線中";
      status.className = "badge bg-success";
      reconnectDelay = 1000;
      await loadSnapshot(); // 重連後補償：重抓全量快照
    };
    sock.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "seat_update") {
        paint(msg.label, msg.status);
        updateAvailableCount();
        if (msg.status !== "AWAY") {
          clearAwayBanners(msg.seat_id, msg.status);
        }
      } else if (msg.type === "notification") {
        handleNotification(msg.data);
      }
    };
    sock.onclose = () => {
      status.textContent = "已斷線，重連中…";
      status.className = "badge bg-danger";
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };
  }

  (async () => {
    await loadSnapshot(); // 先有座位狀態，未讀通知才能判斷警示是否過期
    connect();
    refreshMyBooking();
    loadUnreadNotifications();
  })();
})();
