## Why

使用者報到後，目前只能等系統偵測到「人和物品都離開」滿 5 分鐘，或離席逾時被釋放，座位才會空出來。使用者明明要走了，座位卻還要再占用好幾分鐘，其他人看到的空位數也因此偏少。

使用者希望能主動按「結束使用」，同時保留收拾東西的時間：按下後 30 秒檢查一次，確認人和物品都離開了才釋放；還沒離開就再等 30 秒檢查，直到離開為止。

## What Changes

- 已報到的使用者可在「我的座位」列按「**結束使用**」，進入收拾中。
- 收拾中每 30 秒（`LEAVE_CHECK_SECONDS`，可設定）檢查一次該座位最新的偵測結果：
  - 最新結果是「人與物品皆離開」（`seat_vacant`）→ 釋放座位，預約以 `checked_out` 結束，通知使用者。
  - 最新結果是人還在（`person_present`）或物品還在（`person_left_belongings`）→ 不釋放，30 秒後再檢查。
  - 該座位從未收到任何偵測事件（沒裝攝影機、未標定、偵測端未運作）→ 第一次檢查即釋放。
- 收拾中可按「**繼續使用**」取消結束，座位維持使用中。
- 後端開始記錄每個座位最新的偵測結果與時間（原本偵測事件只用來驅動狀態轉換，不保存結果本身）。
- 資料庫新增欄位（Alembic migration）：`seats.last_detection`、`seats.last_detection_at`、`bookings.leave_requested_at`、`bookings.leave_check_at`。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `seat-booking`：新增「結束使用」需求（收拾中、定期檢查、反悔、無偵測資料時的處理）。
- `seat-detection`：新增「保存最新偵測結果」需求，供結束使用時判斷是否已離開。

## Impact

- 後端：`BookingService`（結束使用、繼續使用、收拾中檢查）、`IdleTimeoutService`（記錄最新偵測結果）、排程新增收拾中檢查工作、`api.py` 新增兩個端點並在預約資料帶出收拾中資訊。
- 資料庫：新增 migration；Render 啟動時會自動套用，本機需 `alembic upgrade head`。
- 前端：`map.js` 的「我的座位」列新增按鈕與倒數。
- 報表：`checked_out` 是既有的結束原因之一，使用率計算只看 `seat_status_logs`，不受影響。
