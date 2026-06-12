# Design: seat-vacancy-system

## Context

現有程式碼僅有記憶體內的預約原型（`src/models/seat.py`、`src/services/booking_service.py`，由 `src/main.py` 跑主控台模擬）。舊架構文件規劃以 Firebase Realtime Database 同步座位狀態，本變更已決議改為 PostgreSQL ＋後端 WebSocket 推播。本機目前尚未安裝 PostgreSQL；專案為兩學期專題，第一學期聚焦偵測核心，第二學期完成雲端與網頁整合。

## Goals / Non-Goals

**Goals:**

- 建立 FastAPI 為核心的 MVC 分層，承載預約、逾時、平面圖、報表四大功能
- 資料層以 SQLAlchemy 抽象，開發期可用 SQLite，正式環境用 PostgreSQL，上線後無痛切換 DBaaS
- YOLOv8 偵測端與 Web 後端解耦：偵測端只發事件／寫狀態，業務規則集中在 Service 層
- 座位狀態的所有變更（不論來源）都走同一個狀態機與歷史紀錄

**Non-Goals:**

- 不做正式的校園 SSO／帳號系統（登入方式定為學號登入，見 D9，未來可換）
- 不做多攝影機自動標定、模型自動再訓練管線
- 不做原生 App（RWD 網頁涵蓋行動裝置）
- 本變更不含 DBaaS 的實際部署，只保證可遷移性

## Decisions

### D1. Web 框架：FastAPI + Jinja2 + SQLAlchemy（MVC 對應）

- **Model**：SQLAlchemy ORM models（`src/models/`）
- **View**：Jinja2 模板＋靜態 JS/CSS（`src/views/templates/`、`src/views/static/`），平面圖以 SVG 渲染、Bootstrap 5 做 RWD
- **Controller**：FastAPI routers（`src/controllers/`），HTTP API 與 WebSocket 端點
- **Service 層**（`src/services/`）承載業務規則（狀態機、預約規則、逾時邏輯），Controller 保持薄
- 替代方案：Django（內建較多但即時功能需 Channels、較重）、Flask（非同步弱）。FastAPI 原生 async 與 WebSocket 最契合即時座位圖。

### D2. 資料層：SQLAlchemy 2.x，連線字串驅動

- `DATABASE_URL` 環境變數決定後端：開發 `sqlite:///dev.db` → 本機 `postgresql+psycopg://…` → DBaaS（Supabase／Neon／RDS 皆為標準 PostgreSQL 連線字串）。
- 限制：只使用 SQLite 與 PostgreSQL 共通的型別與功能（不用 PG 專屬如 JSONB index、LISTEN/NOTIFY），確保開發／正式環境行為一致。
- 使用 Alembic 管理 schema migration，從第一張表開始就建 migration，DBaaS 遷移時直接 `alembic upgrade head`。

### D3. 資料模型

| 資料表 | 重點欄位 | 用途 |
|---|---|---|
| `seats` | id, label, floor, roi(JSON 四點座標), status, updated_at | 座位主檔＋目前狀態＋ROI 標定 |
| `bookings` | id, seat_id, student_id, created_at, checkin_deadline, checked_in_at, ended_at, end_reason | 預約生命週期（end_reason: checked_in／cancelled／no_show／timeout_release…） |
| `seat_status_logs` | id, seat_id, from_status, to_status, source, created_at | 全部狀態轉換歷史，報表唯一資料來源 |
| `idle_events` | id, seat_id, booking_id, away_started_at, notified_at, resolved_at, resolution | 疑似佔位事件（resolution: confirmed／returned／released） |
| `notifications` | id, student_id, seat_id, type, payload, created_at, read_at | 網頁內通知 |

### D4. 座位狀態機（單一入口）

```
AVAILABLE ──預約──▶ RESERVED ──報到(網頁/偵測)──▶ OCCUPIED
    ▲                  │逾期未報到                    │離席≥15分(物品在)
    │◀─────────────────┘                             ▼
    │◀──確認逾時10分／淨空≥5分────────────────────── AWAY
    │                                                │確認或本人返回
    │                                                ▼
    └────────────────────────────────────────── OCCUPIED
（MAINTENANCE 由管理者手動進出）
```

所有狀態轉換集中在 `SeatStateService.transition(seat, to, source)`：驗證合法轉換 → 更新 `seats.status` → 寫 `seat_status_logs` → 廣播 WebSocket。偵測端、預約 API、逾時排程都呼叫同一入口，避免狀態不一致。

### D5. 偵測端與後端的整合方式

