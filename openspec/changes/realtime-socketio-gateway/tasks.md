# Tasks: realtime-socketio-gateway

## 1. Node.js + Socket.IO 閘道服務

- [x] 1.1 建立 `node-gateway/`：`package.json`（express、socket.io）與 `.gitignore`（node_modules）
- [x] 1.2 `server.js`：Socket.IO server，`connection` 讀 `auth.studentId` 加入個人 room
- [x] 1.3 `POST /internal/push`：驗證共用密鑰，依 event 廣播座位更新或推個人通知
- [x] 1.4 `npm install` 並確認服務可於 3001 啟動

## 2. FastAPI 端改為 HTTP 推播

- [x] 2.1 `src/config.py`：新增 `NODE_GATEWAY_URL`、`GATEWAY_SECRET`
- [x] 2.2 `src/services/realtime_gateway.py`：同步 httpx POST 推播（座位更新／通知），失敗吞例外只記 log
- [x] 2.3 `src/main.py`：掛勾改接 HTTP 推播、移除 `run_coroutine_threadsafe` 與 WebSocket 掛載；偵測/REST/排程不變

## 3. 前端改用 Socket.IO client

- [x] 3.1 `map.html`：載入 Socket.IO client、提供 `studentId` 給 JS
- [x] 3.2 `map.js`：`io(NODE_URL,{auth})` 取代原生 WebSocket、事件監聽改寫
- [x] 3.3 保留 connect/reconnect 後重抓 `GET /api/seats` 全量快照補償

## 4. 文件與驗證

- [x] 4.1 `docs/demo_guide.md`：新增本分支「雙服務啟動」說明（uvicorn + node + 防火牆 3001）
- [x] 4.2 端到端驗證：預約 RESERVED／自動報到 OCCUPIED 廣播、自動報到通知經 Node 閘道送達（test_fullchain.mjs → PASS；room 隔離驗證他人通知未外洩）
- [x] 4.3 確認 Python 既有 43 測試仍通過（業務邏輯未動）
