# Proposal: realtime-socketio-gateway

## Why

目前即時推播由 FastAPI 內建的原生 WebSocket 承載（`src/controllers/ws.py`）。為了在畢業專題中對比不同即時通訊技術、並展示 polyglot 微服務架構，本變更在獨立分支 `feature/nodejs-socketio-gateway` 上，新增一個 Node.js + Socket.IO 服務專責即時推播，FastAPI 改以 HTTP 通知該服務。原生 WebSocket 版本保留在 `main` 分支供對照。

## What Changes

- 新增 `node-gateway/`：Node.js + Socket.IO 推播服務，維護瀏覽器連線、以 room 分群（全體座位廣播＋依學號的個人通知頻道）。
- FastAPI 的座位狀態與通知推播掛勾，由「WebSocket 直送」改為「HTTP POST 通知 Node 閘道」；因 POST 為同步呼叫，**移除** `asyncio.run_coroutine_threadsafe` 的同步↔非同步橋接。
- 前端平面圖由原生 `WebSocket` 改用 Socket.IO client；自動重連改由 Socket.IO 內建處理，保留「連線後重抓全量快照」的補償邏輯。
- 本分支不再掛載 FastAPI 的 `/ws/seats`；偵測端、REST API、資料庫、業務邏輯與既有測試完全不變。

## Capabilities

### New Capabilities

（無——本變更為實作層架構替換，不新增對外行為能力。）

### Modified Capabilities

- `floor-map-web`: 即時更新的傳輸實作改為 Socket.IO 閘道；對外可觀察行為（狀態變更 3 秒內反映、斷線重連後補償）維持不變，僅補充推播管道的描述。

## Impact

- **新增執行體**：部署時需同時啟動 FastAPI（uvicorn, 8000）與 Node 閘道（node, 3001）兩個程序；手機連線需另開放防火牆 TCP 3001。
- **程式碼**：新增 `node-gateway/`、`src/services/realtime_gateway.py`；調整 `src/main.py`（掛勾改接 HTTP 推播）、`src/config.py`（Node 閘道位址與共用密鑰）、`src/views/templates/map.html` 與 `src/views/static/js/map.js`。
- **相依**：Node 端新增 `socket.io`、`express`；Python 端沿用既有 `httpx`。
- **分支策略**：僅存在於 `feature/nodejs-socketio-gateway`，`main` 維持原生 WebSocket。
