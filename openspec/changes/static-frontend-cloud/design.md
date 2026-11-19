## Context

目前架構：

- FastAPI 同時提供 Jinja2 頁面（`/login`、`/map`、`/admin/reports`）、REST API、WebSocket（`/ws/seats`）與 APScheduler 逾時掃描。
- 登入以 `SessionMiddleware` 的簽章 cookie 記錄學號；WebSocket 也從同一個 cookie 取得學號，以推送個人通知。
- 模板只帶入三個設定值：學號、報到期限分鐘數、報表的開館時段。
- 偵測事件、ROI 標定、報表 API 都沒有任何驗證。

部署目標與限制：

| 元件 | 平台 | 限制 |
|---|---|---|
| 前端 | GitHub Pages | 只能放靜態檔；網址為 `https://crazyspaghetti123.github.io/Library-seat-Detection/`（子路徑） |
| 後端 | Render 免費方案 | 15 分鐘沒有收到 HTTP 請求或 WebSocket 訊息就休眠，喚醒約 1 分鐘；每月 750 小時；單一執行個體 |
| 資料庫 | Neon 免費方案 | 每月 100 CU-hours、1 GB；閒置 5 分鐘自動暫停 |

repo 是公開的，任何密鑰都不能進版控。

## Goals / Non-Goals

**Goals:**

- 使用者打開 github.io 網址即可使用全部現有功能。
- 本機開發維持 `uvicorn src.main:app` 一個指令、同一個網址。
- 後端公開後，偵測事件、ROI 與報表不能被任意呼叫。
- 後端休眠時，前端有明確的等待提示並自動恢復；開館期間後端保持清醒。
- 費用為零。

**Non-Goals:**

- 不做學校帳號登入（SSO）；學號登入不需密碼，維持為已知限制。
- 不修正報表開館時段的時區錯誤（另案處理）。
- 不支援多個後端執行個體（APScheduler 只能單一實例，免費方案本來就只有一個）。
- 不做自訂網域。

## Decisions

### D1：前端改為靜態頁面，本機由 FastAPI 一併提供

新增 `frontend/` 資料夾：`index.html`（登入）、`map.html`、`admin.html`（報表）、`config.js`，以及從 `src/views/static/` 移入的 `css/`、`js/`。所有引用改為相對路徑，才能在 GitHub Pages 的子路徑下運作。

本機時 FastAPI 以 `StaticFiles(html=True)` 把 `frontend/` 掛在 `/`，API 與 WebSocket 路徑不變，`config.js` 的 API 網址留空代表同源。部署到 Pages 時，由 GitHub Actions 改寫 `config.js` 填入 Render 網址。

**替代方案**：保留 Jinja2 給本機、另做一份靜態版給 Pages。捨棄原因是兩份前端必然分歧。

### D2：模板變數改由 API 提供

- 學號：登入回應與 token 都帶有學號，前端存在瀏覽器。
- 報到期限、開館時段：新增 `GET /api/config`，回傳 `checkin_deadline_minutes`、`open_hour`、`close_hour`。

### D3：學生登入改用簽章 token

`POST /api/auth/login {student_id}` 驗證學號格式（沿用英數 4～15 碼）後，以 `itsdangerous.URLSafeTimedSerializer`（金鑰為 `SECRET_KEY`）簽出 token，有效期 12 小時。

- 一般 API：`Authorization: Bearer <token>`；`require_student()` 改為驗證這個標頭。
- WebSocket：瀏覽器無法自訂 WebSocket 標頭，改用 `/ws/seats?token=<token>`；沒有或無效的 token 仍可連線收座位廣播，只是收不到個人通知。
- 前端存在 `localStorage`，登出即刪除。

**為什麼不沿用 cookie**：前端（github.io）與後端（onrender.com）不同網域，跨站 cookie 需要 `SameSite=None; Secure`，且 Safari 與 Chrome 的第三方 cookie 限制會讓它失效。Bearer token 不受影響，CORS 也不需要開 credentials。

**風險**：token 放在 `localStorage` 會受 XSS 影響。前端寫入 innerHTML 的內容只有座位編號、狀態與系統訊息，都來自後端資料庫，不含使用者輸入的任意文字；學號在登入時已限制為英數。

### D4：偵測端金鑰與管理密碼

| 對象 | 環境變數 | 標頭 | 保護的端點 |
|---|---|---|---|
| 偵測端 | `DETECTION_API_KEY` | `X-API-Key` | `POST /api/detection/events` |
| 管理者 | `ADMIN_TOKEN` | `X-Admin-Token` | `PUT /api/seats/{label}/roi`、`/api/reports/*` |

- 比對使用 `hmac.compare_digest`，避免時序攻擊。
- 環境變數未設定時端點維持開放，方便本機開發與現有測試；啟動時以 WARNING 記錄哪些端點未受保護。部署設定（`render.yaml`）一律要求設定。
- 偵測程式與標定工具以 `--api-key`／`--admin-token` 參數或同名環境變數提供；離線佇列補送時同樣帶金鑰。
- 報表頁第一次載入時詢問管理密碼，存在 `sessionStorage`（關閉分頁即清除）；回應 401 時重新詢問。
- CSV 匯出原本是 `<a href>` 直接下載，無法帶標頭；改為以 fetch 取得後產生下載。

### D5：跨來源存取（CORS）

