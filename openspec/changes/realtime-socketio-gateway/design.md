# Design: realtime-socketio-gateway

## Context

`main` 分支的即時推播：座位狀態轉換（`SeatStateService.transition`）與通知（`NotificationService.notify`）透過事件掛勾，呼叫 `ConnectionManager` 經 FastAPI 原生 WebSocket 送出；因掛勾常在同步情境（APScheduler 排程執行緒、HTTP handler 執行緒）觸發，需 `asyncio.run_coroutine_threadsafe` 把訊息丟回 event loop。本分支將推播職責外移到獨立的 Node.js + Socket.IO 服務。

## Goals / Non-Goals

**Goals:**

- FastAPI 與 Node 閘道職責分離：Python 管業務/資料，Node 管瀏覽器即時連線
- 對外行為與 `main` 一致：座位變色、個人通知、斷線重連後一致
- 保留 Python 端全部既有測試與業務邏輯不動

**Non-Goals:**

- 不改 REST API、偵測端、資料庫結構、業務規則
- 不引入 Redis（HTTP 通知足夠；Redis 方案列為未來可選）
- 不做正式鑑權（沿用學號輕量識別）

## Decisions

### D1. 三程序架構與資料流

```
瀏覽器 ──Socket.IO(3001)──► Node 閘道 ──┐
   ▲                                    │ socket.io emit（room 分群）
   │ HTTP REST(8000)                    │
瀏覽器 ──────────────────► FastAPI ──POST /internal/push──► Node 閘道
偵測端 ──HTTP(8000)──────► FastAPI ──► PostgreSQL
```

座位狀態變更 / 通知產生時：FastAPI 掛勾 → `httpx.post` 到 Node 的 `/internal/push` →
Node 依 payload 的 `target` 決定 emit 到全體（座位廣播）或個人 room（通知）。

### D2. FastAPI 端：同步 HTTP 推播，移除 event loop 橋接

- 新增 `src/services/realtime_gateway.py`：以同步 `httpx.Client` POST 到 Node。
- `SeatStateService.on_transition_hooks` 與 `NotificationService.on_notify_hooks`
  改掛這個 HTTP 推播函式——因為是同步呼叫，**不再需要** `run_coroutine_threadsafe`，
  排程執行緒、請求執行緒都能直接呼叫。
- 推播失敗（Node 未啟動）只記 log、吞例外，**不得影響 DB 交易**（與 main 的掛勾語義一致）。
- 短逾時（如 2 秒）避免阻塞請求；HTTP 請求帶共用密鑰標頭防止外部濫用內部端點。

### D3. Node 閘道：Express + Socket.IO，room 分群

- `POST /internal/push`（驗證 `X-Gateway-Secret`）：
  - `{ "event": "seat_update", "payload": {...} }` → `io.emit('seat_update', payload)` 全體廣播
  - `{ "event": "notification", "studentId": "...", "payload": {...} }` → `io.to('student:'+id).emit('notification', payload)`
- Socket.IO 連線：`connection` 時讀 `socket.handshake.auth.studentId`，
  加入個人 room `student:{id}`（全體廣播用預設命名空間，不需顯式 join）。
- CORS 對開發放行（`origin: '*'`）。

### D4. 學號身分傳遞

學號存在 FastAPI 的簽章 session cookie（httponly），Node 不易解。
採最簡作法：`map.html` 由後端模板already 帶有 `student_id`，前端以
`io(NODE_URL, { auth: { studentId } })` 傳給 Node。符合專題「學號輕量識別」定位。

### D5. 前端：Socket.IO client，自動重連 + 快照補償

- 載入 Socket.IO client，`NODE_URL` 以 `location.protocol + '//' + location.hostname + ':3001'`
  動態組出（本機與手機經 IP 連線皆適用）。
- 移除手寫的指數退避重連（Socket.IO 內建）；保留 `connect`/`reconnect` 時
  `GET /api/seats` 重抓全量快照的補償（Socket.IO 預設不補播斷線期間訊息）。
- 事件名與 payload 結構沿用 main：`seat_update {seat_id,label,status}`、`notification {data}`。

## Risks / Trade-offs

- [多一個程序與一個對外埠（3001）] → demo_guide 提供雙服務啟動步驟；防火牆加開 3001。
- [Node 未啟動時前端收不到即時更新] → 前端仍可用 REST 操作與初始快照；狀態正確只是不即時。可加前端連線狀態指示。
- [跨來源（8000 頁面連 3001）] → Node 端開 CORS；學號經 auth payload 傳遞，非安全鑑權（與專題定位一致）。
- [兩套即時實作分歧] → 限定於分支；事件名與 payload 與 main 對齊，降低前端分歧成本。

## Migration Plan

1. 於 `feature/nodejs-socketio-gateway` 分支開發，`main` 不動。
2. `node-gateway/` `npm install` 後 `node server.js` 啟動於 3001。
3. FastAPI 設 `NODE_GATEWAY_URL` 後照常 `uvicorn` 啟動；前端自動連 3001。
4. 報告中對比兩分支的即時通訊技術與架構差異。

## Open Questions

- 是否需要前端「閘道連線中斷」的明顯指示（目前規劃沿用 main 的連線狀態徽章）。
- 未來若要水平擴充多個 Node 節點，再評估改用 Redis pub/sub（B 方案）。
