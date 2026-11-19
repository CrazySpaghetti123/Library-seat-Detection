## Context

- 偵測端只在座位狀態「改變」時送事件（`person_present`／`person_left_belongings`／`seat_vacant`，已去抖動 5 秒），後端收到後只拿來驅動狀態轉換，沒有保存「這個座位目前偵測到什麼」。
- 計時一律以 DB 中的時間錨點 + APScheduler 週期掃描實作（程序重啟不遺失），掃描間隔 15 秒。
- 座位狀態變更必須經 `SeatStateService.transition()`；`OCCUPIED → AVAILABLE`、`AWAY → AVAILABLE` 已是合法轉換。
- `Booking.end_reason` 已預留 `checked_out`。

## Goals / Non-Goals

**Goals:**

- 使用者主動結束使用，離開後約 30 秒內釋放座位。
- 收拾時間不設上限：只要偵測到人或物品還在，就每 30 秒再檢查。
- 沒有偵測資料的座位也能結束使用（30 秒後釋放）。

**Non-Goals:**

- 不新增座位狀態（收拾中的座位對其他人仍顯示「使用中」）。
- 不處理偵測端離線時的資料新鮮度（見風險）。
- 不改變既有離席逾時流程；收拾中若觸發離席提示，照原規則處理。

## Decisions

### D1：在座位上保存最新偵測結果

`seats` 新增 `last_detection`（事件名稱）與 `last_detection_at`。`IdleTimeoutService.handle_detection_event` 收到任何合法事件都先更新這兩欄，再做原本的狀態處理。

替代方案：從 `idle_events` 推算——但 `person_present` 不會留下 idle event，且未使用中的座位不建立事件，無法得知「目前人還在」。

### D2：收拾中以預約欄位表示，不新增座位狀態

`bookings` 新增 `leave_requested_at`（按下結束的時間，NULL＝未在收拾中）與 `leave_check_at`（下次檢查時間）。座位維持 `OCCUPIED`／`AWAY`，其他使用者不受影響；新增狀態會牽動狀態機、平面圖配色、報表統計，成本不成比例。

### D3：檢查規則

每次檢查讀取座位的 `last_detection`：

| 最新偵測結果 | 處理 |
|---|---|
| `seat_vacant` | 釋放：結束未解決的 idle events、座位 → `AVAILABLE`（source `booking`）、預約 `checked_out`、通知 `checked_out` |
| `person_present`、`person_left_belongings` | `leave_check_at += LEAVE_CHECK_SECONDS`，下次再查 |
| NULL（從未收到事件） | 視為無法偵測，直接釋放 |

物品還在也不釋放，避免下一位使用者預約到桌上還有東西的座位（使用者決定）。

### D4：獨立的 5 秒排程工作

主掃描間隔 15 秒，若把收拾中檢查放在主掃描，實際等待會是 30～45 秒。改為另一個 5 秒一次的工作，只查詢 `leave_requested_at IS NOT NULL AND ended_at IS NULL AND leave_check_at <= now` 的預約，查詢量極小；後端醒著時主掃描本來就讓 Neon 保持運作，不增加額度消耗。

### D5：前端以輪詢取得檢查結果

「我的座位」列顯示到下次檢查的倒數；倒數歸零後數秒重新讀取 `/api/me/booking`。釋放時發 `checked_out` 通知（綠色短暫提示，與被動釋放的紅色常駐警告區分）並沿用座位廣播。未釋放的檢查不發通知，以免每 30 秒寫一筆通知紀錄。`/api/me/booking` 帶出 `leave_requested_at`、`leave_check_at` 與座位的 `last_detection`，讓前端顯示「偵測到您仍在座位」或「物品仍在座位上」。

### D6：API

- `POST /api/bookings/{id}/leave`：限本人、已報到、未結束、尚未在收拾中；回傳預約。
- `POST /api/bookings/{id}/resume`：限本人、正在收拾中；清除兩個欄位。

## Risks / Trade-offs

- **偵測端離線時沿用舊結果**：若偵測端停止時最後一筆是 `person_present`，結束使用會一直等待。緩解：既有的離席流程仍不受影響；偵測端重新上線並送出事件後即恢復判斷。報告中列為限制。
- **按下結束時偵測結果已是 `seat_vacant`**（例如人早已離開才按）：30 秒後立即釋放，符合預期。
- **AWAY 狀態下按結束**：允許；釋放時 `AWAY → AVAILABLE` 是合法轉換，同時結束離席事件。

## Migration Plan

新增一支 Alembic migration（四個可為 NULL 的欄位，SQLite／PostgreSQL 皆支援 `ADD COLUMN`）。Render 啟動指令已含 `alembic upgrade head`；本機與 Neon 各跑一次即可。回滾以 `alembic downgrade -1`。
