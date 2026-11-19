## 1. 設定與資料庫連線

- [x] 1.1 `config.py` 新增 `DETECTION_API_KEY`、`ADMIN_TOKEN`、`ALLOWED_ORIGINS`、`TOKEN_MAX_AGE_HOURS`（預設 12）；`DATABASE_URL` 自動將 `postgres://`／`postgresql://` 轉為 `postgresql+psycopg://`
- [x] 1.2 `database.py` 對 PostgreSQL 啟用 `pool_pre_ping=True`、`pool_recycle=300`，SQLite 不變
- [x] 1.3 測試：連線字串轉換（含已是 psycopg 格式、SQLite 不變）

## 2. 存取控制（後端）

- [x] 2.1 新增 `src/services/auth_service.py`：簽發與驗證學生 token（`itsdangerous`，`SECRET_KEY`，12 小時）、學號格式驗證、金鑰固定時間比對
- [x] 2.2 `POST /api/auth/login`：回傳 `{token, student_id}`，格式錯誤回傳 400 與原錯誤訊息
- [x] 2.3 `require_student()` 改為驗證 `Authorization: Bearer`；缺少、簽章錯誤或過期回傳 401
- [x] 2.4 `POST /api/detection/events` 驗證 `X-API-Key`；`PUT /api/seats/{label}/roi` 與 `/api/reports/*` 驗證 `X-Admin-Token`；未設定金鑰時開放
- [x] 2.5 啟動時對未設定的金鑰記錄 WARNING，列出未受保護的端點
- [x] 2.6 `/ws/seats` 改由查詢參數 `token` 識別學號；無效 token 仍可接收廣播；忽略前端心跳訊息
- [x] 2.7 測試 `tests/test_access_control.py`：登入成功與格式錯誤、token 缺少／竄改／過期、偵測金鑰與管理密碼的接受與拒絕、未設定時開放

## 3. 雲端部署相關端點與中介層

- [x] 3.1 新增 `GET /api/config`（報到期限、開館時段）與 `GET /api/health`（不建立資料庫連線）
- [x] 3.2 `main.py`：移除 `SessionMiddleware` 與 `pages` router；依 `ALLOWED_ORIGINS` 加 CORS（不開 credentials，允許 `Authorization`、`Content-Type`、`X-Admin-Token`）；以 `StaticFiles(html=True)` 將 `frontend/` 掛在 `/`（掛載順序在 API 與 WebSocket 之後）
- [x] 3.3 刪除 `src/controllers/pages.py` 與 `src/views/templates/`；`requirements.txt` 移除 `jinja2`、`python-multipart`（確認無其他使用處）
- [x] 3.4 測試：`/api/config` 數值來自設定、`/api/health` 不呼叫資料庫、CORS 只對允許的來源回應

## 4. 靜態前端

- [x] 4.1 建立 `frontend/`：`index.html`（登入）、`map.html`、`admin.html`，由原模板改寫；`css/`、`js/` 自 `src/views/static/` 移入；所有路徑改為相對路徑
- [x] 4.2 新增 `frontend/config.js`（`apiBase` 預設空字串＝同源）與共用的 `js/api.js`：組合 API 網址、帶 token／管理密碼、401 處理、喚醒重試（3 秒顯示提示、遞增間隔、3 分鐘上限）
- [x] 4.3 登入頁：呼叫 `/api/auth/login`，成功後存 token 與學號並前往 `map.html`；已登入時直接前往
- [x] 4.4 `map.js`：改用 `api.js`；學號與報到期限改由 token 回應與 `/api/config` 取得；WebSocket 連到 `apiBase` 對應的 `ws(s)://…/ws/seats?token=`；每 4 分鐘送出心跳；登出清除 token
- [x] 4.5 `admin.html`／`dashboard.js`：首次查詢前詢問管理密碼（存 `sessionStorage`），401 時重新詢問；開館時段由 `/api/config` 取得；CSV 匯出改為 fetch 後下載
- [x] 4.6 喚醒提示樣式沿用既有深色設計 token，不新增漸層或淺色樣式

