/* 報表儀表板（spec: usage-report / Report Dashboard and Export） */
(() => {
  const charts = {};

  function drawChart(id, type, labels, data, label) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), {
      type,
      data: {
        labels,
        datasets: [{ label, data, backgroundColor: "#0d6efd99", borderColor: "#0d6efd" }],
      },
      options: {
        scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "%" } } },
      },
    });
  }

  async function query(start, end, floor) {
    const f = floor ? `&floor=${encodeURIComponent(floor)}` : "";

    const usage = await (await fetch(`/api/reports/usage?date=${end}${f}`)).json();
    document.getElementById("no-data").classList.toggle("d-none", usage.has_data);
    drawChart(
      "chart-hourly", "bar",
      usage.hourly.map((h) => `${h.hour}:00`),
      usage.hourly.map((h) => h.rate),
      "使用率 %"
    );
    const peak = document.getElementById("peak-hour");
    peak.classList.toggle("d-none", usage.peak_hour === null);
    if (usage.peak_hour !== null) peak.textContent = `尖峰 ${usage.peak_hour}:00`;

    const trend = await (await fetch(`/api/reports/trend?start=${start}&end=${end}${f}`)).json();
    drawChart(
      "chart-trend", "line",
      trend.days.map((d) => d.date),
      trend.days.map((d) => d.rate),
      "日使用率 %"
    );

    const floors = await (await fetch(`/api/reports/floors?start=${start}&end=${end}`)).json();
    drawChart(
      "chart-floors", "bar",
      floors.floors.map((x) => x.floor),
      floors.floors.map((x) => x.rate),
      "平均使用率 %"
    );

    const idle = await (await fetch(`/api/reports/idle?start=${start}&end=${end}`)).json();
    const top = idle.top_seats.length
      ? idle.top_seats.map((s) => `${s.label}（${s.count} 次）`).join("、")
      : "無";
    document.getElementById("idle-stats").innerHTML = `
      <p class="mb-1">佔位逾時釋放：<strong>${idle.released_count}</strong> 次</p>
      <p class="mb-1">平均離席時長：<strong>${idle.avg_away_minutes}</strong> 分鐘</p>
      <p class="mb-0">佔位最多座位：${top}</p>`;
  }

  document.getElementById("query-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const start = document.getElementById("start").value;
    const end = document.getElementById("end").value;
    const floor = document.getElementById("floor").value.trim();
    const f = floor ? `&floor=${encodeURIComponent(floor)}` : "";
    document.getElementById("csv-link").href =
      `/api/reports/usage.csv?start=${start}&end=${end}${f}`;
    query(start, end, floor);
  });

  // 預設帶入今日
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById("start").value = today;
  document.getElementById("end").value = today;
  document.getElementById("query-form").requestSubmit();
})();