`ALLOWED_ORIGINS` 環境變數（逗號分隔），例如 `https://crazyspaghetti123.github.io`。未設定時不加 CORS（本機同源）。不開 `allow_credentials`。允許的標頭：`Authorization`、`Content-Type`、`X-Admin-Token`。

### D6：後端休眠因應

1. **前端喚醒提示**：載入平面圖時若 API 在 3 秒內沒有回應或連線失敗，顯示「伺服器喚醒中，約需一分鐘」，並以遞增間隔重試，最長 3 分鐘；成功後自動載入。登入頁按下登入時同樣處理。
2. **WebSocket 心跳**：平面圖開啟期間每 4 分鐘送出一則 `ping` 文字訊息。Render 自 2026-02 起把收到的 WebSocket 訊息計為活動，有人開著平面圖時後端就不會休眠。
3. **偵測端保持清醒**：新增 `GET /api/health`（不查資料庫，避免喚醒 Neon）。偵測程式每 10 分鐘呼叫一次（`--heartbeat` 可調，0 為關閉）。偵測電腦在開館時段運作，後端就會在這段時間保持清醒，離席逾時可以準時處理。

**休眠期間的逾時**：計時起點存在資料庫，後端醒來後的第一次排程掃描會補處理到期的事件，不會遺漏，只會延遲。

**用量估算**（開館 10:00–20:00）：後端醒著的時間約為開館 10 小時加上最後一次活動後 15 分鐘才休眠，即每天約 10.25 小時；排程器每 15 秒查詢資料庫，Neon 在後端醒著時也一直醒著，停止查詢 5 分鐘後才暫停。

| 服務 | 每月用量（31 天） | 免費額度 |
|---|---|---|
| Render | 約 318 小時 | 750 小時 |
| Neon（0.25 CU） | 約 80 CU-hours | 100 CU-hours |

Neon 剩餘約 20 CU-hours，可容納約 240 次非開館時段的喚醒（每次後端與資料庫約醒 20 分鐘）。前提：

- Neon 的自動擴充上限必須設為 0.25 CU（免費方案預設最高可到 2 CU，用量會放大 8 倍）。
- 偵測端只在開館時段運作，或只在開館時段送出健康檢查；整天運作會讓後端整天清醒，超出 Neon 額度。
- 超過額度不會收費：Render 暫停服務到月底，Neon 暫停運算到月底。部署文件須說明。

開館時段設定為 `OPEN_HOUR=10`、`CLOSE_HOUR=20`（報表分母）。

### D7：資料庫連線

- Neon 提供的連線字串是 `postgresql://…?sslmode=require`；`config.py` 自動把 `postgres://`、`postgresql://` 轉為 `postgresql+psycopg://`，使用者可以直接貼上。
- `create_engine` 對 PostgreSQL 啟用 `pool_pre_ping=True`、`pool_recycle=300`：Neon 閒置暫停後舊連線會失效。
- SQLite 不受影響。

### D8：部署設定檔

- `render.yaml`（Render Blueprint）：Python 免費方案、新加坡區；build 執行 `pip install -r requirements.txt`；start 執行 `alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port $PORT`；`SECRET_KEY` 由 Render 自動產生；`DATABASE_URL`、`DETECTION_API_KEY`、`ADMIN_TOKEN`、`ALLOWED_ORIGINS` 標記為需手動填寫（不寫進檔案）。
- `.github/workflows/pages.yml`：push 到 main 且 `frontend/` 有變動時，以 repo 變數 `API_BASE` 改寫 `config.js`，再發布 `frontend/` 到 GitHub Pages。後端網址不是秘密，用一般變數即可。
- 新增 `docs/deployment.md`：Neon、Render、GitHub Pages 的申請與設定步驟，以及用量限制。

## Risks / Trade-offs

- **[冷啟動約 1 分鐘]** 第一位使用者要等 → 前端顯示喚醒提示；偵測端心跳讓開館時段保持清醒。
- **[免費額度用盡]** Render 超過 750 小時會暫停到月底；Neon 超過 100 CU-hours 會暫停運算 → 部署文件列出估算；展示期間以外可在 Render 暫停服務。
- **[學號登入無密碼]** 任何人都能冒用學號 → 維持為已知限制，寫進報告；token 至少讓後端只接受自己簽發的身分。
- **[金鑰未設定即開放]** 若部署時忘了設定，端點會公開 → `render.yaml` 將金鑰列為必填；啟動時以 WARNING 記錄；部署文件的檢查清單逐項確認。
- **[靜態前端與後端版本不一致]** Pages 與 Render 分開部署 → 兩者都由 push 到 main 觸發，且 API 路徑不變。

## Migration Plan

1. 本機完成改版並通過測試，`uvicorn` 開啟 `http://127.0.0.1:8000/` 操作一輪。
2. 使用者申請 Neon，取得連線字串；本機設定 `DATABASE_URL` 執行 `alembic upgrade head` 與 `seed_seats.py --reset`。
3. 使用者在 Render 以 `render.yaml` 建立服務，填入密鑰；確認 `/api/health`。
4. 在 GitHub 設定 `API_BASE` 變數並開啟 Pages（來源選 GitHub Actions）。
5. 用手機開 github.io 網址驗證；偵測端改指向 Render 網址並帶金鑰。
6. 回退：本機與 seatdb 不受影響；雲端出問題時照舊以本機展示。
