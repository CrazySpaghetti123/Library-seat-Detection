## 1. 資料庫

- [x] 1.1 `Seat` 新增 `last_detection`、`last_detection_at`；`Booking` 新增 `leave_requested_at`、`leave_check_at`
- [x] 1.2 Alembic migration（新增四個可為 NULL 的欄位，含 downgrade）

## 2. 後端

- [x] 2.1 `config.py` 新增 `LEAVE_CHECK_SECONDS`（預設 30）
- [x] 2.2 `IdleTimeoutService.handle_detection_event` 收到合法事件時先記錄最新偵測結果
- [x] 2.3 `BookingService.request_leave`／`resume_use`／`process_leave_checks`（D3 檢查規則）
- [x] 2.4 排程新增 5 秒一次的收拾中檢查工作（D4）
- [x] 2.5 `POST /api/bookings/{id}/leave`、`POST /api/bookings/{id}/resume`；`/api/me/booking` 帶出收拾中欄位與 `last_detection`

## 3. 前端

- [x] 3.1 「我的座位」列：已報到顯示「結束使用」；收拾中顯示倒數、目前偵測結果與「繼續使用」，倒數歸零後重新讀取

## 4. 測試與文件

- [x] 4.1 測試：保存最新偵測結果、離開後釋放、仍在收拾／物品仍在時延後、無偵測資料直接釋放、繼續使用、權限與未報到拒絕、API 端點
- [x] 4.2 更新 `docs/demo_guide.md`（展示步驟）與 `CLAUDE.md`（計時參數）

## 5. 驗證

- [x] 5.1 本機 Playwright：報到 → 結束使用 → 模擬 `person_present` 確認不釋放 → 模擬 `seat_vacant` 確認下一次檢查釋放；另測繼續使用
- [x] 5.2 推送後於雲端以模擬器重跑一次
