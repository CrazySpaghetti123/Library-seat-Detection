## Why

系統目前只能在本機或區網使用。專題第二學期要上線展示，希望使用者打開的網址是 `github.io`，並且不需要付費主機。

GitHub Pages 只能放靜態檔案，無法執行後端，因此前端與後端必須分開部署：前端放 GitHub Pages，後端放免費的 Render（閒置 15 分鐘會休眠），資料庫放 Neon（免費 PostgreSQL）。前後端改成不同網址之後，現有的 Jinja2 伺服器端頁面與 session cookie 登入都無法沿用；後端公開到網路上之後，偵測事件、ROI 標定與報表 API 也不能再完全不設防。

## What Changes

- **BREAKING**：前端改為純靜態網頁（登入、平面圖、報表三頁），不再由 Jinja2 產生；原本模板帶入的設定值改由 `GET /api/config` 取得。本機開發時由 FastAPI 一併提供這些靜態檔，網址與操作方式不變。
- **BREAKING**：登入改為 token。`POST /api/auth/login` 以學號換取簽章 token，前端存在瀏覽器並以 `Authorization: Bearer` 帶上；WebSocket 以查詢參數帶 token。移除 `SessionMiddleware` 與 `/login`、`/logout`、`/map` 等伺服器端頁面路由。
- 新增存取控制：
  - 偵測事件 API 需帶偵測端金鑰（`X-API-Key`）。
  - ROI 標定與報表 API 需帶管理密碼；報表頁進入時詢問一次。
  - 未設定金鑰時（本機開發）維持開放，但啟動時記錄警告。
- 新增雲端部署設定：
  - 後端允許前端網址跨來源存取（CORS），來源由環境變數設定。
  - Neon 連線字串自動轉換為 psycopg 格式，並啟用斷線偵測與連線回收。
  - `render.yaml` 部署設定，啟動時自動執行資料庫 migration。
  - GitHub Actions 自動將前端發布到 GitHub Pages，並寫入後端網址。
- 休眠因應：
  - 前端在後端喚醒期間顯示「伺服器喚醒中」並自動重試。
  - 開啟中的平面圖定時送出 WebSocket 心跳。
  - 偵測端定時呼叫 `GET /api/health`，讓開館期間後端保持清醒，離席逾時能準時處理。

## Capabilities

### New Capabilities

- `access-control`：學生登入 token、偵測端金鑰、管理密碼，以及未設定金鑰時的開發模式行為。
- `cloud-deployment`：前後端分離部署、跨來源存取、設定值 API、後端休眠時的前端行為與保持清醒機制、資料庫連線設定。

### Modified Capabilities

（無）既有需求的行為不變：平面圖、預約、逾時、偵測與報表的規則都相同，只是改由新的登入方式識別學號、由新的部署方式提供。

## Impact

- 前端：`src/views/templates/` 移除；新增靜態頁面（`index.html` 登入、`map.html`、`admin.html` 報表），`map.js`、`dashboard.js` 改為呼叫可設定的 API 網址並帶 token。
- 後端：`src/main.py`（移除 session、加 CORS、提供靜態前端）、`src/controllers/pages.py`（移除）、`api.py`（token 驗證、`/api/auth/login`、`/api/config`、`/api/health`、偵測與 ROI 金鑰）、`reports.py`（管理密碼）、`ws.py`（token 識別學號）、`src/config.py`、`src/database.py`。
- 偵測端：`reporter.py`、`calibrate.py`、`detector.py` 帶金鑰與健康檢查。
- 新增檔案：`render.yaml`、`.github/workflows/pages.yml`、部署說明文件。
- 依賴：不新增套件（簽章使用既有的 `itsdangerous`，CORS 使用 FastAPI 內建）。
- 資料庫：schema 不變；Neon 上的資料從空白開始，以 `seed_seats.py --reset` 建立 6 席。
- 帳號：需要使用者自行申請 Neon、Render，並在 GitHub repo 開啟 Pages。
- 不在範圍內：報表開館時段的時區錯誤（另案）、正式的學校帳號登入（SSO）、自訂網域。
