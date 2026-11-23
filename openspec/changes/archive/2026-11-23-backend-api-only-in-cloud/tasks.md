## 1. 實作

- [x] 1.1 `config.py` 新增 `FRONTEND_URL`（去除結尾 `/`）
- [x] 1.2 `main.py`：未設定時掛載靜態前端；設定時改為最後註冊的 GET 轉址路由（保留路徑與查詢字串，`/api/` 回 404）
- [x] 1.3 `render.yaml` 設定 `FRONTEND_URL`；更新 `docs/deployment.md`、`CLAUDE.md`

## 2. 測試與驗證

- [x] 2.1 測試：轉址目標含路徑與查詢字串、`/api/` 未知路徑 404、API 與 health 正常、未設定時照舊提供前端
- [x] 2.2 部署後確認：後端首頁轉到 github.io、`/api/health` 正常、github.io 全流程不受影響