- 偵測端為獨立程序（`src/detection/`）：OpenCV 讀流 → YOLOv8 推論（偵測 person／backpack／laptop／book，COCO 預訓練起步，後續微調）→ ROI 中心點判定 → 去抖動（連續 5 秒一致才確認）。
- 偵測端透過後端 HTTP API（`POST /api/detection/events`）回報事件，而非直寫資料庫——業務規則（自動報到、AWAY 轉換）留在 Service 層，偵測端保持笨重端點。離線時事件進本地佇列，恢復後補送。
- 替代方案：偵測端直寫 DB（耦合業務規則、難以維持狀態機單一入口，捨棄）；MQTT/訊息佇列（多一個基礎設施，專題規模不需要）。

### D6. 逾時計時：APScheduler in-process 排程

- 15 分提示、10 分釋放、30 分報到期限、5 分淨空釋放，皆由 FastAPI 程序內的 APScheduler 任務驅動；計時錨點（如 away_started_at、checkin_deadline）持久化在 DB，程序重啟後掃描 DB 重建計時，不會遺失。
- 參數放 `config`（環境變數／設定檔），預設 15／10／30／5 分鐘。
- 替代方案：Celery + Redis（過重）、純記憶體 timer（重啟即遺失，捨棄）。

### D7. 即時推播：原生 WebSocket ＋全量快照補償

- 後端維護連線池，狀態轉換後廣播 `{seat_id, status}`；前端連線建立／重連時先 `GET /api/seats` 取全量快照再聽增量，保證斷線後一致。
- 網頁內通知同樣走 WebSocket（登入學號後訂閱個人頻道），未連線時通知落在 `notifications` 表，下次開頁時拉取未讀。

### D8. 報表計算

- 使用率＝(OCCUPIED＋RESERVED＋AWAY 時數)÷開放總時數，由 `seat_status_logs` 的狀態區間累計；查詢以 SQL 聚合即可（專題資料量小，不需預先彙整表）。
- 儀表板用 Chart.js 畫時段長條／趨勢線，CSV 匯出由同一查詢直接序列化。

### D9. 登入方式：學號登入

- 學生進入系統時輸入學號登入，後端以 server-side session（Cookie）保存身分；預約、報到、取消、離席確認與個人通知頻道皆綁定該學號。
- 同一學號 SHALL 同時間僅能持有一筆有效預約／使用中座位，避免一人佔多位。
- 不設密碼與註冊流程（專題範圍），學號格式僅做基本驗證；介面與資料表以 `student_id` 為鍵，未來可無痛替換為校園 SSO。
- 替代方案：校園 SSO／OAuth（需校方介接權限，專題階段不可行）、Email 驗證（增加流程摩擦，對展示無益）。

## Risks / Trade-offs

- [YOLOv8 預訓練模型對背包／筆電在俯視角的辨識率不足] → 第一學期先以 COCO 預訓練驗證流程，採集模擬影像微調；ROI 判定加去抖動降低閃爍誤判。
- [SQLite 與 PostgreSQL 行為差異（並發寫入、型別）] → 限用共通功能；CI／驗收一律跑 PostgreSQL；盡早在本機裝 PostgreSQL。
- [in-process 排程在多 worker 部署時會重複觸發] → 專題階段固定單 worker；設計上計時錨點在 DB，未來要水平擴充時可改成獨立 scheduler 程序。
- [學號輕量識別無法防冒用] → 屬專題範圍外，介面上保留 `student_id` 欄位，未來可替換為校園 SSO。
- [攝影機畫面涉及隱私] → 系統只儲存偵測結果與狀態，不儲存原始影像；展示時對畫面打碼。

## Migration Plan

1. 既有 `src/` 原型併入新 MVC 結構（`Seat`/`BookingService` 邏輯遷入 SQLAlchemy model 與 Service 層），`main.py` 改為 FastAPI 進入點。
2. 開發期 `DATABASE_URL=sqlite:///dev.db`；本機安裝 PostgreSQL 後切換連線字串並以 Alembic 建 schema。
3. 上線時申請 DBaaS（標準 PostgreSQL），`alembic upgrade head` 建表、匯入座位主檔即可，程式碼零修改。
4. `docs/technical_architecture.md`、`docs/roadmap.md` 同步改寫（移除 Firebase）。

## Open Questions

- 訓練資料：模擬場景影像何時採集、標註工具（建議 Roboflow 或 LabelImg）由團隊確認。
- 自習室開放時段（影響使用率分母）需向管理單位確認，先以 08:00–22:00 為預設。
- 平面圖底圖：先用 SVG 手繪示意圖，實地部署時再依真實平面圖調整。
