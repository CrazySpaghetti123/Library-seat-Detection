## Context

`SeatStatusLog`（`src/models/seat.py`）已保存全部狀態轉換：`seat_id`、`from_status`、`to_status`、`source`（booking / detection / timeout / admin）、`created_at`，且 `created_at` 有索引。這是使用率報表的唯一資料來源，可靠且完整。

`SeatStateService.transition()` 在寫入 log 後會呼叫 `on_transition_hooks`，目前簽章為 `fn(seat_id, label, to_status_value)`。`main.py` 於啟動時將 `ws.manager.publish_seat_update` 掛上，因此每次狀態變更都會即時廣播給所有開啟平面圖的瀏覽器。

也就是說，事件流所需的資料在後端全部齊備，缺的只是讀取端點與前端呈現。

## Goals / Non-Goals

**Goals:**

- 讓已存在但不可見的狀態變更資料在平面圖頁露出。
- 歷史事件與即時事件採用一致的資料形狀，前端以同一套渲染邏輯處理。
- 不新增資料表、不改變狀態機規則。

**Non-Goals:**

- 不做事件的篩選、搜尋或分頁（報表頁已負責深入分析）。
- 不持久化前端的事件流內容（重新整理即由 API 重新取得）。
- 不將事件流加入報表頁；此為平面圖頁的即時感呈現。

## Decisions

### D1：擴充 hook 簽章，而非由前端推導變更前狀態

前端其實可以自行推導 `from_status`——`seats` Map 中保有每個座位的前一個狀態。但 `source`（變更來自預約、偵測或逾時）前端無從得知，而「這個座位是被系統自動釋放的，還是有人預約了」正是事件流最有價值的資訊。

`transition()` 內 `from_status` 與 `source` 兩個變數本就存在，只是沒有傳給 hook。擴充簽章為 `fn(seat_id, label, to_status, from_status, source)` 的成本是一行呼叫加上型別註記，換得即時事件與歷史事件的資訊一致。

**替代方案**：WebSocket 收到更新後再打一次 API 取最新事件。捨棄原因是每次狀態變更都多一次往返，且在雲端部署（DB 與 app 分離）時延遲更明顯。

### D2：歷史由 REST 端點提供，即時由 WebSocket 追加，兩者統一形狀

`GET /api/seats/events?limit=N` 回傳 `{events: [{seat_id, label, from_status, to_status, source, created_at}]}`，依 `created_at` 倒序。WebSocket 的 `seat_update` 訊息補上 `from_status` 與 `source` 後，前端可用同一個 `renderEvent()` 處理兩種來源。

`limit` 預設 20、上限 100，避免無界查詢。

### D3：事件流為固定高度的捲動區，前端保留上限筆數

面板高度固定並內部捲動，避免長時間開啟後把頁面撐長。前端保留的事件筆數上限與 API 預設一致（20 筆），超出即移除最舊的節點，防止長時間執行造成 DOM 無限增長。

### D4：來源以中文標籤呈現，不直接顯示原始字串

`source` 的原始值為 `booking` / `detection` / `timeout` / `admin`，直接顯示對使用者無意義。前端映射為「預約」「偵測」「逾時」「管理」，並各給一個色票以便快速掃視。未知來源回退為原始字串，避免新增來源時顯示空白。

### D5：時間以相對時間呈現

事件流的價值在於「剛剛發生了什麼」，因此顯示「3 分鐘前」而非絕對時間戳，並在 `title` 屬性保留完整時間供滑鼠停留查看。所有時間戳為 naive UTC（見 `src/utils.py`），前端需補 `Z` 後再轉本地時間——此為專案既有慣例，`map.js` 處理預約期限時已如此。

## Risks / Trade-offs

- **hook 簽章為破壞性變更** → 掛勾點僅有 `main.py` 一處與測試中的一個假 hook，影響面已完整盤點；型別註記同步更新可讓靜態檢查捕捉遺漏。
- **事件流面板佔用平面圖頁空間** → 於桌面採側欄、行動裝置移至平面圖下方，並限制高度；不影響既有的 360px RWD 需求。
- **高頻狀態變更時的視覺干擾** → 事件進場動畫短暫且包在 `prefers-reduced-motion` 例外中；若現場偵測抖動導致事件過於頻繁，應調整偵測端去抖動門檻而非在此處抑制。
- **`GET /api/seats/events` 未做權限控制** → 與既有的 `GET /api/seats` 一致，皆為登入後可讀的座位狀態資訊，不含個人資料（log 中無學號）。
