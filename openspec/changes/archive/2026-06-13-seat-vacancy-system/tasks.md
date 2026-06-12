# Tasks: seat-vacancy-system

## 1. 專案基礎與 MVC 骨架

- [x] 1.1 建立依賴清單（requirements.txt：fastapi、uvicorn、sqlalchemy、alembic、jinja2、apscheduler、pytest；偵測端 ultralytics、opencv-python 另列）
- [x] 1.2 建立 MVC 目錄結構：`src/models/`、`src/services/`、`src/controllers/`、`src/views/templates/`、`src/views/static/`、`src/detection/`、`src/config.py`
- [x] 1.3 `src/config.py`：讀取 `DATABASE_URL` 與計時參數（提示 15／釋放 10／報到 30／淨空 5 分鐘）等環境變數
- [x] 1.4 改寫 `src/main.py` 為 FastAPI 應用進入點（建立 app、掛載 routers、靜態檔與啟動排程器），原主控台模擬改寫為 `tests/test_booking.py`
- [x] 1.5 建立 pytest 設定並確認 `pytest` 可執行

## 2. 資料層（Model）

- [x] 2.1 SQLAlchemy models：`seats`、`bookings`、`seat_status_logs`、`idle_events`、`notifications`（沿用既有 `SeatStatus` 列舉並新增 `AWAY`）
- [x] 2.2 建立 Alembic 初始 migration，於 SQLite 驗證 `alembic upgrade head`
- [x] 2.3 撰寫座位主檔 seed 腳本（樓層、座位編號、平面圖座標）

## 3. 狀態機與預約服務（Service）

- [x] 3.1 實作 `SeatStateService.transition()`：合法轉換驗證、更新狀態、寫入 `seat_status_logs`、觸發 WebSocket 廣播（先以事件 hook 留接口）
- [x] 3.2 將既有 `BookingService.reserve_seat()` 遷移至 DB 版本：僅 `AVAILABLE` 可預約、建立含報到期限的預約紀錄、同一學號同時間僅一筆有效預約（spec: seat-booking）
- [x] 3.3 實作報到（網頁手動＋偵測自動）與逾期未報到自動釋放（spec: seat-booking / Check-In）
- [x] 3.4 實作取消預約與本人限定檢查（spec: seat-booking / Booking Cancellation）
- [x] 3.5 單元測試：狀態機全部合法／非法轉換、預約—報到—取消—逾期情境

## 4. 離席逾時流程（seat-timeout）

- [x] 4.1 實作 `IdleTimeoutService`：接收「疑似佔位開始／座位淨空／人返回」事件，建立與解除 `idle_events`
- [x] 4.2 APScheduler 任務：15 分鐘達標轉 `AWAY` 並發通知、通知後 10 分鐘未確認釋放、淨空 5 分鐘直接釋放、重啟後由 DB 重建計時
- [x] 4.3 實作「我仍在使用」確認 API 與本人返回視同確認（spec: seat-timeout / Confirmation）
- [x] 4.4 通知服務：寫入 `notifications`、WebSocket 個人頻道推播、未讀拉取 API
- [x] 4.5 單元測試：提示→確認→重計時、提示→逾時→釋放、本人返回取消倒數

## 5. Web 控制器與即時推播（Controller）

- [x] 5.1 REST API：`GET /api/seats`（全量快照）、`POST /api/bookings`、`POST /api/bookings/{id}/checkin`、`POST /api/bookings/{id}/cancel`、`POST /api/seats/{id}/confirm-presence`
- [x] 5.2 WebSocket 端點：座位狀態廣播頻道＋學號個人通知頻道，連線池管理與斷線清理
- [x] 5.3 偵測事件接收 API：`POST /api/detection/events`（入座／離席物品在／淨空），轉交 Service 層處理自動報到與逾時事件

## 6. 前端平面圖（View）

- [x] 6.1 Jinja2 + Bootstrap 5 基礎版型與學號識別（輸入學號進入，存於 session）
- [x] 6.2 SVG 平面圖渲染：依狀態著色（綠／紅／橘／灰）、顯示可預約座位數（spec: floor-map-web）
- [x] 6.3 WebSocket 前端：增量更新著色、斷線自動重連後重抓快照
- [x] 6.4 預約互動：點選綠色座位開預約框、非綠色不可點、成功後顯示報到期限；報到與取消按鈕
- [x] 6.5 網頁內通知 UI：離席提示橫幅＋「我仍在使用」按鈕＋釋放倒數
- [x] 6.6 RWD 驗證：360px 寬行動裝置可完整操作（spec: floor-map-web / Responsive Layout）※已以 iPhone 經熱點實機驗證：平面圖、預約、離席警示與確認流程皆正常

## 7. YOLOv8 偵測端（src/detection/）

- [x] 7.1 ROI 標定工具：OpenCV 介面框選四點座標、與座位編號綁定並寫入 `seats.roi`；未標定畫面記警告並跳過（spec: seat-detection / ROI Calibration）
- [x] 7.2 偵測主迴圈：讀取攝影機／影片流、YOLOv8 推論（person／backpack／laptop／book）、ROI 中心點判定
- [x] 7.3 去抖動邏輯：連續 5 秒一致才確認狀態，短暫遮擋不翻轉（spec: seat-detection / Person Occupancy Detection）
- [x] 7.4 疑似佔位判定：人離開物品在→發事件並於畫面標記橘框；人與物品皆離開→發淨空事件（spec: seat-detection / Idle Belongings Detection）
- [x] 7.5 事件上報與離線佇列：HTTP 上報後端、失敗進本地佇列、恢復後補送（spec: seat-detection / State Change Synchronization）
- [x] 7.6 以錄影檔做端到端驗證：入座→自動報到、離席 15 分→AWAY、逾時→釋放（計時參數可暫調短以利測試）※已以實機攝影機（單座位家中環境、20 秒快速模式）驗證：自動報到、AWAY 警示、本人返回取消倒數、逾時釋放皆通過；平放手機/書本/攤平背包辨識不到為 COCO 預訓練視角限制，留待第二學期場域微調

## 8. 使用率報表（usage-report）

- [x] 8.1 報表查詢服務：由 `seat_status_logs` 計算逐時使用率、日／週趨勢、尖峰時段、樓層比較；無資料區間回 0%（spec: usage-report）
- [x] 8.2 佔位行為統計：逾時釋放次數、平均離席時長、佔位 Top 5 座位
- [x] 8.3 管理者儀表板頁面：Chart.js 圖表＋日期區間查詢
- [x] 8.4 CSV 匯出端點與下載按鈕
- [x] 8.5 單元測試：使用率計算（含跨時段狀態區間切分）與空資料處理

## 9. PostgreSQL 與文件收尾

- [x] 9.1 本機安裝 PostgreSQL，`DATABASE_URL` 切換後跑 Alembic 與完整測試（驗證 SQLite→PG 無行為差異）※已於 PostgreSQL 18.4 驗證：migration、seed、43 測試、預約→自動報到→一人一位→報表端到端皆通過
- [x] 9.2 改寫 `docs/technical_architecture.md`：移除 Firebase，更新為 FastAPI MVC + PostgreSQL + WebSocket 架構與新資料模型
- [x] 9.3 更新 `docs/roadmap.md` 第二學期項目（Firebase 整合改為 PostgreSQL／DBaaS 與 WebSocket）
- [x] 9.4 更新 `CLAUDE.md`（執行方式、架構說明、測試指令）
- [x] 9.5 撰寫 README 啟動指南（安裝依賴、設定 DATABASE_URL、啟動 uvicorn 與偵測端）
