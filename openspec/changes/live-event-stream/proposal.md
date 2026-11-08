## Why

系統已經完整記錄每一次座位狀態變更：`SeatStateService.transition()` 將 `from_status` / `to_status` / `source` / `created_at` 寫入 `seat_status_logs`，WebSocket 也即時推播每次變更。但這些資料在使用者介面上完全不可見——平面圖只把座位換個顏色，變更的來由（預約？偵測？逾時釋放？）與剛才發生過什麼都無從得知。

對使用者而言，這代表看不到「系統正在運作」；對專題展示而言，代表即時系統最有說服力的部分沒有被呈現出來。這份資料已經存在，只差一個露出的位置。

## What Changes

- 新增唯讀端點 `GET /api/seats/events`，回傳最近的座位狀態變更紀錄（含變更前後狀態、來源、時間），供頁面載入時填充事件流。
- **BREAKING**（內部介面）：`SeatStateService.on_transition_hooks` 的簽章由 `fn(seat_id, label, to_status)` 擴充為 `fn(seat_id, label, to_status, from_status, source)`，使 WebSocket 推播能帶出與歷史紀錄一致的資訊。`transition()` 內這兩項資料本就存在，僅未傳遞。
- WebSocket `seat_update` 訊息增加 `from_status` 與 `source` 欄位。
- 平面圖頁新增即時事件流面板：載入時顯示最近數筆歷史，之後由 WebSocket 即時追加，最新一筆有進場提示。

不新增資料表——`seat_status_logs` 已足夠。不改變任何狀態機規則、逾時邏輯或既有 API 的回應格式。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `floor-map-web`: 新增一項需求——平面圖頁須呈現近期座位狀態變更的事件流，並在收到即時推播時追加新事件。既有的著色、即時更新、預約互動、RWD、非顏色編碼與主題需求皆維持不變。

## Impact

- `src/controllers/api.py`：新增 `GET /api/seats/events`。
- `src/controllers/ws.py`：`publish_seat_update` 簽章與訊息內容。
- `src/services/seat_state_service.py`：hook 呼叫時多傳 `from_status` 與 `source`（型別註記一併更新）。
- `src/views/templates/map.html`、`src/views/static/js/map.js`、`src/views/static/css/app.css`：事件流面板。
- `tests/test_state_machine.py`：`test_transition_hook_invoked` 的假 hook 簽章需同步更新。
- 不影響資料庫 schema、Alembic migration、偵測端與報表功能。