## 5. 偵測端

- [x] 5.1 `reporter.py` 支援金鑰，即時上報與離線佇列補送都帶 `X-API-Key`
- [x] 5.2 `detector.py` 新增 `--api-key`（預設讀 `DETECTION_API_KEY`）與 `--heartbeat`（分鐘，預設 10，0 為關閉），定時呼叫 `/api/health`；只在開館時段（`--open-hours 10-20`，預設讀 `OPEN_HOUR`／`CLOSE_HOUR`，以本機時間判斷）送出，避免整天喚醒後端
- [x] 5.3 `calibrate.py` 新增 `--admin-token`（預設讀 `ADMIN_TOKEN`），寫入 ROI 時帶 `X-Admin-Token`
- [x] 5.4 `scripts/simulate_detection.py` 新增 `--api` 與 `--api-key`
- [x] 5.5 測試：reporter 帶金鑰（含補送）

## 6. 部署設定與文件

- [x] 6.1 新增 `render.yaml`：免費方案、新加坡區、build／start 指令（start 先執行 `alembic upgrade head`）、`SECRET_KEY` 自動產生、其餘密鑰 `sync: false`
- [x] 6.2 新增 `.github/workflows/pages.yml`：以 repo 變數 `API_BASE` 改寫 `config.js` 後發布 `frontend/`
- [x] 6.3 新增 `docs/deployment.md`：Neon、Render、GitHub Pages 的申請與設定步驟、密鑰檢查清單、用量估算與超額影響、偵測端改指雲端的設定；Neon 自動擴充上限設為 0.25 CU；Render 設定 `OPEN_HOUR=10`、`CLOSE_HOUR=20`
- [x] 6.4 更新 `CLAUDE.md`、`docs/demo_guide.md`、`docs/technical_architecture.md`（登入方式、前端位置、部署架構）
- [x] 6.5 執行 `python -m pytest -q` 與 `openspec validate static-frontend-cloud --strict`

## 7. 驗證

- [x] 7.1 本機：`uvicorn` 開啟 `http://127.0.0.1:8000/`，以既有的 Playwright 驗收流程跑登入、預約、報到、離席警示、事件流、手機寬度與報表（含管理密碼）
  - 2026-11-19：後端設定偵測金鑰與管理密碼，Edge 自動化 14 項通過：未登入導回、學號格式錯誤、登入、報到期限取自 /api/config、預約與報到、偵測事件無金鑰／錯誤金鑰 401、正確金鑰接受、離席警示經個人頻道送達、報表密碼錯誤重問、正確密碼顯示資料、CSV 帶密碼下載、手機 360px、登出清除 token
- [x] 7.2 本機模擬跨來源：以另一個埠提供 `frontend/` 並設定 `apiBase` 與 `ALLOWED_ORIGINS`，確認登入、API 與 WebSocket 正常
  - 前端以 http.server 放在 8001、後端 8000 設 ALLOWED_ORIGINS：跨來源登入、預約（CORS 預檢）、WebSocket 即時更新、事件流皆正常；未列出的來源不給允許標頭
- [x] 7.3 本機模擬休眠：前端開啟後停止後端再重啟，確認顯示喚醒提示並自動恢復
  - 平面圖開啟中停止後端並重新整理：3 秒內顯示「伺服器喚醒中」，6 秒後重啟後端，頁面自動載入、提示消失、WebSocket 重新連線；全程無非預期的錯誤回應
- [ ] 7.4 雲端：使用者完成 Neon、Render、GitHub Pages 設定後，以手機開啟 github.io 網址完成一輪操作；偵測端以金鑰對雲端上報事件
- [ ] 7.5 確認未帶金鑰的偵測事件、ROI 與報表請求在雲端回傳 401
