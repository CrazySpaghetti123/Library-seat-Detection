## Why

雲端後端（Render）目前也會提供整份前端，打開後端網址會看到和 github.io 一模一樣的網站。對外因此有兩個看似都能用的網址：後端網址休眠時整頁要等約 1 分鐘才打得開，展示或報告時也容易被問「為什麼有兩個網站」。前端的正式網址只有 github.io。

## What Changes

- 新增設定 `FRONTEND_URL`（前端正式網址）。
  - **未設定**（本機開發）：後端照舊一併提供前端，開 `127.0.0.1:8000` 即可操作。
  - **已設定**（雲端）：後端不提供前端檔案；瀏覽器開後端的非 API 網址時，轉址到 `FRONTEND_URL` 的同一路徑（例：`/map.html` → `https://…github.io/Library-seat-Detection/map.html`）。
- `/api/*`、WebSocket `/ws/*` 行為不變；不存在的 `/api/...` 仍回 404，不轉址。
- `render.yaml` 設定 `FRONTEND_URL=https://crazyspaghetti123.github.io/Library-seat-Detection`。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `cloud-deployment`：「前後端分離部署」需求補上雲端後端不提供前端、改為轉址到正式網址。

## Impact

- `src/config.py`、`src/main.py`、`render.yaml`、`docs/deployment.md`、測試。
- 偵測端、模擬器、`/api/health` 只用 API，不受影響；github.io 前端不受影響。
