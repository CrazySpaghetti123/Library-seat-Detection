/* 報表儀表板（spec: usage-report / Report Dashboard and Export）。
   報表 API 需要管理密碼（X-Admin-Token）：第一次查詢前詢問，存在 sessionStorage，401 時重新詢問。 */
(() => {
  const charts = {};
  const authCard = document.getElementById("admin-auth");
  const authError = document.getElementById("admin-error");
  let pending = null;  // 等待輸入密碼後要重跑的查詢

  function askAdmin(wrong) {
    authCard.classList.remove("d-none");
    authError.classList.toggle("d-none", !wrong);
    document.getElementById("admin-token").focus();
  }

  /** 報表 API：帶管理密碼；密碼錯誤時丟出 "unauthorized"。 */
  async function report(path) {
    const { res, data } = await App.json(path, { adminAuth: true });
    if (res.status === 401) {
      App.admin.clear();
      throw new Error("unauthorized");
    }
    return data;
  }

  document.getElementById("admin-form").addEventListener("submit", (e) => {
    e.preventDefault();
    App.admin.save(document.getElementById("admin-token").value);
    authCard.classList.add("d-none");
    if (pending) pending();
  });

  /** 讀取設計 token 的實際色值：Chart.js 只吃色字串，無法直接用 CSS 變數。 */
  function token(name) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim();
  }

  function drawChart(id, type, labels, data, label, colorVar = "--app-chart-1") {
    if (charts[id]) charts[id].destroy();

    const color = token(colorVar);
    const gridColor = token("--app-chart-grid");
    const textColor = token("--app-chart-text");

    charts[id] = new Chart(document.getElementById(id), {
      type,
      data: {
        labels,
        datasets: [{ label, data, backgroundColor: `${color}99`, borderColor: color }],
      },
      options: {
        plugins: { legend: { labels: { color: textColor } } },
        scales: {
          y: {
            beginAtZero: true, max: 100,
            title: { display: true, text: "%", color: textColor },
            ticks: { color: textColor },
            grid: { color: gridColor },
          },
          x: {
            ticks: { color: textColor },
            grid: { color: gridColor },
          },
        },
      },
    });
  }


  async function query(start, end, floor) {
    const f = floor ? `&floor=${encodeURIComponent(floor)}` : "";

    const usage = await report(`/api/reports/usage?date=${end}${f}`);
    document.getElementById("no-data").classList.toggle("d-none", usage.has_data);
    drawChart(
      "chart-hourly", "bar",
      usage.hourly.map((h) => `${h.hour}:00`),
      usage.hourly.map((h) => h.rate),
      "使用率 %"
    );
    document.getElementById("kpi-peak").textContent =
      usage.peak_hour === null ? "–" : `${usage.peak_hour}:00`;

    const trend = await report(`/api/reports/trend?start=${start}&end=${end}${f}`);
    drawChart(
      "chart-trend", "line",
      trend.days.map((d) => d.date),
      trend.days.map((d) => d.rate),
      "日使用率 %",
      "--app-chart-2"
    );

    const floors = await report(`/api/reports/floors?start=${start}&end=${end}`);
    drawChart(
      "chart-floors", "bar",
      floors.floors.map((x) => x.floor),
      floors.floors.map((x) => x.rate),
      "平均使用率 %",
      "--app-chart-3"
    );

    const idle = await report(`/api/reports/idle?start=${start}&end=${end}`);
    const top = idle.top_seats.length
      ? idle.top_seats.map((s) => `${s.label}（${s.count} 次）`).join("、")
      : "無";
    document.getElementById("kpi-released").textContent = `${idle.released_count} 次`;
    document.getElementById("kpi-avg-away").textContent = `${idle.avg_away_minutes} 分`;
    document.getElementById("idle-stats").innerHTML = `
      <p class="mb-1">佔位逾時釋放：<strong>${idle.released_count}</strong> 次</p>
      <p class="mb-1">平均離席時長：<strong>${idle.avg_away_minutes}</strong> 分鐘</p>
      <p class="mb-0">佔位最多座位：${top}</p>`;
  }

  function formValues() {
    return {
      start: document.getElementById("start").value,
      end: document.getElementById("end").value,
      floor: document.getElementById("floor").value.trim(),
    };
  }

  /** 需要管理密碼的動作：沒有密碼先詢問；密碼錯誤則清除後重新詢問，輸入後自動重試。 */
  async function withAdmin(action) {
    pending = () => withAdmin(action);
    if (!App.admin.token() && App.base) {  // 雲端一定有設密碼；本機未設定時直接查
      askAdmin(false);
      return;
    }
    const hadPassword = Boolean(App.admin.token());
    try {
      await action();
      pending = null;
    } catch (err) {
      // 帶了密碼仍被拒＝密碼錯誤；沒帶（本機原本未設、後來設定）＝單純詢問
      if (err.message === "unauthorized") askAdmin(hadPassword);
    }
  }

  document.getElementById("query-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const { start, end, floor } = formValues();
    withAdmin(() => query(start, end, floor));
  });

  // CSV 原本是 <a href> 直接下載，無法帶管理密碼標頭：改為 fetch 後產生下載
  document.getElementById("csv-button").addEventListener("click", () => {
    const { start, end, floor } = formValues();
    const f = floor ? `&floor=${encodeURIComponent(floor)}` : "";
    withAdmin(async () => {
      const res = await App.request(`/api/reports/usage.csv?start=${start}&end=${end}${f}`,
                                    { adminAuth: true });
      if (res.status === 401) {
        App.admin.clear();
        throw new Error("unauthorized");
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `usage_${start}_${end}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    });
  });

  // 開館時段與時區（原本由伺服器模板帶入）
  App.config().then((cfg) => {
    if (cfg.open_hour !== undefined) {
      document.getElementById("open-hours").textContent =
        `${cfg.open_hour}:00–${cfg.close_hour}:00`;
      document.getElementById("report-tz").textContent = cfg.timezone || "當地時間";
    }
  }).catch(() => {});

  // 預設帶入今日
  // 用瀏覽器當地日期（toISOString 為 UTC，台灣凌晨 0～8 點會變成前一天）
  const now = new Date();
  const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, "0"),
                 String(now.getDate()).padStart(2, "0")].join("-");
  document.getElementById("start").value = today;
  document.getElementById("end").value = today;
  document.getElementById("query-form").requestSubmit();
})();
