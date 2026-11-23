## Context

`src/main.py` 最後以 `app.mount("/", StaticFiles(frontend/, html=True))` 提供前端，雲端與本機相同。雲端前端已由 GitHub Pages 提供。

## Decisions

### D1：以單一設定 `FRONTEND_URL` 切換

有設定就代表「前端另有正式網址」，後端改為轉址；沒設定就是本機開發，照舊提供前端。不另設 `SERVE_FRONTEND` 開關，避免兩個設定互相矛盾（例如關掉前端卻沒有轉址目標）。

### D2：轉址而非 404

開後端網址的人多半是要找網站，轉到正式網址比錯誤頁友善。保留路徑與查詢字串，`/admin.html` 會轉到 github.io 的報表頁。使用 307（暫時轉址），避免瀏覽器永久快取，之後若改設定不會被舊轉址卡住。

### D3：API 路徑不轉址

轉址路由排在所有 API、WebSocket 路由之後；`/api/` 開頭的未知路徑回 404，避免程式呼叫打錯 API 時被導向 HTML 頁面而難以除錯。FastAPI 內建的 `/docs`、`/openapi.json` 先註冊，不受影響。

## Risks / Trade-offs

- 本機若誤設 `FRONTEND_URL`，開 `127.0.0.1:8000` 會被轉到雲端前端（連的是雲端後端）。`docs/demo_guide.md` 不設定此變數，風險低；啟動時記錄一行 INFO 說明目前模式。
